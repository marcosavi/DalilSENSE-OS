# DalilSENSE - WP3: Situational Awareness Narration

## Objectives
Test whether small, open-weight text-to-text models can turn structured sensor observations into factual descriptions for blind and low-vision users without inventing information.

## Target deployment
- Raspberry Pi 5 + AI HAT+ 2
- Offline operation

## Models
| Model | Size | Local Mac testing |
|---|---:|---|
| Llama 3.2 Instruct | 1B | `llama3.2:1b` |
| Qwen2.5 Instruct | 1.5B | `qwen2.5:1.5b` |
| Qwen3 | 1.7B | `qwen3:1.7b` |
| Llama 3.2 Instruct | 3B | `llama3.2:3b` (larger comparison) |

### Model characteristics

- These models have downloadable weights.
- Local Mac tests measure narration quality, not performance.
- Hardware compatibility and latency must be tested separately.

## Research Questions
- RQ1. Do open-weight smaller models often hallucinate (add unreal extra information)?
- RQ2. Does the output include prioritization guidelines?
- RQ3. Does the output follow specific length?

## Experiments

### Experiment 1 — Baseline hallucination (RQ1)
Measure how often a small, instruction-tuned model fabricates information when given only a minimal, guideline-free task description. Starting with Qwen2.5-1.5B Instruct over the 27-case synthetic set in `JSON_test/`, outputs are hand-labeled by the researcher. Deliverable: per-model hallucination rate with a short taxonomy of what was added (distances, movement, identity, safety claims, out-of-vocabulary objects). Automated judging is out of scope — it belongs to a later experiment. Full protocol: `experiments/exp1.md`.

## Dataset
**27 synthetic JSON test cases:**
- Exhaustive combinations of `no_object`, `person`, and `other_object` across `left`, `middle`, and `right` (3³ = 27). Values match the dataset labels from `dataset-quickstart.ipynb` (`CLASS_NAMES`).

Example input:
```json
{"left":"other_object","middle":"person","right":"other_object"}
```
- Expected meaning: **“A person is directly ahead.”**
- Side detections are omitted under the person-ahead priority rule.

## Evaluation
- Use a **fixed prompt** and human-validated references.
- Measure unsupported claims, rule adherence, required-fact coverage, spatial/temporal accuracy, and clarity.
- Compare against a **deterministic rule-based baseline**.
- Record model version, decoding settings, and latency.

## Running the script with Ollama
The CLI uses local Ollama at `http://localhost:11434` without an API key.
Set `DEFAULT_MODEL` in `dalilsense/narrator.py` to an installed model tag, then
run `python3 -m dalilsense 'your prompt here'`. Keep prompts and decoding
settings consistent when comparing models.

## Django research dashboard

The web dashboard uses Django 5.2 LTS and the existing local Ollama client.
Python 3.10–3.14 is supported (Python 3.14 requires Django 5.2.8 or later).
From the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
ollama serve
```

If Ollama is already running, keep that instance. In another terminal, activate
`.venv` and start the dashboard:

```sh
python manage.py runserver 127.0.0.1:8001 --noreload
```

Open <http://127.0.0.1:8001/experiments/> (the root URL also redirects here).
The selector lists installed Ollama models by reported parameter count, smallest
first, and marks models up to 3B parameters as small. It displays Ollama's reported
size, which can differ from the model tag. If Ollama is unavailable, new runs are
disabled while saved experiments remain accessible. Install models through Ollama.

### Configure → generate → review

1. Choose one installed model and optionally name the run.
2. Edit the system prompt, starting from the guided formatter, factual narration,
   or minimal-instruction preset if useful.
3. Select the first N JSON cases, a fixed-seed random sample, or specific case IDs.
4. Set temperature, `num_predict`, and `num_ctx`. Advanced settings include the
   generation seed, `top_p`, `top_k`, and `repeat_penalty`. Blank optional settings
   use the installed model's defaults. Thinking output remains disabled.
5. Start the experiment. The run page refreshes live progress every second.
6. Once generation ends, choose Yes or No for each successful output, optionally
   add notes, and click **Save review**. Unreviewed and failed cases do not enter
   the hallucination-rate denominator. This metric is not overall accuracy.

Saved runs show their progress, settings, prompt/input fingerprints, and review
counts. Open any run to continue reviewing, export its complete JSON record or
Markdown summary, or duplicate its configuration. Duplicating uses the saved
input snapshots; select **Start with the current dataset instead** to use updated
files. Every execution creates a new run rather than replacing prior results.
Only one experiment generates at a time on this local server. This version uses
the existing dataset; uploads and automatic batches of configurations are not included.

The previous launch interfaces still work:

```sh
python -m dalilsense.web
python -c 'from dalilsense.web import main; main(port=8001)'
```

The narration CLI (`python -m dalilsense 'your prompt'`) remains independent of
Django and uses the prompt, model, and decoding settings in
`dalilsense/narrator.py`.

### Data and runtime

No database setup or migrations are required. Source inputs remain in
`experiments/JSON_test/`. New experiments live under
`experiments/results/runs/<uuid>/`, with an immutable `config.json` containing the
exact prompt, requested options, model digest/details, and selected input
snapshots. `state.json` tracks execution; outputs, errors, and append-only human
reviews are separate JSONL files. The latest review per case is used for metrics.

Previous results remain accessible at `/exp1/` and retain the original
`experiments/results/exp1/<model>/<prompt-sha>/` layout and archive behavior.
They are not relabeled as configurable runs because their full original settings
were not recorded. Existing files are not migrated or overwritten.

This is a **local, single-process, threaded development server**. Keep
`--noreload` enabled during experiments. A restart interrupts active generation;
the next access marks that run interrupted, preserves completed outputs, and
allows duplication to try again. It never silently resumes a partial experiment.
A shared hosted deployment would require separate worker coordination and
authentication. Do not run multiple server processes against this file store.

Optional environment settings:

- `DALILSENSE_DATASET_DIR`: alternate dataset directory.
- `DALILSENSE_RESULTS_DIR`: alternate legacy experiment results directory.
- `DALILSENSE_RUNS_DIR`: alternate configurable-run storage, useful for isolated tests.
- `DJANGO_SECRET_KEY`: override the local-development key.
- `DJANGO_DEBUG`: defaults to `1` for local development and static-file serving.

New routes are `/experiments/` for setup/history and
`/experiments/<uuid>/` for a saved run. Each run exposes `status/` (GET), `review/`
(POST JSON: `case_id`, boolean `hallucination`, optional `notes`), `summary/`, and
`export/`. Setup accepts a normal CSRF-protected form POST.

The existing dashboard, run, label, stream, and summary URLs are retained. POST
requests to `/exp1/run` and `/exp1/label` require Django's CSRF token; the dashboard
sends it automatically. Scripted HTTP clients must first obtain the CSRF cookie
from `/exp1/` and send it in the `X-CSRFToken` header along with the cookie.

### Shared layout and styles

- `dalilsense/templates/base.html` owns the shared header, navigation, footer,
  and page blocks: `title`, `header_tools`, `content`, `extra_css`, and `extra_js`.
- `dalilsense/static/css/base.css` defines shared design tokens, typography,
  layout, controls, focus indicators, and responsive shell styles.
- Montserrat weights 400–700 are bundled in `dalilsense/static/fonts/montserrat/`
  with their OFL license for offline use. Shared buttons use `.button-primary`
  (blue), `.button-secondary` (navy), and `.button-choice` (outlined, with a pale
  blue selected state driven by `aria-pressed`).
- `dalilsense/static/css/experiment.css` defines dashboard metrics, table,
  sensor values, and review states.
- `dalilsense/static/js/base.js` manages shared navigation disclosures;
  `experiment.js` handles case filtering, streaming, runs, and reviews.
- `workspace.css`, `workspace.js`, and `run.js` provide experiment setup and review.
- `dalilsense/dashboard/runs.py` owns independent run snapshots and execution;
  `forms.py` validates configuration, and `workspace.py` provides HTTP endpoints.
- `dalilsense/dashboard/services.py` retains the legacy experiment runner and
  shared file locking utilities.

Future pages should extend `base.html`, reuse the shared CSS, and load only their
page-specific styles through `extra_css`. Page data is passed through Django's
`json_script` helper, and assets and routes use Django's template tags.

### Checks

```sh
python manage.py check
python manage.py test dalilsense.dashboard
```

Tests mock Ollama and use temporary datasets and result directories. They cover
routing, model selection, template escaping, CSRF, request validation, run
conflicts, labels, archives, summaries, streaming events, and disconnect cleanup.
Configurable-run checks also cover actual background-thread progress, input
snapshots, deterministic selection, configuration forwarding, review gating,
interruption recovery, duplication, notes, and exports.
