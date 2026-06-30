# sType -> output suffix
CATEGORIES = {
    "ACTOR_PERSON": "people",
    "OBJECT_BUILDING": "buildings",
    "OBJECT_PAINTING": "paintings",
    "OBJECT_ROOM": "rooms",
    "OBJECT_ROOM_SEQUENCE": "room_sequences",
}

# Columns to export per sType (order matters for CSV header)
COLUMNS_MISSING = {
    "ACTOR_PERSON": ["url", "appellation", "gender", "ID"],
    "OBJECT_BUILDING": [
        "url",
        "appellation",
        "verbaleDating",
        "processedDating",
        "addressState",
        "addressLocality",
        "addressZip",
        "addressStreet",
        "wikishootme",
        "locationLng",
        "locationLat",
        "ID",
    ],
    "OBJECT_PAINTING": [
        "url",
        "appellation",
        "verbaleDating",
        "processedDating",
        "primaryIconography",
        "iconography",
        "productionMethods_wd",
        "productionMaterials_wd",
        "position",
        "normdata",
        "commissioner",
        "painter",
        "width",
        "length",
        "height",
        "diameter",
        "description_en",
        "description_de",
        "location",
        "condition",
        "ID",
    ],
    "OBJECT_ROOM": [
        "url",
        "appellation",
        "verbaleDating",
        "processedDating",
        "ID",
    ],
    "OBJECT_ROOM_SEQUENCE": [
        "url",
        "appellation",
        "verbaleDating",
        "processedDating",
        "ID",
    ],
}

COLUMNS_EXISTING = {
    "ACTOR_PERSON": ["url", "appellation", "gender", "wikidata_qid", "ID"],
    "OBJECT_BUILDING": [
        "url",
        "appellation",
        "verbaleDating",
        "processedDating",
        "addressState",
        "addressLocality",
        "addressZip",
        "addressStreet",
        "wikishootme",
        "locationLng",
        "locationLat",
        "wikidata_qid",
        "ID",
    ],
    "OBJECT_PAINTING": [
        "url",
        "appellation",
        "verbaleDating",
        "processedDating",
        "primaryIconography",
        "iconography",
        "productionMethods_wd",
        "productionMaterials_wd",
        "position",
        "normdata",
        "commissioner",
        "painter",
        "width",
        "length",
        "height",
        "diameter",
        "description_en",
        "description_de",
        "location",
        "condition",
        "wikidata_qid",
        "ID",
    ],
    "OBJECT_ROOM": [
        "url",
        "appellation",
        "verbaleDating",
        "processedDating",
        "wikidata_qid",
        "ID",
    ],
    "OBJECT_ROOM_SEQUENCE": [
        "url",
        "appellation",
        "verbaleDating",
        "processedDating",
        "wikidata_qid",
        "ID",
    ],
}

PRODUCTION_METHOD_MAP = {
    # technique -> Wikidata Q id
    "FRESCO_PAINTING_TECHNIQUE": "Q134194",
    "OIL_PAINTING_TECHNIQUE": "Q174705",
}

PRODUCTION_MATERIAL_MAP = {
    # material -> Wikidata Q id
    "CANVAS_TEXTILE_MATERIAL": "Q12321255",
    "OIL_PAINT_PAINT": "Q296955",
    "PLASTER_COMPOSITE_COATING": "Q572879",
}

POSITION_MAP = {
    "ceiling": "Q1181933",
    "wall": "Q3305213",
    "equipment": "Q3305213",
}

CONDITION_MAP = {
    # condition -> Wikidata Q id
    "destroyed": "Q56556915",
    "damaged": "Q106379705",
    "translocated": "",  # translocation
    "paintedOver": "",  # overpainted
    "restored": "Q75505084",
    "missing": "Q62077203",
}

# Mapping from existing_paintings.csv column names to Wikidata property IDs
# Used for generating QuickStatements commands
PAINTING_COLUMN_TO_PID = {
    "processedDating": "P571",  # inception #
    "iconography": "P1257",  # depicted Iconclass #
    "productionMethods_wd": "P2079",  # fabrication method #
    "productionMaterials_wd": "P186",  # made from material #
#    "position": "P518",  # Maybe include later, no good WD property equivalent
    "normdata": "P12754",  # Bildindex der Kunst und Architektur ID #
    "commissioner": "P88",  # commissioned by #
    "painter": "P170",  # creator #
    "width": "P2049",  # width #
    "length": "P2043",  # length #
    "height": "P2048",  # height
    "diameter": "P2386",  # diameter
    "description_en": "Den",  # description English
    "description_de": "Dde",  # description German
    "location": "P276",  # location #
    "condition": "P5816",  # state of conservation
}

# Mapping from Wikidata query JSON keys to property IDs
# Used when parsing query_painting_statements.json
WD_QUERY_KEY_TO_PID = {
    "itemDescription_en": "Den",
    "itemDescription_de": "Dde",
    "inception": "P571",
    "iconclass": "P1257",
    "method": "P2079",
    "material": "P186",
    "painter": "P170",
    "commissioner": "P88",
    "width": "P2049",
    "length": "P2043",
    "height": "P2048",
    "diameter": "P2386",
    "location": "P276",
    "condition": "P5816",
    "bildindex": "P12754",
}

# Value maps used when building statements from the existing_*.csv files.
# Keyed by {pid: {raw_csv_value: wikidata_value}}; raw values with no mapping
# are skipped rather than emitted verbatim.
GENDER_MAP = {
    "MALE": "Q6581097",  # male
    "FEMALE": "Q6581072",  # female
}

# Per-entity-type configuration for statement_check.py.
#
# The comparison logic in statement_check.py is generic; everything specific to
# an entity type lives here. Each entry provides:
#   existing_csv         entities already linked to Wikidata (input)
#   wd_query_json        cached SPARQL result of statements already in Wikidata
#   output_csv           QuickStatements CSV of statements missing from Wikidata
#   column_to_pid        {existing_csv column: Wikidata property ID}
#   wd_query_key_to_pid  {SPARQL result key:   Wikidata property ID}
#   value_maps           optional {pid: {raw_value: wikidata_value}}
#   coordinate           optional P625 helper combining two lat/lng columns:
#                        {"pid": ..., "lat": <column>, "lng": <column>}
STATEMENT_CHECKS = {
    "people": {
        "existing_csv": "existing/existing_people.csv",
        "wd_query_json": "sources/query_people_statements.json",
        "output_csv": "missing/missing_people_statements.csv",
        "column_to_pid": {
            "gender": "P21",  # sex or gender
        },
        "value_maps": {"P21": GENDER_MAP},
        "wd_query_key_to_pid": {"gender": "P21"},
    },
    "buildings": {
        "existing_csv": "existing/existing_buildings.csv",
        "wd_query_json": "sources/query_building_statements.json",
        "output_csv": "missing/missing_building_statements.csv",
        "column_to_pid": {
            "processedDating": "P571",  # inception
            "addressZip": "P281",  # postal code
        },
        "coordinate": {"pid": "P625", "lat": "locationLat", "lng": "locationLng"},
        "wd_query_key_to_pid": {
            "inception": "P571",
            "postalCode": "P281",
            "coordinate": "P625",
        },
    },
    "paintings": {
        "existing_csv": "existing/existing_paintings.csv",
        "wd_query_json": "sources/query_painting_statements.json",
        "output_csv": "missing/missing_painting_statements.csv",
        "column_to_pid": PAINTING_COLUMN_TO_PID,
        "wd_query_key_to_pid": WD_QUERY_KEY_TO_PID,
    },
    "rooms": {
        "existing_csv": "existing/existing_rooms.csv",
        "wd_query_json": "sources/query_room_statements.json",
        "output_csv": "missing/missing_room_statements.csv",
        "column_to_pid": {
            "processedDating": "P571",  # inception
        },
        "wd_query_key_to_pid": {"inception": "P571"},
    },
    "room_sequences": {
        "existing_csv": "existing/existing_room_sequences.csv",
        "wd_query_json": "sources/query_room_sequence_statements.json",
        "output_csv": "missing/missing_room_sequence_statements.csv",
        "column_to_pid": {
            "processedDating": "P571",  # inception
        },
        "wd_query_key_to_pid": {"inception": "P571"},
    },
}
