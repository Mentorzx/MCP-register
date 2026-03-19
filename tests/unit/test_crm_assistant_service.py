from __future__ import annotations

import pytest

from mcp_crm.slices.users.domain.errors import ValidationError
from tests.support import build_assistant_service, build_service


@pytest.fixture()
def assistant(tmp_path):
    return build_assistant_service(tmp_path)


class TestAskCRM:
    def test_returns_grounded_answer(self, tmp_path):
        service = build_service(tmp_path)
        assistant = build_assistant_service(tmp_path)

        service.create_user(
            name="Ana",
            email="ana@test.com",
            description="cliente premium interessada em investimentos",
        )

        response = assistant.ask(
            question="Quem parece mais interessado em investimentos?",
            top_k=1,
        )

        assert response.question == "Quem parece mais interessado em investimentos?"
        assert "Ana" in response.answer
        assert len(response.matches) == 1
        assert response.matches[0].name == "Ana"

    def test_returns_fixed_answer_when_there_are_no_matches(self, assistant):
        response = assistant.ask(question="Quem parece um lead premium?", top_k=1)

        assert response.answer == "No matching users were found for this question."
        assert response.matches == []

    def test_rejects_empty_question(self, assistant):
        with pytest.raises(ValidationError):
            assistant.ask(question="  ", top_k=1)
