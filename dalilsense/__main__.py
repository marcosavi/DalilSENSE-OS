import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

MODEL = "meta-llama/llama-3.2-3b-instruct"
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
SYSTEM_PROMPT = """
Who you are: An Orientation and Mobility (O&M) Specialist assisting blind individuals.

What you will get: A JSON describing sensor observations to the user's left, middle (directly ahead), and right. Values may be "person", "other_object", "empty", or "unknown".

What you will output: One short, natural sentence describing the surroundings.

Rules:
1. Use only information provided in the JSON.
2. If a person is directly ahead, mention only that person.
3. Never invent objects, distances, movements, or identities.
4. Never assume "empty" or "unknown" means safe.
5. Output only the description.
"""


def load_dotenv() -> None:
    # Walk up from CWD looking for a .env, stop at filesystem root.
    cwd = Path.cwd().resolve()
    for directory in (cwd, *cwd.parents):
        candidate = directory / ".env"
        if candidate.is_file():
            for raw in candidate.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                os.environ.setdefault(key, value)
            return


def stream_completion(prompt: str, api_key: str) -> int:
    payload = json.dumps({
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": prompt
            }
            ],
        "stream": True,
        "temperature": 0,
        "max_tokens": 80
    }).encode("utf-8")

    req = urllib.request.Request(
        ENDPOINT,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        method="POST",
    )

    try:
        resp = urllib.request.urlopen(req)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code}: {body}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"Network error: {e.reason}", file=sys.stderr)
        return 1

    with resp:
        for raw in resp:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line or not line.startswith("data:"):
                continue
            data = line[len("data:"):].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            for choice in chunk.get("choices", []):
                delta = choice.get("delta") or {}
                piece = delta.get("content")
                if piece:
                    sys.stdout.write(piece)
                    sys.stdout.flush()
    sys.stdout.write("\n")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2 or not argv[1].strip():
        print('Usage: python3 -m dalilsense "your prompt here"', file=sys.stderr)
        return 2

    load_dotenv()
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key or api_key == "sk-or-replace-me":
        print("OPENROUTER_API_KEY is not set. Put it in .env or export it. Keys: https://openrouter.ai/settings/keys", file=sys.stderr)
        return 2

    prompt = " ".join(argv[1:])
    return stream_completion(prompt, api_key)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
