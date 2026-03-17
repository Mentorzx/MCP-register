"""Domain and application errors for the users slice."""

from __future__ import annotations


class MCPCRMError(Exception):
    """Base error for the project."""


class ValidationError(MCPCRMError):
    """Raised when input data is invalid."""


class UserNotFoundError(MCPCRMError):
    """Raised when a user cannot be found."""


class DuplicateEmailError(MCPCRMError):
    """Raised when email uniqueness is violated."""


class VectorStoreError(MCPCRMError):
    """Raised for index lifecycle failures."""
