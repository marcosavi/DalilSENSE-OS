import sys

from dalilsense.narrator import OllamaError, stream_tokens


def main(argv: list[str]) -> int:
    if len(argv) < 2 or not argv[1].strip():
        print('Usage: python3 -m dalilsense "your prompt here"', file=sys.stderr)
        return 2

    prompt = " ".join(argv[1:])
    try:
        for piece in stream_tokens(prompt):
            sys.stdout.write(piece)
            sys.stdout.flush()
    except OllamaError as e:
        print(str(e), file=sys.stderr)
        return 1
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))