"""Narrator client for local Ollama. Stdlib-only."""
import json
import urllib.error
import urllib.request
from typing import Iterator

OLLAMA_HOST = "http://localhost:11434"
DEFAULT_MODEL = "qwen3:1.7b"
SYSTEM_PROMPT = """You are a helpful visual describer, who can see and describe for BVI people. You will not mention this is a JSON; just describe it. Please ensure you provide information about the absence of what is in the left, middle, and right with ONLY ONE sentence at maximum. Most importantly, each sentence should be less than 4 words."""

DECODING = {
    "temperature": 0,
    "num_predict": 128,
    "num_ctx": 1024,
}

class OllamaError(RuntimeError):
    pass

def stream_tokens(
    user_prompt: str, *, model: str = DEFAULT_MODEL,
    system_prompt: str = SYSTEM_PROMPT, options: dict | None = None,
) -> Iterator[str]:
    """Yield response token pieces from Ollama's /api/chat (streaming)."""
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": True,
        "think": False,
        "keep_alive": "24h",
        "options": {**DECODING, **(options or {})},
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{OLLAMA_HOST}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        resp = urllib.request.urlopen(req, timeout=120)
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
            if chunk.get("error"):
                raise OllamaError(str(chunk["error"]))
            piece = (chunk.get("message") or {}).get("content")
            if piece:
                yield piece
            if chunk.get("done"):
                break

def list_models() -> list[str]:
    """Return tag names of models installed locally in Ollama."""
    return sorted(model["name"] for model in list_model_details())


def list_model_details() -> list[dict]:
    """Installed model identities and sizes reported by Ollama."""
    req = urllib.request.Request(
        f"{OLLAMA_HOST}/api/tags",
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.load(resp)
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise OllamaError(f"Could not list models at {OLLAMA_HOST}: {e}") from None
    return data.get("models", [])
