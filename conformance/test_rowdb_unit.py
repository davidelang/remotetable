#!/usr/bin/env python3
"""Offline unit tests for RowDbBackend drivers (mocked HTTP)."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from remotetable.backends import rowdb  # noqa: E402


class FakeHTTP:
    def __init__(self):
        self.calls: list[tuple[str, str, str | None]] = []
        self.handlers = []

    def add(self, method: str, url_substr: str, code: int, body: str):
        self.handlers.append((method, url_substr, code, body))

    def __call__(self, method, url, headers=None, body=None, timeout=60):
        self.calls.append((method, url, body))
        for m, sub, code, resp in self.handlers:
            if method == m and sub in url:
                return code, resp
        return 404, json.dumps({"message": f"no handler for {method} {url}"})


class BaserowUnit(unittest.TestCase):
    def test_list_create_upsert(self):
        fake = FakeHTTP()
        fake.add(
            "GET",
            "table/99",
            200,
            json.dumps(
                {
                    "results": [
                        {"id": 1, "order": "1", "Sync ID": "a", "Name": "Car"},
                    ],
                    "next": "",
                }
            ),
        )
        fake.add("POST", "table/99", 200, json.dumps({"id": 2}))
        fake.add("PATCH", "table/99", 200, "{}")

        with mock.patch.object(rowdb, "_http", side_effect=fake):
            be = rowdb.RowDbBackend(
                "baserow",
                "https://example.test",
                "tok",
                {"Vehicles": "99"},
            )
            conn = be.test_connection()
            self.assertTrue(conn["ok"], conn)
            data = be.read_rows("Vehicles")
            self.assertEqual(data["headers"][0], "Sync ID")
            self.assertEqual(data["rows"][0][0], "a")
            # append new
            w = be.write_rows(
                "Vehicles",
                ["Sync ID", "Name"],
                [["b", "New"]],
                mode="append",
            )
            self.assertEqual(w["written"], 1)
            self.assertTrue(any(c[0] == "POST" for c in fake.calls))
            # upsert existing
            w2 = be.write_rows(
                "Vehicles",
                ["Sync ID", "Name"],
                [["a", "Updated"]],
                mode="append",
            )
            self.assertEqual(w2["written"], 1)
            self.assertTrue(any(c[0] == "PATCH" for c in fake.calls))


if __name__ == "__main__":
    unittest.main()
