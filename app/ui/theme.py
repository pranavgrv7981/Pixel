"""Centralized styling, color palette, and Jarvis-class Qt stylesheet definitions for the desktop UI."""

# Core Color Palette (Jarvis Command Center Aesthetic)
COLOR_BG_DARK = "#0d0f18"         # Deep space master canvas
COLOR_BG_PANEL = "#131622"        # Command sidebar and header glass panels
COLOR_BG_SURFACE = "#1a1e2e"      # Message cards and interactive surfaces
COLOR_BG_INPUT = "#22273d"        # Input capsules and focused elements
COLOR_BG_HOVER = "#2a304d"        # Hover highlight surface

COLOR_BORDER = "#2b324c"          # Subtle HUD border
COLOR_BORDER_FOCUS = "#00f2fe"    # Cyan neon focus glow
COLOR_BORDER_ACCENT = "#4facfe"   # Electric blue secondary border

COLOR_TEXT_PRIMARY = "#e2e8f0"    # High-clarity primary text
COLOR_TEXT_SECONDARY = "#94a3b8"  # Slate secondary text
COLOR_TEXT_MUTED = "#64748b"      # Monospace telemetry and subtle metadata
COLOR_TEXT_WHITE = "#ffffff"

# High-Tech Accent & Status Colors
COLOR_ACCENT = "#00f2fe"          # Primary Cyan Neon (Jarvis core)
COLOR_ACCENT_HOVER = "#4facfe"    # Electric Blue Glow
COLOR_ACCENT_SUBTLE = "rgba(0, 242, 254, 0.12)" # Holographic background wash

COLOR_SUCCESS = "#10b981"         # Emerald Online / Verified status
COLOR_WARNING = "#f59e0b"         # Amber Thinking / Warning state
COLOR_DANGER = "#f43f5e"          # Crimson Alert / Deny state
COLOR_PURPLE = "#a855f7"          # Violet AI reasoning indicator
COLOR_CYAN = "#06b6d4"            # Tech cyan indicator

# Main application stylesheet
APPLICATION_STYLESHEET = f"""
QMainWindow {{
    background-color: {COLOR_BG_DARK};
    color: {COLOR_TEXT_PRIMARY};
}}

QWidget {{
    font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, "Roboto", sans-serif;
    font-size: 13px;
    color: {COLOR_TEXT_PRIMARY};
}}

/* Scroll bars */
QScrollBar:vertical {{
    background: {COLOR_BG_DARK};
    width: 8px;
    margin: 0;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {COLOR_BORDER};
    min-height: 28px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical:hover {{
    background: {COLOR_ACCENT_HOVER};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}

/* Buttons */
QPushButton {{
    background-color: {COLOR_BG_SURFACE};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    padding: 6px 14px;
    color: {COLOR_TEXT_PRIMARY};
    font-weight: 500;
}}
QPushButton:hover {{
    background-color: {COLOR_BG_HOVER};
    border-color: {COLOR_ACCENT};
    color: {COLOR_TEXT_WHITE};
}}
QPushButton:pressed {{
    background-color: {COLOR_BG_INPUT};
}}
QPushButton:disabled {{
    background-color: {COLOR_BG_PANEL};
    border-color: {COLOR_BORDER};
    color: {COLOR_TEXT_MUTED};
}}

QPushButton#primaryButton {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {COLOR_ACCENT}, stop:1 {COLOR_ACCENT_HOVER});
    color: #0b0e17;
    font-weight: 700;
    border: none;
    border-radius: 6px;
    padding: 7px 16px;
}}
QPushButton#primaryButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #38f9d7, stop:1 #4facfe);
    color: #000000;
}}
QPushButton#primaryButton:disabled {{
    background: {COLOR_BORDER};
    color: {COLOR_TEXT_MUTED};
}}

QPushButton#dangerButton {{
    background-color: {COLOR_DANGER};
    color: #ffffff;
    font-weight: 600;
    border: none;
    border-radius: 6px;
}}
QPushButton#dangerButton:hover {{
    background-color: #fb7185;
}}

QPushButton#chipButton {{
    background-color: {COLOR_BG_SURFACE};
    border: 1px solid {COLOR_BORDER};
    border-radius: 12px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 600;
    color: {COLOR_TEXT_SECONDARY};
}}
QPushButton#chipButton:hover {{
    background-color: {COLOR_ACCENT_SUBTLE};
    border-color: {COLOR_ACCENT};
    color: {COLOR_ACCENT};
}}

/* Text edits and Inputs */
QTextEdit, QLineEdit {{
    background-color: {COLOR_BG_INPUT};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    padding: 8px 12px;
    color: {COLOR_TEXT_PRIMARY};
    selection-background-color: {COLOR_ACCENT};
    selection-color: #0b0e17;
}}
QTextEdit:focus, QLineEdit:focus {{
    border: 1px solid {COLOR_BORDER_FOCUS};
    background-color: #272d47;
}}

/* Combo boxes */
QComboBox {{
    background-color: {COLOR_BG_SURFACE};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    padding: 4px 10px;
    color: {COLOR_TEXT_PRIMARY};
    font-weight: 500;
}}
QComboBox:hover {{
    border-color: {COLOR_ACCENT};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox QAbstractItemView {{
    background-color: {COLOR_BG_SURFACE};
    border: 1px solid {COLOR_BORDER};
    color: {COLOR_TEXT_PRIMARY};
    selection-background-color: {COLOR_ACCENT};
    selection-color: #0b0e17;
}}

/* Tooltips */
QToolTip {{
    background-color: {COLOR_BG_PANEL};
    color: {COLOR_TEXT_PRIMARY};
    border: 1px solid {COLOR_BORDER_FOCUS};
    padding: 5px 8px;
    border-radius: 4px;
    font-family: Consolas, monospace;
    font-size: 11px;
}}

/* Dialogs */
QDialog {{
    background-color: {COLOR_BG_PANEL};
    color: {COLOR_TEXT_PRIMARY};
}}

/* List view */
QListWidget {{
    background-color: transparent;
    border: none;
    outline: none;
}}
QListWidget::item {{
    padding: 10px 12px;
    border-radius: 8px;
    margin-bottom: 4px;
    border: 1px solid transparent;
    color: {COLOR_TEXT_PRIMARY};
}}
QListWidget::item:hover {{
    background-color: {COLOR_BG_SURFACE};
    border-color: {COLOR_BORDER};
}}
QListWidget::item:selected {{
    background-color: {COLOR_BG_SURFACE};
    color: {COLOR_TEXT_WHITE};
    border: 1px solid {COLOR_ACCENT};
    border-left: 4px solid {COLOR_ACCENT};
}}
"""
