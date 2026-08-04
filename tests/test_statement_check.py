"""Tests for the generic statement-comparison engine in src.statement_check."""

import csv
import json

import pytest

from src.statement_check import (
    build_potential_statements,
    compute_missing,
    extract_qid,
    format_qs_value,
    normalize_coordinate,
    normalize_for_comparison,
    run_statement_check,
    unify_wikidata_results,
    write_quickstatements_csv,
)


def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    return str(path)


class TestExtractQid:
    def test_entity_url_yields_qid(self):
        assert extract_qid("http://www.wikidata.org/entity/Q12345") == "Q12345"

    def test_empty_url_yields_empty_string(self):
        assert extract_qid("") == ""

    def test_bare_qid_passes_through(self):
        assert extract_qid("Q12345") == "Q12345"


class TestFormatQsValue:
    def test_descriptions_stay_plain(self):
        assert format_qs_value("Den", "painting in Schloss Schleissheim") == (
            "painting in Schloss Schleissheim"
        )

    def test_qid_values_pass_through(self):
        assert format_qs_value("P170", "Q42") == "Q42"

    def test_coordinates_get_at_prefix(self):
        assert format_qs_value("P625", "48.2482/11.5679") == "@48.2482/11.5679"

    def test_four_digit_year_gets_year_precision(self):
        assert format_qs_value("P571", "1720") == "+1720-00-00T00:00:00Z/9"

    def test_full_date_gets_day_precision(self):
        assert format_qs_value("P571", "1720-05-01") == "+1720-05-01T00:00:00Z/11"

    def test_dimensions_get_centimetre_unit(self):
        assert format_qs_value("P2049", "120.5") == "120.5U174728"

    def test_non_numeric_dimension_is_left_alone(self):
        assert format_qs_value("P2049", "unknown") == "unknown"

    def test_configured_string_properties_are_quoted(self):
        assert format_qs_value("P281", "85764") == '"85764"'

    def test_unconfigured_property_is_left_alone(self):
        assert format_qs_value("P1257", "11H") == "11H"


class TestNormalizeCoordinate:
    def test_wkt_point_is_reordered_to_lat_lng(self):
        assert normalize_coordinate("Point(11.5679 48.2482)") == "48.2482,11.5679"

    def test_uppercase_wkt_point_from_qlever_is_supported(self):
        assert normalize_coordinate("POINT(11.5679 48.2482)") == "48.2482,11.5679"

    def test_internal_slash_form_is_converted(self):
        assert normalize_coordinate("48.2482/11.5679") == "48.2482,11.5679"

    def test_values_are_rounded_to_four_decimals(self):
        assert normalize_coordinate("48.24821999/11.56789999") == "48.2482,11.5679"

    def test_wkt_and_slash_forms_compare_equal(self):
        assert normalize_coordinate("Point(11.56789 48.24821)") == normalize_coordinate(
            "48.248213/11.567891"
        )

    def test_unparseable_value_is_returned_unchanged(self):
        assert normalize_coordinate("somewhere") == "somewhere"
        assert normalize_coordinate("Point(a b)") == "Point(a b)"


class TestNormalizeForComparison:
    def test_quotes_are_stripped(self):
        assert normalize_for_comparison("P281", '"85764"') == "85764"

    def test_dates_are_reduced_to_the_year(self):
        assert normalize_for_comparison("P571", "+1720-00-00T00:00:00Z") == "1720"
        assert normalize_for_comparison("P571", "1720-05-01") == "1720"
        assert normalize_for_comparison("P571", "1720") == "1720"

    def test_coordinates_are_normalized(self):
        assert normalize_for_comparison("P625", "Point(11.5679 48.2482)") == (
            "48.2482,11.5679"
        )

    def test_other_values_pass_through(self):
        assert normalize_for_comparison("P170", "Q42") == "Q42"


KEY_TO_PID = {"inception": "P571", "painter": "P170"}


class TestUnifyWikidataResults:
    def test_rows_are_grouped_by_item_and_merged_into_sets(self):
        data = [
            {
                "item": "http://www.wikidata.org/entity/Q1",
                "painter": "http://www.wikidata.org/entity/Q42",
            },
            {
                "item": "http://www.wikidata.org/entity/Q1",
                "painter": "http://www.wikidata.org/entity/Q43",
            },
        ]
        assert unify_wikidata_results(data, KEY_TO_PID) == {
            "Q1": {"P170": {"Q42", "Q43"}}
        }

    def test_rows_without_an_item_are_skipped(self):
        assert unify_wikidata_results([{"inception": "1720"}], KEY_TO_PID) == {}

    def test_empty_values_are_skipped_but_the_item_is_kept(self):
        data = [{"item": "http://www.wikidata.org/entity/Q1", "inception": ""}]
        assert unify_wikidata_results(data, KEY_TO_PID) == {"Q1": {}}

    def test_date_time_suffix_is_stripped(self):
        data = [
            {
                "item": "http://www.wikidata.org/entity/Q1",
                "inception": "1720-01-01T00:00:00Z",
            }
        ]
        assert unify_wikidata_results(data, KEY_TO_PID) == {
            "Q1": {"P571": {"1720-01-01"}}
        }

    def test_labels_are_collected_alongside_statements(self):
        data = [
            {
                "item": "http://www.wikidata.org/entity/Q1",
                "itemLabel_de": "Deckenfresko",
                "itemLabel_en": "ceiling fresco",
            }
        ]
        assert unify_wikidata_results(data, KEY_TO_PID) == {
            "Q1": {
                "itemLabel_de": {"Deckenfresko"},
                "itemLabel_en": {"ceiling fresco"},
            }
        }


class TestBuildPotentialStatements:
    def test_columns_are_mapped_to_property_ids(self, tmp_path):
        path = write_csv(
            tmp_path / "existing.csv",
            ["wikidata_qid", "processedDating"],
            [["Q1", "1720"]],
        )
        check = {"column_to_pid": {"processedDating": "P571"}}
        assert build_potential_statements(path, check) == {"Q1": {"P571": {"1720"}}}

    def test_rows_without_a_qid_are_skipped(self, tmp_path):
        path = write_csv(
            tmp_path / "existing.csv",
            ["wikidata_qid", "processedDating"],
            [["", "1720"], ["  ", "1730"]],
        )
        check = {"column_to_pid": {"processedDating": "P571"}}
        assert build_potential_statements(path, check) == {}

    def test_semicolon_cells_become_multiple_values(self, tmp_path):
        path = write_csv(
            tmp_path / "existing.csv", ["wikidata_qid", "painter"], [["Q1", "Q42;Q43"]]
        )
        check = {"column_to_pid": {"painter": "P170"}}
        assert build_potential_statements(path, check) == {
            "Q1": {"P170": {"Q42", "Q43"}}
        }

    def test_empty_cells_produce_no_statement(self, tmp_path):
        path = write_csv(
            tmp_path / "existing.csv",
            ["wikidata_qid", "processedDating"],
            [["Q1", ""]],
        )
        check = {"column_to_pid": {"processedDating": "P571"}}
        assert build_potential_statements(path, check) == {"Q1": {}}

    def test_value_maps_translate_raw_values(self, tmp_path):
        path = write_csv(
            tmp_path / "existing.csv", ["wikidata_qid", "gender"], [["Q1", "MALE"]]
        )
        check = {
            "column_to_pid": {"gender": "P21"},
            "value_maps": {"P21": {"MALE": "Q6581097"}},
        }
        assert build_potential_statements(path, check) == {"Q1": {"P21": {"Q6581097"}}}

    def test_unmappable_values_are_skipped(self, tmp_path):
        path = write_csv(
            tmp_path / "existing.csv", ["wikidata_qid", "gender"], [["Q1", "OTHER"]]
        )
        check = {
            "column_to_pid": {"gender": "P21"},
            "value_maps": {"P21": {"MALE": "Q6581097"}},
        }
        assert build_potential_statements(path, check) == {"Q1": {}}

    def test_coordinate_columns_are_combined(self, tmp_path):
        path = write_csv(
            tmp_path / "existing.csv",
            ["wikidata_qid", "locationLat", "locationLng"],
            [["Q1", "48.2482", "11.5679"]],
        )
        check = {
            "column_to_pid": {},
            "coordinate": {"pid": "P625", "lat": "locationLat", "lng": "locationLng"},
        }
        assert build_potential_statements(path, check) == {
            "Q1": {"P625": {"48.2482/11.5679"}}
        }

    def test_partial_coordinate_is_skipped(self, tmp_path):
        path = write_csv(
            tmp_path / "existing.csv",
            ["wikidata_qid", "locationLat", "locationLng"],
            [["Q1", "48.2482", ""]],
        )
        check = {
            "column_to_pid": {},
            "coordinate": {"pid": "P625", "lat": "locationLat", "lng": "locationLng"},
        }
        assert build_potential_statements(path, check) == {"Q1": {}}


class TestComputeMissing:
    def test_statement_already_in_wikidata_is_not_reported(self):
        potential = {"Q1": {"P571": {"1720"}}}
        existing = {"Q1": {"P571": {"1720-01-01"}}}
        assert compute_missing(potential, existing) == {}

    def test_statement_absent_from_wikidata_is_reported(self):
        potential = {"Q1": {"P571": {"1720"}}}
        assert compute_missing(potential, {}) == {"Q1": {"P571": ["1720"]}}

    def test_only_the_absent_value_of_a_property_is_reported(self):
        potential = {"Q1": {"P170": {"Q42", "Q43"}}}
        existing = {"Q1": {"P170": {"Q42"}}}
        assert compute_missing(potential, existing) == {"Q1": {"P170": ["Q43"]}}

    def test_comparison_is_normalized_for_coordinates(self):
        potential = {"Q1": {"P625": {"48.248213/11.567891"}}}
        existing = {"Q1": {"P625": {"Point(11.56789 48.24821)"}}}
        assert compute_missing(potential, existing) == {}

    def test_other_items_statements_do_not_mask_a_gap(self):
        potential = {"Q1": {"P571": {"1720"}}}
        existing = {"Q2": {"P571": {"1720"}}}
        assert compute_missing(potential, existing) == {"Q1": {"P571": ["1720"]}}


class TestWriteQuickstatementsCsv:
    def test_one_row_per_statement_with_qid_first(self, tmp_path):
        out = tmp_path / "out.csv"
        missing = {"Q1": {"P571": ["1720"], "P170": ["Q42"]}}

        total = write_quickstatements_csv(missing, str(out))

        assert total == 2
        rows = list(csv.reader(out.open(encoding="utf-8")))
        assert rows[0] == ["qid", "P170", "P571"]
        assert rows[1] == ["Q1", "Q42", ""]
        assert rows[2] == ["Q1", "", "+1720-00-00T00:00:00Z/9"]

    def test_header_only_when_nothing_is_missing(self, tmp_path):
        out = tmp_path / "out.csv"

        assert write_quickstatements_csv({}, str(out)) == 0

        assert list(csv.reader(out.open(encoding="utf-8"))) == [["qid"]]

    def test_items_are_written_in_sorted_order(self, tmp_path):
        out = tmp_path / "out.csv"
        missing = {"Q2": {"P571": ["1730"]}, "Q1": {"P571": ["1720"]}}

        assert write_quickstatements_csv(missing, str(out)) == 2

        rows = list(csv.reader(out.open(encoding="utf-8")))
        assert [r[0] for r in rows[1:]] == ["Q1", "Q2"]


class TestRunStatementCheck:
    @pytest.fixture
    def check(self, tmp_path, monkeypatch):
        """A minimal buildings-style check wired up inside tmp_path."""
        monkeypatch.chdir(tmp_path)
        write_csv(
            tmp_path / "existing.csv",
            ["wikidata_qid", "processedDating", "addressZip"],
            [["Q1", "1720", "85764"], ["Q2", "1730", "80333"]],
        )
        wd = tmp_path / "wd.json"
        wd.write_text(
            json.dumps(
                [
                    {
                        "item": "http://www.wikidata.org/entity/Q1",
                        "inception": "1720-01-01T00:00:00Z",
                    }
                ]
            ),
            encoding="utf-8",
        )
        return {
            "existing_csv": "existing.csv",
            "wd_query_json": "wd.json",
            "output_csv": "missing/out.csv",
            "column_to_pid": {"processedDating": "P571", "addressZip": "P281"},
            "wd_query_key_to_pid": {"inception": "P571", "postalCode": "P281"},
        }

    def test_returns_stats_and_writes_only_missing_statements(self, check, tmp_path):
        stats = run_statement_check("buildings", check)

        assert stats == {
            "label": "buildings",
            "potential": 4,
            "existing": 1,
            "missing": 3,
        }
        rows = list(csv.reader((tmp_path / "missing" / "out.csv").open()))
        assert rows[0] == ["qid", "P281", "P571"]
        # Q1's inception is already in Wikidata, so only its postal code is missing.
        assert rows[1:] == [
            ["Q1", '"85764"', ""],
            ["Q2", '"80333"', ""],
            ["Q2", "", "+1730-00-00T00:00:00Z/9"],
        ]

    def test_output_directory_is_created(self, check, tmp_path):
        run_statement_check("buildings", check)
        assert (tmp_path / "missing").is_dir()

    def test_missing_input_file_skips_the_check(self, check):
        check["wd_query_json"] = "does_not_exist.json"
        assert run_statement_check("buildings", check) is None

    def test_labels_are_excluded_from_the_existing_statement_count(
        self, check, tmp_path
    ):
        (tmp_path / "wd.json").write_text(
            json.dumps(
                [
                    {
                        "item": "http://www.wikidata.org/entity/Q1",
                        "inception": "1720-01-01T00:00:00Z",
                        "itemLabel_de": "Schloss",
                        "itemLabel_en": "palace",
                    }
                ]
            ),
            encoding="utf-8",
        )
        stats = run_statement_check("buildings", check)
        assert stats is not None
        assert stats["existing"] == 1
