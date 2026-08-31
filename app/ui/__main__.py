"""Module entry point for python -m app.ui."""

import sys
from app.ui.app import run_gui

if __name__ == "__main__":
    sys.exit(run_gui())
