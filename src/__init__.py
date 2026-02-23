"""
CBDDsync - Synchronization tools for deckenmalerei.eu and Wikidata

This package provides tools to analyze and synchronize data between
the deckenmalerei.eu database and Wikidata.
"""

__version__ = "0.1.0"

# Make main function accessible for imports
from src.entity_check import main

__all__ = ["main"]
