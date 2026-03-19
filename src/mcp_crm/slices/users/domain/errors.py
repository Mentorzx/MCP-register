from __future__ import annotations


class MCPCRMError(Exception):
    pass


class ValidationError(MCPCRMError):
    pass


class UserNotFoundError(MCPCRMError):
    pass


class DuplicateEmailError(MCPCRMError):
    pass


class VectorStoreError(MCPCRMError):
    pass


class ConfigurationError(MCPCRMError):
    pass
