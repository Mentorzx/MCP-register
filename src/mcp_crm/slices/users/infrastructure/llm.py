from __future__ import annotations

import json
from urllib import error, request

from mcp_crm.slices.users.application.ports import LLMPort
from mcp_crm.slices.users.domain.errors import ConfigurationError
from mcp_crm.slices.users.infrastructure.config import Settings
from mcp_crm.slices.users.infrastructure.logging import get_logger

logger = get_logger(__name__)


class StubLLMClient(LLMPort):
    """Deterministic local stub used in tests and smoke flows."""

    def generate(self, *, system_prompt: str, prompt: str) -> str:
        del system_prompt
        question = _extract_question(prompt)
        matches = _extract_matches(prompt)
        if not matches:
            return f"Stub answer: no CRM matches were found for '{question}'."

        summary = "; ".join(matches[:2])
        return f"Stub answer for '{question}': relevant CRM matches are {summary}."


class OpenAICompatibleLLMClient(LLMPort):
    """Minimal chat-completions client for OpenAI-compatible APIs."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        model: str,
        timeout_seconds: int,
    ) -> None:
        if not api_key:
            raise ConfigurationError(
                "MCP_LLM_API_KEY must be set when MCP_LLM_PROVIDER=openai-compatible"
            )
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds

    def generate(self, *, system_prompt: str, prompt: str) -> str:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
        }
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            self._url,
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with request.urlopen(req, timeout=self._timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            logger.warning(
                "openai-compatible request failed",
                extra={"event": "llm.http_error", "status": exc.code},
            )
            raise RuntimeError(f"LLM request failed with status {exc.code}") from exc
        except error.URLError as exc:
            logger.warning("openai-compatible request failed", extra={"event": "llm.io"})
            raise RuntimeError("LLM request failed") from exc

        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("LLM response payload was invalid") from exc
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("LLM response was empty")
        return content.strip()


def build_llm_client(settings: Settings) -> LLMPort:
    provider = settings.llm_provider.strip().lower()
    if provider in {"", "disabled", "none"}:
        raise ConfigurationError(
            "ask_crm is unavailable because no LLM provider is configured"
        )
    if provider == "stub":
        return StubLLMClient()
    if provider in {"openai", "openai-compatible"}:
        return OpenAICompatibleLLMClient(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    raise ConfigurationError(f"unsupported MCP_LLM_PROVIDER: {settings.llm_provider}")


def _extract_question(prompt: str) -> str:
    for line in prompt.splitlines():
        if line.startswith("Question: "):
            return line.removeprefix("Question: ").strip()
    return "the CRM question"


def _extract_matches(prompt: str) -> list[str]:
    matches: list[str] = []
    for line in prompt.splitlines():
        if line.startswith("- "):
            matches.append(line[2:].strip())
    return matches
