"""Configurable-run regressions: isolated files and no real model inference."""
import io
import json
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

from django.test import Client, SimpleTestCase, TransactionTestCase, override_settings

from dalilsense import narrator
from . import runs, services, workspace
from .forms import ExperimentForm

MODELS = [
    {"name": "large:8b", "digest": "large-digest", "details": {"parameter_size": "8B"}},
    {"name": "small:1b", "digest": "small-digest", "details": {"parameter_size": "1B", "quantization_level": "Q4_K_M"}},
]


class WorkspaceTests(TransactionTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.cases = self.root / "cases"
        self.cases.mkdir()
        for number in range(4):
            (self.cases / f"case_{number:03}.json").write_text(json.dumps({"left": "person", "middle": "no_object", "right": "no_object"}))
        settings = override_settings(DALILSENSE_RUNS_DIR=self.root / "runs")
        settings.enable()
        self.addCleanup(settings.disable)
        for target, name, value in ((services, "DATASET_DIR", self.cases),
                                    (services, "RESULTS_DIR", self.root / "legacy"),
                                    (services, "HUB", services.Hub()),
                                    (runs, "ACTIVE", set()), (runs, "LIVE", {})):
            p = patch.object(target, name, value)
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(workspace, "list_model_details", return_value=MODELS)
        p.start()
        self.addCleanup(p.stop)
        self.data = {"name": "Test configuration", "model": "small:1b", "system_prompt": "Describe only observed facts.",
                     "selection": "first", "case_count": 2, "sample_seed": 42,
                     "temperature": .3, "num_predict": 64, "num_ctx": 2048, "seed": 21,
                     "top_p": .8, "top_k": 30, "repeat_penalty": 1.1}

    def form(self, data=None):
        return ExperimentForm(data or self.data, models=MODELS, cases=services.load_cases())

    def start(self, data=None, finish=True):
        form = self.form(data)
        self.assertTrue(form.is_valid(), form.errors)
        with patch.object(runs.threading, "Thread"):
            run_id = runs.start(form.configuration())
        if finish:
            with patch.object(runs, "stream_tokens", side_effect=lambda *args, **kwargs: iter(["A person ", "on the left."])):
                runs.execute(run_id)
        return run_id

    def test_setup_model_order_presets_and_no_storage_side_effects(self):
        response = self.client.get("/experiments/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Start experiment")
        self.assertContains(response, "4 JSON files available")
        self.assertContains(response, "Small model")
        self.assertLess(response.content.index(b'small:1b'), response.content.index(b'large:8b'))
        self.assertFalse((self.root / "runs").exists())
        home = self.client.get("/")
        self.assertEqual(home.status_code, 200)
        self.assertContains(home, "No runs yet")

    def test_post_redirects_to_new_run_and_rejects_concurrent_run(self):
        with patch.object(runs.threading, "Thread"):
            response = self.client.post("/experiments/", self.data)
            duplicate = self.client.post("/experiments/", self.data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/experiments/"))
        self.assertContains(duplicate, "Another experiment is running", status_code=400)
        self.assertEqual(len(list((self.root / "runs").glob("*/config.json"))), 1)

    def test_first_random_and_manual_selections(self):
        first = self.form()
        self.assertTrue(first.is_valid())
        self.assertEqual([c["case_id"] for c in first.configuration()["cases"]], ["case_000", "case_001"])
        random = self.form({**self.data, "selection": "random"})
        same = self.form({**self.data, "selection": "random"})
        self.assertTrue(random.is_valid())
        self.assertTrue(same.is_valid())
        self.assertEqual(random.configuration()["cases"], same.configuration()["cases"])
        manual = self.form({**self.data, "selection": "manual", "case_ids": ["case_003", "case_001"]})
        self.assertTrue(manual.is_valid())
        self.assertEqual([c["case_id"] for c in manual.configuration()["cases"]], ["case_001", "case_003"])

    def test_invalid_configuration_creates_no_run(self):
        invalid = [{"case_count": 5}, {"case_count": 0}, {"temperature": "nan"}, {"temperature": 3},
                   {"num_predict": -1}, {"num_ctx": 0}, {"model": "not-installed"}, {"system_prompt": " "},
                   {"selection": "manual", "case_ids": []}, {"selection": "manual", "case_ids": ["../../bad"]},
                   {"selection": "random", "sample_seed": ""}, {"top_p": 2}]
        for changes in invalid:
            with self.subTest(changes=changes):
                form = self.form({**self.data, **changes})
                self.assertFalse(form.is_valid())
        response = self.client.post("/experiments/", {**self.data, "num_predict": -1})
        self.assertEqual(response.status_code, 400)
        self.assertFalse((self.root / "runs").exists())

    def test_settings_and_exact_inputs_reach_runner_and_persist(self):
        run_id = self.start(finish=False)
        config = runs.load_config(run_id)
        # Subsequent dataset edits cannot change the queued run.
        (self.cases / "case_000.json").write_text('{"left":"changed"}')
        with patch.object(runs, "stream_tokens", side_effect=lambda *a, **kw: iter(["output"])) as generate:
            runs.execute(run_id)
        self.assertEqual(generate.call_count, 2)
        args, kwargs = generate.call_args_list[0]
        self.assertEqual(json.loads(args[0]), config["cases"][0]["input"])
        self.assertEqual(kwargs["system_prompt"], self.data["system_prompt"])
        self.assertEqual(kwargs["options"], config["options"])
        self.assertEqual(kwargs["model"], self.data["model"])
        self.assertEqual(config["model_digest"], "small-digest")
        snapshot = runs.snapshot(run_id)
        self.assertEqual(snapshot["status"], "completed")
        self.assertEqual(snapshot["n_out"], 2)
        self.assertTrue(snapshot["review_ready"])

    def test_new_runs_never_overwrite_previous_configs_or_reviews(self):
        first = self.start()
        runs.save_review(first, "case_000", True, "Invented distance.")
        original = {p.name: p.read_bytes() for p in runs.directory(first).iterdir()}
        second = self.start({**self.data, "temperature": .9, "system_prompt": "A different prompt"})
        self.assertNotEqual(first, second)
        self.assertEqual({p.name: p.read_bytes() for p in runs.directory(first).iterdir()}, original)
        self.assertEqual(runs.snapshot(second)["n_lbl"], 0)
        self.assertEqual(len(runs.history()), 2)

    def test_review_controls_only_after_generation_and_server_enforces_it(self):
        run_id = self.start(finish=False)
        url = f"/experiments/{run_id}/"
        self.assertNotContains(self.client.get(url), 'class="review-form"')
        response = self.client.post(url + "review/", {"case_id": "case_000", "hallucination": False}, content_type="application/json")
        self.assertEqual(response.status_code, 409)
        with patch.object(runs, "stream_tokens", side_effect=lambda *a, **kw: iter(["output"])):
            runs.execute(run_id)
        self.assertContains(self.client.get(url), 'class="review-form"', count=2)
        self.assertContains(self.client.get(url), "Unreviewed", count=3)

    def test_review_notes_updates_and_reviewed_only_rate(self):
        run_id = self.start()
        url = f"/experiments/{run_id}/review/"
        response = self.client.post(url, {"case_id": "case_000", "hallucination": True, "notes": "Distance invented"}, content_type="application/json")
        self.assertEqual(response.json(), {"n_lbl": 1, "n_h": 1, "rate": "100.0%"})
        response = self.client.post(url, {"case_id": "case_000", "hallucination": False, "notes": "Corrected review"}, content_type="application/json")
        self.assertEqual(response.json(), {"n_lbl": 1, "n_h": 0, "rate": "0.0%"})
        self.assertEqual(runs.snapshot(run_id)["labels"]["case_000"]["notes"], "Corrected review")
        for body in ({"case_id": "case_000", "hallucination": "no"}, [], {"case_id": "case_000", "hallucination": False, "notes": "x" * 4001}):
            self.assertEqual(self.client.post(url, body, content_type="application/json").status_code, 400)
        response = self.client.post(url, {"case_id": "missing", "hallucination": False}, content_type="application/json")
        self.assertEqual(response.status_code, 409)

    def test_case_errors_blank_output_and_review_successes_only(self):
        run_id = self.start({**self.data, "case_count": 3}, finish=False)
        with patch.object(runs, "stream_tokens", side_effect=[narrator.OllamaError("offline"), iter([]), iter(["ok"])]):
            runs.execute(run_id)
        data = runs.snapshot(run_id)
        self.assertEqual(data["status"], "completed_with_errors")
        self.assertEqual(len(data["errors"]), 2)
        self.assertEqual(data["n_out"], 1)
        response = self.client.get(f"/experiments/{run_id}/")
        self.assertContains(response, 'class="review-form"', count=1)
        self.assertContains(response, "Error: offline")

    def test_restart_marks_run_interrupted_and_preserves_outputs(self):
        run_id = self.start(finish=False)
        services.append_jsonl(runs.directory(run_id) / "outputs.jsonl", {"case_id": "case_000", "output": "saved", "latency_ms": 5})
        runs.ACTIVE.clear()
        services.HUB.running.clear()
        data = runs.snapshot(run_id)
        self.assertEqual(data["status"], "interrupted")
        self.assertEqual(data["n_out"], 1)
        self.assertTrue(data["review_ready"])
        self.assertEqual(runs.load_config(run_id)["system_prompt"], self.data["system_prompt"])

    def test_duplicate_uses_saved_inputs_and_preserves_optional_defaults(self):
        run_id = self.start({**self.data, "seed": "", "top_p": "", "top_k": "", "repeat_penalty": ""})
        (self.cases / "case_000.json").write_text('{"changed":true}')
        response = self.client.get("/experiments/", {"duplicate": run_id})
        form = response.context["form"]
        self.assertIsNone(form.initial["seed"])
        self.assertEqual(form.cases["case_000"]["left"], "person")
        self.assertEqual(form.initial["case_ids"], ["case_000", "case_001"])
        with patch.object(runs.threading, "Thread"):
            response = self.client.post(f"/experiments/?duplicate={run_id}", {**self.data, "selection": "manual", "case_ids": ["case_000", "case_001"]})
        self.assertEqual(response.status_code, 302)
        new_id = response.url.split("/")[2]
        self.assertEqual(runs.load_config(new_id)["cases"], runs.load_config(run_id)["cases"])

    def test_exports_include_configuration_inputs_and_reviews(self):
        run_id = self.start()
        runs.save_review(run_id, "case_000", True, "Unsupported claim")
        response = self.client.get(f"/experiments/{run_id}/export/")
        self.assertEqual(response.json()["config"]["options"]["temperature"], .3)
        self.assertEqual(response.json()["labels"]["case_000"]["notes"], "Unsupported claim")
        self.assertIn("attachment", response["Content-Disposition"])
        summary = self.client.get(f"/experiments/{run_id}/summary/")
        self.assertContains(summary, "temperature: 0.3")
        self.assertContains(summary, "Unsupported claim")
        self.assertContains(summary, "Unreviewed")

    def test_csrf_and_missing_runs(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post("/experiments/", self.data).status_code, 403)
        run_id = self.start()
        self.assertEqual(client.post(f"/experiments/{run_id}/review/", {}).status_code, 403)
        client.get("/experiments/")
        token = client.cookies["csrftoken"].value
        response = client.post(f"/experiments/{run_id}/review/", {"case_id": "case_000", "hallucination": False}, content_type="application/json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(client.get("/experiments/00000000-0000-0000-0000-000000000000/").status_code, 404)
        self.assertEqual(client.get("/experiments/?duplicate=../../bad").status_code, 404)

    def test_offline_setup_still_shows_history(self):
        self.start()
        with patch.object(workspace, "list_model_details", side_effect=narrator.OllamaError("Ollama unavailable")):
            response = self.client.get("/experiments/")
        self.assertContains(response, "Ollama unavailable")
        self.assertContains(response, "disabled>Start experiment")
        home = self.client.get("/")
        self.assertEqual(home.status_code, 200)
        self.assertContains(home, "Test configuration")

    def test_status_live_text_and_escaped_output(self):
        run_id = self.start(finish=False)
        runs.LIVE[run_id] = {"case_id": "case_000", "output": "partial"}
        response = self.client.get(f"/experiments/{run_id}/status/")
        self.assertEqual(response.json()["live"]["output"], "partial")
        self.assertEqual(response["Cache-Control"], "no-store")
        with patch.object(runs, "stream_tokens", side_effect=lambda *a, **kw: iter(['<script>alert(1)</script>'])):
            runs.execute(run_id)
        response = self.client.get(f"/experiments/{run_id}/")
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertContains(response, '&lt;script&gt;alert(1)&lt;/script&gt;')

    def test_worker_start_failure_is_recorded(self):
        form = self.form()
        self.assertTrue(form.is_valid())
        with patch.object(runs.threading, "Thread") as thread:
            thread.return_value.start.side_effect = RuntimeError("failed to start")
            run_id = runs.start(form.configuration())
        self.assertEqual(runs.snapshot(run_id)["status"], "failed")
        self.assertFalse(runs.ACTIVE)
        self.assertFalse(services.HUB.running)

    def test_real_background_thread_progress_then_review(self):
        started, release, finished = threading.Event(), threading.Event(), threading.Event()
        execute = runs.execute

        def tokens(*args, **kwargs):
            yield "A person"
            started.set()
            if not release.wait(3):
                raise RuntimeError("Test worker timed out")
            yield " on the left."

        def worker(run_id):
            try:
                execute(run_id)
            finally:
                finished.set()

        with patch.object(runs, "stream_tokens", side_effect=tokens), patch.object(runs, "execute", side_effect=worker):
            try:
                response = self.client.post("/experiments/", {**self.data, "case_count": 1})
                self.assertEqual(response.status_code, 302)
                self.assertTrue(started.wait(2))
                progress = self.client.get(response.url + "status/").json()
                self.assertFalse(progress["review_ready"])
                self.assertEqual(progress["live"]["output"], "A person")
            finally:
                release.set()
                self.assertTrue(finished.wait(3))
        progress = self.client.get(response.url + "status/").json()
        self.assertTrue(progress["review_ready"])
        self.assertEqual(progress["n_out"], 1)


class NarratorConfigurationTests(SimpleTestCase):
    def test_ollama_payload_uses_requested_settings_without_mutating_defaults(self):
        original = dict(narrator.DECODING)
        response = io.BytesIO(b'{"message":{"content":"hello"},"done":true}\n')
        with patch.object(narrator.urllib.request, "urlopen", return_value=response) as request:
            self.assertEqual(list(narrator.stream_tokens("input", model="small:1b", system_prompt="custom", options={"temperature": .8, "seed": 5})), ["hello"])
        payload = json.loads(request.call_args.args[0].data)
        self.assertEqual(payload["messages"][0]["content"], "custom")
        self.assertEqual(payload["options"], {**original, "temperature": .8, "seed": 5})
        self.assertEqual(narrator.DECODING, original)
        self.assertFalse(payload["think"])

    def test_stream_error_is_not_treated_as_success(self):
        with patch.object(narrator.urllib.request, "urlopen", return_value=io.BytesIO(b'{"error":"model missing"}\n')):
            with self.assertRaisesMessage(narrator.OllamaError, "model missing"):
                list(narrator.stream_tokens("input"))
