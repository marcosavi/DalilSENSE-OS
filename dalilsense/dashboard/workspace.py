"""Configure, run, and review independent experiments."""
import json

from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from dalilsense.narrator import OllamaError, list_model_details
from . import runs, services
from .forms import ExperimentForm
from .models import Run


@require_GET
def home(request):
    rows = Run.objects.all()
    try:
        models = list_model_details()
    except OllamaError:
        models = []
    return render(request, "dashboard/home.html", {
        "runs": rows, "has_runs": rows.exists(),
        "models": models, "models_available": bool(models)
    })


def get_run(run_id):
    try:
        return runs.snapshot(run_id)
    except (FileNotFoundError, ValueError, KeyError):
        raise Http404("Experiment not found.") from None


def initial_for(config):
    # Duplicate uses the saved inputs, even if the dataset has since changed.
    return {"name": config["name"] + " (copy)", "model": config["model"],
            "system_prompt": config["system_prompt"], "selection": "manual",
            "case_count": len(config["cases"]), "case_ids": [case["case_id"] for case in config["cases"]],
            **{key: None for key in ("seed", "top_p", "top_k", "repeat_penalty")},
            **config["options"]}


@require_http_methods(["GET", "POST"])
def index(request):
    connection_error = ""
    try:
        models = list_model_details()
    except OllamaError as exc:
        models, connection_error = [], str(exc)
    source = get_run(request.GET["duplicate"])["config"] if request.GET.get("duplicate") else None
    cases = [(case["case_id"], case["input"]) for case in source["cases"]] if source else services.load_cases()
    initial = initial_for(source) if source else None
    form = ExperimentForm(request.POST if request.method == "POST" else None,
                          models=models, cases=cases, initial=initial)
    if request.method == "POST" and form.is_valid():
        try:
            run_id = runs.start(form.configuration())
        except runs.RunBusy as exc:
            form.add_error(None, str(exc))
        else:
            return redirect("experiments:detail", run_id=run_id)
    return render(request, "dashboard/workspace.html", {
        "form": form, "models_available": bool(models), "connection_error": connection_error,
        "available_count": len(cases),
        "source": source, "advanced_fields": [form[key] for key in ("seed", "top_p", "top_k", "repeat_penalty")],
    }, status=400 if request.method == "POST" else 200)


@require_GET
def detail(request, run_id):
    data = get_run(run_id)
    errors = {row["case_id"]: row["message"] for row in data["errors"]}
    rows = []
    for case in data["config"]["cases"]:
        key = case["case_id"]
        output = data["outputs"].get(key, {})
        review = data["labels"].get(key, {})
        rows.append({
            "case_id": key, "input": json.dumps(case["input"], indent=2),
            "output": output.get("output", ""), "latency": output.get("latency_ms"),
            "error": errors.get(key, ""), "can_review": data["review_ready"] and bool(output),
            "verdict": "Yes" if review.get("hallucination") is True else "No" if review.get("hallucination") is False else "Unreviewed",
            "yes": review.get("hallucination") is True, "no": review.get("hallucination") is False,
            "notes": review.get("notes", ""),
        })
    return render(request, "dashboard/run.html", {
        **data, "rows": rows,
        "page_state": {"running": not data["review_ready"], "total": data["total"],
                       "statusUrl": reverse("experiments:status", args=[run_id]),
                       "reviewUrl": reverse("experiments:review", args=[run_id])},
    })


@require_GET
def status(request, run_id):
    data = get_run(run_id)
    response = JsonResponse({key: value for key, value in data.items() if key != "config"})
    response["Cache-Control"] = "no-store"
    return response


@require_POST
def review(request, run_id):
    get_run(run_id)
    try:
        body = json.loads(request.body)
        if not isinstance(body, dict):
            raise ValueError("A JSON object is required.")
        case_id, verdict, notes = body.get("case_id"), body.get("hallucination"), body.get("notes", "")
        if not isinstance(case_id, str) or not isinstance(verdict, bool):
            raise ValueError("Choose Yes or No for a generated case.")
        if not isinstance(notes, str) or len(notes) > 4000:
            raise ValueError("Notes must contain at most 4,000 characters.")
        data = runs.save_review(str(run_id), case_id, verdict, notes)
    except runs.RunBusy as exc:
        return JsonResponse({"error": str(exc)}, status=409)
    except (ValueError, UnicodeDecodeError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse({key: data[key] for key in ("n_lbl", "n_h", "rate")})


@require_GET
def summary(request, run_id):
    data = get_run(run_id)
    response = HttpResponse(runs.summary_text(data), content_type="text/markdown; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="experiment-{run_id}.md"'
    return response


@require_GET
def export(request, run_id):
    response = JsonResponse(get_run(run_id), json_dumps_params={"indent": 2})
    response["Content-Disposition"] = f'attachment; filename="experiment-{run_id}.json"'
    return response
