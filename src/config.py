"""
config.py

Configuration mappings.
"""

# sType -> output suffix
CATEGORIES = {
    "ACTOR_PERSON": "people",
    "OBJECT_BUILDING": "buildings",
    "OBJECT_PAINTING": "paintings",
}

# Columns to export per sType (order matters for CSV header)
COLUMNS = {
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
