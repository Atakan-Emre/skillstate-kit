"""Optional, stateless JSON adapter for compatible chat-completions endpoints."""

from __future__ import annotations

import math
from urllib.parse import urlsplit

from .errors import BudgetExceeded, ValidationError
from .jsonio import dumps, loads


class JSONChatModel:
    """User-configured endpoint; never reads an IDE's session credentials.

    Install the http extra. Each call sends only the supplied context. Endpoint
    compatibility must include messages and response_format=json_object.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout: float = 120,
        *,
        transport=None,
    ):
        parsed = urlsplit(base_url)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise ValidationError("Use an http(s) endpoint without credentials in the URL")
        if not isinstance(model, str) or not model:
            raise ValidationError("A model name is required")
        if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise ValidationError("Model timeout must be positive and finite")
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model, self.api_key, self.timeout, self.transport = model, api_key, timeout, transport

    async def __call__(self, context: dict) -> dict:
        try:
            import httpx
        except ImportError as exc:
            raise ValidationError("Install skillstate-kit[http] for HTTP model access") from exc
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        payload = {
            "model": self.model,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": "Return only the requested JSON object. Do not include reasoning traces.",
                },
                {"role": "user", "content": dumps(context, 1_000_000)},
            ],
        }
        try:
            async with (
                httpx.AsyncClient(
                    timeout=self.timeout,
                    transport=self.transport,
                    trust_env=False,
                    follow_redirects=False,
                ) as client,
                client.stream("POST", self.url, headers=headers, json=payload) as response,
            ):
                if response.status_code != 200:
                    raise ValidationError(f"Model endpoint returned HTTP {response.status_code}")
                chunks, size = [], 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > 1_000_000:
                        raise BudgetExceeded("Model HTTP response exceeds 1000000 bytes")
                    chunks.append(chunk)
        except httpx.HTTPError as exc:
            raise ValidationError(
                f"Model endpoint transport failed ({type(exc).__name__})"
            ) from exc
        try:
            envelope = loads(b"".join(chunks).decode("utf-8"))
            content = envelope["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise ValidationError("Model response content must be JSON text")
            return loads(content, 256_000)
        except (KeyError, IndexError, TypeError, UnicodeError) as exc:
            raise ValidationError("Model endpoint returned an incompatible response") from exc
