echo "Downloading source data files..."
mkdir -p sources
BASE_URL="https://raw.githubusercontent.com/arthist-lmu/plafond3d/main/dumps/deckenmalerei.eu/2025_02"
curl -fsSL "$BASE_URL/entities.json"  -o sources/entities.json
curl -fsSL "$BASE_URL/relations.json" -o sources/relations.json
curl -fsSL "$BASE_URL/resources.json" -o sources/resources.json
echo "✓ Source data downloaded"