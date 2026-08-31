"""Desktop application UI package (PySide6)."""

from app.ui.app import run_gui
from app.ui.controller import AssistantController
from app.ui.main_window import MainWindow

__all__ = [
    "AssistantController",
    "MainWindow",
    "run_gui",
]
