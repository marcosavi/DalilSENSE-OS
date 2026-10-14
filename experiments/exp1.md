# Experiment 1 — Baseline Hallucination Test

This file is the protocol for Experiment 1 of DalilSENSE WP3. It describes what we're testing, how we're testing it, and what artifacts the experiment should produce. The top-level `README.md` references this file from its "Experiments" section.

## Research question
RQ1 — Do small open-weight instruction-tuned models hallucinate (add information not present in the input JSON)?

## Hypothesis
A ≤ 2B-parameter model given only (a) the input schema and (b) "describe what you were given, nothing else" will frequently add unsupported detail that is not derivable from the JSON.

## Setup

### Input dataset — `experiments/JSON_test/`
27 test cases, one JSON file per case. Exhaustive combinations of `{no_object, person, other_object}` across `{left, middle, right}` (3³ = 27). Vocabulary matches `dataset-quickstart.ipynb` (`CLASS_NAMES`).

Example case:
```json
{"left":"other_object","middle":"person","right":"other_object"}
```

### Prompt
Guideline-free. Defined in `dalilsense/__main__.py`:

```
SYSTEM_PROMPT = """
You will receive a JSON with sensor observations in three positions: "left", "middle" (directly ahead), and "right". Each value is one of: "no_object", "person", "other_object". Describe what you were given in less than 50 characters. Nothing else.
"""
```

### Model under test
- **Qwen2.5-1.5B Instruct** via local Ollama

### Decoding
- `temperature = 0`
- `num_predict = 128`
- `num_ctx = 1024`. See `dalilsense/__main__.py`.


Yes## Procedure
1. Generate the 27 case files in `experiments/JSON_test/` (deterministic).
2. For each case, run `python3 -m dalilsense '<case JSON>'`
3. Record the raw model output plus latency.
3. **Human labels**: for every (input, output) pair, label `hallucination ∈ {yes, no}` and note *what* was added.
4. Summarize: per-model hallucination rate and specific patterns.

## What counts as a hallucination
Any claim in the output that cannot be grounded in the input JSON.

Examples:
- Distances ("3 feet away")
- Movements ("approaching", "walking")
- Identity ("a man", "a child")
- Safety / affordance claims ("the path is clear", "unsafe to proceed")
- Objects outside the vocabulary ("car", "wall", "chair")