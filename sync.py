import argparse
import sys
from pathlib import Path

from src.entity_check import main as exists_in_both_main
from src.statement_check import main as statement_check_main

# Add project root to Python path to enable absolute imports
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def main():
    """Main entry point for the sync tool."""
    parser = argparse.ArgumentParser(description="CbDD ↔ Wikidata sync analysis")
    parser.add_argument(
        "--overwrite-descriptions",
        action="store_true",
        help="propose CbDD descriptions even for items that already have one "
        "in that language (replacing it); by default only empty ones are filled",
    )
    args = parser.parse_args()

    print("Running CBDDsync analysis...")
    print("=" * 60)
    exists_in_both_main()
    print("=" * 60)
    print("\nRunning statement checks...")
    print("=" * 60)
    statement_check_main(overwrite_descriptions=args.overwrite_descriptions)
    print("=" * 60)
    print("✓ Analysis complete!")


if __name__ == "__main__":
    main()
