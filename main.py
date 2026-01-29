"""Main entry point for Mushroom Spore Analyzer"""
import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont
from PySide6.QtCore import QTranslator, QLocale
from database.schema import init_database, get_app_settings, update_app_settings
from database.models import SettingsDB
from ui.main_window import MainWindow


def main():
    """Initialize and run the application."""
    # Initialize database
    print("Initializing database...")
    init_database()

    # Create and run application
    app = QApplication(sys.argv)
    app.setApplicationName("MycoLog - Mushroom Log and Spore Analyzer")
    app_font = app.font()
    if app_font.pointSize() <= 0:
        app_font.setPointSize(10)
        app.setFont(app_font)
    translator = QTranslator()
    app_settings = get_app_settings()
    lang_code = app_settings.get("ui_language")
    if not lang_code:
        lang_code = SettingsDB.get_setting("ui_language")
    if not lang_code:
        system_locale = QLocale.system().name().lower()
        system_prefix = system_locale.split("_")[0]
        if system_prefix in ("de",):
            lang_code = "de_DE"
        elif system_prefix in ("nb", "no"):
            lang_code = "nb_NO"
        elif system_prefix in ("en",):
            lang_code = "en"
        else:
            lang_code = "en"
        update_app_settings({"ui_language": lang_code})
        SettingsDB.set_setting("ui_language", lang_code)
    if lang_code != "en":
        qm_path = Path(__file__).parent / "i18n" / f"MycoLog_{lang_code}.qm"
        if translator.load(str(qm_path)):
            app.installTranslator(translator)
            app._translator = translator

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
