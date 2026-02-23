from src.entity_check import main as exists_in_both_main
import sys
from pathlib import Path


# Add project root to Python path to enable absolute imports
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def main():
    """Main entry point for the sync tool."""
    # For now, just run exists_in_both
    # Could be extended to support multiple commands via argparse
    print("Running CBDDsync analysis...")
    print("=" * 60)
    exists_in_both_main()
    print("=" * 60)
    print("✓ Analysis complete!")


if __name__ == "__main__":
    main()
