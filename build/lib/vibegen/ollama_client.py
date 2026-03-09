"""Minimal Ollama chat client used by vibegen.

This module is a minimal wrapper around Ollama's local HTTP API and is
intentionally dependency-light (only ``requests``).
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

try:
    import requests
except ImportError as e:
    raise SystemExit(
        "Missing dependency 'requests'. "
        "Install it into your environment (e.g. `uv add requests`)."
    ) from e

_DEFAULT_API = "http://localhost:11434"
# Conservative fallback when the model's context length cannot be queried.
_FALLBACK_CTX = 4096


class OllamaClient:
    """Thin wrapper around the Ollama local HTTP API.

    Args:
        model: Ollama model name, e.g. ``qwen2.5-coder:14b``.
        api: Base URL of the Ollama server.
        verbose: If True, log request details to stderr.
    """

    def __init__(
        self,
        model: str,
        api: str = _DEFAULT_API,
        verbose: bool = False,
    ) -> None:
        self.model = model
        self.api = api.rstrip("/")
        self.verbose = verbose
        self._model_ctx: int | None = None

    def model_context_length(self) -> int:
        """Return the model's maximum context length from ``/api/show``.

        The result is cached after the first successful query.
        Falls back to ``_FALLBACK_CTX`` if the model info cannot be retrieved.
        """
        if self._model_ctx is not None:
            return self._model_ctx

        try:
            resp = requests.post(
                f"{self.api}/api/show",
                json={"name": self.model},
                timeout=30,
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            model_info: dict[str, Any] = data.get("model_info", {})
            for key, value in model_info.items():
                if key.endswith(".context_length") and isinstance(value, int):
                    self._model_ctx = value
                    return value
        except Exception:
            pass

        self._model_ctx = _FALLBACK_CTX
        return self._model_ctx

    def chat(
        self,
        user: str,
        system: str = "",
        num_ctx: int = 0,
    ) -> str:
        """Send a chat message and return the full response text.

        Args:
            user: The user-role message.
            system: The system-role message (optional).
            num_ctx: Context window override in tokens. 0 means use model default.

        Returns:
            The model's complete response as a plain string.

        Raises:
            requests.HTTPError: If the Ollama server returns a non-2xx status.
        """
        payload: dict[str, object] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system or ""},
                {"role": "user", "content": user},
            ],
        }
        if num_ctx > 0:
            payload["options"] = {"num_ctx": num_ctx}

        if self.verbose:
            print(f"[OllamaClient] POST {self.api}/api/chat", file=sys.stderr)
            print(json.dumps(payload, indent=2), file=sys.stderr)

        resp = requests.post(
            f"{self.api}/api/chat",
            json=payload,
            stream=True,
            timeout=600,
        )
        resp.raise_for_status()
        return self._collect_response(resp)

    def _collect_response(self, resp: requests.Response) -> str:
        """Assemble streamed response chunks into a single string."""
        parts: list[str] = []

        for raw_line in resp.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            try:
                obj = json.loads(raw_line)
            except json.JSONDecodeError:
                continue

            if not isinstance(obj, dict):
                continue

            if "message" in obj and isinstance(obj["message"], dict):
                # Ollama chat API format
                msg = obj["message"].get("content")
                if isinstance(msg, str):
                    parts.append(msg)
            elif "choices" in obj and obj.get("choices"):
                # OpenAI-compatible format
                choice = obj["choices"][0]
                msg = (choice.get("message") or {}).get("content")
                if isinstance(msg, str):
                    parts.append(msg)
            elif "response" in obj:
                # Ollama generate API format
                parts.append(obj["response"])

            if obj.get("done"):
                break

        return "".join(parts)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: call the Ollama chat API and print the response."""
    parser = argparse.ArgumentParser(
        description="Call Ollama chat API and return response text"
    )
    parser.add_argument(
        "--model", required=True, help="Model name, e.g. qwen2.5-coder:14b"
    )
    parser.add_argument("--system", default="", help="System role prompt")
    parser.add_argument(
        "--system-file",
        default=None,
        help="Path to file containing the system prompt",
    )
    parser.add_argument("--user", default=None, help="User prompt")
    parser.add_argument(
        "--user-file",
        default=None,
        help="Path to file containing the user prompt",
    )
    parser.add_argument(
        "--api",
        default=_DEFAULT_API,
        help="Ollama API URL",
    )
    parser.add_argument(
        "--num-ctx",
        type=int,
        default=0,
        help="Context window size in tokens (0 = model default)",
    )
    parser.add_argument("--verbose", action="store_true", help="Print debug info")
    args = parser.parse_args(argv)

    system_content = args.system
    if args.system_file:
        with open(args.system_file, encoding="utf-8") as f:
            system_content = f.read()

    user_content = args.user
    if args.user_file:
        with open(args.user_file, encoding="utf-8") as f:
            user_content = f.read()

    if user_content is None:
        raise SystemExit("Either --user or --user-file must be provided")

    client = OllamaClient(model=args.model, api=args.api, verbose=args.verbose)
    print(client.chat(user=user_content, system=system_content, num_ctx=args.num_ctx))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
