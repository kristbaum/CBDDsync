"""Tests for the pure helpers in src.update_queries (no network)."""

import json

import pytest

from src.update_queries import QUERIES, select_queries, simplify_bindings


class TestSimplifyBindings:
    def test_bindings_are_flattened_to_values(self):
        raw = json.dumps(
            {
                "results": {
                    "bindings": [
                        {
                            "item": {
                                "type": "uri",
                                "value": "http://www.wikidata.org/entity/Q1",
                            },
                            "gender": {"type": "uri", "value": "Q6581097"},
                        },
                        {"item": {"type": "uri", "value": "Q2"}},
                    ]
                }
            }
        ).encode()

        assert simplify_bindings(raw) == [
            {"item": "http://www.wikidata.org/entity/Q1", "gender": "Q6581097"},
            {"item": "Q2"},
        ]

    def test_empty_result(self):
        raw = json.dumps({"results": {"bindings": []}}).encode()
        assert simplify_bindings(raw) == []


class TestSelectQueries:
    def test_no_names_selects_all(self):
        assert select_queries([]) == list(QUERIES)

    def test_named_queries_are_kept_in_order(self):
        assert select_queries(["paintings", "entities"]) == ["paintings", "entities"]

    def test_unknown_name_is_rejected(self):
        with pytest.raises(ValueError, match="nope"):
            select_queries(["people", "nope"])


class TestQueries:
    def test_every_query_declares_its_prefixes(self):
        # QLever has no built-in prefix registry.
        for _, query in QUERIES.values():
            assert "PREFIX wdt:" in query

    def test_statement_files_match_the_statement_checks(self):
        from src.config import STATEMENT_CHECKS

        files = {f"sources/{f}" for f, _ in QUERIES.values()}
        for check in STATEMENT_CHECKS.values():
            assert check["wd_query_json"] in files
