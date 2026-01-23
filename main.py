"""Main entry point for Mushroom Spore Analyzer"""
import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont
from database.schema import init_database
from ui.main_window import MainWindow


def main():
    """Initialize and run the application."""
    # Initialize database
    print("Initializing database...")
    init_database()

    # Create and run application
    app = QApplication(sys.argv)
    app.setApplicationName("Mushroom Spore Analyzer")
    app_font = app.font()
    if app_font.pointSize() <= 0:
        app_font.setPointSize(10)
        app.setFont(app_font)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
