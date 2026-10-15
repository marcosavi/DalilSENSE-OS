"""Independent, durable runs for the configurable experiment workspace.

JSON snapshots are written atomically. One process owns generation, while disk
records remain available after a restart. Network calls never hold the file lock.
"""
import hashlib
import json
import threading
import time
import uuid
from pathlib import Path

from django.conf import settings

from dalilsense.narrator import stream_tokens
from . import services
from .models import Run

ACTIVE = set()
LIVE = {}
TERMINAL = {"completed", "completed_with_errors", "failed", "interrupted"}
STATUS_LABELS = {"running": "Generating", "completed": "Ready for review",
                 "completed_with_errors": "Finished with errors", "failed": "Failed", "interrupted": "Interrupted"}


class RunBusy(ValueError):
    pass


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def directory(run_id):
    return Path(settings.DALILSENSE_RUNS_DIR) / str(uuid.UUID(str(run_id)))


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def load_config(run_id):
    return json.loads((directory(run_id) / "config.json").read_text(encoding="utf-8"))


def read_state(run_id):
    """Caller holds the shared lock; orphaned workers become interrupted runs."""
    path = directory(run_id) / "state.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    if state["status"] == "running" and str(run_id) not in ACTIVE:
        state.update(status="interrupted", finished_at=now(), message="The server stopped before this run finished. Duplicate it to run again.")
        write_json(path, state)
    return state


def snapshot(run_id):
    run_id = str(uuid.UUID(str(run_id)))
    with services.HUB.lock:
        config = load_config(run_id)
        state = read_state(run_id)
        path = directory(run_id)
        outputs = {r["case_id"]: r for r in services.read_jsonl(path / "outputs.jsonl")}
        labels = {r["case_id"]: r for r in services.read_jsonl(path / "labels_human.jsonl")}
        errors = services.read_jsonl(path / "errors.jsonl")
        reviewed = {key: value for key, value in labels.items() if key in outputs and isinstance(value.get("hallucination"), bool)}
        n_h = sum(r["hallucination"] for r in reviewed.values())
        latencies = [r["latency_ms"] for r in outputs.values()]
        return {
            "config": config, **state, "status_label": STATUS_LABELS.get(state["status"], state["status"]),
            "outputs": outputs, "labels": reviewed,
            "errors": errors, "live": dict(LIVE.get(run_id, {})),
            "total": len(config["cases"]), "n_out": len(outputs), "n_lbl": len(reviewed), "n_h": n_h,
            "rate": f"{n_h / len(reviewed):.1%}" if reviewed else "—",
            "mean_latency_ms": round(sum(latencies) / len(latencies)) if latencies else None,
            "review_ready": state["status"] in TERMINAL,
        }


def history():
    rows = []
    root = Path(settings.DALILSENSE_RUNS_DIR)
    if not root.exists():
        return rows
    for path in root.glob("*/config.json"):
        try:
            rows.append(snapshot(path.parent.name))
        except (ValueError, OSError, KeyError):
            # A damaged external file must not hide other saved experiments.
            continue
    return sorted(rows, key=lambda row: row["config"]["created_at"], reverse=True)


def start(configuration):
    with services.HUB.lock:
        if ACTIVE or services.HUB.running:
            raise RunBusy("Another experiment is running. Wait for it to finish before starting a new one.")
        run_id = str(uuid.uuid4())
        config = {
            **configuration, "id": run_id, "created_at": now(),
            "prompt_sha": hashlib.sha256(configuration["system_prompt"].encode()).hexdigest(),
            "dataset_sha": hashlib.sha256(json.dumps(configuration["cases"], sort_keys=True).encode()).hexdigest(),
        }
        path = directory(run_id)
        path.mkdir(parents=True)
        write_json(path / "config.json", config)
        write_json(path / "state.json", {"status": "running", "finished_at": None, "message": ""})
        ACTIVE.add(run_id)
        services.HUB.running.add("run:" + run_id)
        try:
            threading.Thread(target=execute, args=(run_id,), daemon=True).start()
        except RuntimeError:
            ACTIVE.discard(run_id)
            services.HUB.running.discard("run:" + run_id)
            write_json(path / "state.json", {"status": "failed", "finished_at": now(), "message": "Could not start the worker. Duplicate this run to retry."})
    try:
        sync_run(run_id)
    except Exception as exc:
        services.append_jsonl(path / "errors.jsonl", {"case_id": "sync", "message": f"SQLite sync failed: {exc}"})
    return run_id


def execute(run_id):
    path = directory(run_id)
    status, message = "completed", ""
    try:
        config = load_config(run_id)
        for case in config["cases"]:
            case_id = case["case_id"]
            with services.HUB.lock:
                LIVE[run_id] = {"case_id": case_id, "output": ""}
            pieces = []
            started = time.monotonic()
            try:
                for piece in stream_tokens(json.dumps(case["input"]), model=config["model"],
                                           system_prompt=config["system_prompt"], options=config["options"]):
                    pieces.append(piece)
                    with services.HUB.lock:
                        LIVE[run_id]["output"] = "".join(pieces)
                if not "".join(pieces).strip():
                    raise ValueError("The model returned no text.")
            except Exception as exc:
                services.append_jsonl(path / "errors.jsonl", {"case_id": case_id, "message": str(exc)})
                status = "completed_with_errors"
                continue
            services.append_jsonl(path / "outputs.jsonl", {
                **case, "output": "".join(pieces), "latency_ms": int((time.monotonic() - started) * 1000),
                "model": config["model"], "run_id": run_id, "prompt_sha": config["prompt_sha"],
            })
    except Exception as exc:
        status, message = "failed", str(exc)
    finally:
        with services.HUB.lock:
            try:
                write_json(path / "state.json", {"status": status, "finished_at": now(), "message": message})
            finally:
                LIVE.pop(run_id, None)
                ACTIVE.discard(run_id)
                services.HUB.running.discard("run:" + run_id)
        try:
            sync_run(run_id)
        except Exception as exc:
            services.append_jsonl(path / "errors.jsonl", {"case_id": "sync", "message": f"SQLite sync failed: {exc}"})


def save_review(run_id, case_id, verdict, notes):
    with services.HUB.lock:
        data = snapshot(run_id)
        if not data["review_ready"] or case_id not in data["outputs"]:
            raise RunBusy("Review is available for generated outputs after the run finishes.")
        services.append_jsonl(directory(run_id) / "labels_human.jsonl", {
            "case_id": case_id, "hallucination": verdict, "notes": notes, "at": now(),
        })
        fresh = snapshot(run_id)
    sync_run(run_id, data=fresh)
    return fresh


def sync_run(run_id, *, data=None):
    """Upsert the SQLite index row for a run from its on-disk snapshot."""
    run_id = str(uuid.UUID(str(run_id)))
    if data is None:
        data = snapshot(run_id)
    config = data["config"]
    Run.objects.update_or_create(
        id=run_id,
        defaults={
            "name": config.get("name") or config.get("model", ""),
            "model": config.get("model", ""),
            "model_digest": config.get("model_digest", "") or "",
            "status": data["status"],
            "created_at": config.get("created_at", ""),
            "finished_at": data.get("finished_at") or "",
            "prompt_sha": config.get("prompt_sha", ""),
            "dataset_sha": config.get("dataset_sha", ""),
            "selection": config.get("selection", ""),
            "sample_seed": config.get("sample_seed"),
            "total": data["total"],
            "n_out": data["n_out"],
            "n_lbl": data["n_lbl"],
            "n_h": data["n_h"],
            "rate": data["rate"],
            "mean_latency_ms": data["mean_latency_ms"],
            "summary_md": summary_text(data),
        },
    )


def summary_text(data):
    config = data["config"]
    lines = [
        f'# Experiment — {config["name"]}', "",
        f'- Run: {config["id"]}', f'- Model: {config["model"]}',
        f'- Model digest: {config["model_digest"] or "not reported"}',
        f'- Created: {config["created_at"]}', f'- Status: {data["status"]}',
        f'- Prompt SHA: {config["prompt_sha"]}', f'- Dataset SHA: {config["dataset_sha"]}',
        f'- Input selection: {config["selection"]}', f'- Sampling seed: {config["sample_seed"]}',
        '- Thinking: disabled',
        f'- Generated: {data["n_out"]}/{data["total"]}',
        f'- Reviewed: {data["n_lbl"]}/{data["n_out"]}',
        f'- Hallucination rate among reviewed outputs: {data["rate"]}',
        f'- Mean generation latency: {data["mean_latency_ms"]} ms',
        "", "## System prompt", "", *("> " + line for line in config["system_prompt"].splitlines()),
        "", "## Generation settings", "",
        *(f'- {key}: {value}' for key, value in config["options"].items()),
        "", "Unspecified optional settings use the installed model's defaults.",
        "", "## Cases", "", "| Case | Input | Output | Latency | Hallucination | Notes |",
        "|---|---|---|---|---|---|",
    ]
    errors = {row["case_id"]: row["message"] for row in data["errors"]}
    for case in config["cases"]:
        key = case["case_id"]
        output = data["outputs"].get(key, {})
        review = data["labels"].get(key, {})
        verdict = ("Yes" if review["hallucination"] else "No") if "hallucination" in review else "Unreviewed"
        cells = [key, json.dumps(case["input"]), output.get("output", errors.get(key, "Not generated")),
                 str(output.get("latency_ms", "—")), verdict, review.get("notes", "")]
        lines.append("| " + " | ".join(services._md_cell(cell) for cell in cells) + " |")
    return "\n".join(lines) + "\n"
