from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class User:
    id: int
    name: str
    email: str
    description: str


@dataclass(slots=True, frozen=True)
class SearchResult:
    user: User
    score: float


@dataclass(slots=True, frozen=True)
class UserResponse:
    id: int
    name: str
    email: str
    description: str


@dataclass(slots=True, frozen=True)
class SearchUserResponse:
    id: int
    name: str
    email: str
    description: str
    score: float


@dataclass(slots=True, frozen=True)
class AskCRMResponse:
    question: str
    answer: str
    matches: list[SearchUserResponse]
