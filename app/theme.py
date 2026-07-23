"""Single shared design system for the app: colors + one global QSS.

Widgets should rely on objectName / class selectors defined here rather
than setting their own inline stylesheets, so the whole app stays visually
consistent.
"""

COLORS = {
    "bg": "#141519",
    "bg_elevated": "#1b1d23",
    "surface": "#22252b",
    "surface_hover": "#2a2e35",
    "border": "#2f333c",
    "border_hover": "#4F8EF7",
    "text_primary": "#f2f3f5",
    "text_secondary": "#9ca3af",
    "text_muted": "#6b7280",
    "accent": "#4F8EF7",
    "accent_hover": "#6ea1f9",
    "scrollbar": "#343942",
}

FONT_FAMILY = "Segoe UI, -apple-system, sans-serif"

STYLESHEET = f"""
* {{
    font-family: {FONT_FAMILY};
}}

QWidget {{
    background: {COLORS["bg"]};
    color: {COLORS["text_primary"]};
}}

QLabel {{
    background: transparent;
}}

QToolTip {{
    background: {COLORS["bg_elevated"]};
    color: {COLORS["text_primary"]};
    border: 1px solid {COLORS["border"]};
    padding: 4px 8px;
    border-radius: 4px;
}}

QScrollArea {{
    background: transparent;
    border: none;
}}

QScrollArea > QWidget > QWidget {{
    background: transparent;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background: {COLORS["scrollbar"]};
    border-radius: 5px;
    min-height: 30px;
}}

QScrollBar::handle:vertical:hover {{
    background: {COLORS["border_hover"]};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}

/* ---- Top bar ---- */

#topBar {{
    background: {COLORS["bg_elevated"]};
    border-bottom: 1px solid {COLORS["border"]};
}}

#backButton {{
    background: transparent;
    color: {COLORS["text_secondary"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
    padding: 6px 14px;
    font-size: 13px;
    font-weight: 600;
}}

#backButton:hover {{
    color: {COLORS["text_primary"]};
    border-color: {COLORS["border_hover"]};
    background: {COLORS["surface"]};
}}

#topBarTitle {{
    font-size: 15px;
    font-weight: 700;
    color: {COLORS["text_primary"]};
}}

/* ---- Home page ---- */

#pageTitle {{
    font-size: 34px;
    font-weight: 700;
    letter-spacing: -0.5px;
}}

#pageSubtitle {{
    color: {COLORS["text_secondary"]};
    font-size: 14px;
}}

#sectionLabel {{
    font-size: 18px;
    font-weight: 600;
    color: {COLORS["text_primary"]};
}}

/* ---- Tool card ---- */

#toolCard {{
    background: {COLORS["surface"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 16px;
}}

#toolCard:hover {{
    background: {COLORS["surface_hover"]};
    border: 1px solid {COLORS["border_hover"]};
}}

#toolCard QLabel {{
    background: transparent;
    border: none;
}}

#cardTitle {{
    font-size: 16px;
    font-weight: 700;
    color: {COLORS["text_primary"]};
}}

#cardDescription {{
    font-size: 12px;
    color: {COLORS["text_secondary"]};
}}

#cardArrow {{
    font-size: 20px;
    color: {COLORS["accent"]};
}}

#toolCard[disabledCard="true"] {{
    background: {COLORS["bg_elevated"]};
}}

#toolCard[disabledCard="true"]:hover {{
    background: {COLORS["bg_elevated"]};
    border: 1px solid {COLORS["border"]};
}}

#toolCard[disabledCard="true"] #cardTitle {{
    color: {COLORS["text_secondary"]};
}}

#toolCard[disabledCard="true"] #cardArrow {{
    color: {COLORS["text_muted"]};
    font-size: 12px;
    font-weight: 600;
}}

/* ---- Buttons ---- */

QPushButton {{
    background: {COLORS["accent"]};
    color: white;
    border: none;
    border-radius: 8px;
    padding: 10px 18px;
    font-size: 13px;
    font-weight: 600;
}}

QPushButton:hover {{
    background: {COLORS["accent_hover"]};
}}

QPushButton:disabled {{
    background: {COLORS["border"]};
    color: {COLORS["text_muted"]};
}}

QPushButton[flat="true"] {{
    background: {COLORS["surface"]};
    color: {COLORS["text_primary"]};
    border: 1px solid {COLORS["border"]};
}}

QPushButton[flat="true"]:hover {{
    border-color: {COLORS["border_hover"]};
}}

/* ---- Toggle group (segmented control) ---- */

QPushButton#toggleChip {{
    background: {COLORS["surface"]};
    color: {COLORS["text_secondary"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
    padding: 8px 16px;
    font-size: 13px;
    font-weight: 600;
}}

QPushButton#toggleChip:hover {{
    color: {COLORS["text_primary"]};
    border-color: {COLORS["border_hover"]};
    background: {COLORS["surface_hover"]};
}}

QPushButton#toggleChip:checked {{
    background: {COLORS["accent"]};
    border-color: {COLORS["accent"]};
    color: white;
}}

QPushButton#toggleChip:checked:hover {{
    background: {COLORS["accent_hover"]};
    border-color: {COLORS["accent_hover"]};
}}

/* ---- Inputs ---- */

QComboBox, QLineEdit, QSpinBox, QTextEdit {{
    background: {COLORS["surface"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
    padding: 6px 10px;
    color: {COLORS["text_primary"]};
}}

QComboBox:hover, QLineEdit:hover, QSpinBox:hover, QTextEdit:hover {{
    border-color: {COLORS["border_hover"]};
}}

QComboBox::drop-down {{
    border: none;
    width: 24px;
}}

QComboBox QAbstractItemView {{
    background: {COLORS["bg_elevated"]};
    border: 1px solid {COLORS["border"]};
    selection-background-color: {COLORS["surface_hover"]};
    outline: none;
}}

/* ---- List widget ---- */

QListWidget {{
    background: {COLORS["surface"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 12px;
    padding: 6px;
    outline: none;
}}

QListWidget::item {{
    padding: 8px;
    border-radius: 8px;
    color: {COLORS["text_primary"]};
    margin: 1px 0;
}}

QListWidget::item:hover {{
    background: {COLORS["surface_hover"]};
}}

QListWidget::item:selected {{
    background: {COLORS["surface_hover"]};
    border: 1px solid {COLORS["border_hover"]};
    color: {COLORS["text_primary"]};
}}

/* ---- Progress bar ---- */

QProgressBar {{
    background: {COLORS["surface"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
    text-align: center;
    color: {COLORS["text_secondary"]};
    height: 18px;
}}

QProgressBar::chunk {{
    background: {COLORS["accent"]};
    border-radius: 7px;
}}

/* ---- Generic panel ---- */

#panel {{
    background: {COLORS["bg_elevated"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 16px;
}}

#mutedLabel {{
    color: {COLORS["text_secondary"]};
    font-size: 12px;
}}

#fieldLabel {{
    color: {COLORS["text_secondary"]};
    font-size: 13px;
    font-weight: 600;
}}

/* ---- Drop zone ---- */

#dropZone {{
    background: {COLORS["bg_elevated"]};
    border: 2px dashed {COLORS["border"]};
    border-radius: 16px;
}}

#dropZone[dragActive="true"] {{
    border-color: {COLORS["accent"]};
    background: {COLORS["surface"]};
}}

#dropZoneLabel {{
    color: {COLORS["text_secondary"]};
    font-size: 14px;
}}
"""


def apply_theme(app):
    app.setStyleSheet(STYLESHEET)
