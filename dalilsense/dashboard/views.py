"""HTTP endpoints for the local experiment dashboard."""
import json
import queue
import re
import threading
import time

from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from dalilsense.narrator import DEFAULT_MODEL, OllamaError, SYSTEM_PROMPT, list_models

from . import services


def requested_model(data):
    model = data.get("model", DEFAULT_MODEL)
    if model is None or model == "":
        return DEFAULT_MODEL
    # Keep existing Ollama names and directory mapping, but reject path traversal.
    if (not isinstance(model, str) or len(model) > 255
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]*", model)
            or any(part in ("", ".", "..") for part in model.split("/"))):
        raise ValueError("A valid Ollama model name is required.")
    return model


def json_body(request):
    try:
        body = json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError):
        raise ValueError("A valid JSON object is required.") from None
    if not isinstance(body, dict):
        raise ValueError("A valid JSON object is required.")
    return body


def review_stats(labels):
    n_lbl = len(labels)
    n_h = sum(1 for row in labels.values() if row.get("hallucination"))
    return {"n_lbl": n_lbl, "n_h": n_h, "rate": f"{n_h / n_lbl:.0%}" if n_lbl else "—"}


@require_GET
@ensure_csrf_cookie
def index(request):
    try:
        model = requested_model(request.GET)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    try:
        installed = list_models()
    except OllamaError:
        installed = []
    installed = installed or [DEFAULT_MODEL]
    if model not in installed:
        model = installed[0]
    with services.HUB.lock:
        outputs = services.read_outputs(model)
        labels = services.read_labels(model)
        errors = {r["case_id"]: r["message"] for r in services.read_jsonl(
            services.model_results_dir(model) / "errors.jsonl"
        )}
        running = model in services.HUB.running
    rows = []
    cases = services.load_cases()
    for case_id, case_input in cases:
        rec = outputs.get(case_id, {})
        output = rec.get("output", "")
        verdict = labels.get(case_id, {}).get("hallucination")
        valid = bool(re.fullmatch(
            r"Left: (none|person|object); Ahead: (none|person|object); Right: (none|person|object)", output
        ))
        rows.append({
            "case_id": case_id,
            "sensors": [(title, case_input[key].replace("_", " ")) for key, title in
                        (("left", "Left"), ("middle", "Ahead"), ("right", "Right"))],
            "output": "Error: " + errors[case_id] if case_id in errors else output,
            "output_class": "output error" if case_id in errors else "output",
            "meta": f'{len(output)} chars · {"Format valid" if valid else "Check format"}' if rec else "",
            "latency": f'{rec["latency_ms"]} ms' if rec.get("latency_ms") is not None else "—",
            "row_class": "labeled-y" if verdict is True else "labeled-n" if verdict is False else "",
            "yes": verdict is True, "no": verdict is False,
            "disabled": running or not rec,
        })
    stats = review_stats(labels)
    return render(request, "dashboard/experiment.html", {
        **stats, "model": model, "models": installed, "rows": rows,
        "running": running, "total": len(cases), "n_out": len(outputs),
        "n_lbl_or_dash": stats["n_lbl"] or "—",
        "show_model_logo": model.lower().split("/")[-1].startswith("qwen"),
        "system_prompt": SYSTEM_PROMPT.strip(),
        "run_status": "Run in progress…" if running else "",
        "page_state": {
            "model": model, "total": len(cases), "running": running,
            "errorCount": len(errors), "completed": list(outputs),
            "urls": {name: reverse(f"dashboard:{name}") for name in ("run", "label", "stream")},
        },
    })


@require_POST
def run(request):
    try:
        model = requested_model(json_body(request))
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    with services.HUB.lock:
        if model in services.HUB.running or any(key.startswith("run:") for key in services.HUB.running):
            return JsonResponse({"status": "already_running"}, status=409)
        services.HUB.running.add(model)
        try:
            threading.Thread(target=services.run_experiment, args=(model,), daemon=True).start()
        except RuntimeError:
            services.HUB.running.discard(model)
            return JsonResponse({"error": "Could not start the experiment."}, status=503)
    return JsonResponse({"status": "started"})


@require_POST
def label(request):
    try:
        body = json_body(request)
        model = requested_model(body)
        case_id = body.get("case_id")
        if not isinstance(case_id, str):
            raise ValueError("A case ID is required.")
        if not isinstance(body.get("hallucination"), bool):
            raise ValueError("A yes or no verdict is required.")
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    with services.HUB.lock:
        if model in services.HUB.running or case_id not in services.read_outputs(model):
            return JsonResponse({"error": "Wait for a completed run before reviewing."}, status=409)
        services.append_jsonl(services.model_results_dir(model) / "labels_human.jsonl", {
            "case_id": case_id, "hallucination": body["hallucination"],
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
        services.write_summary(model)
        stats = review_stats(services.read_labels(model))
    return JsonResponse({"status": "ok", **stats})


def event_stream(model):
    hub = services.HUB
    subscriber = hub.subscribe(model)
    try:
        with hub.lock:
            running = model in hub.running
        yield f'data: {json.dumps({"type": "state", "running": running})}\n\n'
        while True:
            try:
                event = subscriber.get(timeout=15)
            except queue.Empty:
                yield ": keep-alive\n\n"
                continue
            yield f"data: {json.dumps(event)}\n\n"
    finally:
        hub.unsubscribe(model, subscriber)


@require_GET
def stream(request):
    try:
        model = requested_model(request.GET)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    response = StreamingHttpResponse(event_stream(model), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


@require_GET
def summary(request):
    try:
        model = requested_model(request.GET)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    with services.HUB.lock:
        path = services.model_results_dir(model) / "summary.md"
        if not path.exists():
            services.write_summary(model)
        return HttpResponse(path.read_bytes(), content_type="text/markdown; charset=utf-8")
