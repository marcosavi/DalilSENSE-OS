"""Experiment execution, file persistence, and process-local event broadcasting."""
import hashlib
import json
import queue
import shutil
import threading
import time
from collections import defaultdict
from pathlib import Path

from django.conf import settings

from dalilsense.narrator import (
    DECODING,
    OllamaError,
    SYSTEM_PROMPT,
    stream_tokens,
)

PROMPT_SHA = hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest()[:12]

DATASET_DIR = Path(settings.DALILSENSE_DATASET_DIR)
RESULTS_DIR = Path(settings.DALILSENSE_RESULTS_DIR)


def safe_dir(model: str) -> str:
    return model.replace("/", "--").replace(":", "_")


def model_results_dir(model: str) -> Path:
    return RESULTS_DIR / safe_dir(model) / PROMPT_SHA


def read_jsonl(path: Path) -> list[dict]:
    with HUB.lock:
        if not path.exists():
            return []
        rows = []
        for line in path.read_text().splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows


def read_outputs(model: str) -> dict[str, dict]:
    return {r["case_id"]: r for r in read_jsonl(model_results_dir(model) / "outputs.jsonl")}


def read_labels(model: str) -> dict[str, dict]:
    return {r["case_id"]: r for r in read_jsonl(model_results_dir(model) / "labels_human.jsonl")}


def append_jsonl(path: Path, record: dict) -> None:
    with HUB.lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")


def load_cases() -> list[tuple[str, dict]]:
    return [(p.stem, json.loads(p.read_text())) for p in sorted(DATASET_DIR.glob("case_*.json"))]


class Hub:
    """Fan-out pub/sub for SSE subscribers, keyed by model."""

    def __init__(self):
        self.lock = threading.RLock()
        self.subs: dict[str, list[queue.Queue]] = defaultdict(list)
        self.running: set[str] = set()

    def subscribe(self, model: str) -> queue.Queue:
        q: queue.Queue = queue.Queue()
        with self.lock:
            self.subs[model].append(q)
        return q

    def unsubscribe(self, model: str, q: queue.Queue) -> None:
        with self.lock:
            if q in self.subs[model]:
                self.subs[model].remove(q)

    def publish(self, model: str, event: dict) -> None:
        with self.lock:
            subs = list(self.subs[model])
        for q in subs:
            q.put(event)


HUB = Hub()


def run_experiment(model: str) -> None:
    try:
        out_path = model_results_dir(model) / "outputs.jsonl"
        # Keep previous runs and their human labels together before starting fresh.
        run_dir = model_results_dir(model)
        run_dir.mkdir(parents=True, exist_ok=True)
        with HUB.lock:
            existing = [run_dir / name for name in ("outputs.jsonl", "labels_human.jsonl", "summary.md", "errors.jsonl") if (run_dir / name).exists()]
            if existing:
                archive = run_dir / "history" / str(time.time_ns())
                archive.mkdir(parents=True)
                for path in existing:
                    shutil.copy2(path, archive / path.name)
                for path in existing:
                    path.unlink()
        HUB.publish(model, {"type": "reset"})
        for case_id, case_input in load_cases():
            HUB.publish(model, {"type": "start", "case_id": case_id})
            prompt_str = json.dumps(case_input)
            start = time.monotonic()
            pieces: list[str] = []
            try:
                for piece in stream_tokens(prompt_str, model=model):
                    pieces.append(piece)
                    HUB.publish(model, {"type": "token", "case_id": case_id, "piece": piece})
            except OllamaError as e:
                append_jsonl(run_dir / "errors.jsonl", {"case_id": case_id, "message": str(e)})
                HUB.publish(model, {"type": "error", "case_id": case_id, "message": str(e)})
                continue
            output = "".join(pieces)
            latency_ms = int((time.monotonic() - start) * 1000)
            append_jsonl(out_path, {
                "case_id": case_id,
                "input": case_input,
                "output": output,
                "latency_ms": latency_ms,
                "model": model,
                "prompt_sha": PROMPT_SHA,
            })
            HUB.publish(model, {
                "type": "done", "case_id": case_id,
                "output": output, "latency_ms": latency_ms,
            })
        write_summary(model)
    except Exception as e:
        append_jsonl(model_results_dir(model) / "errors.jsonl", {"case_id": "run", "message": str(e)})
        HUB.publish(model, {"type": "run_error", "message": str(e)})
    finally:
        with HUB.lock:
            HUB.running.discard(model)
        HUB.publish(model, {"type": "complete"})


def _md_cell(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", "<br>")


def write_summary(model: str) -> None:
    with HUB.lock:
        total = len(load_cases())
        outputs = read_outputs(model)
        labels = read_labels(model)
        labeled = [v for v in labels.values() if "hallucination" in v]
        n_lbl = len(labeled)
        n_h = sum(1 for v in labeled if v["hallucination"])
        rate = f"{n_h / n_lbl:.1%}" if n_lbl else "—"
        decoding_lines = "\n".join(f"- {k}: {v}" for k, v in DECODING.items())
        rows = []
        for case_id, case_input in load_cases():
            rec = outputs.get(case_id, {})
            output_text = rec.get("output", "")
            latency = rec.get("latency_ms")
            latency_text = f"{latency}ms" if latency is not None else "—"
            lbl = labels.get(case_id, {})
            if "hallucination" in lbl:
                label_text = "Y" if lbl["hallucination"] else "N"
            else:
                label_text = "—"
            rows.append(
                f"| {case_id} | `{_md_cell(json.dumps(case_input))}` | {_md_cell(output_text) or '—'} | {latency_text} | {label_text} |"
            )
        summary = (
            f"# Guided prompt evaluation — `{model}`\n\n"
            f"- **Model:** `{model}`\n"
            f"- **Prompt SHA (first 12):** `{PROMPT_SHA}`\n"
            f"- **Runs completed:** {len(outputs)}/{total}\n"
            f"- **Labeled:** {n_lbl}/{total}\n"
            f"- **Hallucinations:** {n_h}/{n_lbl} (rate: {rate})\n"
            f"- **Last updated:** {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n\n"
            f"## System prompt\n\n"
            f"```\n{SYSTEM_PROMPT.strip()}\n```\n\n"
            f"## Decoding\n\n{decoding_lines}\n\n"
            f"## Cases\n\n"
            f"| id | input | output | latency | label |\n"
            f"|----|-------|--------|---------|-------|\n"
            + "\n".join(rows)
            + "\n"
        )
        run_dir = model_results_dir(model)
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "summary.md").write_text(summary, encoding="utf-8")
