# Guided prompt evaluation — `qwen3:1.7b`

- **Model:** `qwen3:1.7b`
- **Prompt SHA (first 12):** `d622592cc38d`
- **Runs completed:** 27/27
- **Labeled:** 0/27
- **Hallucinations:** 0/0 (rate: —)
- **Last updated:** 2026-10-14T08:55:12Z

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
| case_000 | `{"left": "no_object", "middle": "no_object", "right": "no_object"}` | Left: none; Ahead: none; Right: none | 400ms | — |
| case_001 | `{"left": "no_object", "middle": "no_object", "right": "person"}` | Left: none; Ahead: none; Right: person | 387ms | — |
| case_002 | `{"left": "no_object", "middle": "no_object", "right": "other_object"}` | Left: none; Ahead: none; Right: object | 448ms | — |
| case_003 | `{"left": "no_object", "middle": "person", "right": "no_object"}` | Left: none; Ahead: person; Right: none | 544ms | — |
| case_004 | `{"left": "no_object", "middle": "person", "right": "person"}` | Left: none; Ahead: person; Right: person | 545ms | — |
| case_005 | `{"left": "no_object", "middle": "person", "right": "other_object"}` | Left: none; Ahead: person; Right: object | 527ms | — |
| case_006 | `{"left": "no_object", "middle": "other_object", "right": "no_object"}` | Left: none; Ahead: object; Right: none | 549ms | — |
| case_007 | `{"left": "no_object", "middle": "other_object", "right": "person"}` | Left: none; Ahead: object; Right: person | 536ms | — |
| case_008 | `{"left": "no_object", "middle": "other_object", "right": "other_object"}` | Left: none; Ahead: object; Right: object | 539ms | — |
| case_009 | `{"left": "person", "middle": "no_object", "right": "no_object"}` | Left: person; Ahead: none; Right: none | 527ms | — |
| case_010 | `{"left": "person", "middle": "no_object", "right": "person"}` | Left: person; Ahead: none; Right: person | 508ms | — |
| case_011 | `{"left": "person", "middle": "no_object", "right": "other_object"}` | Left: person; Ahead: none; Right: object | 525ms | — |
| case_012 | `{"left": "person", "middle": "person", "right": "no_object"}` | Left: person; Ahead: person; Right: none | 514ms | — |
| case_013 | `{"left": "person", "middle": "person", "right": "person"}` | Left: person; Ahead: person; Right: person | 508ms | — |
| case_014 | `{"left": "person", "middle": "person", "right": "other_object"}` | Left: person; Ahead: person; Right: object | 517ms | — |
| case_015 | `{"left": "person", "middle": "other_object", "right": "no_object"}` | Left: person; Ahead: object; Right: none | 511ms | — |
| case_016 | `{"left": "person", "middle": "other_object", "right": "person"}` | Left: person; Ahead: object; Right: person | 513ms | — |
| case_017 | `{"left": "person", "middle": "other_object", "right": "other_object"}` | Left: person; Ahead: object; Right: object | 511ms | — |
| case_018 | `{"left": "other_object", "middle": "no_object", "right": "no_object"}` | Left: object; Ahead: none; Right: none | 515ms | — |
| case_019 | `{"left": "other_object", "middle": "no_object", "right": "person"}` | Left: object; Ahead: none; Right: person | 507ms | — |
| case_020 | `{"left": "other_object", "middle": "no_object", "right": "other_object"}` | Left: object; Ahead: none; Right: object | 518ms | — |
| case_021 | `{"left": "other_object", "middle": "person", "right": "no_object"}` | Left: object; Ahead: person; Right: none | 525ms | — |
| case_022 | `{"left": "other_object", "middle": "person", "right": "person"}` | Left: object; Ahead: person; Right: person | 514ms | — |
| case_023 | `{"left": "other_object", "middle": "person", "right": "other_object"}` | Left: object; Ahead: person; Right: object | 513ms | — |
| case_024 | `{"left": "other_object", "middle": "other_object", "right": "no_object"}` | Left: object; Ahead: object; Right: none | 513ms | — |
| case_025 | `{"left": "other_object", "middle": "other_object", "right": "person"}` | Left: object; Ahead: object; Right: person | 518ms | — |
| case_026 | `{"left": "other_object", "middle": "other_object", "right": "other_object"}` | Left: object; Ahead: object; Right: object | 510ms | — |
