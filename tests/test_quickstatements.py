"""Tests for the QuickStatements V1 rendering in src.quickstatements."""

import pytest

from src.quickstatements import qs_line, qs_string, write_qs_file


class TestQsString:
    def test_value_is_quoted(self):
        assert qs_string("85764") == '"85764"'

    def test_whitespace_runs_are_collapsed(self):
        assert qs_string(" Malerei\tin\nMünchen ") == '"Malerei in München"'

    def test_embedded_double_quotes_are_replaced(self):
        assert qs_string('Saal "Kaiser"') == "\"Saal 'Kaiser'\""


class TestQsLine:
    def test_plain_statement_is_tab_separated(self):
        assert qs_line("Q1", "P170", "Q42") == "Q1\tP170\tQ42"

    def test_qualifiers_follow_the_value(self):
        line = qs_line("LAST", "P710", "Q42", qualifiers=[("P1545", '"1"')])
        assert line == 'LAST\tP710\tQ42\tP1545\t"1"'

    def test_references_are_written_as_source_properties(self):
        line = qs_line(
            "Q1", "P571", "+1720-00-00T00:00:00Z/9", references=[("P248", "Q7")]
        )
        assert line == "Q1\tP571\t+1720-00-00T00:00:00Z/9\tS248\tQ7"

    @pytest.mark.parametrize("prefix", ["+", "-"])
    def test_prefix_is_put_before_the_entity(self, prefix):
        assert qs_line("Q1", "P710", "somevalue", prefix=prefix) == (
            f"{prefix}Q1\tP710\tsomevalue"
        )

    def test_unknown_prefix_is_rejected(self):
        with pytest.raises(ValueError):
            qs_line("Q1", "P170", "Q42", prefix="*")


class TestWriteQsFile:
    def test_one_command_per_line(self, tmp_path):
        out = tmp_path / "out.qs"

        assert write_qs_file(["Q1\tP170\tQ42", "Q2\tP170\tQ43"], str(out)) == 2

        assert out.read_text(encoding="utf-8") == "Q1\tP170\tQ42\nQ2\tP170\tQ43\n"

    def test_empty_batch_writes_an_empty_file(self, tmp_path):
        out = tmp_path / "out.qs"
        assert write_qs_file([], str(out)) == 0
        assert out.read_text(encoding="utf-8") == ""
