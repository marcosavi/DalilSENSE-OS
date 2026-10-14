# Experiment 1 — `qwen3:1.7b`

- **Model:** `qwen3:1.7b`
- **Prompt SHA (first 12):** `d51b8e0418fe`
- **Runs completed:** 16/27
- **Labeled:** 1/27
- **Hallucinations:** 1/1 (rate: 100.0%)
- **Last updated:** 2026-10-14T08:24:22Z

## System prompt

```
You will receive a JSON with sensor observations in three positions: "left", "middle" (directly ahead), and "right".
Each value is one of: "no_object", "person", "other_object".
Describe what you were given in less than 50 characters. Nothing else.
```

## Decoding

- temperature: 0
- num_predict: 128
- num_ctx: 1024

## Cases

| id | input | output | latency | label |
|----|-------|--------|---------|-------|
| case_000 | `{"left": "no_object", "middle": "no_object", "right": "no_object"}` | All sensors are clear. | 1153ms | Y |
| case_001 | `{"left": "no_object", "middle": "no_object", "right": "person"}` | {"left": "no_object", "middle": "no_object", "right": "person"} | 840ms | — |
| case_002 | `{"left": "no_object", "middle": "no_object", "right": "other_object"}` | {"left": "no_object", "middle": "no_object", "right": "other_object"} | 806ms | — |
| case_003 | `{"left": "no_object", "middle": "person", "right": "no_object"}` | {"left": "no_object", "middle": "person", "right": "no_object"} | 772ms | — |
| case_004 | `{"left": "no_object", "middle": "person", "right": "person"}` | {"left": "no_object", "middle": "person", "right": "person"} | 748ms | — |
| case_005 | `{"left": "no_object", "middle": "person", "right": "other_object"}` | {"left": "no_object", "middle": "person", "right": "other_object"} | 794ms | — |
| case_006 | `{"left": "no_object", "middle": "other_object", "right": "no_object"}` | {"left": "no_object", "middle": "other_object", "right": "no_object"} | 837ms | — |
| case_007 | `{"left": "no_object", "middle": "other_object", "right": "person"}` | {"left": "no_object", "middle": "other_object", "right": "person"} | 773ms | — |
| case_008 | `{"left": "no_object", "middle": "other_object", "right": "other_object"}` | {"left": "no_object", "middle": "other_object", "right": "other_object"} | 807ms | — |
| case_009 | `{"left": "person", "middle": "no_object", "right": "no_object"}` | There is a person in the left, no objects in middle and right. | 664ms | — |
| case_010 | `{"left": "person", "middle": "no_object", "right": "person"}` | {"left": "person", "middle": "no_object", "right": "person"} | 772ms | — |
| case_011 | `{"left": "person", "middle": "no_object", "right": "other_object"}` | Left: person, Middle: no_object, Right: other_object | 573ms | — |
| case_012 | `{"left": "person", "middle": "person", "right": "no_object"}` | There is a person on the left and a person in the middle. | 593ms | — |
| case_013 | `{"left": "person", "middle": "person", "right": "person"}` | {"left": "person", "middle": "person", "right": "person"} | 700ms | — |
| case_014 | `{"left": "person", "middle": "person", "right": "other_object"}` | {"left": "person", "middle": "person", "right": "other_object"} | 748ms | — |
| case_015 | `{"left": "person", "middle": "other_object", "right": "no_object"}` | Left: person, Middle: other_object, Right: no_object | 619ms | — |
| case_016 | `{"left": "person", "middle": "other_object", "right": "person"}` | — | — | — |
| case_017 | `{"left": "person", "middle": "other_object", "right": "other_object"}` | — | — | — |
| case_018 | `{"left": "other_object", "middle": "no_object", "right": "no_object"}` | — | — | — |
| case_019 | `{"left": "other_object", "middle": "no_object", "right": "person"}` | — | — | — |
| case_020 | `{"left": "other_object", "middle": "no_object", "right": "other_object"}` | — | — | — |
| case_021 | `{"left": "other_object", "middle": "person", "right": "no_object"}` | — | — | — |
| case_022 | `{"left": "other_object", "middle": "person", "right": "person"}` | — | — | — |
| case_023 | `{"left": "other_object", "middle": "person", "right": "other_object"}` | — | — | — |
| case_024 | `{"left": "other_object", "middle": "other_object", "right": "no_object"}` | — | — | — |
| case_025 | `{"left": "other_object", "middle": "other_object", "right": "person"}` | — | — | — |
| case_026 | `{"left": "other_object", "middle": "other_object", "right": "other_object"}` | — | — | — |
