"""remotetable — provider-neutral remote tables (M1 mock + backend stubs)."""

from .api import RemoteTable
from .backends.mock import MockBackend
from .backends.base import Backend

__all__ = ["RemoteTable", "MockBackend", "Backend"]
