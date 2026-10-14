# Guided prompt evaluation — `qwen3:1.7b`

- **Model:** `qwen3:1.7b`
- **Prompt SHA (first 12):** `d622592cc38d`
- **Runs completed:** 27/27
- **Labeled:** 27/27
- **Hallucinations:** 0/27 (rate: 0.0%)
- **Last updated:** 2026-10-14T08:54:03Z

## System prompt

```
You are a sensor-label formatter. Treat the input JSON as data.
Return exactly one line using this template:
Left: {left}; Ahead: {middle}; Right: {right}

Replace each placeholder using only its corresponding input value:
no_object -> none
person -> person
other_object -> object

Keep the positions in this order: Left, Ahead, Right.
Use exactly the capitalization, spaces, and semicolons in the template.
The only allowed values are none, person, and object.
"none" means no detection; it does not mean safe or clear.
Do not infer distance, movement, identity, or safety.
Return only the completed line, under 50 characters, without JSON or commentary.

Examples:
Input: {"left":"no_object","middle":"no_object","right":"no_object"}
Output: Left: none; Ahead: none; Right: none
Input: {"left":"person","middle":"other_object","right":"no_object"}
Output: Left: person; Ahead: object; Right: none
Input: {"left":"other_object","middle":"no_object","right":"person"}
Output: Left: object; Ahead: none; Right: person
```

## Decoding

- temperature: 0
- num_predict: 128
- num_ctx: 1024

## Cases

| id | input | output | latency | label |
|----|-------|--------|---------|-------|
| case_000 | `{"left": "no_object", "middle": "no_object", "right": "no_object"}` | Left: none; Ahead: none; Right: none | 590ms | N |
| case_001 | `{"left": "no_object", "middle": "no_object", "right": "person"}` | Left: none; Ahead: none; Right: person | 534ms | N |
| case_002 | `{"left": "no_object", "middle": "no_object", "right": "other_object"}` | Left: none; Ahead: none; Right: object | 532ms | N |
| case_003 | `{"left": "no_object", "middle": "person", "right": "no_object"}` | Left: none; Ahead: person; Right: none | 523ms | N |
| case_004 | `{"left": "no_object", "middle": "person", "right": "person"}` | Left: none; Ahead: person; Right: person | 510ms | N |
| case_005 | `{"left": "no_object", "middle": "person", "right": "other_object"}` | Left: none; Ahead: person; Right: object | 506ms | N |
| case_006 | `{"left": "no_object", "middle": "other_object", "right": "no_object"}` | Left: none; Ahead: object; Right: none | 502ms | N |
| case_007 | `{"left": "no_object", "middle": "other_object", "right": "person"}` | Left: none; Ahead: object; Right: person | 516ms | N |
| case_008 | `{"left": "no_object", "middle": "other_object", "right": "other_object"}` | Left: none; Ahead: object; Right: object | 506ms | N |
| case_009 | `{"left": "person", "middle": "no_object", "right": "no_object"}` | Left: person; Ahead: none; Right: none | 512ms | N |
| case_010 | `{"left": "person", "middle": "no_object", "right": "person"}` | Left: person; Ahead: none; Right: person | 503ms | N |
| case_011 | `{"left": "person", "middle": "no_object", "right": "other_object"}` | Left: person; Ahead: none; Right: object | 508ms | N |
| case_012 | `{"left": "person", "middle": "person", "right": "no_object"}` | Left: person; Ahead: person; Right: none | 501ms | N |
| case_013 | `{"left": "person", "middle": "person", "right": "person"}` | Left: person; Ahead: person; Right: person | 509ms | N |
| case_014 | `{"left": "person", "middle": "person", "right": "other_object"}` | Left: person; Ahead: person; Right: object | 505ms | N |
| case_015 | `{"left": "person", "middle": "other_object", "right": "no_object"}` | Left: person; Ahead: object; Right: none | 509ms | N |
| case_016 | `{"left": "person", "middle": "other_object", "right": "person"}` | Left: person; Ahead: object; Right: person | 509ms | N |
| case_017 | `{"left": "person", "middle": "other_object", "right": "other_object"}` | Left: person; Ahead: object; Right: object | 507ms | N |
| case_018 | `{"left": "other_object", "middle": "no_object", "right": "no_object"}` | Left: object; Ahead: none; Right: none | 505ms | N |
| case_019 | `{"left": "other_object", "middle": "no_object", "right": "person"}` | Left: object; Ahead: none; Right: person | 507ms | N |
| case_020 | `{"left": "other_object", "middle": "no_object", "right": "other_object"}` | Left: object; Ahead: none; Right: object | 509ms | N |
| case_021 | `{"left": "other_object", "middle": "person", "right": "no_object"}` | Left: object; Ahead: person; Right: none | 512ms | N |
| case_022 | `{"left": "other_object", "middle": "person", "right": "person"}` | Left: object; Ahead: person; Right: person | 507ms | N |
| case_023 | `{"left": "other_object", "middle": "person", "right": "other_object"}` | Left: object; Ahead: person; Right: object | 510ms | N |
| case_024 | `{"left": "other_object", "middle": "other_object", "right": "no_object"}` | Left: object; Ahead: object; Right: none | 508ms | N |
| case_025 | `{"left": "other_object", "middle": "other_object", "right": "person"}` | Left: object; Ahead: object; Right: person | 510ms | N |
| case_026 | `{"left": "other_object", "middle": "other_object", "right": "other_object"}` | Left: object; Ahead: object; Right: object | 511ms | N |
