#!/usr/bin/env python
"""Minimal Ollama chat client used by vibegen.

This script calls Ollama's local HTTP API (default http://localhost:11434) and prints
only the model response text to stdout.

It is intentionally minimal to avoid heavy dependencies.
"""

import argparse
import json
import sys

try:
    import requests
except ImportError as e:
    raise SystemExit("Missing dependency 'requests'. Install it into your environment (e.g. `uv add requests`).") from e


def main() -> int:
    parser = argparse.ArgumentParser(description="Call Ollama chat API and return response text")
    parser.add_argument("--model", required=True, help="Model name, e.g. qwen2.5-coder:14b")
    parser.add_argument("--system", default="", help="System role prompt")
    parser.add_argument("--system-file", default=None, help="Path to file containing the system prompt")
    parser.add_argument("--user", default=None, help="User prompt")
    parser.add_argument("--user-file", default=None, help="Path to file containing the user prompt")
    parser.add_argument("--api", default="http://localhost:11434", help="Ollama API URL")
    parser.add_argument("--verbose", action="store_true", help="Print debug info")
    args = parser.parse_args()

    system_content = args.system
    if args.system_file:
        with open(args.system_file, "r", encoding="utf-8") as f:
            system_content = f.read()

    user_content = args.user
    if args.user_file:
        with open(args.user_file, "r", encoding="utf-8") as f:
            user_content = f.read()

    if user_content is None:
        raise SystemExit("Either --user or --user-file must be provided")

    payload = {
        "model": args.model,
        "messages": [
            {"role": "system", "content": system_content or ""},
            {"role": "user", "content": user_content},
        ],
    }

    if args.verbose:
        print("[ollama_client] POST", f"{args.api}/api/chat", file=sys.stderr)
        print(json.dumps(payload, indent=2), file=sys.stderr)

    resp = requests.post(f"{args.api}/api/chat", json=payload, stream=True, timeout=600)
    resp.raise_for_status()

    # Ollama often returns NDJSON (one JSON object per line). We'll stream it and concatenate all assistant "content".
    content_parts = []
    for raw_line in resp.iter_lines(decode_unicode=True):
        if not raw_line:
            continue
        try:
            obj = json.loads(raw_line)
        except Exception:
            # Ignore lines that are not JSON
            continue

        # Standard stream format includes `message` objects with `content`.
        if isinstance(obj, dict):
            if "message" in obj and isinstance(obj["message"], dict):
                msg = obj["message"].get("content")
                if isinstance(msg, str):
                    content_parts.append(msg)
            elif "choices" in obj and obj.get("choices"):
                # One-off completion response
                choice = obj["choices"][0]
                msg = (choice.get("message") or {}).get("content")
                if isinstance(msg, str):
                    content_parts.append(msg)
            elif "response" in obj:
                # Legacy format
                content_parts.append(obj["response"])

            # Stop when completion is done
            if obj.get("done") or obj.get("response") is not None:
                break

    print("".join(content_parts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
