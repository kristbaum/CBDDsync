"""Tests for the entity comparison logic in src.entity_check."""

import csv

import pytest

from src.config import COLUMNS_EXISTING, COLUMNS_MISSING
from src.entity_check import (
    build_internal_to_q,
    filter_existing,
    filter_missing,
    find_building_for_painting,
    load_query_ids,
    write_csv,
)


def index_relations(relations):
    """Build the (by_source, by_target) indexes entity_check.main() constructs."""
    by_source: dict[str, list[dict]] = {}
    by_target: dict[str, list[dict]] = {}
    for r in relations:
        by_source.setdefault(r["ID"], []).append(r)
        by_target.setdefault(r["relTar"], []).append(r)
    return by_source, by_target


def part_relation(parent_id, child_id):
    return {"ID": parent_id, "relTar": child_id, "relDir": "->", "sType": "PART"}


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.reader(f))


@pytest.fixture
def sources(tmp_path, monkeypatch):
    """A tmp_path cwd with a sources/ directory, as the loaders expect."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "sources").mkdir()
    return tmp_path / "sources"


class TestLoadQueryIds:
    def test_internal_ids_are_collected(self, sources):
        (sources / "query.csv").write_text(
            "item,deckenmalerei_eu_ID\n"
            "http://www.wikidata.org/entity/Q1,ENT-1\n"
            "http://www.wikidata.org/entity/Q2,ENT-2\n",
            encoding="utf-8",
        )
        assert load_query_ids() == {"ENT-1", "ENT-2"}

    def test_rows_without_an_internal_id_are_skipped(self, sources):
        (sources / "query.csv").write_text(
            "item,deckenmalerei_eu_ID\nhttp://www.wikidata.org/entity/Q1,\n",
            encoding="utf-8",
        )
        assert load_query_ids() == set()


class TestBuildInternalToQ:
    def test_entity_urls_are_reduced_to_qids(self, sources):
        (sources / "query.csv").write_text(
            "item,deckenmalerei_eu_ID\nhttp://www.wikidata.org/entity/Q1,ENT-1\n",
            encoding="utf-8",
        )
        assert build_internal_to_q() == {"ENT-1": "Q1"}

    def test_incomplete_rows_are_skipped(self, sources):
        (sources / "query.csv").write_text(
            "item,deckenmalerei_eu_ID\n,ENT-1\nhttp://www.wikidata.org/entity/Q2,\n",
            encoding="utf-8",
        )
        assert build_internal_to_q() == {}


ENTITIES = [
    {"ID": "P-1", "sType": "OBJECT_PAINTING"},
    {"ID": "P-2", "sType": "OBJECT_PAINTING"},
    {"ID": "B-1", "sType": "OBJECT_BUILDING"},
]


class TestFilterEntities:
    def test_missing_are_those_absent_from_the_query(self):
        result = filter_missing(ENTITIES, {"P-1"}, "OBJECT_PAINTING")
        assert [e["ID"] for e in result] == ["P-2"]

    def test_existing_are_those_present_in_the_query(self):
        result = filter_existing(ENTITIES, {"P-1"}, "OBJECT_PAINTING")
        assert [e["ID"] for e in result] == ["P-1"]

    def test_other_entity_types_are_excluded(self):
        assert filter_missing(ENTITIES, set(), "OBJECT_BUILDING") == [
            {"ID": "B-1", "sType": "OBJECT_BUILDING"}
        ]


class TestFindBuildingForPainting:
    def test_direct_parent_building_is_found(self):
        entities = {"B-1": {"ID": "B-1", "sType": "OBJECT_BUILDING"}}
        by_source, by_target = index_relations([part_relation("B-1", "P-1")])
        building = find_building_for_painting("P-1", entities, by_source, by_target)
        assert building is not None
        assert building["ID"] == "B-1"

    def test_hierarchy_is_walked_upwards(self):
        entities = {
            "R-1": {"ID": "R-1", "sType": "OBJECT_ROOM"},
            "RS-1": {"ID": "RS-1", "sType": "OBJECT_ROOM_SEQUENCE"},
            "B-1": {"ID": "B-1", "sType": "OBJECT_BUILDING"},
        }
        by_source, by_target = index_relations(
            [
                part_relation("R-1", "P-1"),
                part_relation("RS-1", "R-1"),
                part_relation("B-1", "RS-1"),
            ]
        )
        building = find_building_for_painting("P-1", entities, by_source, by_target)
        assert building is not None
        assert building["ID"] == "B-1"

    def test_returns_none_when_no_building_is_reachable(self):
        entities = {"R-1": {"ID": "R-1", "sType": "OBJECT_ROOM"}}
        by_source, by_target = index_relations([part_relation("R-1", "P-1")])
        assert find_building_for_painting("P-1", entities, by_source, by_target) is None

    def test_returns_none_without_relations(self):
        assert find_building_for_painting("P-1", {}, {}, {}) is None

    def test_non_part_relations_are_ignored(self):
        entities = {"B-1": {"ID": "B-1", "sType": "OBJECT_BUILDING"}}
        rel = part_relation("B-1", "P-1") | {"sType": "PAINTERS"}
        by_source, by_target = index_relations([rel])
        assert find_building_for_painting("P-1", entities, by_source, by_target) is None

    def test_relation_cycle_does_not_recurse_forever(self):
        entities = {
            "R-1": {"ID": "R-1", "sType": "OBJECT_ROOM"},
            "R-2": {"ID": "R-2", "sType": "OBJECT_ROOM"},
        }
        by_source, by_target = index_relations(
            [
                part_relation("R-1", "P-1"),
                part_relation("R-2", "R-1"),
                part_relation("R-1", "R-2"),
            ]
        )
        assert find_building_for_painting("P-1", entities, by_source, by_target) is None


class TestWriteCsv:
    def test_person_row_uses_the_configured_columns(self, tmp_path):
        out = tmp_path / "people.csv"
        entities = [
            {
                "ID": "A-1",
                "appellation": "Cosmas Damian Asam",
                "gender": "MALE",
                "normdata": {"gnd": "118504118"},
            }
        ]

        write_csv("ACTOR_PERSON", entities, str(out), COLUMNS_MISSING)

        assert read_csv(out) == [
            ["url", "appellation", "gender", "gnd", "ID"],
            [
                "https://www.deckenmalerei.eu/A-1",
                "Cosmas Damian Asam",
                "MALE",
                "118504118",
                "A-1",
            ],
        ]

    def test_person_without_normdata_gets_an_empty_gnd(self, tmp_path):
        out = tmp_path / "people.csv"
        entities = [{"ID": "A-1", "appellation": "Asam", "gender": "MALE"}]

        write_csv("ACTOR_PERSON", entities, str(out), COLUMNS_MISSING)

        header, row = read_csv(out)
        assert row[header.index("gnd")] == ""

    def test_header_is_written_for_an_empty_entity_list(self, tmp_path):
        out = tmp_path / "people.csv"
        write_csv("ACTOR_PERSON", [], str(out), COLUMNS_MISSING)
        assert read_csv(out) == [["url", "appellation", "gender", "gnd", "ID"]]

    def test_wikidata_qid_column_is_filled_from_the_mapping(self, tmp_path):
        out = tmp_path / "people.csv"
        entities = [{"ID": "A-1", "appellation": "Asam", "gender": "MALE"}]

        write_csv(
            "ACTOR_PERSON",
            entities,
            str(out),
            COLUMNS_EXISTING,
            internal_to_q={"A-1": "Q57169"},
        )

        header, row = read_csv(out)
        assert row[header.index("wikidata_qid")] == "Q57169"

    def test_building_row_gets_dating_and_wikishootme_link(self, tmp_path):
        out = tmp_path / "buildings.csv"
        entities = [
            {
                "ID": "B-1",
                "appellation": "Schloss",
                "verbaleDating": "ca. 1720",
                "locationLat": "48.2482",
                "locationLng": "11.5679",
            }
        ]

        write_csv("OBJECT_BUILDING", entities, str(out), COLUMNS_MISSING)

        header, row = read_csv(out)
        assert row[header.index("processedDating")] == "1720"
        assert row[header.index("wikishootme")] == (
            "https://wikishootme.toolforge.org/#lat=48.2482&lng=11.5679&zoom=18"
        )

    def test_painting_row_maps_every_derived_field(self, tmp_path):
        out = tmp_path / "paintings.csv"
        entities = [
            {
                "ID": "P-1",
                "sType": "OBJECT_PAINTING",
                "appellation": "Deckenfresko",
                "verbaleDating": "1720",
                "iconography": ["11H", "31A"],
                "productionMethods": ["FRESCO_PAINTING_TECHNIQUE"],
                "productionMaterials": ["PLASTER_COMPOSITE_COATING"],
                "position": {"ceiling": True},
                "normdata": {"bildindex": "obj23829038?part=3"},
                "dimension": {"width": 120, "height": 80},
                "condition": {"restored": True, "destroyed": False},
            }
        ]
        by_source, by_target = index_relations(
            [
                part_relation("B-1", "P-1"),
                {
                    "ID": "P-1",
                    "relTar": "A-1",
                    "relDir": "->",
                    "sType": "PAINTERS",
                },
                {
                    "ID": "P-1",
                    "relTar": "A-2",
                    "relDir": "->",
                    "sType": "COMMISSIONERS",
                },
            ]
        )
        entities_by_id = {
            "B-1": {"ID": "B-1", "sType": "OBJECT_BUILDING", "appellation": "Schloss"}
        }
        internal_to_q = {"A-1": "Q57169", "A-2": "Q99", "B-1": "Q12345"}

        write_csv(
            "OBJECT_PAINTING",
            entities,
            str(out),
            COLUMNS_MISSING,
            relations_by_source=by_source,
            relations_by_target=by_target,
            internal_to_q=internal_to_q,
            entities_by_id=entities_by_id,
        )

        header, row = read_csv(out)
        cell = dict(zip(header, row, strict=True))
        assert cell["processedDating"] == "1720"
        assert cell["iconography"] == "11H;31A"
        assert cell["productionMethods_wd"] == "Q134194"
        assert cell["productionMaterials_wd"] == "Q572879"
        assert cell["position"] == "Q1181933"
        assert cell["normdata"] == "23829038"
        assert cell["painter"] == "Q57169"
        assert cell["commissioner"] == "Q99"
        assert cell["width"] == "120"
        assert cell["height"] == "80"
        assert cell["length"] == ""
        assert cell["description_en"] == "painting in Schloss"
        assert cell["description_de"] == "Malerei in Schloss"
        assert cell["location"] == "Q12345"
        assert cell["condition"] == "Q75505084"

    def test_painting_without_a_building_gets_empty_derived_fields(self, tmp_path):
        out = tmp_path / "paintings.csv"
        entities = [{"ID": "P-1", "sType": "OBJECT_PAINTING", "appellation": "Fresko"}]

        write_csv("OBJECT_PAINTING", entities, str(out), COLUMNS_MISSING)

        header, row = read_csv(out)
        cell = dict(zip(header, row, strict=True))
        assert cell["description_en"] == ""
        assert cell["description_de"] == ""
        assert cell["location"] == ""
