"""UI styling: dark theme with a cyan accent.

The palette follows the sibling ``materialConvert`` tool: deep neutral greys,
a cyan accent (``#00AFFF``) for focus / selection / active tabs, mint green for
the text inside editable fields, and colour-coded buttons (green = apply,
purple = preview / refresh, red = clear).

Only the window itself sets a background through the ``batchAttributeEditorWindow``
objectName (this project uses a plain QWidget, not a QMainWindow), so the global
``QWidget`` rule carries text colour and font only and never leaks a background
into popups or scroll bars.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------

BACKGROUND = "#232323"          # window background
PANEL = "#282828"               # group box fill
INPUT = "#151515"               # input / table fill
DARK = "#1a1a1a"                # inactive tabs, alternate rows, combo popup
LOG_BG = "#1C1C1C"              # read-only text areas
BORDER = "#333333"
TEXT = "#DCDCDC"
MUTED = "#8A9199"               # hint text
ACCENT = "#00AFFF"              # focus rings, selection, active tab
VALUE = "#00FFAD"               # text inside editable fields
LABEL = "#8DBAE8"               # soft blue labels / default button text
WARNING = "#E5C07B"
ERROR = "#E06C75"
SUCCESS = "#98C379"

# ---------------------------------------------------------------------------
# Layout metrics (single source of truth shared with the widget code)
# ---------------------------------------------------------------------------

OUTER_MARGIN = 8            # window edge → first section
SECTION_SPACING = 8         # vertical gap between sections
ROW_SPACING = 6             # gap between rows inside a section
COLUMN_SPACING = 8          # gap between the bottom left / right columns
GROUP_INSET = 10            # horizontal inset of a group box content

STYLESHEET = f"""
/* ---------- window ---------- */
QWidget#batchAttributeEditorWindow {{ background-color: {BACKGROUND}; }}
QWidget {{
    color: {TEXT};
    font-family: 'Segoe UI', 'Microsoft YaHei';
}}

/* ---------- group boxes ---------- */
QGroupBox {{
    color: {LABEL};
    font-weight: bold;
    border: 1px solid {BORDER};
    border-radius: 4px;
    margin-top: 10px;
    padding-top: 15px;
    background-color: {PANEL};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    color: {ACCENT};
}}

/* ---------- editable fields ---------- */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {INPUT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 5px 8px;
    color: {VALUE};
    font-family: 'Consolas', 'Microsoft YaHei';
}}
QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover,
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid {ACCENT};
}}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 6px solid {LABEL};
    margin-right: 5px;
}}
QComboBox QAbstractItemView {{
    background-color: {DARK};
    color: {TEXT};
    border: 1px solid {BORDER};
    selection-background-color: #2E3D4D;
    selection-color: white;
}}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    background-color: #2a2a2a;
    border-left: 1px solid {BORDER};
    border-bottom: 1px solid {BORDER};
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    background-color: #2a2a2a;
    border-left: 1px solid {BORDER};
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 5px solid {LABEL};
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {LABEL};
}}

/* ---------- read-only text ---------- */
QPlainTextEdit, QTextEdit {{
    background-color: {LOG_BG};
    border: 1px solid #3A3A3A;
    border-radius: 4px;
    padding: 4px;
    color: {TEXT};
    font-family: 'Consolas', 'Microsoft YaHei';
}}

/* ---------- scroll areas (transparent so the group box fill shows through) ---------- */
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget {{ background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}

/* ---------- buttons ---------- */
QPushButton {{
    background-color: #2E3D4D;
    color: {LABEL};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 5px 14px;
    min-width: 60px;
    font-weight: bold;
    font-family: 'Segoe UI', 'Microsoft YaHei';
}}
QPushButton:hover {{ background-color: #3E4D5D; color: white; border: 1px solid {ACCENT}; }}
QPushButton:pressed {{ background-color: #24303C; }}
QPushButton:disabled {{ background-color: #3f3f3f; color: #7a7a7a; border: 1px solid {BORDER}; }}

QPushButton#applyButton {{ background-color: #2b5c46; color: #8de8b8; }}
QPushButton#applyButton:hover {{ background-color: #3b7c5e; color: white; border: 1px solid {VALUE}; }}
QPushButton#applyButton:disabled {{ background-color: #3f3f3f; color: #7a7a7a; border: 1px solid {BORDER}; }}

QPushButton#previewButton {{ background-color: #3d2b5c; color: #c48de8; }}
QPushButton#previewButton:hover {{ background-color: #4e3b7c; color: white; border: 1px solid #B500FF; }}
QPushButton#previewButton:disabled {{ background-color: #3f3f3f; color: #7a7a7a; border: 1px solid {BORDER}; }}

QPushButton#refreshBtn {{ background-color: #3d2b5c; color: #c48de8; }}
QPushButton#refreshBtn:hover {{ background-color: #4e3b7c; color: white; border: 1px solid #B500FF; }}

QPushButton#clearBtn {{ background-color: #4C3232; color: #E0A3A3; }}
QPushButton#clearBtn:hover {{ background-color: #5C3D3D; color: white; border: 1px solid {ERROR}; }}

/* ---------- check / radio ---------- */
QCheckBox, QRadioButton {{ color: {TEXT}; spacing: 5px; }}
QCheckBox::indicator:unchecked {{ border: 1px solid #555; background-color: {INPUT}; border-radius: 2px; }}
QCheckBox::indicator:checked {{ border: 1px solid {ACCENT}; background-color: {ACCENT}; border-radius: 2px; }}
QRadioButton::indicator:unchecked {{ border: 1px solid #555; background-color: {INPUT}; border-radius: 7px; }}
QRadioButton::indicator:checked {{ border: 1px solid {ACCENT}; background-color: {ACCENT}; border-radius: 7px; }}

/* ---------- tables ---------- */
QTableView, QTreeView, QListView {{
    background-color: {INPUT};
    alternate-background-color: {DARK};
    border: 1px solid {BORDER};
    border-radius: 4px;
    color: {TEXT};
    font-family: 'Consolas', 'Microsoft YaHei';
    font-size: 12px;
    gridline-color: transparent;
    selection-background-color: #2E3D4D;
    selection-color: white;
}}
QTableView::item {{ padding: 2px 4px; border: none; }}
QHeaderView::section {{
    background-color: #262626;
    color: {LABEL};
    border: none;
    border-right: 1px solid {BORDER};
    border-bottom: 1px solid {BORDER};
    padding: 4px 6px;
    font-weight: bold;
}}
QTableCornerButton::section {{ background-color: #262626; border: none; }}

/* ---------- scroll bars ---------- */
QScrollBar:vertical {{ background-color: {DARK}; width: 8px; border-radius: 4px; margin: 0; }}
QScrollBar::handle:vertical {{ background-color: #444; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background-color: #555; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
QScrollBar:horizontal {{ background-color: {DARK}; height: 8px; border-radius: 4px; margin: 0; }}
QScrollBar::handle:horizontal {{ background-color: #444; border-radius: 4px; min-width: 30px; }}
QScrollBar::handle:horizontal:hover {{ background-color: #555; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}

/* ---------- splitter ---------- */
QSplitter::handle {{ background-color: {BORDER}; }}
QSplitter::handle:vertical {{ height: 4px; }}
QSplitter::handle:horizontal {{ width: 4px; }}

/* ---------- state labels ---------- */
QLabel#hintLabel {{ color: {MUTED}; }}
QLabel#warningLabel {{ color: {WARNING}; }}
QLabel#errorLabel {{ color: {ERROR}; }}
QLabel#successLabel {{ color: {SUCCESS}; }}
QLabel#emptyStateLabel {{
    color: {MUTED};
    font-size: 13px;
    padding: 24px;
}}

/* ---------- invalid input ---------- */
QLineEdit[invalid="true"], QSpinBox[invalid="true"], QDoubleSpinBox[invalid="true"] {{
    border: 1px solid {ERROR};
}}

/* ---------- tooltip ---------- */
QToolTip {{
    background-color: {DARK};
    color: {TEXT};
    border: 1px solid {BORDER};
    padding: 4px 6px;
}}
"""
