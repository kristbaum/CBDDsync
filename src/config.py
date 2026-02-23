# sType -> output suffix
CATEGORIES = {
    "ACTOR_PERSON": "people",
    "OBJECT_BUILDING": "buildings",
    "OBJECT_PAINTING": "paintings",
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
    "processedDating": "P571",           # inception #
    "iconography": "P1257",              # depicted Iconclass #
    "productionMethods_wd": "P2079",     # fabrication method #
    "productionMaterials_wd": "P186",    # made from material #
    "position": "P518",                  # applies to part
    "normdata": "P12754",                 # Bildindex der Kunst und Architektur ID #
    "commissioner": "P88",               # commissioned by #
    "painter": "P170",                   # creator #
    "width": "P2049",                    # width #
    "length": "P2043",                   # length #
    "height": "P2048",                   # height
    "diameter": "P2386",                 # diameter
    "description_en": "Den",             # description English
    "description_de": "Dde",             # description German
    "location": "P276",                  # location #
    "condition": "P5816",               # state of conservation
}

# Mapping from Wikidata query JSON keys to property IDs
# Used when parsing query_painting_statements.json
WD_QUERY_KEY_TO_PID = {
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
