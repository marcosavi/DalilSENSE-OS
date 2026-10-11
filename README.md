# DalilSENSE - WP3: Situational Awareness Narration

## Objective
Test whether small, open-weight text-to-text models can turn structured sensor observations into factual descriptions for blind and low-vision users without inventing information.

## Target deployment
Raspberry Pi 5 + AI HAT+ 2, operating offline.

## Models
| Model | Size | Local Mac testing |
|---|---:|---|
| Llama 3.2 Instruct | 1B | `llama3.2:1b` |
| Qwen2.5 Instruct | 1.5B | `qwen2.5:1.5b` |
| Qwen3 | 1.7B | `qwen3:1.7b` |
| Llama 3.2 Instruct | 3B | `llama3.2:3b` (larger comparison) |

- These models have downloadable weights.
- Local Mac tests measure narration quality, not performance.
- Hardware compatibility and latency must be tested separately.

## Research Questions
- RQ1. Do open-weight smaller models often hallucinate (add unreal extra information)?
- RQ2. Does the output include prioritization guidelines?
- RQ3. Does the output follow specific length?

## Dataset
**64 synthetic JSON test cases:**
- Exhaustive combinations of `person`, `other_object`, `empty`, and `unknown` across `left`, `middle`, and `right`.

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
Choose the hosted model by editing `MODEL` in the script. To use the same Python script with **local Ollama**, change its endpoint to `http://localhost:11434/v1/chat/completions`, set `MODEL` to an Ollama model tag, and bypass its mandatory OpenRouter API-key check. Use consistent system/user message roles and generation settings when comparing models.
