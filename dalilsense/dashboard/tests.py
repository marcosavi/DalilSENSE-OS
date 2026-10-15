"""Regression checks use temporary files and mocked Ollama, never research results."""
import json
import queue
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.staticfiles import finders
from django.test import Client, TransactionTestCase

from dalilsense.narrator import DEFAULT_MODEL, OllamaError

from . import services, views


class ExperimentTests(TransactionTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.dataset = self.root / "cases"
        self.dataset.mkdir()
        self.case = {"left": "no_object", "middle": "person", "right": "other_object"}
        for i in range(2):
            (self.dataset / f"case_{i:03}.json").write_text(json.dumps(self.case))
        for name, value in (("DATASET_DIR", self.dataset), ("RESULTS_DIR", self.root / "results"),
                            ("HUB", services.Hub())):
            p = patch.object(services, name, value)
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(views, "list_models", return_value=[DEFAULT_MODEL, "llama3.2:1b"])
        p.start()
        self.addCleanup(p.stop)
        self.model = DEFAULT_MODEL

    def post(self, path, body):
        return self.client.post(path, data=json.dumps(body), content_type="application/json")

    def output(self, text="Left: none; Ahead: person; Right: object"):
        services.append_jsonl(services.model_results_dir(self.model) / "outputs.jsonl", {
            "case_id": "case_000", "input": self.case, "output": text,
            "latency_ms": 42, "model": self.model, "prompt_sha": services.PROMPT_SHA,
        })

    def test_dashboard_routes_assets_and_read_only_loading(self):
        home = self.client.get("/")
        self.assertEqual(home.status_code, 200)
        self.assertContains(home, "No runs yet")
        for url in ("/exp1", "/exp1/"):
            response = self.client.get(url)
            self.assertContains(response, "Run all 2")
            self.assertContains(response, 'id="row-case_000"')
            self.assertContains(response, "/static/css/base.css")
            self.assertTemplateUsed(response, "base.html")
        self.assertFalse((self.root / "results").exists())
        for asset in ("css/base.css", "css/experiment.css", "js/base.js", "js/experiment.js",
                      "cmu-q-logo.webp", "qwen-logo.webp"):
            self.assertIsNotNone(finders.find(asset))
        self.assertEqual(self.client.get("/missing").status_code, 404)

    def test_model_selection_and_ollama_unavailable_fallback(self):
        response = self.client.get("/exp1/", {"model": "llama3.2:1b"})
        self.assertEqual(response.context["model"], "llama3.2:1b")
        self.assertFalse(response.context["show_model_logo"])
        with patch.object(views, "list_models", side_effect=OllamaError("offline")):
            response = self.client.get("/exp1/", {"model": "missing"})
        self.assertEqual(response.context["model"], DEFAULT_MODEL)

    def test_escaping_and_safe_page_state(self):
        self.output('</script><script>alert("output")</script>')
        response = self.client.get("/exp1/")
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, '<script>alert("output")</script>')
        # Even unexpected upstream names must not break out of JSON script data.
        with patch.object(views, "list_models", return_value=['qwen</script><script>alert(1)</script>']):
            response = self.client.get("/exp1/")
        self.assertContains(response, r"\u003C/script\u003E")
        self.assertNotContains(response, "<script>alert(1)</script>")

    def test_run_and_duplicate_rejection(self):
        with patch.object(views.threading, "Thread") as worker:
            self.assertEqual(self.post("/exp1/run", {}).json(), {"status": "started"})
            response = self.post("/exp1/run", {})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"status": "already_running"})
        worker.assert_called_once_with(target=services.run_experiment, args=(self.model,), daemon=True)
        worker.return_value.start.assert_called_once()

    def test_thread_start_failure_releases_running_flag(self):
        with patch.object(views.threading, "Thread") as worker:
            worker.return_value.start.side_effect = RuntimeError("cannot start")
            self.assertEqual(self.post("/exp1/run", {}).status_code, 503)
        self.assertNotIn(self.model, services.HUB.running)

    def test_labels_are_append_only_with_latest_verdict_counted(self):
        self.output()
        for verdict in (True, False):
            response = self.post("/exp1/label", {"case_id": "case_000", "hallucination": verdict})
            self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "n_lbl": 1, "n_h": 0, "rate": "0%"})
        run_dir = services.model_results_dir(self.model)
        self.assertEqual(len(services.read_jsonl(run_dir / "labels_human.jsonl")), 2)
        self.assertIn("**Labeled:** 1/2", (run_dir / "summary.md").read_text())
        self.assertContains(self.client.get("/exp1/"), 'class="labeled-n"')

    def test_reviews_require_completed_output_and_idle_model(self):
        body = {"case_id": "case_000", "hallucination": True}
        self.assertEqual(self.post("/exp1/label", body).status_code, 409)
        self.output()
        services.HUB.running.add(self.model)
        self.assertEqual(self.post("/exp1/label", body).status_code, 409)

    def test_invalid_requests_and_methods(self):
        for body in ("{", "[]", "null", '{"model": []}', '{"model": "../.."}'):
            response = self.client.post("/exp1/run", body, content_type="application/json")
            self.assertEqual(response.status_code, 400)
        for body in ({"case_id": [], "hallucination": True},
                     {"case_id": "case_000", "hallucination": "yes"}):
            self.assertEqual(self.post("/exp1/label", body).status_code, 400)
        for route in ("/exp1/", "/exp1/stream", "/exp1/summary"):
            self.assertEqual(self.client.get(route, {"model": ".."}).status_code, 400)
        self.assertEqual(self.client.get("/exp1/run").status_code, 405)
        self.assertEqual(self.client.get("/exp1/label").status_code, 405)
        self.assertEqual(self.post("/exp1/stream", {}).status_code, 405)

    def test_csrf_required_and_token_accepted(self):
        client = Client(enforce_csrf_checks=True)
        self.output()
        body = {"case_id": "case_000", "hallucination": False}
        for path in ("/exp1/run", "/exp1/label"):
            self.assertEqual(client.post(path, body, content_type="application/json").status_code, 403)
        client.get("/exp1/")
        token = client.cookies["csrftoken"].value
        response = client.post("/exp1/label", body, content_type="application/json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200)
        with patch.object(views.threading, "Thread"):
            response = client.post("/exp1/run", {}, content_type="application/json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200)

    def test_sse_initial_state_events_heartbeat_and_cleanup(self):
        response = self.client.get("/exp1/stream")
        self.assertEqual(response["Content-Type"], "text/event-stream")
        self.assertEqual(response["Cache-Control"], "no-cache")
        stream = iter(response.streaming_content)
        self.assertIn(b'"running": false', next(stream))
        subscriber = services.HUB.subs[self.model][0]
        services.HUB.publish(self.model, {"type": "token", "case_id": "case_000", "piece": "Left"})
        self.assertIn(b'"piece": "Left"', next(stream))
        with patch.object(subscriber, "get", side_effect=queue.Empty):
            self.assertEqual(next(stream), b": keep-alive\n\n")
        response.close()
        self.assertEqual(services.HUB.subs[self.model], [])

    def test_run_writes_outputs_and_archives_existing_results(self):
        self.output("old output")
        run_dir = services.model_results_dir(self.model)
        services.append_jsonl(run_dir / "labels_human.jsonl", {"case_id": "case_000", "hallucination": True})
        services.append_jsonl(run_dir / "errors.jsonl", {"case_id": "old", "message": "old error"})
        services.write_summary(self.model)
        before = {p.name: p.read_bytes() for p in run_dir.iterdir()}
        subscriber = services.HUB.subscribe(self.model)
        services.HUB.running.add(self.model)
        with patch.object(services, "stream_tokens", side_effect=lambda *a, **kw: iter(["new ", "output"])):
            services.run_experiment(self.model)
        archive = next((run_dir / "history").iterdir())
        self.assertEqual({p.name: p.read_bytes() for p in archive.iterdir()}, before)
        self.assertEqual(len(services.read_outputs(self.model)), 2)
        self.assertEqual(services.read_outputs(self.model)["case_000"]["output"], "new output")
        self.assertEqual(services.read_labels(self.model), {})
        events = []
        while not subscriber.empty():
            events.append(subscriber.get()["type"])
        self.assertEqual(events, ["reset", "start", "token", "token", "done", "start", "token", "token", "done", "complete"])
        self.assertNotIn(self.model, services.HUB.running)

    def test_case_error_is_recorded_and_remaining_cases_continue(self):
        services.HUB.running.add(self.model)
        with patch.object(services, "stream_tokens", side_effect=[OllamaError("offline"), iter(["ok"])]):
            services.run_experiment(self.model)
        self.assertEqual(list(services.read_outputs(self.model)), ["case_001"])
        errors = services.read_jsonl(services.model_results_dir(self.model) / "errors.jsonl")
        self.assertEqual(errors, [{"case_id": "case_000", "message": "offline"}])
        self.assertNotIn(self.model, services.HUB.running)

    def test_run_error_releases_flag_and_publishes_completion(self):
        subscriber = services.HUB.subscribe(self.model)
        services.HUB.running.add(self.model)
        with patch.object(services, "load_cases", side_effect=RuntimeError("bad dataset")):
            services.run_experiment(self.model)
        events = []
        while not subscriber.empty():
            events.append(subscriber.get()["type"])
        self.assertEqual(events, ["reset", "run_error", "complete"])
        self.assertNotIn(self.model, services.HUB.running)

    def test_summary_serves_existing_bytes_without_overwriting(self):
        self.output()
        services.write_summary(self.model)
        path = services.model_results_dir(self.model) / "summary.md"
        before = path.read_bytes()
        response = self.client.get("/exp1/summary")
        self.assertEqual(response["Content-Type"], "text/markdown; charset=utf-8")
        self.assertEqual(response.content, before)
        self.assertEqual(path.read_bytes(), before)

    def test_summary_generated_when_missing(self):
        response = self.client.get("/exp1/summary")
        self.assertContains(response, "**Runs completed:** 0/2")
