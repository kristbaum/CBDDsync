"""Tests for the pure helper functions in src.utils."""

import pytest

from src.utils import (
    extract_bildindex,
    join_list_field,
    map_and_join,
    map_position_to_wd,
    process_verbal_dating,
)


class TestMapPositionToWd:
    def test_empty_position_defaults_to_painting(self):
        assert map_position_to_wd(None) == "Q3305213"
        assert map_position_to_wd({}) == "Q3305213"
        assert map_position_to_wd("") == "Q3305213"

    def test_dict_with_true_flag_maps_to_qid(self):
        assert map_position_to_wd({"ceiling": True, "wall": False}) == "Q1181933"

    def test_string_position_maps_to_qid(self):
        assert map_position_to_wd("wall") == "Q3305213"

    def test_position_lookup_is_case_insensitive(self):
        assert map_position_to_wd("  Ceiling  ") == "Q1181933"

    def test_list_position_maps_first_entry(self):
        assert map_position_to_wd(["equipment"]) == "Q3305213"


class TestJoinListField:
    def test_none_becomes_empty_string(self):
        assert join_list_field(None) == ""

    def test_list_is_semicolon_joined(self):
        assert join_list_field(["11H", "31A"]) == "11H;31A"

    def test_empty_list_is_empty_string(self):
        assert join_list_field([]) == ""

    def test_scalar_is_stringified(self):
        assert join_list_field(42) == "42"
        assert join_list_field("11H") == "11H"


MATERIAL_MAPPING = {
    "OIL_PAINT_PAINT": "Q296955",
    "PLASTER_COMPOSITE_COATING": "Q572879",
}


class TestMapAndJoin:
    def test_falsy_input_is_empty_string(self):
        assert map_and_join(None, MATERIAL_MAPPING) == ""
        assert map_and_join([], MATERIAL_MAPPING) == ""

    def test_single_string_is_treated_as_one_item(self):
        assert map_and_join("OIL_PAINT_PAINT", MATERIAL_MAPPING) == "Q296955"

    def test_list_is_mapped_and_joined(self):
        result = map_and_join(
            ["OIL_PAINT_PAINT", "PLASTER_COMPOSITE_COATING"], MATERIAL_MAPPING
        )
        assert result == "Q296955;Q572879"

    def test_unmapped_values_are_dropped(self):
        assert map_and_join(["UNKNOWN_MATERIAL"], MATERIAL_MAPPING) == ""
        assert (
            map_and_join(["UNKNOWN", "OIL_PAINT_PAINT"], MATERIAL_MAPPING) == "Q296955"
        )


class TestExtractBildindex:
    def test_missing_or_non_dict_is_empty_string(self):
        assert extract_bildindex(None) == ""
        assert extract_bildindex("obj123") == ""
        assert extract_bildindex({}) == ""
        assert extract_bildindex({"bildindex": ""}) == ""

    def test_obj_prefix_is_stripped(self):
        assert extract_bildindex({"bildindex": "obj23829038"}) == "23829038"

    def test_part_suffix_is_ignored(self):
        assert extract_bildindex({"bildindex": "obj23829038?part=3"}) == "23829038"

    def test_obj_prefix_match_is_case_insensitive(self):
        assert extract_bildindex({"bildindex": "OBJ23829038"}) == "23829038"

    def test_falls_back_to_first_digit_run(self):
        assert extract_bildindex({"bildindex": "12345?part=3"}) == "12345"

    def test_value_without_digits_is_empty_string(self):
        assert extract_bildindex({"bildindex": "no-digits-here"}) == ""


class TestProcessVerbalDating:
    def test_none_is_empty_string(self):
        assert process_verbal_dating(None) == ""

    def test_exact_year_passes_through(self):
        assert process_verbal_dating("1820") == "1820"

    def test_surrounding_whitespace_is_stripped(self):
        assert process_verbal_dating("  1820  ") == "1820"

    @pytest.mark.parametrize(
        "value", ["ca. 1820", "ca 1820", "c. 1820", "circa 1820", "um 1820", "UM 1820"]
    )
    def test_approximate_forms_yield_the_year(self, value):
        assert process_verbal_dating(value) == "1820"

    @pytest.mark.parametrize(
        "value", ["18. Jahrhundert", "1820-1830", "182", "before 1820", ""]
    )
    def test_unparseable_forms_are_empty_string(self, value):
        assert process_verbal_dating(value) == ""
