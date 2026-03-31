from __future__ import annotations

from mcp_crm.slices.users.application.ports import LLMPort
from mcp_crm.slices.users.application.user_service import UserService
from mcp_crm.slices.users.domain.errors import ValidationError
from mcp_crm.slices.users.domain.user import AskCRMResponse, SearchUserResponse
from mcp_crm.slices.users.infrastructure.config import get_project_config

_CFG = get_project_config()


class CRMAssistantService:
    """Ground CRM answers in semantic search results before calling the LLM."""

    def __init__(
        self,
        user_service: UserService,
        llm: LLMPort,
        *,
        system_prompt: str,
    ) -> None:
        self._user_service = user_service
        self._llm = llm
        self._system_prompt = system_prompt

    def ask(
        self,
        *,
        question: str,
        top_k: int = _CFG.search.default_top_k,
    ) -> AskCRMResponse:
        candidate = question.strip()
        if not candidate:
            raise ValidationError("question must not be empty")

        matches = self._user_service.search_users(
            query=candidate,
            top_k=top_k,
        )
        if not matches:
            return AskCRMResponse(
                question=candidate,
                answer="No matching users were found for this question.",
                matches=[],
            )

        prompt = _build_prompt(candidate, matches)
        answer = self._llm.generate(
            system_prompt=self._system_prompt,
            prompt=prompt,
        ).strip()
        return AskCRMResponse(
            question=candidate,
            answer=answer,
            matches=matches,
        )


def _build_prompt(question: str, matches: list[SearchUserResponse]) -> str:
    lines = [
        f"Question: {question}",
        "",
        "Relevant CRM users:",
    ]
    for match in matches:
        lines.append(
            (
                f"- {match.name} <{match.email}> | "
                f"description={match.description} | score={match.score:.6f}"
            )
        )
    lines.extend(
        [
            "",
            "Answer using only the CRM users listed above.",
            "If the context is insufficient, say that explicitly.",
        ]
    )
    return "\n".join(lines)
