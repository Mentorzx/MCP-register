"""User entities for the users slice."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class User:
    """Persisted user model."""

    id: int
    name: str
    email: str
    description: str


@dataclass(slots=True, frozen=True)
class SearchResult:
    """User plus semantic similarity score."""

    user: User
    score: float
