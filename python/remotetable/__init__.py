"""remotetable — provider-neutral remote tables (mock + live backends + CLI)."""

from .api import RemoteTable
from .backends.base import Backend
from .backends.ethercalc import EtherCalcBackend
from .backends.excel_graph import ExcelGraphBackend
from .backends.google_sheets import GoogleSheetsBackend
from .backends.mock import MockBackend
from .ids import BackendIds

__all__ = [
    "RemoteTable",
    "Backend",
    "MockBackend",
    "GoogleSheetsBackend",
    "ExcelGraphBackend",
    "EtherCalcBackend",
    "BackendIds",
]
