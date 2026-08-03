"""remotetable — provider-neutral remote tables (mock + live backends + CLI)."""

from .api import RemoteTable
from .backends.base import Backend
from .backends.ethercalc import EtherCalcBackend
from .backends.excel_graph import ExcelGraphBackend
from .backends.google_sheets import GoogleSheetsBackend
from .backends.mock import MockBackend
from .backends.rowdb import RowDbBackend
from .backends.zoho_sheet import ZohoSheetBackend
from .ids import BackendIds

__all__ = [
    "RemoteTable",
    "Backend",
    "MockBackend",
    "GoogleSheetsBackend",
    "ExcelGraphBackend",
    "EtherCalcBackend",
    "RowDbBackend",
    "ZohoSheetBackend",
    "BackendIds",
]
