# DalilSENSE — WP3: Situational Awareness Narration

## Model
- **Meta Llama 3.2 1B Instruct** (text-to-text)
- **Testing:** OpenRouter (`meta-llama/llama-3.2-1b-instruct`)
- **Target deployment:** Raspberry Pi 5 + AI HAT+ 2
- **Task:** Structured scene JSON → concise natural-language narration

## Research Questions
1. **Factual grounding:** Does the model avoid adding details absent from the JSON?
2. **Guideline adherence:** Does it follow prioritization and uncertainty rules?
3. **Narration quality:** Are descriptions accurate, concise, and useful for situational awareness?
4. **On-device feasibility:** Are latency and memory usage suitable for real-time narration?

## Dataset
**100 synthetic JSON test cases:**
- **64** exhaustive static combinations of `person`, `other_object`, `empty`, and `unknown` across left, middle, and right
- **20** challenging priority and ambiguity cases
- **16** temporal cases showing changes between observations

## Evaluation
Compare narrations against human-validated references for hallucinations, rule adherence, spatial/temporal accuracy, and clarity. Measure on-device latency separately from hosted API testing.

## CLI usage (OpenRouter)

Quick way to send a prompt to Llama 3.2 1B Instruct via OpenRouter and stream the reply to the terminal.

1. Get an API key: https://openrouter.ai/settings/keys
2. Put it in a `.env` file at the repo root (gitignored):

   ```
   OPENROUTER_API_KEY=sk-or-...
   ```

   Or export it in your shell: `export OPENROUTER_API_KEY="sk-or-..."`.

3. Run from the repo root:

   ```bash
   python3 -m dalilsense "please, explain graph theory"
   ```

Streams tokens to stdout as they are generated. Stdlib-only, no `pip install` needed.