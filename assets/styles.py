# Colors
LILAC = "#6C4EB4"
DARK_BG = "#1e1e1e"
LIGHT_TEXT = "#eeeeee"

# Global stylesheet for the entire UI
STYLE_SHEET = f"""
/* === General base elements === */
QWidget {{
    background-color: {DARK_BG};
    color: {LIGHT_TEXT};
    font-family: 'Segoe UI', sans-serif;
    font-size: 14px;
}}

QLabel {{
    font-weight: bold;
    margin-bottom: 4px;
}}

QComboBox, QTextBrowser {{
    background-color: #2c2c2c;
    color: {LIGHT_TEXT};
    border: 1px solid {LILAC};
    padding: 6px;
    border-radius: 6px;
    min-height: 30px;
}}

QTextBrowser {{
    border: 1px solid #444;
    padding: 12px;
    border-radius: 8px;
}}

/* === General buttons === */
QPushButton {{
    background-color: {LILAC};
    color: white;
    padding: 10px 20px;
    border-radius: 8px;
    font-weight: bold;
}}

QPushButton:hover {{
    background-color: #9b59b6;
}}

QPushButton:pressed {{
    background-color: #5e3370;
}}

/* === Sidebar === */

/* Sidebar background */
QWidget#Sidebar {{
    background-color: #2a2a2a;
    border-right: 1px solid #444;
}}

/* Sidebar buttons */
QWidget#Sidebar QPushButton {{
    background-color: #2f2f2f;
    color: #cccccc;
    font-size: 15px;
    height: 48px;
    min-height: 48px;
    max-height: 48px;
    padding-left: 20px;
    padding-right: 20px;
    border-radius: 8px;
    text-align: left;
    font-weight: 500;

}}

QWidget#Sidebar QPushButton:hover {{
    background-color: #3a3a3a;
    color: white;
}}

QWidget#Sidebar QPushButton:checked {{
    background-color: #3a3a3a;
    border-left: 4px solid {LILAC};
    padding-left: 16px;
    font-weight: 600;
    color: white;
}}
"""
