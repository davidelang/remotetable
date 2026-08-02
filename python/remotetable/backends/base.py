from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, List, Sequence


class Backend(ABC):
    backend_id: str

    @abstractmethod
    def test_connection(self) -> dict[str, Any]:
        ...

    @abstractmethod
    def list_tabs(self) -> List[str]:
        ...

    @abstractmethod
    def ensure_headers(self, tab: str, headers: List[str]) -> dict[str, Any]:
        ...

    @abstractmethod
    def read_rows(self, tab: str) -> dict[str, Any]:
        ...

    @abstractmethod
    def write_rows(
        self,
        tab: str,
        headers: List[str],
        rows: List[List[str]],
        mode: str = "append",
    ) -> dict[str, Any]:
        ...
