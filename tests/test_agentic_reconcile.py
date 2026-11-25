"""Pure logic of the agentic-reconcile skill scripts (no network, no sources/)."""

import sys
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "agentic-reconcile" / "scripts")
)

import cbdd_hints
import cbdd_ingest

UUID_P = "11111111-1111-4111-8111-111111111111"
UUID_W = "22222222-2222-4222-8222-222222222222"
UUID_B = "33333333-3333-4333-8333-333333333333"


def item(**props):
    base = {"label": "", **{p: [] for p in cbdd_hints.PROPS}}
    base.update(props)
    return base


# --- names -------------------------------------------------------------------


def test_variants_natural_order_and_swaps():
    v = cbdd_ingest.variants("Reiser, Joseph Anton")
    assert v[0] == "Joseph Anton Reiser"
    assert "Joseph Reiser" in v
    assert "Josef Anton Reiser" in v


def test_variants_particle_and_title():
    assert (
        cbdd_ingest.variants("Mengersen, Franz Josef von")[0]
        == "Franz Josef von Mengersen"
    )
    v = cbdd_ingest.variants("Baden-Durlach, Albertina Friederike, Markgräfin")
    assert "Albertina Friederike von Baden-Durlach" in v


def test_variants_drop_dates_and_life_in_name():
    assert cbdd_ingest.variants("Kopp, Gottfried (1652–1723)") == ["Gottfried Kopp"]
    assert cbdd_ingest.life_in_name(["Kopp, Gottfried (1652–1723)"]) == (1652, 1723)
    assert cbdd_ingest.life_in_name(["Kopp, Gottfried"]) == (None, None)


# --- ingest file ---------------------------------------------------------------


def fake_dump():
    entities = {
        UUID_P: {
            "ID": UUID_P,
            "sType": "ACTOR_PERSON",
            "appellation": "Reiser, Joseph Anton (1757–1805)",
            "gender": "MALE",
            "normdata": {"gnd": "118599283"},
        },
        UUID_W: {
            "ID": UUID_W,
            "sType": "OBJECT_PAINTING",
            "appellation": "Deckenbild",
            "verbaleDating": "1780",
        },
        UUID_B: {
            "ID": UUID_B,
            "sType": "OBJECT_BUILDING",
            "appellation": "Bad Buchau, Stiftskirche",
            "addressLocality": "Bad Buchau",
            "addressStreet": "Schlossplatz 1",
            "locationLat": "48.06",
            "locationLng": "9.61",
            "verbaleDating": "1773",
            "addressZip": "88422",
            "functions": ["CHURCHES_BUILDINGS"],
            "normdata": {"gnd": "not-a-gnd", "bildindex": "obj20012345"},
        },
    }
    incoming = {
        UUID_P: [{"ID": UUID_W, "relTar": UUID_P, "sType": "PAINTERS", "relDir": "->"}]
    }
    parent = {UUID_W: UUID_B}
    return entities, incoming, parent


def test_build_people_ingest():
    entities, incoming, parent = fake_dump()
    ingest, kind = cbdd_ingest.build([UUID_P], entities, incoming, parent, {}, "test")
    assert kind == "people"
    e = ingest["source_entities"][f"_:cbdd:{UUID_P}"]
    assert e["labels"]["de"] == "Joseph Anton Reiser"
    assert e["types"] == [cbdd_ingest.HUMAN]
    assert "Maler" in e["descriptions"]["de"] and "1780" in e["descriptions"]["de"]
    props = {f["property"]: f["value"] for f in e["attributes"]}
    assert props["P10626"]["value"] == UUID_P
    assert props["P227"]["value"] == "118599283"
    assert props["P569"]["time"].startswith("+1757")
    claims = {c["id"]: c for c in ingest["claims"]}
    assert claims[f"{UUID_P}:P10626"]["route"] == "direct"
    assert "reference" not in claims[f"{UUID_P}:P10626"]
    gnd = claims[f"{UUID_P}:P227"]
    assert gnd["route"] == "curator"
    assert gnd["reference"]["snaks"][0] == {
        "property": "P10626",
        "value": {"type": "string", "value": UUID_P},
    }


def test_build_buildings_ingest_skips_malformed_gnd_claim():
    entities, incoming, parent = fake_dump()
    ingest, kind = cbdd_ingest.build([UUID_B], entities, incoming, parent, {}, "test")
    assert kind == "buildings"
    e = ingest["source_entities"][f"_:cbdd:{UUID_B}"]
    assert e["types"] == cbdd_ingest.BUILDING_TYPES
    props = {f["property"]: f["value"] for f in e["attributes"]}
    assert props["P625"] == {"type": "coordinate", "lat": 48.06, "lon": 9.61}
    assert props["P2092"]["value"] == "20012345"
    ids = {c["id"] for c in ingest["claims"]}
    assert f"{UUID_B}:P2092" in ids and f"{UUID_B}:P227" not in ids
    assert "malformed" in e["hint"]
    assert e["search_names"] == {"de": ["Schlossplatz 1"]}


def test_build_skips_linked_and_refuses_mixed_types():
    entities, incoming, parent = fake_dump()
    ingest, _ = cbdd_ingest.build(
        [UUID_P, UUID_B], entities, incoming, parent, {UUID_B: "Q1"}, "t"
    )
    assert list(ingest["source_entities"]) == [f"_:cbdd:{UUID_P}"]
    try:
        cbdd_ingest.build([UUID_P, UUID_B], entities, incoming, parent, {}, "t")
    except SystemExit as ex:
        assert "one entity type" in str(ex)
    else:
        raise AssertionError("mixed types must be refused")


# --- hints -------------------------------------------------------------------


def test_all_years_spans():
    assert cbdd_hints.all_years("1668-72") == list(range(1668, 1673))
    assert cbdd_hints.all_years("1000-2020, 1773") == [1773]


def test_lifetime_rules():
    painter = [("PAINTERS", [1780], True)]
    assert (
        cbdd_hints.lifetime(
            item(P569=["+1757-00-00T00:00:00Z"], P570=["+1805-00-00T00:00:00Z"]),
            painter,
        )[0]
        == "+"
    )
    assert cbdd_hints.lifetime(item(P569=["+1902-00-00T00:00:00Z"]), painter)[0] == "-"
    # templates may be centuries older; only "lived before the work" counts
    assert (
        cbdd_hints.lifetime(
            item(P570=["+1600-00-00T00:00:00Z"]), [("TEMPLATE_PROVIDERS", [1780], True)]
        )[0]
        == "+"
    )
    # a borrowed (building) dating never contradicts
    assert (
        cbdd_hints.lifetime(
            item(P569=["+1902-00-00T00:00:00Z"]), [("PAINTERS", [1780], False)]
        )[0]
        == "?"
    )
    assert cbdd_hints.lifetime(item(), painter)[0] == "?"


def test_address_match():
    house = item(label="Engelsgrube 66", P6375=["Engelsgrube 66"])
    assert cbdd_hints.address_match("Engelsgrube 66", house)
    assert not cbdd_hints.address_match("Engelsgrube 6", house)
    assert cbdd_hints.address_match(
        "Große Messergasse 6", item(P6375=["Große Messergasse 6a"])
    )
    assert not cbdd_hints.address_match("Kirchplatz", item(label="Kirchplatz"))


def test_same_town():
    src = {"addressLocality": "Lübeck", "locationLat": "53.87", "locationLng": "10.69"}
    no_point = item(label="Engelsgrube 12")
    assert cbdd_hints.same_town(src, no_point, "Bauwerk in der Lübecker Altstadt")
    assert not cbdd_hints.same_town(src, no_point, "Bauwerk in Göttingen")
    assert cbdd_hints.same_town(src, item(P625=[[53.871, 10.688]]), "")
    assert not cbdd_hints.same_town(src, item(P625=[[51.53, 9.93]]), "in Lübeck")


def test_add_candidate_respects_rejected():
    e = {"rejected": [{"id": "Q1"}], "candidates": []}
    ev = cbdd_hints.evidence("custom", "+", "x", "P227")
    assert not cbdd_hints.add_candidate(e, "Q1", ev)
    assert cbdd_hints.add_candidate(e, "Q2", ev)
    assert cbdd_hints.add_candidate(e, "Q2", ev)
    assert len(e["candidates"]) == 1 and len(e["candidates"][0]["evidence"]) == 2


def test_hint_replaces_gnd_line():
    e = {"hint": "CbDD: Teil von X · GND 1 (lobid): 'a'"}
    cbdd_hints.hint(e, "GND 1 (lobid): 'b'")
    cbdd_hints.hint(e, "P10626 on several items")
    cbdd_hints.hint(e, "P10626 on several items")
    assert (
        e["hint"] == "CbDD: Teil von X · GND 1 (lobid): 'b' · P10626 on several items"
    )


def test_people_names_split_into_aliases_and_search_names():
    entities, incoming, parent = fake_dump()
    entities[UUID_P]["alternativeNames"] = ["Reißer, Joseph Anton"]
    ingest, _ = cbdd_ingest.build([UUID_P], entities, incoming, parent, {}, "t")
    e = ingest["source_entities"][f"_:cbdd:{UUID_P}"]
    assert e["labels"]["de"] == "Joseph Anton Reiser"
    assert e["aliases"] == {"de": ["Joseph Anton Reißer"]}
    assert "Joseph Reiser" in e["search_names"]["de"]
    assert "(CbDD)" not in e["descriptions"]["de"]


def test_create_mode_people():
    entities, incoming, parent = fake_dump()
    ingest, _ = cbdd_ingest.build(
        [UUID_P], entities, incoming, parent, {}, "t", create=True
    )
    assert ingest["create_requires"] == ["P31"]
    assert ingest["source_entities"][f"_:cbdd:{UUID_P}"]["on_no_match"] == "create"
    new = {c["property"]: c for c in ingest["claims"] if c.get("only_if_created")}
    assert new["P31"]["value"] == "Q5"
    assert new["P21"]["value"] == "Q6581097"
    assert new["P106"]["value"] == "Q1028181"  # PAINTERS
    assert new["P569"]["value"]["time"] == "+1757-00-00T00:00:00Z"  # from the name
    assert new["P570"]["value"]["precision"] == 9
    assert all(
        c["route"] == "curator" and c["reference"]["source"] == "src:cbdd"
        for c in new.values()
    )


def test_create_mode_buildings_uses_sync_mapping():
    entities, incoming, parent = fake_dump()
    ingest, _ = cbdd_ingest.build(
        [UUID_B], entities, incoming, parent, {}, "t", create=True
    )
    e = ingest["source_entities"][f"_:cbdd:{UUID_B}"]
    assert e["descriptions"]["de"] == "Kirchengebäude in Bad Buchau"
    claims = {c["property"]: c for c in ingest["claims"] if c.get("only_if_created")}
    new = {pid: c["value"] for pid, c in claims.items()}
    assert new["P31"] == "Q16970"
    assert new["P571"] == {
        "type": "time",
        "time": "+1773-00-00T00:00:00Z",
        "precision": 9,
    }
    # The postal code is a qualifier of the street address, not a statement.
    assert "P281" not in new
    assert new["P6375"] == {
        "type": "monolingualtext",
        "text": "Schlossplatz 1",
        "lang": "de",
    }
    assert claims["P6375"]["qualifiers"] == [
        {"property": "P281", "value": {"type": "string", "value": "88422"}}
    ]
    assert new["P625"] == {"type": "coordinate", "lat": 48.06, "lon": 9.61}


def test_without_create_no_creation_claims():
    entities, incoming, parent = fake_dump()
    ingest, _ = cbdd_ingest.build([UUID_B], entities, incoming, parent, {}, "t")
    assert not any(c.get("only_if_created") for c in ingest["claims"])
    assert ingest["source_entities"][f"_:cbdd:{UUID_B}"]["on_no_match"] == "curator"


def test_cbdd_duplicate_check():
    import cbdd_preflight

    ingest = {
        "source_entities": {
            f"_:cbdd:{UUID_P}": {
                "kind": "person",
                "status": "match",
                "qid": "Q1",
                "attributes": [{"property": "P227", "value": {"value": "118"}}],
            }
        }
    }
    dump = [
        {"ID": UUID_P, "sType": "ACTOR_PERSON", "normdata": {"gnd": "118"}},
        {
            "ID": UUID_W,
            "sType": "ACTOR_PERSON",
            "appellation": "Byss",
            "normdata": {"gnd": "118"},
        },
    ]
    assert len(cbdd_preflight.duplicates(ingest, {}, dump, "")) == 1
    assert cbdd_preflight.duplicates(ingest, {}, dump, f"duplicate of {UUID_W}") == []


def test_create_mode_cbdd_author():
    entities, incoming, parent = fake_dump()
    author = "55555555-5555-4555-8555-555555555555"
    entities[author] = {
        "ID": author,
        "sType": "ACTOR_PERSON",
        "appellation": "Muster, Erika",
        "gender": "FEMALE",
    }
    incoming[author] = [
        {"ID": UUID_W, "relTar": author, "sType": "AUTHORS", "relDir": "->"}
    ]
    ingest, _ = cbdd_ingest.build(
        [author], entities, incoming, parent, {}, "t", create=True
    )
    e = ingest["source_entities"][f"_:cbdd:{author}"]
    assert e["descriptions"]["de"] == (
        "Autorin im Corpus der barocken Deckenmalerei in Deutschland"
    )
    new = {
        c["property"]: c["value"] for c in ingest["claims"] if c.get("only_if_created")
    }
    assert new["P106"] == "Q482980" and new["P21"] == "Q6581072"


def test_work_year_ignores_building_history():
    wy = cbdd_ingest.work_year
    hist = {"sType": "OBJECT_BUILDING", "verbaleDating": "1132, 1603-1605, 1706-1712"}
    assert wy(hist, hist) == (1603, False)  # medieval founding skipped, fallback only
    phase = {"sType": "OBJECT_BUILDING", "verbaleDating": "1750-1752"}
    assert wy(phase, phase) == (1750, True)
    long = {"sType": "OBJECT_BUILDING", "verbaleDating": "1354-1979"}
    assert wy(long, long) == (None, False)
    room = {"sType": "OBJECT_ROOM"}  # undated: the host building's dating
    assert wy(room, phase) == (1750, True)
    painting = {"sType": "OBJECT_PAINTING", "verbaleDating": "1618"}
    assert wy(painting, long) == (1618, True)
    assert not cbdd_ingest.single_phase("1184, 1750-1752")
