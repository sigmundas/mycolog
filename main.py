"""Main entry point for Mushroom Spore Analyzer"""
import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication, QSplashScreen
from PySide6.QtGui import QFont, QPixmap, QPainter, QColor
from PySide6.QtCore import QTranslator, QLocale, Qt
from database.schema import init_database, get_app_settings, update_app_settings
from database.models import SettingsDB
from ui.main_window import MainWindow

APP_VERSION = "0.3.1"


def _create_splash(app: QApplication, version: str) -> QSplashScreen | None:
    logo_path = Path(__file__).parent / "assets" / "mycolog-logo.png"
    if not logo_path.exists():
        return None
    logo = QPixmap(str(logo_path))
    if logo.isNull():
        return None

    extra_height = 36
    splash_pixmap = QPixmap(logo.width(), logo.height() + extra_height)
    splash_pixmap.fill(Qt.white)

    painter = QPainter(splash_pixmap)
    painter.drawPixmap(0, 0, logo)
    painter.setPen(QColor(60, 60, 60))
    font = QFont(app.font())
    font.setPointSize(max(9, font.pointSize() - 1))
    painter.setFont(font)
    painter.drawText(
        0,
        logo.height(),
        splash_pixmap.width(),
        extra_height,
        Qt.AlignCenter,
        f"v{version}" if version else ""
    )
    painter.end()

    splash = QSplashScreen(splash_pixmap)
    splash.setWindowFlag(Qt.WindowStaysOnTopHint, True)
    return splash


def main():
    """Initialize and run the application."""
    # Initialize database
    print("Initializing database...")
    init_database()

    # Create and run application
    app = QApplication(sys.argv)
    app.setApplicationName("MycoLog - Mushroom Log and Spore Analyzer")
    app.setApplicationVersion(APP_VERSION)
    app_font = app.font()
    if app_font.pointSize() <= 0:
        app_font.setPointSize(10)
        app.setFont(app_font)

    splash = _create_splash(app, APP_VERSION)
    if splash:
        splash.show()
        app.processEvents()

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

    window = MainWindow(app_version=APP_VERSION)
    window.show()
    if splash:
        splash.finish(window)
    window.start_update_check()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
