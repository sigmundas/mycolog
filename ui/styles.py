
"""Modern stylesheet for the application."""

MODERN_STYLE = """
QMainWindow {
    background-color: #f5f5f5;
}

QWidget {
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 10pt;
}

QGroupBox {
    background-color: white;
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 12px;
    font-weight: bold;
    color: #2c3e50;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 4px 8px;
    background-color: white;
    border-radius: 4px;
}

QPushButton {
    background-color: #3498db;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 10px 20px;
    font-weight: bold;
    font-size: 10pt;
}

QPushButton:hover {
    background-color: #2980b9;
}

QPushButton:pressed {
    background-color: #21618c;
}

QPushButton:disabled {
    background-color: #bdc3c7;
    color: #7f8c8d;
}

QPushButton#measureButton {
    background-color: #27ae60;
}

QPushButton#measureButton:hover {
    background-color: #229954;
}

QPushButton#loadButton {
    background-color: #9b59b6;
}

QPushButton#loadButton:hover {
    background-color: #8e44ad;
}

QLineEdit {
    background-color: white;
    border: 2px solid #e0e0e0;
    border-radius: 6px;
    padding: 8px;
    font-size: 10pt;
}

QLineEdit:focus {
    border: 2px solid #3498db;
}

QTextEdit {
    background-color: white;
    border: 2px solid #e0e0e0;
    border-radius: 6px;
    padding: 8px;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 9pt;
}

QLabel {
    color: #2c3e50;
}

QLabel#imageLabel {
    background-color: #ecf0f1;
    border: 2px solid #bdc3c7;
    border-radius: 8px;
}

QLabel#headerLabel {
    font-size: 12pt;
    font-weight: bold;
    color: #2c3e50;
}

QLabel#objectiveTag {
    background-color: rgba(52, 152, 219, 200);
    color: white;
    font-weight: bold;
    font-size: 11pt;
    border-radius: 6px;
    padding: 8px 12px;
}

QMenuBar {
    background-color: #34495e;
    color: white;
    padding: 4px;
}

QMenuBar::item {
    background-color: transparent;
    color: white;
    padding: 8px 12px;
}

QMenuBar::item:selected {
    background-color: #2c3e50;
    border-radius: 4px;
}

QMenu {
    background-color: white;
    border: 1px solid #e0e0e0;
    border-radius: 4px;
}

QMenu::item {
    padding: 8px 24px;
}

QMenu::item:selected {
    background-color: #3498db;
    color: white;
}

QDialog {
    background-color: #f5f5f5;
}

QComboBox {
    background-color: white;
    border: 2px solid #e0e0e0;
    border-radius: 6px;
    padding: 8px;
    font-size: 10pt;
}

QComboBox QAbstractItemView {
    background-color: white;
    color: #2c3e50;
    selection-background-color: #3498db;
    selection-color: white;
}

QComboBox QAbstractItemView::item {
    color: #2c3e50;
    background-color: white;
}

QComboBox QAbstractItemView::item:selected,
QComboBox QAbstractItemView::item:hover {
    background-color: #3498db;
    color: white;
}

QComboBoxPrivateContainer {
    background-color: white;
    border: 1px solid #e0e0e0;
}

QComboBoxPrivateContainer QListView {
    background-color: white;
    color: #2c3e50;
    selection-background-color: #3498db;
    selection-color: white;
}

QComboBoxPrivateContainer QListView::item {
    color: #2c3e50;
    background-color: white;
}

QComboBoxPrivateContainer QListView::item:selected,
QComboBoxPrivateContainer QListView::item:hover {
    background-color: #3498db;
    color: white;
}

QComboBox:focus {
    border: 2px solid #3498db;
}

QComboBox::drop-down {
    border: none;
    width: 30px;
}

QComboBox::down-arrow {
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #7f8c8d;
    margin-right: 8px;
}
"""
