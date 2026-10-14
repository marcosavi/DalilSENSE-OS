"""Narrator client for local Ollama. Stdlib-only."""
import json
import urllib.error
import urllib.request
from typing import Iterator

OLLAMA_HOST = "http://localhost:11434"
DEFAULT_MODEL = "qwen3:1.7b"
SYSTEM_PROMPT = """
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
"""

DECODING = {
    "temperature": 0,
    "num_predict": 128,
    "num_ctx": 1024,
}

class OllamaError(RuntimeError):
    pass

def stream_tokens(user_prompt: str, *, model: str = DEFAULT_MODEL) -> Iterator[str]:
    """Yield response token pieces from Ollama's /api/chat (streaming)."""
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "stream": True,
        "think": False,
        "keep_alive": "24h",
        "options": DECODING,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{OLLAMA_HOST}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        resp = urllib.request.urlopen(req)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise OllamaError(f"HTTP {e.code}: {body}") from None
    except urllib.error.URLError as e:
        raise OllamaError(f"Could not reach Ollama at {OLLAMA_HOST}: {e.reason}. Is `ollama serve` running?") from None

    with resp:
        for raw in resp:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue
            piece = (chunk.get("message") or {}).get("content")
            if piece:
                yield piece
            if chunk.get("done"):
                break

def list_models() -> list[str]:
    """Return tag names of models installed locally in Ollama."""
    req = urllib.request.Request(
        f"{OLLAMA_HOST}/api/tags",
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.load(resp)
    except urllib.error.URLError as e:
        raise OllamaError(f"Could not reach Ollama at {OLLAMA_HOST}: {e.reason}") from None
    return sorted(m["name"] for m in data.get("models", []))