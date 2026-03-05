"""Multi-Browser Operator — entry point."""

import sys
import os

# Ensure the parent directory is on sys.path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.gui import run_app

if __name__ == "__main__":
    run_app()
