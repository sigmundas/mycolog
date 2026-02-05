"""Main application window with zoom, pan, and measurements table."""
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                                QPushButton, QLabel, QFileDialog, QMessageBox,
                                QGroupBox, QTableWidget, QTableWidgetItem,
                                QHeaderView, QAbstractItemView, QTabWidget,
                                QRadioButton, QButtonGroup, QSplitter, QComboBox,
                                QCheckBox, QDoubleSpinBox, QDialog, QFormLayout,
                                QDialogButtonBox, QSpinBox, QSizePolicy, QToolButton,
                                QStyle, QLineEdit, QApplication, QProgressDialog,
                                QToolTip, QCompleter)
from PySide6.QtGui import (
    QPixmap,
    QAction,
    QColor,
    QImage,
    QPainter,
    QPen,
    QIcon,
    QKeySequence,
    QShortcut,
    QDesktopServices,
)
from PySide6.QtCore import (
    Qt,
    QPointF,
    QRectF,
    QSize,
    QTimer,
    Signal,
    QPoint,
    QEvent,
    QStringListModel,
    QUrl,
)
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
import json
import html
import numpy as np
import math
import sqlite3
import time
from pathlib import Path
import re
from PIL import Image, ExifTags
from database.models import ObservationDB, ImageDB, MeasurementDB, SettingsDB, ReferenceDB, CalibrationDB
from database.schema import (
    get_connection,
    get_app_settings,
    save_app_settings,
    update_app_settings,
    get_database_path,
    get_images_dir,
    init_database,
    load_objectives
)
from utils.annotation_capture import save_spore_annotation
from utils.thumbnail_generator import generate_all_sizes
from utils.image_utils import cleanup_import_temp_file
from utils.heic_converter import maybe_convert_heic
from utils.vernacular_utils import (
    normalize_vernacular_language,
    vernacular_language_label,
    common_name_display_label,
    resolve_vernacular_db_path,
    list_available_vernacular_languages,
)
from .image_gallery_widget import ImageGalleryWidget
from .calibration_dialog import CalibrationDialog
from .zoomable_image_widget import ZoomableImageLabel
from .spore_preview_widget import SporePreviewWidget
from .observations_tab import ObservationsTab
from .styles import MODERN_STYLE
from utils.db_share import export_database_bundle as export_db_bundle
from utils.db_share import import_database_bundle as import_db_bundle
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle, Circle


class SpinnerWidget(QWidget):
    """Simple spinning doughnut indicator."""

    def __init__(self, parent=None, size=56):
        super().__init__(parent)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(60)
        self.setFixedSize(size, size)

    def _tick(self):
        self._angle = (self._angle + 30) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        size = min(self.width(), self.height())
        rect = QRectF(6, 6, size - 12, size - 12)

        base_pen = QPen(QColor(220, 220, 220), 6)
        base_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(base_pen)
        painter.drawEllipse(rect)

        arc_pen = QPen(QColor(52, 152, 219), 6)
        arc_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(arc_pen)
        painter.drawArc(rect, int(self._angle * 16), int(120 * 16))


class LoadingDialog(QDialog):
    """Modal loading dialog with a spinner."""

    def __init__(self, parent=None, text="Loading..."):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        self.spinner = SpinnerWidget(self, size=60)
        layout.addWidget(self.spinner, alignment=Qt.AlignCenter)
        label = QLabel(text)
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)


class ScaleBarCalibrationDialog(QDialog):
    """Simple scale bar calibration dialog for two-point measurement."""

    def __init__(self, main_window, initial_um: float = 10.0, previous_key: str | None = None):
        super().__init__(main_window)
        self.setWindowTitle("Scale bar")
        self.setModal(False)
        self.main_window = main_window
        self.previous_key = previous_key
        self.scale_applied = False
        self.auto_apply = False

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.length_input = QDoubleSpinBox()
        self.length_input.setRange(0.1, 100000.0)
        self.length_input.setDecimals(2)
        self.length_input.setValue(initial_um)
        self.length_input.setSuffix(" µm")
        form.addRow("Scale bar length:", self.length_input)

        self.scale_label = QLabel("--")
        form.addRow("Custom scale:", self.scale_label)

        layout.addLayout(form)

        btn_row = QHBoxLayout()
        self.select_btn = QPushButton("Select scale bar endpoints")
        self.select_btn.clicked.connect(self._on_select)
        btn_row.addWidget(self.select_btn)
        btn_row.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(close_btn)

        layout.addLayout(btn_row)

    def _on_select(self):
        if not self.main_window:
            return
        self.hide()
        self.main_window.enter_calibration_mode(self)

    def set_calibration_distance(self, distance_pixels: float):
        if not distance_pixels or distance_pixels <= 0:
            return
        length_um = float(self.length_input.value())
        scale_um = length_um / distance_pixels
        scale_nm = scale_um * 1000.0
        self.scale_label.setText(f"{scale_nm:.2f} nm/px")
        self.show()
        self._pending_scale_um = scale_um

    def apply_scale(self, distance_pixels: float):
        if not distance_pixels or distance_pixels <= 0:
            return
        length_um = float(self.length_input.value())
        scale_um = length_um / distance_pixels
        scale_nm = scale_um * 1000.0
        self.scale_label.setText(f"{scale_nm:.2f} nm/px")
        applied = False
        if self.main_window:
            applied = bool(self.main_window.set_custom_scale(scale_um))
        self.scale_applied = applied

    def closeEvent(self, event):
        if not self.scale_applied and self.previous_key:
            self.main_window._populate_scale_combo(self.previous_key)
        super().closeEvent(event)


class DatabaseSettingsDialog(QDialog):
    """Dialog for database and image folder settings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Database Settings")
        self.setModal(True)
        self.setMinimumWidth(520)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.db_path_input = QLineEdit()
        db_browse = QPushButton(self.tr("Browse"))
        db_browse.clicked.connect(self._browse_db_folder)
        db_row = QHBoxLayout()
        db_row.addWidget(self.db_path_input)
        db_row.addWidget(db_browse)
        form.addRow(self.tr("Database folder:"), db_row)

        self.images_dir_input = QLineEdit()
        img_browse = QPushButton(self.tr("Browse"))
        img_browse.clicked.connect(self._browse_images_dir)
        img_row = QHBoxLayout()
        img_row.addWidget(self.images_dir_input)
        img_row.addWidget(img_browse)
        form.addRow(self.tr("Images folder:"), img_row)

        self.contrast_input = QLineEdit()
        form.addRow(self.tr("Contrast values:"), self.contrast_input)
        self.mount_input = QLineEdit()
        form.addRow(self.tr("Mount values:"), self.mount_input)
        self.sample_input = QLineEdit()
        form.addRow(self.tr("Sample values:"), self.sample_input)
        self.measure_input = QLineEdit()
        form.addRow(self.tr("Measure categories:"), self.measure_input)

        hint = QLabel(
            self.tr(
                "Use comma-separated values. Mark the default with a trailing * (example: BF*). "
                "Changes apply to new dialogs."
            )
        )
        hint.setStyleSheet("color: #7f8c8d; font-size: 9pt;")

        layout.addLayout(form)
        layout.addWidget(hint)

        buttons = QHBoxLayout()
        buttons.addStretch()
        save_btn = QPushButton(self.tr("Save"))
        save_btn.setObjectName("primaryButton")
        save_btn.clicked.connect(self._save)
        cancel_btn = QPushButton(self.tr("Cancel"))
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(save_btn)
        buttons.addWidget(cancel_btn)
        layout.addLayout(buttons)

        self._load_settings()

    def _load_settings(self):
        settings = get_app_settings()
        db_folder = settings.get("database_folder")
        if not db_folder and settings.get("database_path"):
            db_folder = str(Path(settings.get("database_path")).parent)
        if not db_folder:
            db_folder = str(get_database_path().parent)
        self.db_path_input.setText(db_folder)
        self.images_dir_input.setText(str(settings.get("images_dir") or get_images_dir()))

        contrast = SettingsDB.get_list_setting("contrast_options", ["BF", "DF", "DIC", "Phase"])
        mount = SettingsDB.get_list_setting(
            "mount_options",
            ["Not set", "Water", "KOH", "Melzer", "Congo Red", "Cotton Blue"]
        )
        sample = SettingsDB.get_list_setting(
            "sample_options",
            ["Not set", "Fresh", "Dried", "Spore print"]
        )
        categories = SettingsDB.get_list_setting(
            "measure_categories",
            ["Spore", "Basidia", "Pleurocystidia", "Cheilocystidia", "Caulocystidia", "Other"]
        )

        contrast_default = SettingsDB.get_setting("contrast_default", contrast[0] if contrast else "BF")
        mount_default = SettingsDB.get_setting("mount_default", mount[0] if mount else "Not set")
        sample_default = SettingsDB.get_setting("sample_default", sample[0] if sample else "Not set")
        category_default = SettingsDB.get_setting("measure_default", categories[0] if categories else "Spore")

        self.contrast_input.setText(self._format_list_with_default(contrast, contrast_default))
        self.mount_input.setText(self._format_list_with_default(mount, mount_default))
        self.sample_input.setText(self._format_list_with_default(sample, sample_default))
        self.measure_input.setText(self._format_list_with_default(categories, category_default))

    def _browse_db_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Select Database Folder", self.db_path_input.text())
        if path:
            self.db_path_input.setText(path)

    def _browse_images_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Select Images Folder", self.images_dir_input.text())
        if path:
            self.images_dir_input.setText(path)

    def _format_list_with_default(self, values, default_value):
        formatted = []
        for value in values:
            if value == default_value:
                formatted.append(f"{value}*")
            else:
                formatted.append(value)
        if default_value and default_value not in values:
            formatted.insert(0, f"{default_value}*")
        return ", ".join(formatted)

    def _parse_list_with_default(self, label, text, fallback_values):
        items = [item.strip() for item in text.split(",") if item.strip()]
        defaults = [item for item in items if "*" in item]
        if len(defaults) != 1:
            QMessageBox.warning(
                self,
                "Invalid Defaults",
                f"{label} values must include exactly one default marked with *."
            )
            return None, None

        seen = set()
        cleaned = []
        default_value = None
        for item in items:
            is_default = "*" in item
            name = item.replace("*", "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            cleaned.append(name)
            if is_default:
                default_value = name

        if not cleaned:
            cleaned = fallback_values
            default_value = fallback_values[0] if fallback_values else None

        return cleaned, default_value

    def _save(self):
        settings = get_app_settings()
        db_folder = self.db_path_input.text().strip()
        images_dir = self.images_dir_input.text().strip()

        old_db_path = settings.get("database_path")
        old_ref_path = settings.get("reference_database_path")
        if db_folder:
            settings["database_folder"] = db_folder
            settings.pop("database_path", None)
            settings.pop("reference_database_path", None)
        else:
            settings.pop("database_folder", None)

        if images_dir:
            settings["images_dir"] = images_dir
        else:
            settings.pop("images_dir", None)

        save_app_settings(settings)

        if db_folder:
            try:
                target_dir = Path(db_folder)
                target_dir.mkdir(parents=True, exist_ok=True)
                new_db = target_dir / "mushrooms.db"
                new_ref = target_dir / "reference_values.db"
                if old_db_path and Path(old_db_path).exists() and Path(old_db_path) != new_db:
                    Path(old_db_path).replace(new_db)
                if old_ref_path and Path(old_ref_path).exists() and Path(old_ref_path) != new_ref:
                    Path(old_ref_path).replace(new_ref)
            except Exception as exc:
                QMessageBox.warning(self, "Database Move Failed", str(exc))
        init_database()

        contrast, contrast_default = self._parse_list_with_default(
            "Contrast",
            self.contrast_input.text(),
            ["BF", "DF", "DIC", "Phase"]
        )
        mount, mount_default = self._parse_list_with_default(
            "Mount",
            self.mount_input.text(),
            ["Not set", "Water", "KOH", "Melzer", "Congo Red", "Cotton Blue"]
        )
        sample, sample_default = self._parse_list_with_default(
            "Sample",
            self.sample_input.text(),
            ["Not set", "Fresh", "Dried", "Spore print"]
        )
        categories, category_default = self._parse_list_with_default(
            "Measure category",
            self.measure_input.text(),
            ["Spore", "Basidia", "Pleurocystidia", "Cheilocystidia", "Caulocystidia", "Other"]
        )

        if not all([contrast, mount, sample, categories, contrast_default, mount_default, sample_default, category_default]):
            return

        SettingsDB.set_list_setting("contrast_options", contrast)
        SettingsDB.set_list_setting("mount_options", mount)
        SettingsDB.set_list_setting("sample_options", sample)
        SettingsDB.set_list_setting("measure_categories", categories)
        SettingsDB.set_setting("contrast_default", contrast_default)
        SettingsDB.set_setting("mount_default", mount_default)
        SettingsDB.set_setting("sample_default", sample_default)
        SettingsDB.set_setting("measure_default", category_default)

        self.accept()


class LanguageSettingsDialog(QDialog):
    """Dialog for UI and vernacular language settings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Language")
        self.setModal(True)
        self.setMinimumWidth(420)
        self._ui_changed = False
        self._vernacular_changed = False
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.ui_combo = QComboBox()
        self.ui_combo.addItem(self.tr("English"), "en")
        self.ui_combo.addItem(self.tr("Norwegian"), "nb_NO")
        self.ui_combo.addItem(self.tr("German"), "de_DE")
        form.addRow(self.tr("UI language:"), self.ui_combo)

        self.vernacular_combo = QComboBox()
        self._populate_vernacular_languages()
        form.addRow(self.tr("Vernacular names:"), self.vernacular_combo)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._load_settings()

    def _populate_vernacular_languages(self):
        self.vernacular_combo.blockSignals(True)
        self.vernacular_combo.clear()
        for code in list_available_vernacular_languages():
            label = vernacular_language_label(code) or code
            self.vernacular_combo.addItem(self.tr(label), code)
        self.vernacular_combo.blockSignals(False)

    def _load_settings(self):
        current_ui = SettingsDB.get_setting("ui_language", "en")
        current_vern = normalize_vernacular_language(SettingsDB.get_setting("vernacular_language", "no"))
        ui_index = self.ui_combo.findData(current_ui)
        if ui_index >= 0:
            self.ui_combo.setCurrentIndex(ui_index)
        vern_index = self.vernacular_combo.findData(current_vern)
        if vern_index >= 0:
            self.vernacular_combo.setCurrentIndex(vern_index)
        elif self.vernacular_combo.count():
            self.vernacular_combo.setCurrentIndex(0)

    def _save(self):
        old_ui = SettingsDB.get_setting("ui_language", "en")
        old_vern = normalize_vernacular_language(SettingsDB.get_setting("vernacular_language", "no"))

        new_ui = self.ui_combo.currentData()
        new_vern = normalize_vernacular_language(self.vernacular_combo.currentData())

        if new_ui and new_ui != old_ui:
            SettingsDB.set_setting("ui_language", new_ui)
            update_app_settings({"ui_language": new_ui})
            self._ui_changed = True

        if new_vern and new_vern != old_vern:
            SettingsDB.set_setting("vernacular_language", new_vern)
            update_app_settings({"vernacular_language": new_vern})
            self._vernacular_changed = True

        if self._vernacular_changed:
            parent = self.parent()
            if parent and hasattr(parent, "apply_vernacular_language_change"):
                parent.apply_vernacular_language_change()

        if self._ui_changed:
            QMessageBox.information(
                self,
                self.tr("Language"),
                self.tr("Language change will apply after restart.")
            )

        self.accept()


#
# Vernacular language helpers live in utils.vernacular_utils.
#


class VernacularDB:
    """Simple helper for vernacular name lookup."""

    def __init__(self, db_path: Path, language_code: str | None = None):
        self.db_path = db_path
        self.language_code = normalize_vernacular_language(language_code) if language_code else None
        self._has_language_column = None

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _has_language(self) -> bool:
        if self._has_language_column is None:
            with self._connect() as conn:
                cur = conn.execute("PRAGMA table_info(vernacular_min)")
                self._has_language_column = any(row[1] == "language_code" for row in cur.fetchall())
        return bool(self._has_language_column)

    def _language_clause(self, language_code: str | None) -> tuple[str, list[str]]:
        if not self._has_language():
            return "", []
        raw = language_code or self.language_code
        if not raw:
            return "", []
        lang = normalize_vernacular_language(raw)
        if not lang:
            return "", []
        return " AND v.language_code = ? ", [lang]

    def list_languages(self) -> list[str]:
        if not self._has_language():
            return []
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT DISTINCT language_code
                FROM vernacular_min
                WHERE language_code IS NOT NULL AND language_code != ''
                ORDER BY language_code
                """
            )
            return [row[0] for row in cur.fetchall() if row and row[0]]

    def suggest_vernacular(self, prefix: str, genus: str | None = None, species: str | None = None) -> list[str]:
        prefix = prefix.strip()
        if not prefix:
            return []
        lang_clause, lang_params = self._language_clause(None)
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT DISTINCT v.vernacular_name
                FROM vernacular_min v
                JOIN taxon_min t ON t.taxon_id = v.taxon_id
                WHERE v.vernacular_name LIKE ? || '%'
                  AND (? IS NULL OR t.genus = ?)
                  AND (? IS NULL OR t.specific_epithet = ?)
                """
                + lang_clause
                + """
                ORDER BY v.vernacular_name
                LIMIT 200
                """,
                (prefix, genus, genus, species, species, *lang_params),
            )
            return [row[0] for row in cur.fetchall() if row and row[0]]

    def suggest_vernacular_for_taxon(
        self, genus: str | None = None, species: str | None = None, limit: int = 200
    ) -> list[str]:
        genus = genus.strip() if genus else None
        species = species.strip() if species else None
        if not genus and not species:
            return []
        lang_clause, lang_params = self._language_clause(None)
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT DISTINCT v.vernacular_name
                FROM vernacular_min v
                JOIN taxon_min t ON t.taxon_id = v.taxon_id
                WHERE (? IS NULL OR t.genus = ?)
                  AND (? IS NULL OR t.specific_epithet = ?)
                """
                + lang_clause
                + """
                ORDER BY v.is_preferred_name DESC, v.vernacular_name
                LIMIT ?
                """,
                (genus, genus, species, species, *lang_params, limit),
            )
            return [row[0] for row in cur.fetchall() if row and row[0]]

    def taxon_from_vernacular(self, name: str) -> tuple[str, str, str | None] | None:
        name = name.strip()
        if not name:
            return None
        lang_clause, lang_params = self._language_clause(None)
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT t.genus, t.specific_epithet, t.family
                FROM vernacular_min v
                JOIN taxon_min t ON t.taxon_id = v.taxon_id
                WHERE v.vernacular_name = ?
                """
                + lang_clause
                + """
                ORDER BY v.is_preferred_name DESC, v.vernacular_name
                LIMIT 1
                """,
                (name, *lang_params),
            )
            row = cur.fetchone()
            if not row:
                return None
            return row[0], row[1], row[2]

    def vernacular_from_taxon(self, genus: str, species: str) -> str | None:
        if not genus or not species:
            return None
        lang_clause, lang_params = self._language_clause(None)
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT v.vernacular_name
                FROM vernacular_min v
                JOIN taxon_min t ON t.taxon_id = v.taxon_id
                WHERE t.genus = ? COLLATE NOCASE
                  AND t.specific_epithet = ? COLLATE NOCASE
                """
                + lang_clause
                + """
                ORDER BY v.is_preferred_name DESC, v.vernacular_name
                LIMIT 1
                """,
                (genus, species, *lang_params),
            )
            row = cur.fetchone()
            return row[0] if row else None

    def suggest_genus(self, prefix: str) -> list[str]:
        prefix = prefix.strip()
        if not prefix:
            return []
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT DISTINCT genus
                FROM taxon_min
                WHERE genus LIKE ? || '%'
                ORDER BY genus
                LIMIT 200
                """,
                (prefix,),
            )
            return [row[0] for row in cur.fetchall() if row and row[0]]

    def suggest_species(self, genus: str, prefix: str) -> list[str]:
        genus = genus.strip()
        prefix = prefix.strip()
        if not genus:
            return []
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT DISTINCT specific_epithet
                FROM taxon_min
                WHERE genus = ?
                  AND specific_epithet LIKE ? || '%'
                ORDER BY specific_epithet
                LIMIT 200
                """,
                (genus, prefix),
            )
            return [row[0] for row in cur.fetchall() if row and row[0]]

class ReferenceValuesDialog(QDialog):
    """Dialog for editing reference spore size values."""

    plot_requested = Signal(dict)
    save_requested = Signal(dict)

    def __init__(self, genus, species, ref_values=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Reference Values"))
        self.setModal(True)
        self.setMinimumSize(440, 280)
        self.genus = genus or ""
        self.species = species or ""
        self.ref_values = ref_values or {}
        self._suppress_taxon_autofill = False
        self._last_genus = ""
        self._last_species = ""

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.vernacular_input = QLineEdit()
        self.genus_input = QLineEdit()
        self.species_input = QLineEdit()
        self.source_input = QComboBox()
        self.source_input.setEditable(True)
        self.source_input.setInsertPolicy(QComboBox.NoInsert)
        self.mount_input = QLineEdit(self.ref_values.get("mount_medium") or "")
        self.vernacular_label = QLabel(self._vernacular_label())
        form.addRow(self.vernacular_label, self.vernacular_input)
        form.addRow(self.tr("Genus:"), self.genus_input)
        form.addRow(self.tr("Species:"), self.species_input)
        form.addRow(self.tr("Source:"), self.source_input)
        form.addRow(self.tr("Mount medium:"), self.mount_input)
        layout.addLayout(form)

        self._genus_model = QStringListModel()
        self._species_model = QStringListModel()
        self._genus_completer = QCompleter(self._genus_model, self)
        self._genus_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._genus_completer.setCompletionMode(QCompleter.PopupCompletion)
        self._species_completer = QCompleter(self._species_model, self)
        self._species_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._species_completer.setCompletionMode(QCompleter.PopupCompletion)
        self.genus_input.setCompleter(self._genus_completer)
        self.species_input.setCompleter(self._species_completer)
        self._genus_completer.activated.connect(self._on_genus_selected)
        self._species_completer.activated.connect(self._on_species_selected)
        self.genus_input.textChanged.connect(self._on_genus_text_changed)
        self.species_input.textChanged.connect(self._on_species_text_changed)
        self.genus_input.editingFinished.connect(self._on_genus_editing_finished)
        self.species_input.editingFinished.connect(self._on_species_editing_finished)
        self.genus_input.installEventFilter(self)
        self.species_input.installEventFilter(self)

        self.vernacular_db = None
        lang = normalize_vernacular_language(SettingsDB.get_setting("vernacular_language", "no"))
        db_path = resolve_vernacular_db_path(lang)
        if db_path:
            self.vernacular_db = VernacularDB(db_path, language_code=lang)
        self._vernacular_model = QStringListModel()
        self._vernacular_completer = QCompleter(self._vernacular_model, self)
        self._vernacular_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._vernacular_completer.setCompletionMode(QCompleter.PopupCompletion)
        self.vernacular_input.setCompleter(self._vernacular_completer)
        self._vernacular_completer.activated.connect(self._on_vernacular_selected)
        self.vernacular_input.textChanged.connect(self._on_vernacular_text_changed)
        self.vernacular_input.editingFinished.connect(self._on_vernacular_editing_finished)
        self.vernacular_input.installEventFilter(self)

        self.table = QTableWidget(3, 5)
        self.table.setHorizontalHeaderLabels(
            [self.tr("Min"), self.tr("5%"), self.tr("50%"), self.tr("95%"), self.tr("Max")]
        )
        self.table.setVerticalHeaderLabels([self.tr("Length"), self.tr("Width"), self.tr("Q")])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.setMinimumHeight(120)
        layout.addWidget(self.table)

        info_label = QLabel(
            self.tr(
                "Percentiles assume an approximately normal distribution. "
                "The 50% column represents the median (middle value)."
            )
        )
        info_label.setStyleSheet("color: #7f8c8d; font-size: 9pt;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        def _set_cell(row, col, value):
            if value is None:
                return
            item = QTableWidgetItem(f"{value:g}")
            self.table.setItem(row, col, item)

        _set_cell(0, 0, self.ref_values.get("length_min"))
        _set_cell(0, 1, self.ref_values.get("length_p05"))
        _set_cell(0, 2, self.ref_values.get("length_p50"))
        _set_cell(0, 3, self.ref_values.get("length_p95"))
        _set_cell(0, 4, self.ref_values.get("length_max"))
        _set_cell(1, 0, self.ref_values.get("width_min"))
        _set_cell(1, 1, self.ref_values.get("width_p05"))
        _set_cell(1, 2, self.ref_values.get("width_p50"))
        _set_cell(1, 3, self.ref_values.get("width_p95"))
        _set_cell(1, 4, self.ref_values.get("width_max"))
        _set_cell(2, 0, self.ref_values.get("q_min"))
        _set_cell(2, 2, self.ref_values.get("q_p50"))
        _set_cell(2, 4, self.ref_values.get("q_max"))

        btn_row = QHBoxLayout()
        plot_btn = QPushButton(self.tr("Plot"))
        plot_btn.clicked.connect(self._on_plot_clicked)
        save_btn = QPushButton(self.tr("Save"))
        save_btn.clicked.connect(self._on_save_clicked)
        clear_btn = QPushButton(self.tr("Clear"))
        clear_btn.clicked.connect(self._on_clear_clicked)
        cancel_btn = QPushButton(self.tr("Cancel"))
        cancel_btn.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(plot_btn)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(clear_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        self._populate_genus(self.genus)
        self._populate_species(self.genus, self.species)
        self._populate_sources(self.genus, self.species, self.ref_values.get("source"))
        self._maybe_set_vernacular_from_taxon()
        self._maybe_load_reference()
        self._sync_taxon_cache()

        self.genus_input.textChanged.connect(self._on_genus_changed)
        self.species_input.textChanged.connect(self._on_species_changed)
        self.source_input.currentTextChanged.connect(self._on_source_changed)
        self.mount_input.textChanged.connect(self._on_mount_changed)

    def _vernacular_label(self) -> str:
        lang = normalize_vernacular_language(SettingsDB.get_setting("vernacular_language", "no"))
        base = self.tr("Common name")
        return f"{common_name_display_label(lang, base)}:"

    def apply_vernacular_language_change(self) -> None:
        if hasattr(self, "vernacular_label"):
            self.vernacular_label.setText(self._vernacular_label())
        lang = normalize_vernacular_language(SettingsDB.get_setting("vernacular_language", "no"))
        db_path = resolve_vernacular_db_path(lang)
        if not db_path:
            return
        if self.vernacular_db and self.vernacular_db.db_path == db_path:
            self.vernacular_db.language_code = lang
        else:
            self.vernacular_db = VernacularDB(db_path, language_code=lang)
        self._maybe_set_vernacular_from_taxon()

    def _cell_value(self, row, col):
        item = self.table.item(row, col)
        if not item:
            return None
        try:
            return float(item.text().strip())
        except ValueError:
            return None


    def get_data(self):
        return {
            "genus": self.genus_input.text().strip() or None,
            "species": self.species_input.text().strip() or None,
            "source": self.source_input.currentText().strip() or None,
            "mount_medium": self.mount_input.text().strip() or None,
            "length_min": self._cell_value(0, 0),
            "length_p05": self._cell_value(0, 1),
            "length_p50": self._cell_value(0, 2),
            "length_p95": self._cell_value(0, 3),
            "length_max": self._cell_value(0, 4),
            "width_min": self._cell_value(1, 0),
            "width_p05": self._cell_value(1, 1),
            "width_p50": self._cell_value(1, 2),
            "width_p95": self._cell_value(1, 3),
            "width_max": self._cell_value(1, 4),
            "q_min": self._cell_value(2, 0),
            "q_p50": self._cell_value(2, 2),
            "q_max": self._cell_value(2, 4),
        }

    def _has_species(self):
        data = self.get_data()
        return bool(data.get("genus") and data.get("species"))

    def _on_plot_clicked(self):
        data = self.get_data()
        self.plot_requested.emit(data)
        self.accept()

    def _on_save_clicked(self):
        data = self.get_data()
        if not (data.get("genus") and data.get("species")):
            QMessageBox.warning(
                self,
                self.tr("Missing Species"),
                self.tr("Please enter genus and species to save.")
            )
            return
        self.save_requested.emit(data)

    def _on_clear_clicked(self):
        self.vernacular_input.setText("")
        self.genus_input.setText("")
        self.species_input.setText("")
        self.source_input.setCurrentText("")
        self.mount_input.setText("")
        self._clear_table()
        self.plot_requested.emit({})

    def _populate_combo(self, combo, values, current):
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("")
        for value in values:
            combo.addItem(value)
        if current:
            idx = combo.findText(current)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            else:
                combo.setCurrentText(current)
        else:
            combo.setCurrentIndex(-1)
            combo.setEditText("")
        combo.blockSignals(False)

    def _populate_genus(self, current):
        self.genus_input.blockSignals(True)
        self.genus_input.setText(current or "")
        self.genus_input.blockSignals(False)
        self._update_genus_suggestions(current or "")

    def _populate_species(self, genus, current):
        self.species_input.blockSignals(True)
        self.species_input.setText(current or "")
        self.species_input.blockSignals(False)
        self._update_species_suggestions(genus or "", current or "")

    def _populate_sources(self, genus, species, current):
        values = ReferenceDB.list_sources(genus or "", species or "", current or "")
        self._populate_combo(self.source_input, values, current)

    def _clear_table(self):
        self.table.clearContents()

    def _on_genus_text_changed(self, text):
        if self._suppress_taxon_autofill:
            return
        self._update_genus_suggestions(text or "")
        if not text.strip():
            self._suppress_taxon_autofill = True
            self.species_input.setText("")
            self._suppress_taxon_autofill = False
            self._species_model.setStringList([])
            # Reset species completer filtering
            if self._species_completer:
                self._species_completer.setCompletionPrefix("")
        else:
            # Reset species completer filtering when genus changes
            if self._species_completer and not self.species_input.hasFocus():
                self._species_completer.setCompletionPrefix("")

    def _on_species_text_changed(self, text):
        if self._suppress_taxon_autofill:
            return
        genus = self.genus_input.text().strip()
        if not genus:
            self._species_model.setStringList([])
            return
        self._update_species_suggestions(genus, text or "")
        if text.strip():
            self._maybe_set_vernacular_from_taxon()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.FocusIn:
            if obj == self.vernacular_input:
                if not self.vernacular_input.text().strip():
                    # Reset completer filtering when focusing empty field
                    if self._vernacular_completer:
                        self._vernacular_completer.setCompletionPrefix("")
                    self._update_vernacular_suggestions_for_taxon()
                    if self._vernacular_model.stringList():
                        self._vernacular_completer.complete()
            elif obj == self.genus_input:
                text = self.genus_input.text().strip()
                self._update_genus_suggestions(text)
                if self._genus_model.stringList():
                    self._genus_completer.complete()
            elif obj == self.species_input:
                genus = self.genus_input.text().strip()
                if genus:
                    text = self.species_input.text().strip()
                    self._update_species_suggestions(genus, text)
                    if self._species_model.stringList():
                        self._species_completer.complete()
        return super().eventFilter(obj, event)

    def _load_reference(self, genus, species, source, mount_medium=None):
        ref = ReferenceDB.get_reference(genus, species, source, mount_medium)
        if not ref:
            return
        self._clear_table()
        self.mount_input.setText(ref.get("mount_medium") or "")

        def _set_cell(row, col, value):
            if value is None:
                return
            item = QTableWidgetItem(f"{value:g}")
            self.table.setItem(row, col, item)

        _set_cell(0, 0, ref.get("length_min"))
        _set_cell(0, 1, ref.get("length_p05"))
        _set_cell(0, 2, ref.get("length_p50"))
        _set_cell(0, 3, ref.get("length_p95"))
        _set_cell(0, 4, ref.get("length_max"))
        _set_cell(1, 0, ref.get("width_min"))
        _set_cell(1, 1, ref.get("width_p05"))
        _set_cell(1, 2, ref.get("width_p50"))
        _set_cell(1, 3, ref.get("width_p95"))
        _set_cell(1, 4, ref.get("width_max"))
        _set_cell(2, 0, ref.get("q_min"))
        _set_cell(2, 2, ref.get("q_p50"))
        _set_cell(2, 4, ref.get("q_max"))

    def _maybe_load_reference(self):
        genus = self.genus_input.text().strip()
        species = self.species_input.text().strip()
        source = self.source_input.currentText().strip()
        mount = self.mount_input.text().strip()

        if not (genus and species):
            return

        if source:
            if mount:
                ref = ReferenceDB.get_reference(genus, species, source, mount)
                if ref:
                    self._load_reference(genus, species, source, mount)
                    return
            mounts = ReferenceDB.list_mount_mediums(genus, species, source)
            if len(mounts) == 1:
                self.mount_input.setText(mounts[0] or "")
                self._load_reference(genus, species, source, mounts[0] if mounts else None)
                return
            ref = ReferenceDB.get_reference(genus, species, source)
            if ref:
                self._load_reference(genus, species, source)

    def _on_genus_changed(self, text):
        genus = text.strip()
        species = self.species_input.text().strip()
        self._populate_sources(genus, species, self.source_input.currentText().strip())
        self._clear_table()

    def _on_species_changed(self, text):
        genus = self.genus_input.text().strip()
        species = text.strip()
        sources = ReferenceDB.list_sources(genus, species, "")
        self._populate_sources(genus, species, self.source_input.currentText().strip())
        if len(sources) == 1:
            self.source_input.setCurrentText(sources[0])
        self._maybe_load_reference()

    def _on_source_changed(self, text):
        genus = self.genus_input.text().strip()
        species = self.species_input.text().strip()
        source = text.strip()
        if genus and species and source:
            self._maybe_load_reference()

    def _on_mount_changed(self, text):
        self._maybe_load_reference()

    def _on_vernacular_text_changed(self, text):
        if not self.vernacular_db:
            return
        if self._suppress_taxon_autofill:
            return
        if not text.strip():
            self._update_vernacular_suggestions_for_taxon()
            return
        genus = self.genus_input.text().strip() or None
        species = self.species_input.text().strip() or None
        suggestions = self.vernacular_db.suggest_vernacular(text, genus=genus, species=species)
        
        # If text exactly matches any suggestion, clear the model to prevent popup
        text_lower = text.strip().lower()
        if any(s.lower() == text_lower for s in suggestions):
            self._vernacular_model.setStringList([])
            if self._vernacular_completer:
                self._vernacular_completer.popup().hide()
        else:
            self._vernacular_model.setStringList(suggestions)

    def _update_vernacular_suggestions_for_taxon(self):
        if not self.vernacular_db:
            return
        genus = self.genus_input.text().strip() or None
        species = self.species_input.text().strip() or None
        if not genus and not species:
            self._vernacular_model.setStringList([])
            self._set_vernacular_placeholder_from_suggestions([])
            return
        suggestions = self.vernacular_db.suggest_vernacular_for_taxon(genus=genus, species=species)
        self._vernacular_model.setStringList(suggestions)
        self._set_vernacular_placeholder_from_suggestions(suggestions)

    def _set_vernacular_placeholder_from_suggestions(self, suggestions: list[str]) -> None:
        if not hasattr(self, "vernacular_input"):
            return
        if not suggestions:
            self.vernacular_input.setPlaceholderText("")
            return
        preview = "; ".join(suggestions[:4])
        self.vernacular_input.setPlaceholderText(f"{self.tr('e.g.,')} {preview}")

    def _on_vernacular_selected(self, name):
        # Hide the popup after selection
        if self._vernacular_completer:
            self._vernacular_completer.popup().hide()
        
        if not self.vernacular_db:
            return
        taxon = self.vernacular_db.taxon_from_vernacular(name)
        if taxon:
            genus, species, _family = taxon
            self._suppress_taxon_autofill = True
            self.genus_input.setText(genus)
            self.species_input.setText(species)
            self._suppress_taxon_autofill = False
            self._sync_taxon_cache()

    def _on_vernacular_editing_finished(self):
        if not self.vernacular_db:
            return
        name = self.vernacular_input.text().strip()
        if not name:
            return
        taxon = self.vernacular_db.taxon_from_vernacular(name)
        if taxon:
            genus, species, _family = taxon
            self._suppress_taxon_autofill = True
            self.genus_input.setText(genus)
            self.species_input.setText(species)
            self._suppress_taxon_autofill = False
            self._sync_taxon_cache()

    def _on_genus_selected(self, genus):
        """Handle genus selection from completer."""
        # Hide the popup after selection
        if self._genus_completer:
            self._genus_completer.popup().hide()

    def _on_species_selected(self, species):
        """Handle species selection from completer."""
        # Hide the popup after selection
        if self._species_completer:
            self._species_completer.popup().hide()
        
        # Update vernacular name suggestions
        if self.vernacular_db:
            self._maybe_set_vernacular_from_taxon()

    def _on_genus_editing_finished(self):
        if not self.vernacular_db or self._suppress_taxon_autofill:
            return
        self._handle_taxon_change()
        self._maybe_set_vernacular_from_taxon()

    def _on_species_editing_finished(self):
        if not self.vernacular_db or self._suppress_taxon_autofill:
            return
        self._handle_taxon_change()
        self._maybe_set_vernacular_from_taxon()

    def _handle_taxon_change(self):
        if not hasattr(self, "_last_genus"):
            self._sync_taxon_cache()
            return
        genus = self.genus_input.text().strip()
        species = self.species_input.text().strip()
        if genus != self._last_genus or species != self._last_species:
            if genus and species and self.vernacular_input.text().strip():
                self._suppress_taxon_autofill = True
                self.vernacular_input.setText("")
                self._suppress_taxon_autofill = False
                # Reset vernacular completer filtering after clearing
                if self._vernacular_completer:
                    self._vernacular_completer.setCompletionPrefix("")
        self._last_genus = genus
        self._last_species = species

    def _sync_taxon_cache(self):
        self._last_genus = self.genus_input.text().strip()
        self._last_species = self.species_input.text().strip()

    def _maybe_set_vernacular_from_taxon(self):
        if not self.vernacular_db:
            return
        if self.vernacular_input.text().strip():
            return
        genus = self.genus_input.text().strip()
        species = self.species_input.text().strip()
        if not genus or not species:
            return
        suggestions = self.vernacular_db.suggest_vernacular_for_taxon(genus=genus, species=species)
        if not suggestions:
            self._set_vernacular_placeholder_from_suggestions([])
            return
        if len(suggestions) == 1:
            self._suppress_taxon_autofill = True
            self.vernacular_input.setText(suggestions[0])
            self._suppress_taxon_autofill = False
            self._set_vernacular_placeholder_from_suggestions([])
        else:
            self._set_vernacular_placeholder_from_suggestions(suggestions)

    def _update_genus_suggestions(self, text):
        if self.vernacular_db:
            values = self.vernacular_db.suggest_genus(text)
        else:
            values = ReferenceDB.list_genera(text or "")
        
        # If text exactly matches a single suggestion, clear the model to prevent popup
        text_stripped = text.strip()
        if len(values) == 1 and values[0].lower() == text_stripped.lower():
            self._genus_model.setStringList([])
            if self._genus_completer:
                self._genus_completer.popup().hide()
        else:
            self._genus_model.setStringList(values)

    def _update_species_suggestions(self, genus, text):
        if self.vernacular_db:
            values = self.vernacular_db.suggest_species(genus, text)
        else:
            values = ReferenceDB.list_species(genus or "", text or "")
        
        # If text exactly matches a single suggestion, clear the model to prevent popup
        text_stripped = text.strip()
        if len(values) == 1 and values[0].lower() == text_stripped.lower():
            self._species_model.setStringList([])
            if self._species_completer:
                self._species_completer.popup().hide()
        else:
            self._species_model.setStringList(values)

class MainWindow(QMainWindow):
    """Main application window with modern UI and measurement table."""

    def __init__(self, app_version: str | None = None):
        super().__init__()
        self.setWindowTitle("MycoLog")
        self.setGeometry(100, 100, 1600, 900)
        self.app_version = app_version or ""
        self._update_check_started = False
        self._pixmap_cache: dict[str, QPixmap] = {}
        self._pixmap_cache_order: list[str] = []
        self._pixmap_cache_max = 6
        self._pixmap_cache_observation_id = None

        self.current_image_path = None
        self.current_image_id = None
        self.current_pixmap = None
        self.points = []  # Will store 4 points for two measurements
        self.measurement_lines = {}  # Dict mapping measurement_id -> [line1, line2]
        self.temp_lines = []  # Temporary lines for current measurement in progress
        self.measure_mode = "rectangle"
        self.measurements_cache = []
        self.rect_stage = 0
        self.rect_line1_start = None
        self.rect_line1_end = None
        self.rect_line2_start = None
        self.rect_line2_end = None
        self.rect_width_dir = None
        self.rect_length_dir = None
        self.rect_length_dir = None

        # Current objective settings
        self.current_objective = None
        self.current_objective_name = None
        self.microns_per_pixel = 0.5

        # Active observation tracking
        self.active_observation_id = None
        self.active_observation_name = None
        self.observation_images = []

        # Gallery thumbnail rotation tracking (measurement_id -> extra rotation in degrees)
        self.gallery_rotations = {}
        self.current_image_index = -1
        self.export_scale_percent = 100.0
        self.export_format = "png"
        self.default_measure_color = QColor("#1E90FF")
        self.measure_color = QColor(self.default_measure_color)
        self.measurement_labels = []
        self.measurement_active = False
        self._auto_started_for_microscope = False
        self.auto_threshold = None
        self.auto_threshold_default = 0.12
        self.auto_gray_cache = None
        self.auto_gray_cache_id = None
        self.auto_max_radius = None
        self.gallery_filter_mode = None
        self.gallery_filter_value = None
        self.gallery_filter_ids = set()
        self._last_gallery_category = None
        self._pending_gallery_category = None
        self._suppress_gallery_update = False
        self._gallery_refresh_in_progress = False
        self._gallery_refresh_timer = None
        self._gallery_refresh_pending = False
        self._gallery_last_refresh_time = 0.0
        self.loading_dialog = None
        self.reference_values = {}
        self.suppress_scale_prompt = False
        self._measure_category_sync = False

        # Calibration mode tracking
        self.calibration_mode = False
        self.calibration_dialog = None
        self.calibration_points = []

        # Apply modern stylesheet
        self.setStyleSheet(MODERN_STYLE)

        self.init_ui()
        self._populate_scale_combo()
        self.load_default_objective()

    def eventFilter(self, obj, event):
        """Show certain tooltips immediately on hover."""
        if obj.property("instant_tooltip"):
            if event.type() == QEvent.Enter:
                tip = obj.toolTip()
                if tip:
                    QToolTip.showText(obj.mapToGlobal(QPoint(0, obj.height())), tip, obj)
            elif event.type() == QEvent.Leave:
                QToolTip.hideText()
        return super().eventFilter(obj, event)

    def init_ui(self):
        """Initialize the user interface."""
        # Create menu bar
        self.create_menu_bar()

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # Observation header
        self.observation_header_label = QLabel("")
        self.observation_header_label.setStyleSheet(
            "font-size: 12pt; font-weight: bold; color: #2c3e50;"
        )
        self.observation_header_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        main_layout.addWidget(self.observation_header_label)

        # Main tabbed interface (takes full width)
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabPosition(QTabWidget.North)
        self.tab_widget.currentChanged.connect(self.on_tab_changed)
        # Observations tab (new - first tab)
        self.observations_tab = ObservationsTab()
        self.observations_tab.observation_selected.connect(self.on_observation_selected)
        self.observations_tab.image_selected.connect(self.on_image_selected)
        self.tab_widget.addTab(self.observations_tab, self.tr("Observations"))

        # Measure tab (includes control panel on left and stats panel on right)
        measure_tab = self.create_measure_tab()
        self.tab_widget.addTab(measure_tab, self.tr("Measure"))

        # Analysis tab
        gallery_tab = self.create_gallery_panel()
        self.tab_widget.addTab(gallery_tab, self.tr("Analysis"))
        self.refresh_gallery_filter_options()

        main_layout.addWidget(self.tab_widget, 1)

    def create_menu_bar(self):
        """Create the menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu(self.tr("File"))

        export_ml_action = QAction(self.tr("Export ML"), self)
        export_handler = getattr(self, "export_ml_dataset", None)
        if export_handler is None:
            export_handler = lambda: QMessageBox.warning(
                self,
                self.tr("Export Unavailable"),
                self.tr("Export ML is not available.")
            )
        export_ml_action.triggered.connect(export_handler)
        file_menu.addAction(export_ml_action)

        export_inat_action = QAction(self.tr("Export iNaturalist"), self)
        export_inat_action.triggered.connect(
            lambda: self.show_export_placeholder("iNaturalist")
        )
        file_menu.addAction(export_inat_action)

        export_arts_action = QAction(self.tr("Export Artsobservasjoner"), self)
        export_arts_action.triggered.connect(
            lambda: self.show_export_placeholder("Artsobservasjoner")
        )
        file_menu.addAction(export_arts_action)

        export_db_action = QAction(self.tr("Export DB"), self)
        export_db_action.triggered.connect(self.export_database_bundle)
        file_menu.addAction(export_db_action)

        import_db_action = QAction(self.tr("Import DB"), self)
        import_db_action.triggered.connect(self.import_database_bundle)
        file_menu.addAction(import_db_action)

        file_menu.addSeparator()

        exit_action = QAction(self.tr("Exit"), self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        settings_menu = menubar.addMenu(self.tr("Settings"))
        profile_action = QAction(self.tr("User profile"), self)
        profile_action.triggered.connect(self.open_profile_dialog)
        settings_menu.addAction(profile_action)
        database_action = QAction(self.tr("Database"), self)
        database_action.triggered.connect(self.open_database_settings_dialog)
        settings_menu.addAction(database_action)
        calib_action = QAction(self.tr("Calibration"), self)
        calib_action.setShortcut("Ctrl+K")
        calib_action.triggered.connect(self.open_calibration_dialog)
        settings_menu.addAction(calib_action)

        language_action = QAction(self.tr("Language"), self)
        language_action.triggered.connect(self.open_language_settings_dialog)
        settings_menu.addAction(language_action)

        help_menu = menubar.addMenu(self.tr("Help"))
        version_text = self.tr("Version: {version}").format(
            version=self.app_version or self.tr("Unknown")
        )
        version_action = QAction(version_text, self)
        version_action.setEnabled(False)
        help_menu.addAction(version_action)

        release_action = QAction(self.tr("Open latest release"), self)
        release_action.triggered.connect(
            lambda: QDesktopServices.openUrl(
                QUrl("https://github.com/sigmundas/mycolog/releases/latest")
            )
        )
        help_menu.addAction(release_action)

    def start_update_check(self):
        """Check GitHub for newer releases without blocking the UI."""
        if self._update_check_started:
            return
        self._update_check_started = True
        current_version = self._parse_version(self.app_version)
        if current_version is None:
            return
        if not hasattr(self, "_update_network"):
            self._update_network = QNetworkAccessManager(self)
        
        # Use Atom feed instead of API - no rate limits!
        req = QNetworkRequest(QUrl("https://github.com/sigmundas/mycolog/releases.atom"))
        req.setHeader(QNetworkRequest.UserAgentHeader, f"MycoLog/{self.app_version}")
        
        reply = self._update_network.get(req)
        reply.finished.connect(
            lambda: self._handle_atom_reply(reply, current_version)
        )

    def _handle_atom_reply(self, reply: QNetworkReply, current_version: tuple[int, ...]):
        """Handle Atom feed response from GitHub releases."""
        try:
            if reply.error() != QNetworkReply.NoError:
                return  # Silently fail - update check is non-critical
            
            payload = bytes(reply.readAll())
            
            # Parse XML properly
            from xml.etree import ElementTree as ET
            root = ET.fromstring(payload.decode("utf-8"))
            
            # Atom namespace
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            
            # Find first entry (latest release)
            entry = root.find('atom:entry', ns)
            if entry is None:
                return
            
            title_elem = entry.find('atom:title', ns)
            link_elem = entry.find('atom:link[@rel="alternate"]', ns)
            
            if title_elem is None or link_elem is None:
                return
            
            title = title_elem.text.strip()
            url = link_elem.get('href', '').strip()
            
            # Extract version from title (e.g., "v0.2.2" -> "0.2.2")
            version = title.lower().replace("release", "").strip().lstrip("v").strip()
            
            if self._is_newer_version(version, current_version):
                self._show_update_dialog(version, url)
                
        except Exception:
            pass  # Silently fail - update check is non-critical
        finally:
            reply.deleteLater()


    def _parse_version(self, version: str | None) -> tuple[int, ...] | None:
        if not version:
            return None
        raw = str(version).strip()
        if raw.startswith("v"):
            raw = raw[1:]
        raw = raw.split("-", 1)[0].split("+", 1)[0]
        parts = raw.split(".")
        if not parts:
            return None
        values = []
        for part in parts:
            if not part.isdigit():
                return None
            values.append(int(part))
        return tuple(values)

    def _is_newer_version(self, latest: str, current: tuple[int, ...]) -> bool:
        latest_parsed = self._parse_version(latest)
        if latest_parsed is None:
            return False
        max_len = max(len(latest_parsed), len(current))
        latest_padded = latest_parsed + (0,) * (max_len - len(latest_parsed))
        current_padded = current + (0,) * (max_len - len(current))
        return latest_padded > current_padded

    def _show_update_dialog(self, latest_version: str, url: str):
        current = self.app_version or self.tr("Unknown")
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Information)
        box.setWindowTitle(self.tr("Update available"))
        box.setText(self.tr("A newer version of MycoLog is available."))
        box.setInformativeText(
            self.tr("Current version: {current}\nLatest version: {latest}").format(
                current=current,
                latest=latest_version
            )
        )
        open_btn = box.addButton(self.tr("Open download page"), QMessageBox.AcceptRole)
        box.addButton(self.tr("Later"), QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() == open_btn:
            QDesktopServices.openUrl(QUrl(url))

    def create_control_panel(self):
        """Create the left control panel."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(10)

        # Image loading group
        # Import/Export now available from the top menus

        # Scale group
        calib_group = QGroupBox(self.tr("Scale"))
        self.calib_group = calib_group
        calib_layout = QVBoxLayout()

        self.scale_combo = QComboBox()
        self.scale_combo.currentIndexChanged.connect(self.on_scale_combo_changed)
        calib_layout.addWidget(self.scale_combo)

        self.calib_info_label = QLabel("No objective")
        self.calib_info_label.setWordWrap(True)
        self.calib_info_label.setStyleSheet("color: #7f8c8d; font-size: 9pt;")
        self.calib_info_label.setTextFormat(Qt.RichText)
        self.calib_info_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.calib_info_label.setOpenExternalLinks(False)
        self.calib_info_label.linkActivated.connect(self._on_calibration_link_clicked)
        calib_layout.addWidget(self.calib_info_label)

        calib_group.setLayout(calib_layout)
        layout.addWidget(calib_group)

        # Measurement category group
        category_group = QGroupBox(self.tr("Measure Category"))
        category_layout = QVBoxLayout()

        self.measure_category_combo = QComboBox()
        self._populate_measure_categories()
        self.measure_category_combo.currentIndexChanged.connect(self.on_measure_category_changed)
        category_layout.addWidget(self.measure_category_combo)

        category_group.setLayout(category_layout)
        layout.addWidget(category_group)

        # Measurement group
        measure_group = QGroupBox(self.tr("Measure"))
        measure_layout = QVBoxLayout()

        action_row = QHBoxLayout()
        self.measure_button = QPushButton(self.tr("Start measuring"))
        self.measure_button.setCheckable(True)
        self.measure_button.setStyleSheet("font-weight: bold; padding: 6px 10px;")
        self.measure_button.clicked.connect(self._on_measure_button_clicked)
        action_row.addWidget(self.measure_button)
        action_row.addStretch()
        measure_layout.addLayout(action_row)

        mode_row = QHBoxLayout()
        self.mode_group = QButtonGroup(self)
        self.mode_lines = QRadioButton(self.tr("Lines"))
        self.mode_rect = QRadioButton(self.tr("Rectangle"))
        self.mode_rect.setChecked(True)
        self.mode_group.addButton(self.mode_lines)
        self.mode_group.addButton(self.mode_rect)
        self.mode_lines.toggled.connect(self.on_measure_mode_changed)
        self.mode_rect.toggled.connect(self.on_measure_mode_changed)
        mode_row.addWidget(self.mode_lines)
        mode_row.addWidget(self.mode_rect)
        mode_row.addStretch()
        measure_layout.addLayout(mode_row)

        palette_row = QHBoxLayout()
        palette_row.addWidget(QLabel("Color:"))
        self.color_button_group = QButtonGroup(self)
        self.color_button_group.setExclusive(True)
        self.measure_color_buttons = []
        palette_colors = [
            ("Blue", QColor("#1E90FF")),
            ("Red", QColor("#FF3B30")),
            ("Green", QColor("#2ECC71")),
            ("Magenta", QColor("#E056FD")),
            ("Orange", QColor("#ECAF11")),
            ("Cyan", QColor("#1CEBEB")),
            ("Black", QColor("#000000")),
        ]
        for name, color in palette_colors:
            btn = QPushButton()
            btn.setFixedSize(18, 18)
            btn.setCheckable(True)
            btn.clicked.connect(lambda _, c=color: self.set_measure_color(c))
            self.color_button_group.addButton(btn)
            self.measure_color_buttons.append((btn, color))
            palette_row.addWidget(btn)
        palette_row.addStretch()
        measure_layout.addLayout(palette_row)

        self.set_measure_color(self.measure_color)

        self.measure_status_label = QLabel("")
        self.measure_status_label.setWordWrap(True)
        self.measure_status_label.setStyleSheet("color: #27ae60; font-weight: bold; font-size: 9pt;")
        self.measure_status_label.setVisible(True)
        measure_layout.addWidget(self.measure_status_label)

        measure_group.setLayout(measure_layout)
        layout.addWidget(measure_group)

        # Zoom controls
        zoom_group = QGroupBox(self.tr("View"))
        zoom_layout = QVBoxLayout()
        view_buttons_row = QHBoxLayout()

        reset_btn = QPushButton(self.tr("Reset"))
        reset_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        reset_btn.setStyleSheet("font-size: 8pt; padding: 4px 6px;")
        reset_btn.clicked.connect(self.reset_view)
        view_buttons_row.addWidget(reset_btn)

        export_image_btn = QPushButton(self.tr("Export image"))
        export_image_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        export_image_btn.setStyleSheet("font-size: 8pt; padding: 4px 6px;")
        export_image_btn.clicked.connect(self.export_annotated_image)
        view_buttons_row.addWidget(export_image_btn)
        view_buttons_row.setStretch(0, 1)
        view_buttons_row.setStretch(1, 1)
        zoom_layout.addLayout(view_buttons_row)

        self.show_measures_checkbox = QCheckBox(self.tr("Show measures"))
        self.show_measures_checkbox.toggled.connect(self.on_show_measures_toggled)
        zoom_layout.addWidget(self.show_measures_checkbox)

        self.show_rectangles_checkbox = QCheckBox(self.tr("Show rectangles"))
        self.show_rectangles_checkbox.setChecked(True)
        self.show_rectangles_checkbox.toggled.connect(self.on_show_rectangles_toggled)
        zoom_layout.addWidget(self.show_rectangles_checkbox)

        self.show_scale_bar_checkbox = QCheckBox(self.tr("Show scale bar"))
        self.show_scale_bar_checkbox.toggled.connect(self.on_show_scale_bar_toggled)
        zoom_layout.addWidget(self.show_scale_bar_checkbox)

        scale_bar_row = QHBoxLayout()
        self.scale_bar_input = QDoubleSpinBox()
        self.scale_bar_input.setRange(0.1, 100000.0)
        self.scale_bar_input.setDecimals(2)
        self.scale_bar_input.setValue(10.0)
        self.scale_bar_input.setSingleStep(1.0)
        self.scale_bar_input.valueChanged.connect(self.on_scale_bar_value_changed)
        scale_bar_row.addWidget(self.scale_bar_input)
        scale_bar_row.addWidget(QLabel("μm"))
        scale_bar_row.addStretch()
        self.scale_bar_container = QWidget()
        scale_bar_layout = QHBoxLayout(self.scale_bar_container)
        scale_bar_layout.setContentsMargins(0, 0, 0, 0)
        scale_bar_layout.addLayout(scale_bar_row)
        self.scale_bar_container.setVisible(False)
        zoom_layout.addWidget(self.scale_bar_container)

        zoom_group.setLayout(zoom_layout)
        layout.addWidget(zoom_group)

        info_group = QGroupBox(self.tr("Info"))
        info_layout = QVBoxLayout()
        self.exif_info_label = QLabel("No image loaded")
        self.exif_info_label.setWordWrap(True)
        self.exif_info_label.setStyleSheet("color: #2c3e50; font-size: 8pt;")
        self.exif_info_label.setTextFormat(Qt.RichText)
        self.exif_info_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.exif_info_label.setOpenExternalLinks(True)
        info_layout.addWidget(self.exif_info_label)
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        layout.addStretch()
        self.update_measurement_button_state()
        return panel

    def create_measure_tab(self):
        """Create the measure tab with control panel, image panel, and stats panel."""
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)

        self.measure_tab = tab

        # Left panel - controls (fixed width)
        left_panel = self.create_control_panel()
        left_panel.setMaximumWidth(250)
        left_panel.setMinimumWidth(250)
        layout.addWidget(left_panel)

        # Center - image panel
        image_panel = self.create_image_panel()
        layout.addWidget(image_panel, 1)

        # Right panel - Stats and measurements table (fixed width)
        right_panel = self.create_right_panel()
        right_panel.setMaximumWidth(340)
        right_panel.setMinimumWidth(340)
        layout.addWidget(right_panel)

        self.next_image_shortcut = QShortcut(QKeySequence(Qt.Key_N), tab)
        self.next_image_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        self.next_image_shortcut.activated.connect(self.goto_next_image)

        self.prev_image_shortcut = QShortcut(QKeySequence(Qt.Key_P), tab)
        self.prev_image_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        self.prev_image_shortcut.activated.connect(self.goto_previous_image)

        self.start_measurement()
        return tab

    def create_image_panel(self):
        """Create the image panel with zoomable image."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        self.image_label = ZoomableImageLabel()
        self.image_label.setObjectName("imageLabel")
        self.image_label.setMinimumSize(800, 400)
        self.image_label.clicked.connect(self.image_clicked)
        self.image_label.set_measurement_color(self.measure_color)
        self.image_label.set_measurement_active(self.measurement_active)
        self.image_label.set_pan_without_shift(not self.measurement_active)
        if hasattr(self, "show_measures_checkbox"):
            self.image_label.set_show_measure_labels(self.show_measures_checkbox.isChecked())
        if hasattr(self, "show_rectangles_checkbox"):
            self.image_label.set_show_measure_overlays(self.show_rectangles_checkbox.isChecked())

        self.measure_gallery = ImageGalleryWidget(
            self.tr("Images"),
            self,
            show_delete=False,
            show_badges=False,
            min_height=50,
            default_height=220,
        )
        self.measure_gallery.imageClicked.connect(self._on_measure_gallery_clicked)

        splitter = QSplitter(Qt.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self.image_label)
        splitter.addWidget(self.measure_gallery)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([700, 220])

        layout.addWidget(splitter)
        return panel

    def create_gallery_panel(self):
        """Create the gallery panel showing all measured spores in a grid."""
        from PySide6.QtWidgets import QScrollArea, QGridLayout, QCheckBox

        panel = QWidget()
        main_layout = QVBoxLayout(panel)
        main_layout.setContentsMargins(10, 10, 10, 10)

        splitter = QSplitter(Qt.Horizontal)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        left_controls = QHBoxLayout()
        left_controls.addWidget(QLabel("Measurement Type:"))
        self.gallery_filter_combo = QComboBox()
        self.gallery_filter_combo.setFixedWidth(140)
        self.gallery_filter_combo.currentIndexChanged.connect(self.on_gallery_thumbnail_setting_changed)
        left_controls.addWidget(self.gallery_filter_combo)

        self.gallery_plot_settings = {
            "bins": 8,
            "ci": True,
            "legend": False,
            "avg_q": True,
            "q_minmax": True,
            "x_min": None,
            "x_max": None,
            "y_min": None,
            "y_max": None,
        }

        plot_settings_btn = QPushButton(self.tr("Plot settings"))
        plot_settings_btn.clicked.connect(self.open_gallery_plot_settings)
        left_controls.addWidget(plot_settings_btn)

        plot_export_btn = QPushButton(self.tr("Export Plot"))
        plot_export_btn.clicked.connect(self.export_graph_plot_svg)
        left_controls.addWidget(plot_export_btn)

        reference_btn = QPushButton(self.tr("Reference Values"))
        reference_btn.clicked.connect(self.open_reference_values_dialog)
        left_controls.addWidget(reference_btn)

        left_controls.addStretch()
        left_layout.addLayout(left_controls)

        self.gallery_stats_label = QLabel("")
        self.gallery_stats_label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        self.gallery_stats_label.setWordWrap(False)
        self.gallery_stats_label.setMaximumHeight(22)
        self.gallery_stats_label.setMinimumHeight(22)
        self.gallery_stats_label.setStyleSheet("color: #2c3e50; font-size: 9pt;")
        left_layout.addWidget(self.gallery_stats_label)

        self.gallery_plot_figure = Figure(figsize=(6, 3.8))
        self.gallery_plot_canvas = FigureCanvas(self.gallery_plot_figure)
        self.gallery_plot_canvas.mpl_connect("pick_event", self.on_gallery_plot_pick)
        left_layout.addWidget(self.gallery_plot_canvas)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        right_controls = QHBoxLayout()
        right_controls.addWidget(QLabel("Columns:"))
        self.gallery_columns_spin = QSpinBox()
        self.gallery_columns_spin.setRange(1, 12)
        self.gallery_columns_spin.setValue(4)
        self.gallery_columns_spin.valueChanged.connect(self.on_gallery_thumbnail_setting_changed)
        right_controls.addWidget(self.gallery_columns_spin)

        self.orient_checkbox = QCheckBox(self.tr("Orient"))
        self.orient_checkbox.setToolTip("Rotate thumbnails so length axis is vertical")
        self.orient_checkbox.stateChanged.connect(self.on_gallery_thumbnail_setting_changed)
        right_controls.addWidget(self.orient_checkbox)

        self.uniform_scale_checkbox = QCheckBox(self.tr("Uniform scale"))
        self.uniform_scale_checkbox.setToolTip("Use the same scale for all thumbnails")
        self.uniform_scale_checkbox.stateChanged.connect(self.on_gallery_thumbnail_setting_changed)
        right_controls.addWidget(self.uniform_scale_checkbox)

        export_btn = QPushButton(self.tr("Export Thumbnails"))
        export_btn.clicked.connect(self.export_gallery_composite)
        right_controls.addWidget(export_btn)
        self.clear_filter_btn = QPushButton(self.tr("Clear Filter"))
        self.clear_filter_btn.clicked.connect(self.clear_gallery_filter)
        right_controls.addWidget(self.clear_filter_btn)
        self.gallery_filter_label = QLabel("")
        self.gallery_filter_label.setStyleSheet("color: #7f8c8d; font-size: 9pt;")
        right_controls.addWidget(self.gallery_filter_label)
        right_controls.addStretch()
        right_layout.addLayout(right_controls)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self.gallery_container = QWidget()
        self.gallery_grid = QGridLayout(self.gallery_container)
        self.gallery_grid.setSpacing(10)
        self.gallery_grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        scroll.setWidget(self.gallery_container)
        right_layout.addWidget(scroll)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        main_layout.addWidget(splitter)

        return panel

    def create_right_panel(self):
        """Create the right panel with statistics, preview, and measurements table."""
        from PySide6.QtWidgets import QScrollArea, QGridLayout

        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(5)
        layout.setContentsMargins(0, 0, 0, 0)

        # Measurement preview group
        self.preview_group = QGroupBox("Measurement Preview")
        preview_layout = QVBoxLayout()
        preview_layout.setContentsMargins(5, 5, 5, 5)

        self.spore_preview = SporePreviewWidget()
        self.spore_preview.dimensions_changed.connect(self.on_dimensions_changed)
        self.spore_preview.delete_requested.connect(self.delete_measurement)
        self.spore_preview.set_measure_color(self.measure_color)
        preview_layout.addWidget(self.spore_preview)

        self.calibration_apply_btn = QPushButton(self.tr("Set Scale"))
        self.calibration_apply_btn.setVisible(False)
        self.calibration_apply_btn.clicked.connect(self.apply_calibration_scale)
        preview_layout.addWidget(self.calibration_apply_btn)

        self.preview_group.setLayout(preview_layout)
        layout.addWidget(self.preview_group)
        self._update_preview_title()

        # Measurements table group
        measurements_group = QGroupBox("Measurements")
        measurements_layout = QVBoxLayout()
        measurements_layout.setContentsMargins(5, 5, 5, 5)

        self.measurements_table = QTableWidget()
        self.measurements_table.setColumnCount(5)
        self.measurements_table.setHorizontalHeaderLabels(["Image", "Category", "L", "W", "Q"])

        # Set column widths
        header = self.measurements_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)

        self.measurements_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.measurements_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.measurements_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.measurements_table.setAlternatingRowColors(True)
        self.measurements_table.setStyleSheet("""
            QTableWidget::item:selected {
                background-color: #2980b9;
                color: white;
            }
            QTableWidget::item:selected:!active {
                background-color: #3498db;
                color: white;
            }
        """)
        self.measurements_table.itemSelectionChanged.connect(self.on_measurement_selected)

        measurements_layout.addWidget(self.measurements_table)

        measurements_group.setLayout(measurements_layout)
        layout.addWidget(measurements_group)

        return panel

    def load_default_objective(self):
        """Load the default or last used objective."""
        dialog = CalibrationDialog(self)
        objective = dialog.get_last_used_objective()
        if objective:
            self.apply_objective(objective)

    def open_calibration_dialog(self, select_custom=False, objective_key=None, calibration_id=None):
        """Open the calibration dialog."""
        dialog = CalibrationDialog(self)
        if select_custom:
            dialog.select_custom_tab()
        if objective_key:
            dialog.select_objective_key(objective_key)
        if calibration_id:
            dialog.select_calibration(calibration_id)
        dialog.calibration_saved.connect(self._on_calibration_saved_from_dialog)
        return dialog.exec() == QDialog.Accepted

    def _on_calibration_link_clicked(self, _link: str) -> None:
        objective_key = getattr(self, "_calib_link_objective_key", None)
        calibration_id = getattr(self, "_calib_link_calibration_id", None)
        if not objective_key or not calibration_id:
            return
        self.open_calibration_dialog(
            select_custom=False,
            objective_key=objective_key,
            calibration_id=calibration_id,
        )

    def _on_calibration_saved_from_dialog(self, objective: dict) -> None:
        if self.active_observation_id:
            self._refresh_active_observation_after_calibration()
            return
        self.apply_objective(objective)

    def _refresh_active_observation_after_calibration(self) -> None:
        if not self.active_observation_id:
            return
        display_name = self.active_observation_name
        if not display_name:
            obs = ObservationDB.get_observation(self.active_observation_id)
            if obs:
                display_name = obs.get("display_name") or obs.get("name") or obs.get("species") or ""
        if not display_name:
            display_name = f"Observation {self.active_observation_id}"
        self._on_observation_selected_impl(
            self.active_observation_id,
            display_name,
            switch_tab=False,
            schedule_gallery=True,
        )

    def _populate_scale_combo(self, selected_key=None):
        """Populate the scale combo with objectives and Custom."""
        if not hasattr(self, "scale_combo"):
            return
        objectives = self.load_objective_definitions()

        def _sort_key(item):
            key, obj = item
            match = re.search(r"(\d+)", str(key))
            return int(match.group(1)) if match else 9999

        self.scale_combo.blockSignals(True)
        self.scale_combo.clear()
        for key, obj in sorted(objectives.items(), key=_sort_key):
            label = obj.get("name") or obj.get("magnification") or key
            self.scale_combo.addItem(label, key)
        self.scale_combo.addItem("Scale bar", "custom")
        if selected_key is None:
            selected_key = self.current_objective_name
        if selected_key:
            idx = self.scale_combo.findData(selected_key)
            if idx >= 0:
                self.scale_combo.setCurrentIndex(idx)
        self.scale_combo.blockSignals(False)
        self._last_scale_combo_key = self.scale_combo.currentData()

    def on_scale_combo_changed(self):
        """Handle objective selection from the scale combo."""
        if not hasattr(self, "scale_combo"):
            return
        previous_key = getattr(self, "_last_scale_combo_key", None)
        selected_key = self.scale_combo.currentData()
        if selected_key == "custom":
            dialog = ScaleBarCalibrationDialog(self, previous_key=previous_key)
            dialog.show()
            return

        if not selected_key:
            return
        objectives = self.load_objective_definitions()
        objective = objectives.get(selected_key)
        if objective:
            if not self.apply_objective(objective):
                self.scale_combo.blockSignals(True)
                if previous_key is None:
                    self.scale_combo.setCurrentIndex(0)
                else:
                    idx = self.scale_combo.findData(previous_key)
                    if idx >= 0:
                        self.scale_combo.setCurrentIndex(idx)
                self.scale_combo.blockSignals(False)
                return
            self._last_scale_combo_key = selected_key

    def apply_objective(self, objective):
        """Apply an objective's settings."""
        old_scale = self.microns_per_pixel
        previous_key = self.current_objective_name
        new_scale = objective.get("microns_per_pixel", 0.5)
        if not self._maybe_rescale_current_image(old_scale, new_scale):
            self._populate_scale_combo(previous_key)
            return False
        self.current_objective = objective
        self.current_objective_name = objective.get("magnification") or objective.get("name")
        self.microns_per_pixel = new_scale

        # Update calibration info
        mag = objective.get("magnification", "Unknown")
        scale_nm = self.microns_per_pixel * 1000.0
        self.calib_info_label.setText(f"{mag}: {scale_nm:.2f} nm/px")
        self._calib_link_objective_key = None
        self._calib_link_calibration_id = None

        # Update image overlay
        if self.current_pixmap:
            self.image_label.set_objective_text(mag)
            self.image_label.set_objective_color(self._objective_color_for_name(mag))
        self.image_label.set_microns_per_pixel(self.microns_per_pixel)

        if self.current_image_id:
            ImageDB.update_image(
                self.current_image_id,
                scale=self.microns_per_pixel,
                objective_name=self.current_objective_name
            )
        self._populate_scale_combo(self.current_objective_name)
        self._last_scale_combo_key = self.current_objective_name
        return True

    def load_objective_definitions(self):
        """Load objective definitions from the calibration database."""
        return load_objectives()

    def set_custom_scale(self, scale, warning_text=None):
        """Apply a custom scale and optionally warn about mismatches."""
        old_scale = self.microns_per_pixel
        previous_key = self.current_objective_name
        if not self._maybe_rescale_current_image(old_scale, scale):
            self._populate_scale_combo(previous_key)
            return False
        self.current_objective = {
            "name": "Custom",
            "magnification": "Custom",
            "microns_per_pixel": scale
        }
        self.current_objective_name = "Custom"
        self.microns_per_pixel = scale
        scale_nm = scale * 1000.0
        self.calib_info_label.setText(f"Scale bar: {scale_nm:.2f} nm/px")
        self._calib_link_objective_key = None
        self._calib_link_calibration_id = None

        if self.current_pixmap:
            self.image_label.set_objective_text("Scale bar")
            self.image_label.set_objective_color(QColor("#7f8c8d"))
        self.image_label.set_microns_per_pixel(self.microns_per_pixel)

        if warning_text:
            self.measure_status_label.setText(warning_text)
            self.measure_status_label.setStyleSheet(
                "color: #e67e22; font-weight: bold; font-size: 9pt;"
            )

        if self.current_image_id:
            ImageDB.update_image(
                self.current_image_id,
                scale=scale,
                objective_name=self.current_objective_name
            )
        self._populate_scale_combo("custom")
        self._last_scale_combo_key = "custom"
        return True

    def apply_image_scale(self, image_data):
        """Apply scale/objective metadata from an image record."""
        scale = image_data.get('scale_microns_per_pixel')
        if scale is not None and scale <= 0:
            scale = None
        objective_name = image_data.get('objective_name')
        calibration_id = image_data.get('calibration_id')
        objective_lookup = self.load_objective_definitions()
        show_old_calibration_warning = False

        self.suppress_scale_prompt = True
        if objective_name and objective_name in objective_lookup:
            objective = objective_lookup[objective_name]
            objective_scale = objective.get('microns_per_pixel', 0)
            if scale and objective_scale:
                diff_ratio = abs(objective_scale - scale) / objective_scale
            else:
                diff_ratio = 0 if scale is None else 1

            if scale and diff_ratio > 0.01:
                self.current_objective = objective
                self.current_objective_name = objective_name
                self.microns_per_pixel = scale
                show_old_calibration_warning = True

                mag = objective.get("magnification") or objective.get("name") or objective_name
                calib_date = None
                calib_obj_key = objective_name
                if calibration_id:
                    cal = CalibrationDB.get_calibration(calibration_id)
                    if cal:
                        raw_date = cal.get("calibration_date", "")
                        calib_date = raw_date[:10] if raw_date else None
                        calib_obj_key = cal.get("objective_key", calib_obj_key)

                scale_nm = self.microns_per_pixel * 1000.0
                if calib_date and calibration_id:
                    self._calib_link_objective_key = calib_obj_key
                    self._calib_link_calibration_id = calibration_id
                    self.calib_info_label.setText(
                        self.tr("Older scale used: {scale:.2f} nm/px<br/>Calibration: <a href=\"calibration\">{date}</a>")
                        .format(scale=scale_nm, date=calib_date)
                    )
                else:
                    self._calib_link_objective_key = None
                    self._calib_link_calibration_id = None
                    self.calib_info_label.setText(
                        self.tr("Older scale used: {scale:.2f} nm/px<br/>Calibration: --")
                        .format(scale=scale_nm)
                    )

                if self.current_pixmap:
                    self.image_label.set_objective_text(mag)
                    self.image_label.set_objective_color(self._objective_color_for_name(mag))
                self.image_label.set_microns_per_pixel(self.microns_per_pixel)

                self.measure_status_label.setText(self.tr("Warning: Older calibration standard used."))
                self.measure_status_label.setStyleSheet(
                    "color: #e67e22; font-weight: bold; font-size: 9pt;"
                )

                self._populate_scale_combo(objective_name)
            else:
                self.apply_objective(objective)
                if scale:
                    self.microns_per_pixel = scale
        elif scale:
            self.set_custom_scale(scale)
        elif objective_name:
            self.current_objective_name = objective_name
            self.calib_info_label.setText(f"{objective_name}: -- nm/px")
            self._calib_link_objective_key = None
            self._calib_link_calibration_id = None
            if self.current_pixmap:
                self.image_label.set_objective_text(objective_name)
                self.image_label.set_objective_color(self._objective_color_for_name(objective_name))
            self._populate_scale_combo(objective_name)
        else:
            self._populate_scale_combo()
        if (
            not show_old_calibration_warning
            and hasattr(self, "measure_status_label")
            and self.measure_status_label.text() == self.tr("Warning: Older calibration standard used.")
        ):
            self.measure_status_label.setText("")
            self.measure_status_label.setStyleSheet("")
        self.suppress_scale_prompt = False

    def update_controls_for_image_type(self, image_type):
        """Adjust calibration and category controls based on image type."""
        is_field = (image_type == "field")
        if hasattr(self, "scale_combo"):
            self.scale_combo.setEnabled(not is_field)
        if hasattr(self, "measure_category_combo"):
            self.measure_category_combo.setEnabled(not is_field)
        if hasattr(self, "measure_button"):
            self.measure_button.setEnabled(not is_field)
        if hasattr(self, "mode_lines"):
            self.mode_lines.setEnabled(not is_field)
        if hasattr(self, "mode_rect"):
            self.mode_rect.setEnabled(not is_field)
        if hasattr(self, "measure_category_combo"):
            if not self.measurements_table.selectedIndexes() and not self.measurement_active:
                target = "other" if is_field else "spore"
                idx = self.measure_category_combo.findData(target)
                if idx >= 0:
                    self.measure_category_combo.blockSignals(True)
                    self.measure_category_combo.setCurrentIndex(idx)
                    self.measure_category_combo.blockSignals(False)
        if is_field:
            image_data = None
            if self.current_image_id:
                image_data = ImageDB.get_image(self.current_image_id)
            has_scale = False
            if image_data:
                has_scale = bool(
                    image_data.get("objective_name") or image_data.get("scale_microns_per_pixel")
                )
            if not has_scale:
                self.current_objective_name = None
                self.image_label.set_objective_text("")
        if is_field:
            if self.measurement_active:
                self.stop_measurement()
        else:
            if not self.measurement_active and not self._auto_started_for_microscope:
                self.start_measurement()
                self._auto_started_for_microscope = True
        if hasattr(self, "measure_status_label") and is_field:
            self.measure_status_label.setText(self.tr("Field photo - no scale set"))
            self.measure_status_label.setStyleSheet("color: #e67e22; font-weight: bold; font-size: 9pt;")
        elif hasattr(self, "measure_status_label") and not is_field:
            if self.measure_status_label.text() == self.tr("Field photo - no scale set"):
                self.measure_status_label.setText("")
                self.measure_status_label.setStyleSheet("")

    def load_image_record(self, image_data, display_name=None, refresh_table=True):
        """Load an image record into the viewer."""
        original_path = image_data['filepath']
        output_dir = Path(__file__).parent.parent / "data" / "imports"
        converted_path = maybe_convert_heic(original_path, output_dir)
        if converted_path is None:
            QMessageBox.warning(
                self,
                "HEIC Conversion Failed",
                f"Could not convert {Path(original_path).name} to JPEG."
            )
            return

        if converted_path != original_path:
            ImageDB.update_image(image_data['id'], filepath=converted_path)
            image_data = dict(image_data)
            image_data['filepath'] = converted_path

        self.current_image_path = image_data['filepath']
        self.current_image_id = image_data['id']
        self.auto_gray_cache = None
        self.auto_gray_cache_id = None

        self.current_pixmap = self._load_pixmap_cached(self.current_image_path)
        self.image_label.set_image(self.current_pixmap)
        self.update_exif_panel(self.current_image_path)
        QTimer.singleShot(0, self.image_label.reset_view)

        filename = Path(self.current_image_path).name
        if hasattr(self, "image_info_label"):
            if display_name:
                self.image_info_label.setText(f"{display_name}\n{filename}")
            elif self.active_observation_name:
                self.image_info_label.setText(f"{self.active_observation_name}\n{filename}")
            else:
                self.image_info_label.setText(f"Loaded: {filename}")

        self.apply_image_scale(image_data)
        self.image_label.set_microns_per_pixel(self.microns_per_pixel)
        self.update_controls_for_image_type(image_data.get("image_type"))
        if self.current_objective_name:
            self.image_label.set_objective_color(
                self._objective_color_for_name(self.current_objective_name)
            )
        stored_color = image_data.get('measure_color')
        if stored_color:
            self.set_measure_color(QColor(stored_color))
        else:
            self.set_measure_color(self.measure_color or self.default_measure_color)
        self.refresh_observation_images(select_image_id=self.current_image_id)
        self.measurement_lines = {}
        self.temp_lines = []
        self.points = []
        self.load_measurement_lines()
        self.update_display_lines()
        self.update_statistics()
        if refresh_table:
            self.update_measurements_table()
        if not self._suppress_gallery_update:
            self.schedule_gallery_refresh()

        self._prefetch_adjacent_images()

    def refresh_observation_images(self, select_image_id=None):
        """Refresh the image list for the active observation."""
        if not self.active_observation_id:
            self.observation_images = []
            self.current_image_index = -1
            self._pixmap_cache.clear()
            self._pixmap_cache_order.clear()
            self._pixmap_cache_observation_id = None
            self.update_image_navigation_ui()
            if hasattr(self, "measure_gallery"):
                self.measure_gallery.clear()
            return

        if self._pixmap_cache_observation_id != self.active_observation_id:
            self._pixmap_cache.clear()
            self._pixmap_cache_order.clear()
            self._pixmap_cache_observation_id = self.active_observation_id

        self.observation_images = ImageDB.get_images_for_observation(self.active_observation_id)
        if hasattr(self, "measure_gallery"):
            self.measure_gallery.set_observation_id(self.active_observation_id)
        if select_image_id:
            for idx, image in enumerate(self.observation_images):
                if image['id'] == select_image_id:
                    self.current_image_index = idx
                    break
            else:
                self.current_image_index = -1
        elif self.current_image_id:
            for idx, image in enumerate(self.observation_images):
                if image['id'] == self.current_image_id:
                    self.current_image_index = idx
                    break
            else:
                self.current_image_index = 0 if self.observation_images else -1
        else:
            self.current_image_index = 0 if self.observation_images else -1

        self.update_image_navigation_ui()
        if hasattr(self, "measure_gallery"):
            self.measure_gallery.select_image(self.current_image_id)

    def update_image_navigation_ui(self):
        """Update navigation button state and label."""
        total = len(self.observation_images)
        if total <= 0 or self.current_image_index < 0:
            if hasattr(self, "image_group"):
                self.image_group.setTitle("Image (0/0)")
            if hasattr(self, "prev_image_btn"):
                self.prev_image_btn.setEnabled(False)
            if hasattr(self, "next_image_btn"):
                self.next_image_btn.setEnabled(False)
            return

        label_text = f"({self.current_image_index + 1}/{total})"
        if hasattr(self, "image_group"):
            self.image_group.setTitle(f"Image {label_text}")
        if hasattr(self, "prev_image_btn"):
            self.prev_image_btn.setEnabled(self.current_image_index > 0)
        if hasattr(self, "next_image_btn"):
            self.next_image_btn.setEnabled(self.current_image_index < total - 1)

    def _cache_pixmap(self, path: str, pixmap: QPixmap) -> None:
        if not path or pixmap is None or pixmap.isNull():
            return
        if path in self._pixmap_cache_order:
            self._pixmap_cache_order.remove(path)
        self._pixmap_cache[path] = pixmap
        self._pixmap_cache_order.append(path)
        while len(self._pixmap_cache_order) > self._pixmap_cache_max:
            oldest = self._pixmap_cache_order.pop(0)
            self._pixmap_cache.pop(oldest, None)

    def _load_pixmap_cached(self, path: str) -> QPixmap:
        if path in self._pixmap_cache:
            return self._pixmap_cache[path]
        pixmap = QPixmap(path)
        self._cache_pixmap(path, pixmap)
        return pixmap

    def _prefetch_adjacent_images(self) -> None:
        if not self.observation_images:
            return
        if self.current_image_index < 0:
            idx = -1
            if self.current_image_id:
                for i, image in enumerate(self.observation_images):
                    if image.get("id") == self.current_image_id:
                        idx = i
                        break
            if idx < 0:
                return
        else:
            idx = self.current_image_index

        targets = [idx - 1, idx + 1]
        for target in targets:
            if target < 0 or target >= len(self.observation_images):
                continue
            path = self.observation_images[target].get("filepath")
            if not path:
                continue
            if path in self._pixmap_cache:
                continue
            QTimer.singleShot(0, lambda p=path: self._load_pixmap_cached(p))

    def goto_previous_image(self):
        """Navigate to the previous image."""
        if self.current_image_index <= 0:
            return
        self.goto_image_index(self.current_image_index - 1)

    def goto_next_image(self):
        """Navigate to the next image."""
        if self.current_image_index < 0 or self.current_image_index >= len(self.observation_images) - 1:
            return
        self.goto_image_index(self.current_image_index + 1)

    def _on_measure_gallery_clicked(self, image_id, _filepath):
        if not image_id:
            return
        for idx, image in enumerate(self.observation_images):
            if image.get("id") == image_id:
                self.current_image_index = idx
                self.goto_image_index(idx)
                self.update_image_navigation_ui()
                if hasattr(self, "measure_gallery"):
                    self.measure_gallery.select_image(image_id)
                return

    def goto_image_index(self, index):
        """Load an image by index from the active observation."""
        if index < 0 or index >= len(self.observation_images):
            return
        image_data = self.observation_images[index]
        self.load_image_record(image_data, display_name=self.active_observation_name, refresh_table=True)

    def get_objective_name_for_storage(self):
        """Return the objective name to store with an image."""
        if self.current_objective_name:
            return self.current_objective_name
        if self.current_objective and self.current_objective.get("magnification"):
            return self.current_objective["magnification"]
        if self.microns_per_pixel:
            return "Custom"
        return None

    def update_observation_header(self, observation_id):
        """Update the observation header label."""
        if not observation_id:
            self.observation_header_label.setText("")
            return

        observation = ObservationDB.get_observation(observation_id)
        if not observation:
            self.observation_header_label.setText("")
            return

        genus = observation.get('genus') or ''
        species = observation.get('species') or observation.get('species_guess') or 'sp.'
        uncertain = observation.get('uncertain', 0)
        display_name = f"{genus} {species}".strip() or "Unknown"
        if uncertain:
            display_name = f"? {display_name}"
        date = observation.get('date') or "Unknown date"
        self.observation_header_label.setText(f"{display_name} - {date}")

    def clear_current_image_display(self):
        """Clear the current image and overlays."""
        self.current_image_id = None
        self.current_image_path = None
        self.current_pixmap = None
        self.auto_gray_cache = None
        self.auto_gray_cache_id = None
        self.points = []
        self.measurement_lines = {}
        self.temp_lines = []
        self.image_label.set_image(None)
        self.image_label.set_objective_text("")
        self.update_exif_panel(None)
        self.image_label.clear_preview_line()
        self.image_label.clear_preview_rectangle()
        self.spore_preview.clear()
        self.update_display_lines()

    def load_image(self):
        """Load a microscope image."""
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Open Microscope Image", "",
            "Images (*.png *.jpg *.jpeg *.tif *.tiff *.heic *.heif);;All Files (*)"
        )

        if not paths:
            return

        output_dir = get_images_dir() / "imports"
        output_dir.mkdir(parents=True, exist_ok=True)
        last_image_data = None
        for path in paths:
            converted_path = maybe_convert_heic(path, output_dir)
            if converted_path is None:
                QMessageBox.warning(
                    self,
                    "HEIC Conversion Failed",
                    f"Could not convert {Path(path).name} to JPEG."
                )
                continue

            objective_name = self.get_objective_name_for_storage()
            calibration_id = CalibrationDB.get_active_calibration_id(objective_name) if objective_name else None
            image_id = ImageDB.add_image(
                observation_id=self.active_observation_id,
                filepath=converted_path,
                image_type='microscope',
                scale=self.microns_per_pixel,
                objective_name=objective_name,
                contrast=SettingsDB.get_setting(
                    "contrast_default",
                    SettingsDB.get_list_setting("contrast_options", ["BF", "DF", "DIC", "Phase"])[0]
                ),
                calibration_id=calibration_id
            )

            image_data = ImageDB.get_image(image_id)
            stored_path = image_data.get("filepath") if image_data else converted_path

            # Generate thumbnails for ML training
            try:
                generate_all_sizes(stored_path, image_id)
            except Exception as e:
                print(f"Warning: Could not generate thumbnails: {e}")

            last_image_data = ImageDB.get_image(image_id)
            cleanup_import_temp_file(path, converted_path, stored_path, output_dir)

        if last_image_data:
            self.load_image_record(last_image_data, refresh_table=True)
            self.refresh_observation_images(select_image_id=last_image_data['id'])

    def zoom_in(self):
        """Zoom in the image."""
        self.image_label.zoom_in()

    def zoom_out(self):
        """Zoom out the image."""
        self.image_label.zoom_out()

    def reset_view(self):
        """Reset zoom and pan."""
        self.image_label.reset_view()

    def set_measure_color(self, color):
        """Set the active measurement color and update palette."""
        self.measure_color = QColor(color)
        if hasattr(self, "image_label"):
            self.image_label.set_measurement_color(self.measure_color)
        if hasattr(self, "spore_preview"):
            self.spore_preview.set_measure_color(self.measure_color)
        if self.current_image_id:
            ImageDB.update_image(
                self.current_image_id,
                measure_color=self.measure_color.name()
            )
        for btn, btn_color in getattr(self, "measure_color_buttons", []):
            selected = btn_color.name() == self.measure_color.name()
            border = "3px solid #2c3e50" if selected else "1px solid #bdc3c7"
            btn.setStyleSheet(f"background-color: {btn_color.name()}; border: {border};")
            btn.setChecked(selected)

    def on_show_measures_toggled(self, checked):
        """Toggle measurement labels on the main image."""
        self.image_label.set_show_measure_labels(checked)

    def on_show_rectangles_toggled(self, checked):
        """Toggle measurement overlays on the main image."""
        if hasattr(self, "image_label"):
            self.image_label.set_show_measure_overlays(checked)
        self.update_display_lines()
        return

    def on_show_scale_bar_toggled(self, checked):
        """Toggle scale bar display."""
        if hasattr(self, "scale_bar_container"):
            self.scale_bar_container.setVisible(checked)
        scale_value = self.scale_bar_input.value() if hasattr(self, "scale_bar_input") else 10.0
        self.image_label.set_scale_bar(checked, scale_value)

    def on_scale_bar_value_changed(self, value):
        """Update scale bar size."""
        if hasattr(self, "show_scale_bar_checkbox") and self.show_scale_bar_checkbox.isChecked():
            self.image_label.set_scale_bar(True, value)

    def start_measurement(self):
        """Enable measurement mode."""
        self.measurement_active = True
        self.update_measurement_button_state()
        if hasattr(self, "measurements_table"):
            self.measurements_table.clearSelection()
        if hasattr(self, "spore_preview"):
            self.spore_preview.clear()
        self._clear_measurement_highlight()
        if hasattr(self, "image_label"):
            self.image_label.set_pan_without_shift(True)
            self.image_label.set_measurement_active(True)
        self.on_measure_mode_changed()

    def stop_measurement(self):
        """Disable measurement mode and clear any in-progress points."""
        if not self.measurement_active:
            return
        self.measurement_active = False
        self.abort_measurement(show_status=False)
        self.update_measurement_button_state()
        if hasattr(self, "image_label"):
            self.image_label.set_pan_without_shift(True)
            self.image_label.set_measurement_active(False)
        self.measure_status_label.setText(self.tr("Stopped - Start measuring"))
        self.measure_status_label.setStyleSheet("color: #7f8c8d; font-weight: bold; font-size: 9pt;")

    def update_measurement_button_state(self):
        """Update Start/Stop button state based on measurement mode."""
        if hasattr(self, "measure_button"):
            self.measure_button.blockSignals(True)
            self.measure_button.setChecked(self.measurement_active)
            if self.measurement_active:
                self.measure_button.setText(self.tr("Stop measuring"))
                self.measure_button.setStyleSheet(
                    "font-weight: bold; padding: 6px 10px; background-color: #e74c3c; color: white;"
                )
            else:
                self.measure_button.setText(self.tr("Start measuring"))
                self.measure_button.setStyleSheet("font-weight: bold; padding: 6px 10px;")
            self.measure_button.blockSignals(False)

    def _on_measure_button_clicked(self):
        """Handle measure mode button click."""
        if self.measurement_active:
            self.stop_measurement()
        else:
            if not self._check_scale_before_measure():
                return
            self.start_measurement()

    def _check_scale_before_measure(self):
        """Warn if measuring without a scale."""
        if not self.current_image_id:
            return True
        image_data = ImageDB.get_image(self.current_image_id)
        if not image_data or image_data.get("image_type") != "field":
            return True
        scale = image_data.get("scale_microns_per_pixel")
        if scale is not None and scale > 0:
            return True

        dialog = QMessageBox(self)
        dialog.setWindowTitle("No Scale Set")
        dialog.setText("This is a field photo and no scale is set.")
        set_btn = dialog.addButton("Set scale", QMessageBox.AcceptRole)
        dialog.addButton("Cancel", QMessageBox.RejectRole)
        dialog.exec()
        if dialog.clickedButton() == set_btn:
            self.open_calibration_dialog()
        return False

    def on_measure_category_changed(self):
        """Update category for selected measurement."""
        self._update_preview_title()
        if self._measure_category_sync:
            return
        selected_rows = self.measurements_table.selectedIndexes()
        if not selected_rows:
            return
        row = selected_rows[0].row()
        if row >= len(self.measurements_cache):
            return
        measurement = self.measurements_cache[row]
        measurement_id = measurement.get("id")
        new_type = self.measure_category_combo.currentData()
        if not measurement_id or not new_type:
            return
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE spore_measurements SET measurement_type = ? WHERE id = ?',
            (new_type, measurement_id)
        )
        conn.commit()
        conn.close()
        self.measurements_cache[row]["measurement_type"] = new_type
        self.refresh_gallery_filter_options()
        self.schedule_gallery_refresh()

    def abort_measurement(self, show_status=True):
        """Abort the current measurement."""
        self.points = []
        self.temp_lines = []
        self.image_label.clear_preview_line()
        self.image_label.clear_preview_rectangle()
        self.rect_stage = 0
        self.rect_line1_start = None
        self.rect_line1_end = None
        self.rect_line2_start = None
        self.rect_line2_end = None
        self.rect_width_dir = None
        self.update_display_lines()
        if show_status:
            self.measure_status_label.setText(self.tr("Aborted - Start measuring"))
            self.measure_status_label.setStyleSheet("color: #e67e22; font-weight: bold; font-size: 9pt;")

    def on_measure_mode_changed(self):
        """Switch between line and rectangle measurement modes."""
        if self.mode_lines.isChecked():
            self.measure_mode = "lines"
        else:
            self.measure_mode = "rectangle"
        self.abort_measurement(show_status=False)
        if self.measurement_active:
            if self.measure_mode == "rectangle":
                self.measure_status_label.setText(self.tr("Rectangle: Click point 1"))
                self.measure_status_label.setStyleSheet("color: #3498db; font-weight: bold; font-size: 9pt;")
            else:
                self.measure_status_label.setText(self.tr("Ready - Click to start"))
                self.measure_status_label.setStyleSheet("color: #27ae60; font-weight: bold; font-size: 9pt;")
        else:
            self.measure_status_label.setText(self.tr("Start measuring to begin"))
            self.measure_status_label.setStyleSheet("color: #7f8c8d; font-weight: bold; font-size: 9pt;")

    def image_clicked(self, pos):
        """Handle image clicks for measurement or calibration."""
        # Handle calibration mode first
        if self.calibration_mode:
            self.handle_calibration_click(pos)
            return

        # If idle, allow clicking existing measurement overlays to select
        if not self.measurement_active and self.rect_stage == 0 and len(self.points) == 0:
            measurement_id = self.find_measurement_at_point(pos)
            if measurement_id:
                self.select_measurement_in_table(measurement_id)
                return
        if not self.measurement_active:
            return

        if self.measure_mode == "rectangle":
            self.handle_rectangle_measurement(pos)
            return

        # Auto-start measurement if we have an image but no active measurement
        if len(self.points) == 0 and self.current_image_path:
            # Automatically start a new measurement
            self.points = []
            self.temp_lines = []
            self.measure_status_label.setText(self.tr("Click point 1"))
            self.measure_status_label.setStyleSheet("color: #3498db; font-weight: bold; font-size: 9pt;")

        # Add point
        self.points.append(pos)

        # Update status and preview line
        if len(self.points) == 1:
            # Start preview line from point 1
            self.image_label.set_preview_line(self.points[0])
            self.measure_status_label.setText(self.tr("Click point 2"))
        elif len(self.points) == 2:
            # Complete first line, clear preview
            self.image_label.clear_preview_line()
            line1 = [
                self.points[0].x(), self.points[0].y(),
                self.points[1].x(), self.points[1].y()
            ]
            self.temp_lines.append(line1)
            self.update_display_lines()
            self.measure_status_label.setText(self.tr("Click point 3"))
        elif len(self.points) == 3:
            # Start preview line from point 3
            self.image_label.set_preview_line(self.points[2])
            self.measure_status_label.setText(self.tr("Click point 4"))
        elif len(self.points) == 4:
            # Complete second line, clear preview
            self.image_label.clear_preview_line()
            line2 = [
                self.points[2].x(), self.points[2].y(),
                self.points[3].x(), self.points[3].y()
            ]
            self.temp_lines.append(line2)
            self.update_display_lines()
            self.complete_measurement()

    def complete_measurement(self):
        """Complete the 4-point measurement and calculate Q."""
        # Calculate first distance
        dx1 = self.points[1].x() - self.points[0].x()
        dy1 = self.points[1].y() - self.points[0].y()
        dist1_pixels = np.sqrt(dx1**2 + dy1**2)
        dist1_microns = dist1_pixels * self.microns_per_pixel

        # Calculate second distance
        dx2 = self.points[3].x() - self.points[2].x()
        dy2 = self.points[3].y() - self.points[2].y()
        dist2_pixels = np.sqrt(dx2**2 + dy2**2)
        dist2_microns = dist2_pixels * self.microns_per_pixel

        # Auto-detect length (longer) and width (shorter)
        if dist1_microns >= dist2_microns:
            length_microns = dist1_microns
            width_microns = dist2_microns
        else:
            length_microns = dist2_microns
            width_microns = dist1_microns

        # Calculate Q (length/width ratio)
        q_value = length_microns / width_microns if width_microns > 0 else 0

        # Save to database with point coordinates and get measurement ID
        measurement_category = self.measure_category_combo.currentData()
        measurement_id = MeasurementDB.add_measurement(
            self.current_image_id,
            length=length_microns,
            width=width_microns,
            measurement_type=measurement_category,
            notes=f"Q={q_value:.1f}",
            points=self.points
        )

        ImageDB.update_image(
            self.current_image_id,
            scale=self.microns_per_pixel,
            objective_name=self.current_objective_name
        )

        # Save ML annotation with bounding box
        if self.current_pixmap and measurement_category == "spore":
            image_shape = (self.current_pixmap.height(), self.current_pixmap.width())
            try:
                save_spore_annotation(
                    image_id=self.current_image_id,
                    measurement_id=measurement_id,
                    points=self.points,
                    length_um=length_microns,
                    width_um=width_microns,
                    image_shape=image_shape
                )
            except Exception as e:
                print(f"Warning: Could not save ML annotation: {e}")

        # Store the lines associated with this measurement
        saved_lines = self.temp_lines.copy()
        self.measurement_lines[measurement_id] = saved_lines
        if len(saved_lines) >= 2:
            self.measurement_labels.append(
                self._build_measurement_label(
                    measurement_id,
                    saved_lines[0],
                    saved_lines[1],
                    length_microns,
                    width_microns
                )
            )
        self.temp_lines = []
        self.update_display_lines()

        # Update display
        self.measure_status_label.setText(self.tr("Click to measure next"))
        self.measure_status_label.setStyleSheet("color: #27ae60; font-weight: bold; font-size: 9pt;")

        # Update table and statistics
        self.update_measurements_table()
        self.update_statistics()

        # Auto-show preview for the just-completed measurement
        measurements = MeasurementDB.get_measurements_for_image(self.current_image_id)
        if measurements:
            # Get the last measurement (the one we just added)
            last_measurement = measurements[-1]
            self.show_measurement_preview(last_measurement)

        # Reset for next measurement - ready for next click
        self.points = []

    def handle_rectangle_measurement(self, pos):
        """Handle rectangle-based interactive measurement."""
        if not self.current_image_path:
            return

        if self.rect_stage == 0:
            self.rect_line1_start = pos
            self.image_label.set_preview_line(pos)
            self.rect_stage = 1
            self.measure_status_label.setText(self.tr("Rectangle: Click point 2"))
            self.measure_status_label.setStyleSheet("color: #3498db; font-weight: bold; font-size: 9pt;")
            return

        if self.rect_stage == 1:
            self.rect_line1_end = pos
            self.image_label.clear_preview_line()

            dx = self.rect_line1_end.x() - self.rect_line1_start.x()
            dy = self.rect_line1_end.y() - self.rect_line1_start.y()
            length = math.sqrt(dx**2 + dy**2)
            if length < 0.001:
                return

            self.rect_width_dir = QPointF(-dy / length, dx / length)
            self.rect_length_dir = QPointF(dx / length, dy / length)
            self.image_label.set_preview_rectangle(
                self.rect_line1_start,
                self.rect_line1_end,
                self.rect_width_dir,
                "line2"
            )
            self.rect_stage = 2
            self.measure_status_label.setText(self.tr("Rectangle: Set width, click point 3"))
            self.measure_status_label.setStyleSheet("color: #3498db; font-weight: bold; font-size: 9pt;")
            return

        if self.rect_stage == 2:
            if not self.rect_width_dir:
                return
            line1_mid = QPointF(
                (self.rect_line1_start.x() + self.rect_line1_end.x()) / 2,
                (self.rect_line1_start.y() + self.rect_line1_end.y()) / 2
            )
            delta = pos - line1_mid
            width_distance = delta.x() * self.rect_width_dir.x() + delta.y() * self.rect_width_dir.y()
            self.rect_line2_start = self.rect_line1_start + self.rect_width_dir * width_distance
            self.rect_line2_end = self.rect_line1_end + self.rect_width_dir * width_distance

            self.image_label.set_preview_rectangle(
                self.rect_line2_start,
                self.rect_line2_end,
                self.rect_width_dir,
                "line1"
            )
            self.rect_stage = 3
            self.measure_status_label.setText(self.tr("Rectangle: Adjust start line, click point 4"))
            self.measure_status_label.setStyleSheet("color: #3498db; font-weight: bold; font-size: 9pt;")
            return

        if self.rect_stage == 3:
            if not self.rect_width_dir or not self.rect_length_dir:
                return
            line2_mid = QPointF(
                (self.rect_line2_start.x() + self.rect_line2_end.x()) / 2,
                (self.rect_line2_start.y() + self.rect_line2_end.y()) / 2
            )
            delta = pos - line2_mid
            width_distance = delta.x() * self.rect_width_dir.x() + delta.y() * self.rect_width_dir.y()
            line1_start = self.rect_line2_start + self.rect_width_dir * width_distance
            line1_end = self.rect_line2_end + self.rect_width_dir * width_distance

            self.image_label.clear_preview_rectangle()

            line1_mid = QPointF((line1_start.x() + line1_end.x()) / 2,
                                (line1_start.y() + line1_end.y()) / 2)
            line2_mid = QPointF((self.rect_line2_start.x() + self.rect_line2_end.x()) / 2,
                                (self.rect_line2_start.y() + self.rect_line2_end.y()) / 2)
            center = QPointF((line1_mid.x() + line2_mid.x()) / 2,
                             (line1_mid.y() + line2_mid.y()) / 2)

            length_len = math.sqrt((line1_end.x() - line1_start.x())**2 +
                                   (line1_end.y() - line1_start.y())**2)
            half_length = length_len / 2
            center_line_start = center - self.rect_length_dir * half_length
            center_line_end = center + self.rect_length_dir * half_length

            width_vec = line1_mid - line2_mid
            width = abs(width_vec.x() * self.rect_width_dir.x() + width_vec.y() * self.rect_width_dir.y())
            width_half = width / 2
            width_line_start = center - self.rect_width_dir * width_half
            width_line_end = center + self.rect_width_dir * width_half

            self.points = [center_line_start, center_line_end, width_line_start, width_line_end]
            self.temp_lines = [
                [center_line_start.x(), center_line_start.y(), center_line_end.x(), center_line_end.y()],
                [width_line_start.x(), width_line_start.y(), width_line_end.x(), width_line_end.y()]
            ]
            self.update_display_lines()
            self.complete_measurement()

            self.rect_stage = 0
            self.rect_line1_start = None
            self.rect_line1_end = None
            self.rect_line2_start = None
            self.rect_line2_end = None
            self.rect_width_dir = None
            self.rect_length_dir = None

    def update_display_lines(self):
        """Update the display with all lines (saved + temporary)."""
        show_saved = True
        if hasattr(self, "show_rectangles_checkbox"):
            show_saved = self.show_rectangles_checkbox.isChecked()
        if self.measure_mode == "lines":
            rectangles = []
            all_lines = []
            self._line_index_map = {}
            if show_saved:
                for measurement_id, lines_list in self.measurement_lines.items():
                    for line in lines_list:
                        idx = len(all_lines)
                        all_lines.append(line)
                        self._line_index_map.setdefault(measurement_id, []).append(idx)
            all_lines.extend(self.temp_lines)
            self.image_label.set_measurement_rectangles(rectangles)
            self.image_label.set_measurement_lines(all_lines)
            self._rect_index_map = {}
        else:
            rectangles, self._rect_index_map = self._build_measurement_rectangles_with_ids() if show_saved else ([], {})
            self.image_label.set_measurement_rectangles(rectangles)
            self.image_label.set_measurement_lines(self.temp_lines)
            self._line_index_map = {}
        self.image_label.set_measurement_labels(self.measurement_labels)

    def build_measurement_rectangles(self):
        """Build rectangle corner lists from saved measurement lines."""
        rectangles, _ = self._build_measurement_rectangles_with_ids()
        return rectangles

    def _build_measurement_rectangles_with_ids(self):
        """Build rectangle corner lists and an index map keyed by measurement id."""
        rectangles = []
        rect_index_map = {}
        for measurement_id, lines_list in self.measurement_lines.items():
            if len(lines_list) < 2:
                continue
            line1 = lines_list[0]
            line2 = lines_list[1]
            p1 = QPointF(line1[0], line1[1])
            p2 = QPointF(line1[2], line1[3])
            p3 = QPointF(line2[0], line2[1])
            p4 = QPointF(line2[2], line2[3])

            length_vec = p2 - p1
            length_len = math.sqrt(length_vec.x()**2 + length_vec.y()**2)
            width_vec = p4 - p3
            width_len = math.sqrt(width_vec.x()**2 + width_vec.y()**2)
            if length_len < 0.001 or width_len < 0.001:
                continue

            length_dir = QPointF(length_vec.x() / length_len, length_vec.y() / length_len)
            width_dir = QPointF(-length_dir.y(), length_dir.x())

            line1_mid = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
            line2_mid = QPointF((p3.x() + p4.x()) / 2, (p3.y() + p4.y()) / 2)
            center = QPointF((line1_mid.x() + line2_mid.x()) / 2,
                             (line1_mid.y() + line2_mid.y()) / 2)

            half_length = length_len / 2
            half_width = width_len / 2

            corners = [
                center - width_dir * half_width - length_dir * half_length,
                center + width_dir * half_width - length_dir * half_length,
                center + width_dir * half_width + length_dir * half_length,
                center - width_dir * half_width + length_dir * half_length,
            ]
            rect_index_map[measurement_id] = len(rectangles)
            rectangles.append(corners)
        return rectangles, rect_index_map

    def _distance_point_to_segment(self, point, a, b):
        """Return distance between a point and a line segment."""
        ab = b - a
        ap = point - a
        ab_len_sq = ab.x() * ab.x() + ab.y() * ab.y()
        if ab_len_sq == 0:
            return math.sqrt(ap.x() * ap.x() + ap.y() * ap.y())
        t = (ap.x() * ab.x() + ap.y() * ab.y()) / ab_len_sq
        t = max(0.0, min(1.0, t))
        closest = QPointF(a.x() + ab.x() * t, a.y() + ab.y() * t)
        dx = point.x() - closest.x()
        dy = point.y() - closest.y()
        return math.sqrt(dx * dx + dy * dy)

    def _point_in_polygon(self, point, polygon):
        """Check if a point is inside a polygon using ray casting."""
        inside = False
        n = len(polygon)
        if n < 3:
            return False
        p1 = polygon[0]
        for i in range(1, n + 1):
            p2 = polygon[i % n]
            if point.y() > min(p1.y(), p2.y()):
                if point.y() <= max(p1.y(), p2.y()):
                    if point.x() <= max(p1.x(), p2.x()):
                        if p1.y() != p2.y():
                            xinters = (point.y() - p1.y()) * (p2.x() - p1.x()) / (p2.y() - p1.y()) + p1.x()
                        if p1.x() == p2.x() or point.x() <= xinters:
                            inside = not inside
            p1 = p2
        return inside

    def find_measurement_at_point(self, pos, threshold=6.0):
        """Return measurement_id if click is near a measurement overlay."""
        if not self.measurement_lines:
            return None

        best_id = None
        best_dist = threshold
        for measurement_id, lines_list in self.measurement_lines.items():
            if len(lines_list) < 2:
                continue
            line1 = lines_list[0]
            line2 = lines_list[1]
            p1 = QPointF(line1[0], line1[1])
            p2 = QPointF(line1[2], line1[3])
            p3 = QPointF(line2[0], line2[1])
            p4 = QPointF(line2[2], line2[3])

            # Check distance to the two measurement lines
            dist = min(
                self._distance_point_to_segment(pos, p1, p2),
                self._distance_point_to_segment(pos, p3, p4)
            )

            # Check rectangle edges for better selection on rectangle view
            corners = self.build_measurement_rectangles_for_lines(line1, line2)
            if corners:
                for i in range(4):
                    a = corners[i]
                    b = corners[(i + 1) % 4]
                    dist = min(dist, self._distance_point_to_segment(pos, a, b))
                if self._point_in_polygon(pos, corners):
                    dist = 0.0

            if dist <= best_dist:
                best_dist = dist
                best_id = measurement_id

        return best_id

    def build_measurement_rectangles_for_lines(self, line1, line2):
        """Build rectangle corners for a specific measurement."""
        p1 = QPointF(line1[0], line1[1])
        p2 = QPointF(line1[2], line1[3])
        p3 = QPointF(line2[0], line2[1])
        p4 = QPointF(line2[2], line2[3])

        length_vec = p2 - p1
        length_len = math.sqrt(length_vec.x()**2 + length_vec.y()**2)
        width_vec = p4 - p3
        width_len = math.sqrt(width_vec.x()**2 + width_vec.y()**2)
        if length_len < 0.001 or width_len < 0.001:
            return None

        length_dir = QPointF(length_vec.x() / length_len, length_vec.y() / length_len)
        width_dir = QPointF(-length_dir.y(), length_dir.x())

        line1_mid = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
        line2_mid = QPointF((p3.x() + p4.x()) / 2, (p3.y() + p4.y()) / 2)
        center = QPointF((line1_mid.x() + line2_mid.x()) / 2,
                         (line1_mid.y() + line2_mid.y()) / 2)

        half_length = length_len / 2
        half_width = width_len / 2

        return [
            center - width_dir * half_width - length_dir * half_length,
            center + width_dir * half_width - length_dir * half_length,
            center + width_dir * half_width + length_dir * half_length,
            center - width_dir * half_width + length_dir * half_length,
        ]

    def _objective_color_for_name(self, name):
        """Return the objective tag color based on magnification."""
        if not name:
            return QColor(52, 152, 219)
        match = re.search(r"(\d+)", str(name))
        mag = int(match.group(1)) if match else None
        if mag in (10,):
            return QColor("#f1c40f")
        if mag in (16, 20, 25, 32):
            return QColor("#2ecc71")
        if mag in (40, 50):
            return QColor("#3498db")
        if mag in (63,):
            return QColor("#1f4ea8")
        if mag in (4, 5):
            return QColor("#e74c3c")
        if mag in (6,):
            return QColor("#f39c12")
        return QColor("#3498db")

    def _format_exposure_time(self, value):
        """Format exposure time for display."""
        if value is None:
            return "-"
        try:
            if isinstance(value, tuple):
                value = value[0] / value[1] if value[1] else 0
            if value >= 1:
                text = f"{value:.1f}".rstrip("0").rstrip(".")
                return f"{text}s"
            if value > 0:
                denom = round(1 / value)
                return f"1/{denom}"
        except Exception:
            return "-"
        return "-"

    def _format_fstop(self, value):
        """Format f-stop for display."""
        if value is None:
            return "-"
        try:
            if isinstance(value, tuple):
                value = value[0] / value[1] if value[1] else 0
            return f"f/{value:.1f}".rstrip("0").rstrip(".")
        except Exception:
            return "-"

    def _extract_exif_lines(self, image_path):
        """Extract EXIF info lines for overlay display."""
        path = Path(image_path) if image_path else None
        if not path or not path.exists():
            return []
        lines = []
        lines.append(f"File: {path.name}")

        try:
            with Image.open(path) as img:
                exif = img.getexif()
                if not exif:
                    return lines
                exif_data = {ExifTags.TAGS.get(k, k): v for k, v in exif.items()}
        except Exception:
            return lines

        date = exif_data.get("DateTimeOriginal") or exif_data.get("DateTime")
        if date:
            lines.append(f"Date: {date}")

        iso = exif_data.get("ISOSpeedRatings")
        if iso is None:
            iso = exif_data.get("PhotographicSensitivity")
        if isinstance(iso, tuple):
            iso = iso[0]
        if iso is not None:
            lines.append(f"ISO: {iso}")

        fstop = self._format_fstop(exif_data.get("FNumber") or exif_data.get("ApertureValue"))
        if fstop != "-":
            lines.append(f"F-stop: {fstop}")

        shutter = self._format_exposure_time(exif_data.get("ExposureTime"))
        if shutter == "-":
            shutter = self._format_exposure_time(exif_data.get("ShutterSpeedValue"))
        if shutter != "-":
            lines.append(f"Shutter: {shutter}")

        make = exif_data.get("Make", "")
        model = exif_data.get("Model", "")
        camera = " ".join(part for part in (make, model) if part).strip()
        if camera:
            lines.append(f"Camera: {camera}")

        return lines

    def update_exif_panel(self, image_path):
        """Update the Info panel with EXIF data."""
        if not hasattr(self, "exif_info_label"):
            return
        lines = self._extract_exif_lines(image_path)
        if not lines:
            self.exif_info_label.setText("No image loaded")
            return
        folder_path = Path(image_path).resolve().parent
        folder_uri = folder_path.as_uri()
        html_lines = [html.escape(line) for line in lines]
        html_lines.append(
            f'Folder: <a href="{folder_uri}">Folder location</a>'
        )
        self.exif_info_label.setText("<br>".join(html_lines))

    def _get_gray_image(self):
        """Return a cached grayscale numpy array of the current image."""
        if not self.current_pixmap or not self.current_image_id:
            return None
        if self.auto_gray_cache_id == self.current_image_id and self.auto_gray_cache is not None:
            return self.auto_gray_cache

        image = self.current_pixmap.toImage().convertToFormat(QImage.Format.Format_Grayscale8)
        width = image.width()
        height = image.height()
        buf = image.constBits() if hasattr(image, "constBits") else image.bits()
        arr = np.frombuffer(buf, dtype=np.uint8)
        bytes_per_line = image.bytesPerLine()
        gray = arr.reshape((height, bytes_per_line))[:, :width].copy()
        self.auto_gray_cache = gray
        self.auto_gray_cache_id = self.current_image_id
        return gray

    def _update_auto_threshold_from_points(self, points):
        """Update the auto threshold based on a refined measurement."""
        if not self.active_observation_id or len(points) != 4:
            return
        gray = self._get_gray_image()
        if gray is None:
            return
        h, w = gray.shape
        line1_mid = QPointF((points[0].x() + points[1].x()) / 2,
                            (points[0].y() + points[1].y()) / 2)
        line2_mid = QPointF((points[2].x() + points[3].x()) / 2,
                            (points[2].y() + points[3].y()) / 2)
        center = QPointF((line1_mid.x() + line2_mid.x()) / 2,
                         (line1_mid.y() + line2_mid.y()) / 2)
        cx = int(round(center.x()))
        cy = int(round(center.y()))
        if cx < 0 or cy < 0 or cx >= w or cy >= h:
            return
        center_intensity = float(gray[cy, cx])
        edge_samples = []
        for pt in points:
            x = int(round(pt.x()))
            y = int(round(pt.y()))
            if 0 <= x < w and 0 <= y < h:
                edge_samples.append(float(gray[y, x]))
        if not edge_samples:
            return
        edge_mean = float(np.mean(edge_samples))
        max_radius = self._update_auto_max_radius_from_points(points)
        max_radius = max_radius or min(h, w) / 2
        ring_radius = int(min(max_radius * 1.2, min(h, w) / 2))
        ring_samples = []
        for angle in range(0, 360, 30):
            rad = math.radians(angle)
            rx = int(round(cx + math.cos(rad) * ring_radius))
            ry = int(round(cy + math.sin(rad) * ring_radius))
            if 0 <= rx < w and 0 <= ry < h:
                ring_samples.append(float(gray[ry, rx]))
        bg_mean = float(np.mean(ring_samples)) if ring_samples else center_intensity
        threshold = abs(bg_mean - edge_mean) / 255.0
        threshold = max(0.02, min(0.6, threshold))
        self.auto_threshold = threshold
        ObservationDB.set_auto_threshold(self.active_observation_id, threshold)

    def _auto_find_radii(self, cx, cy, gray, background_mean,
                         threshold, max_radius, angle_step=10):
        """Return radii at sampled angles using inward search."""
        height, width = gray.shape
        delta = max(2.0, threshold * 255.0)
        def hit(val):
            return abs(val - background_mean) >= delta

        radii = {}
        for angle in range(0, 180, angle_step):
            rad = math.radians(angle)
            dx = math.cos(rad)
            dy = math.sin(rad)
            for r in range(max_radius, 0, -1):
                x = int(round(cx + dx * r))
                y = int(round(cy + dy * r))
                if x < 0 or y < 0 or x >= width or y >= height:
                    break
                if hit(float(gray[y, x])):
                    radii[angle] = r
                    break
        return radii

    def _update_auto_max_radius_from_points(self, points):
        """Update max recorded spore radius (pixels) from measurement points."""
        if len(points) != 4:
            return self.auto_max_radius
        line1_mid = QPointF((points[0].x() + points[1].x()) / 2,
                            (points[0].y() + points[1].y()) / 2)
        line2_mid = QPointF((points[2].x() + points[3].x()) / 2,
                            (points[2].y() + points[3].y()) / 2)
        center = QPointF((line1_mid.x() + line2_mid.x()) / 2,
                         (line1_mid.y() + line2_mid.y()) / 2)
        max_radius = 0.0
        for pt in points:
            dx = pt.x() - center.x()
            dy = pt.y() - center.y()
            max_radius = max(max_radius, math.hypot(dx, dy))
        if max_radius > 0:
            if self.auto_max_radius is None or max_radius > self.auto_max_radius:
                self.auto_max_radius = max_radius
        return self.auto_max_radius

    def _compute_observation_max_radius(self, observation_id):
        """Initialize auto max radius from stored measurements."""
        if not observation_id:
            self.auto_max_radius = None
            return
        measurements = MeasurementDB.get_measurements_for_observation(observation_id)
        max_radius = None
        for measurement in measurements:
            if not all(measurement.get(f'p{i}_{axis}') is not None
                       for i in range(1, 5) for axis in ['x', 'y']):
                continue
            points = [
                QPointF(measurement['p1_x'], measurement['p1_y']),
                QPointF(measurement['p2_x'], measurement['p2_y']),
                QPointF(measurement['p3_x'], measurement['p3_y']),
                QPointF(measurement['p4_x'], measurement['p4_y'])
            ]
            line1_mid = QPointF((points[0].x() + points[1].x()) / 2,
                                (points[0].y() + points[1].y()) / 2)
            line2_mid = QPointF((points[2].x() + points[3].x()) / 2,
                                (points[2].y() + points[3].y()) / 2)
            center = QPointF((line1_mid.x() + line2_mid.x()) / 2,
                             (line1_mid.y() + line2_mid.y()) / 2)
            for pt in points:
                radius = math.hypot(pt.x() - center.x(), pt.y() - center.y())
                if max_radius is None or radius > max_radius:
                    max_radius = radius
        self.auto_max_radius = max_radius

    def auto_measure_at_click(self, pos):
        """Auto-detect spore axes based on intensity drop from a click point."""
        if not self.current_pixmap or not self.current_image_id:
            return
        gray = self._get_gray_image()
        if gray is None:
            return
        height, width = gray.shape
        cx = int(round(pos.x()))
        cy = int(round(pos.y()))
        if cx < 0 or cy < 0 or cx >= width or cy >= height:
            return

        center_intensity = float(gray[cy, cx])
        threshold = self.auto_threshold if self.auto_threshold is not None else self.auto_threshold_default
        max_radius = self.auto_max_radius if self.auto_max_radius else min(width, height) / 2
        max_radius = int(min(max_radius * 1.2, min(width, height) / 2))
        max_radius = max(10, max_radius)
        ring_samples = []
        for angle in range(0, 360, 30):
            rad = math.radians(angle)
            rx = int(round(cx + math.cos(rad) * max_radius))
            ry = int(round(cy + math.sin(rad) * max_radius))
            if 0 <= rx < width and 0 <= ry < height:
                ring_samples.append(float(gray[ry, rx]))
        bg_mean = float(np.mean(ring_samples)) if ring_samples else center_intensity

        radii = self._auto_find_radii(cx, cy, gray, bg_mean, threshold, max_radius, angle_step=10)

        if len(radii) < 4:
            self.show_auto_debug_dialog(
                pos, radii, None, None, threshold, center_intensity, bg_mean, max_radius
            )
            self.measure_status_label.setText(self.tr("Auto: Edge not found"))
            self.measure_status_label.setStyleSheet("color: #e67e22; font-weight: bold; font-size: 9pt;")
            return

        major_angle = max(radii, key=lambda a: radii[a])
        major_radius = radii[major_angle]
        target_minor = (major_angle + 90) % 180
        minor_angle = min(
            radii.keys(),
            key=lambda a: min(
                abs(a - target_minor),
                abs(a - target_minor + 180),
                abs(a - target_minor - 180)
            )
        )
        minor_radius = radii.get(minor_angle, min(radii.values()))

        major_rad = math.radians(major_angle)
        minor_rad = math.radians(minor_angle)
        center = QPointF(cx, cy)
        major_dir = QPointF(math.cos(major_rad), math.sin(major_rad))
        minor_dir = QPointF(math.cos(minor_rad), math.sin(minor_rad))

        p1 = center - major_dir * major_radius
        p2 = center + major_dir * major_radius
        p3 = center - minor_dir * minor_radius
        p4 = center + minor_dir * minor_radius

        self.points = [p1, p2, p3, p4]
        self.temp_lines = [
            [p1.x(), p1.y(), p2.x(), p2.y()],
            [p3.x(), p3.y(), p4.x(), p4.y()]
        ]
        self.update_display_lines()
        self._update_auto_max_radius_from_points(self.points)
        self.show_auto_debug_dialog(
            pos, radii, major_angle, minor_angle, threshold, center_intensity, bg_mean, max_radius
        )
        self.complete_measurement()

    def show_auto_debug_dialog(self, pos, radii, major_angle, minor_angle,
                               threshold, center_intensity, background_mean,
                               max_radius):
        """Show a debug popup with auto-measure traces and stats."""
        if not self.current_pixmap:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Auto Measure Debug")
        layout = QVBoxLayout(dialog)

        center = QPointF(pos.x(), pos.y())
        crop_size = 300
        half = crop_size / 2
        left = max(0, int(center.x() - half))
        top = max(0, int(center.y() - half))
        right = min(self.current_pixmap.width(), int(center.x() + half))
        bottom = min(self.current_pixmap.height(), int(center.y() + half))
        crop_rect = QRectF(left, top, right - left, bottom - top)

        gray = self._get_gray_image()
        gray_crop = None
        if gray is not None:
            gray_crop = gray[int(crop_rect.y()):int(crop_rect.y() + crop_rect.height()),
                            int(crop_rect.x()):int(crop_rect.x() + crop_rect.width())].copy()

        image_label = QLabel()
        layout.addWidget(image_label)

        controls_row = QHBoxLayout()
        threshold_label = QLabel("Threshold:")
        threshold_input = QDoubleSpinBox()
        threshold_input.setRange(0.02, 0.6)
        threshold_input.setDecimals(3)
        threshold_input.setSingleStep(0.01)
        threshold_input.setValue(float(threshold))
        show_gray_checkbox = QCheckBox(self.tr("Show grayscale"))
        controls_row.addWidget(threshold_label)
        controls_row.addWidget(threshold_input)
        controls_row.addStretch()
        controls_row.addWidget(show_gray_checkbox)
        layout.addLayout(controls_row)

        stats_label = QLabel()
        stats_label.setStyleSheet("font-size: 9pt; color: #2c3e50;")
        layout.addWidget(stats_label)

        plot_label = QLabel()
        layout.addWidget(plot_label)

        def render_overlay(current_threshold):
            base_radii = self._auto_find_radii(
                int(round(center.x())),
                int(round(center.y())),
                gray,
                background_mean,
                current_threshold,
                max_radius,
                angle_step=10
            ) if gray is not None else {}

            full_radii = dict(base_radii)
            for angle, radius in base_radii.items():
                full_radii[(angle + 180) % 360] = radius

            major = None
            minor = None
            if base_radii:
                major = max(base_radii, key=lambda a: base_radii[a])
                target_minor = (major + 90) % 180
                minor = min(
                    base_radii.keys(),
                    key=lambda a: min(
                        abs(a - target_minor),
                        abs(a - target_minor + 180),
                        abs(a - target_minor - 180)
                    )
                )

            if show_gray_checkbox.isChecked() and gray_crop is not None:
                h, w = gray_crop.shape
                gray_img = QImage(gray_crop.data, w, h, w, QImage.Format.Format_Grayscale8)
                base_pixmap = QPixmap.fromImage(gray_img.copy())
            else:
                base_pixmap = self.current_pixmap.copy(crop_rect.toRect())

            target_size = 360
            scale = min(target_size / max(1, base_pixmap.width()),
                        target_size / max(1, base_pixmap.height()))
            scaled = base_pixmap.scaled(
                int(base_pixmap.width() * scale),
                int(base_pixmap.height() * scale),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )

            overlay = QPixmap(scaled.size())
            overlay.fill(Qt.transparent)
            painter = QPainter(overlay)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.drawPixmap(0, 0, scaled)

            center_local = QPointF((center.x() - crop_rect.x()) * scale,
                                   (center.y() - crop_rect.y()) * scale)

            for angle, radius in full_radii.items():
                rad = math.radians(angle)
                dx = math.cos(rad)
                dy = math.sin(rad)
                end = QPointF(center_local.x() + dx * radius * scale,
                              center_local.y() + dy * radius * scale)
                pen_color = QColor(200, 200, 200)
                if major is not None and angle == major:
                    pen_color = QColor(46, 204, 113)
                elif minor is not None and angle % 180 == minor:
                    pen_color = QColor(231, 76, 60)
                painter.setPen(QPen(pen_color, 2))
                painter.drawLine(center_local, end)
                painter.setBrush(pen_color)
                painter.drawEllipse(end, 3, 3)

            painter.setPen(QPen(QColor(52, 152, 219), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(center_local, 4, 4)
            painter.end()

            image_label.setPixmap(overlay)

            direction = "darker" if background_mean < center_intensity else "brighter"
            stats_text = (
                f"Threshold: {current_threshold:.3f} ({direction} edge)\n"
                f"Center intensity: {center_intensity:.1f}  Background: {background_mean:.1f}\n"
                f"Rays found: {len(full_radii)}  Max radius: {max_radius}px"
            )
            stats_label.setText(stats_text)

            if self.active_observation_id:
                self.auto_threshold = current_threshold
                ObservationDB.set_auto_threshold(self.active_observation_id, current_threshold)

            if gray is None:
                plot_label.clear()
                return

            plot_w = 360
            plot_h = 200
            plot_pixmap = QPixmap(plot_w, plot_h)
            plot_pixmap.fill(QColor(255, 255, 255))
            plot_painter = QPainter(plot_pixmap)
            plot_painter.setRenderHint(QPainter.Antialiasing)

            left_pad = 30
            right_pad = 10
            top_pad = 10
            bottom_pad = 25
            axis_w = plot_w - left_pad - right_pad
            axis_h = plot_h - top_pad - bottom_pad

            plot_painter.setPen(QPen(QColor(200, 200, 200), 1))
            for i in range(1, 5):
                y = top_pad + axis_h * (i / 5)
                plot_painter.drawLine(left_pad, int(y), left_pad + axis_w, int(y))
            for i in range(1, 5):
                x = left_pad + axis_w * (i / 5)
                plot_painter.drawLine(int(x), top_pad, int(x), top_pad + axis_h)

            plot_painter.setPen(QPen(QColor(120, 120, 120), 1))
            plot_painter.drawLine(left_pad, top_pad, left_pad, top_pad + axis_h)
            plot_painter.drawLine(left_pad, top_pad + axis_h, left_pad + axis_w, top_pad + axis_h)

            max_radius_local = max(1, max_radius)

            def map_point(r, intensity):
                x = left_pad + ((max_radius_local - r) / max_radius_local) * axis_w
                y = top_pad + axis_h - (intensity / 255.0) * axis_h
                return QPointF(x, y)

            def line_color(angle):
                if major is not None and angle == major:
                    return QColor(46, 204, 113)
                if minor is not None and angle % 180 == minor:
                    return QColor(231, 76, 60)
                return QColor(120, 120, 120, 140)

            cx = int(round(center.x()))
            cy = int(round(center.y()))
            for angle in range(0, 180, 10):
                rad = math.radians(angle)
                dx = math.cos(rad)
                dy = math.sin(rad)
                points = []
                for r in range(max_radius_local, -1, -1):
                    x = int(round(cx + dx * r))
                    y = int(round(cy + dy * r))
                    if x < 0 or y < 0 or x >= gray.shape[1] or y >= gray.shape[0]:
                        break
                    points.append(map_point(r, float(gray[y, x])))
                if len(points) > 1:
                    plot_painter.setPen(QPen(line_color(angle), 1))
                    for i in range(1, len(points)):
                        plot_painter.drawLine(points[i - 1], points[i])

            plot_painter.setPen(QPen(QColor(120, 120, 120), 1))
            plot_painter.drawText(5, top_pad + 10, "I")
            plot_painter.drawText(plot_w - 24, plot_h - 8, "r")
            plot_painter.end()
            plot_label.setPixmap(plot_pixmap)

        threshold_input.valueChanged.connect(lambda value: render_overlay(value))
        show_gray_checkbox.toggled.connect(lambda _: render_overlay(threshold_input.value()))
        render_overlay(threshold_input.value())

        dialog.setLayout(layout)
        dialog.exec()

    def select_measurement_in_table(self, measurement_id):
        """Select a measurement row by id."""
        for row in range(self.measurements_table.rowCount()):
            item = self.measurements_table.item(row, 0)
            if item and item.data(Qt.UserRole) == measurement_id:
                self.measurements_table.selectRow(row)
                self.on_measurement_selected()
                return

    def export_annotated_image(self):
        """Export the current image view with annotations."""
        if not self.current_pixmap:
            QMessageBox.warning(self, "No image", "Load an image before exporting.")
            return

        default_name = "annotated_image"
        if self.active_observation_id:
            obs = ObservationDB.get_observation(self.active_observation_id)
            if obs:
                parts = [
                    obs.get("genus") or "",
                    obs.get("species") or obs.get("species_guess") or "",
                    obs.get("date") or ""
                ]
                name = " ".join([p for p in parts if p]).strip()
                name = name.replace(":", "-")
                name = re.sub(r'[<>:"/\\\\|?*]', "_", name)
                name = re.sub(r"\\s+", " ", name).strip()
                if name:
                    default_name = name

        dialog = ExportImageDialog(
            self.current_pixmap.width(),
            self.current_pixmap.height(),
            self.export_scale_percent,
            self.export_format,
            parent=self
        )
        if dialog.exec() != QDialog.Accepted:
            return

        export_settings = dialog.get_settings()
        self.export_scale_percent = export_settings["scale_percent"]

        default_ext = ".jpg" if self.export_format == "jpg" else ".png"
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export Image",
            f"{default_name}{default_ext}",
            "PNG Images (*.png);;JPEG Images (*.jpg)"
        )
        if not filename:
            return
        if not re.search(r"\.(png|jpe?g)$", filename, re.IGNORECASE):
            filename += default_ext

        exported = self.image_label.export_annotated_pixmap()
        if exported:
            target_w = export_settings["width"]
            target_h = export_settings["height"]
            if target_w and target_h:
                exported = exported.scaled(
                    target_w,
                    target_h,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
            fmt = "JPEG" if filename.lower().endswith((".jpg", ".jpeg")) else "PNG"
            quality = export_settings["quality"]
            if fmt == "JPEG":
                exported.save(filename, fmt, quality)
                self.export_format = "jpg"
            else:
                exported.save(filename, fmt)
                self.export_format = "png"


    def _compute_measurement_center(self, line1, line2):
        """Compute center point for a measurement from two lines."""
        p1 = QPointF(line1[0], line1[1])
        p2 = QPointF(line1[2], line1[3])
        p3 = QPointF(line2[0], line2[1])
        p4 = QPointF(line2[2], line2[3])
        line1_mid = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
        line2_mid = QPointF((p3.x() + p4.x()) / 2, (p3.y() + p4.y()) / 2)
        return QPointF(
            (line1_mid.x() + line2_mid.x()) / 2,
            (line1_mid.y() + line2_mid.y()) / 2
        )

    def _build_measurement_label(self, measurement_id, line1, line2, length_um, width_um):
        """Build a label entry for measurement overlays."""
        center = self._compute_measurement_center(line1, line2)
        return {
            "id": measurement_id,
            "center": center,
            "length_um": length_um,
            "width_um": width_um,
            "line1": line1,
            "line2": line2
        }

    def load_measurement_lines(self):
        """Load measurement lines from database for current image.

        Note: We don't have the original point coordinates stored,
        so we can't reconstruct the exact lines. For now, keep existing
        lines when loading an image. In future, could store point coordinates
        in database.
        """
        self.measurement_lines = {}
        self.temp_lines = []
        self.measurement_labels = []
        self.image_label.set_measurement_lines([])
        self.image_label.set_measurement_rectangles([])
        self.image_label.set_measurement_labels([])

        if not self.current_image_id:
            return

        measurements = MeasurementDB.get_measurements_for_image(self.current_image_id)
        for measurement in measurements:
            if not all(measurement.get(f'p{i}_{axis}') is not None
                       for i in range(1, 5) for axis in ['x', 'y']):
                continue
            line1 = [
                measurement['p1_x'], measurement['p1_y'],
                measurement['p2_x'], measurement['p2_y']
            ]
            line2 = [
                measurement['p3_x'], measurement['p3_y'],
                measurement['p4_x'], measurement['p4_y']
            ]
            self.measurement_lines[measurement['id']] = [line1, line2]
            length_um = measurement.get('length_um')
            width_um = measurement.get('width_um')
            if length_um is None or width_um is None:
                dx1 = line1[2] - line1[0]
                dy1 = line1[3] - line1[1]
                dx2 = line2[2] - line2[0]
                dy2 = line2[3] - line2[1]
                dist1 = math.sqrt(dx1**2 + dy1**2) * self.microns_per_pixel
                dist2 = math.sqrt(dx2**2 + dy2**2) * self.microns_per_pixel
                length_um = max(dist1, dist2)
                width_um = min(dist1, dist2)
            self.measurement_labels.append(
                self._build_measurement_label(measurement['id'], line1, line2, length_um, width_um)
            )

        self.update_display_lines()

    def on_dimensions_changed(self, measurement_id, new_length_um, new_width_um, new_points):
        """Handle dimension changes from the preview widget."""
        # Calculate Q value
        q_value = new_length_um / new_width_um if new_width_um > 0 else 0

        # Update the database
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE spore_measurements
            SET length_um = ?, width_um = ?, notes = ?,
                p1_x = ?, p1_y = ?, p2_x = ?, p2_y = ?,
                p3_x = ?, p3_y = ?, p4_x = ?, p4_y = ?
            WHERE id = ?
        ''', (new_length_um, new_width_um, f"Q={q_value:.1f}",
              new_points[0].x(), new_points[0].y(),
              new_points[1].x(), new_points[1].y(),
              new_points[2].x(), new_points[2].y(),
              new_points[3].x(), new_points[3].y(),
              measurement_id))

        conn.commit()
        conn.close()

        # Update the UI
        self.update_measurements_table()
        self.update_statistics()

        # Update the measurement lines on the main image
        # Reconstruct the lines from the new points
        line1 = [new_points[0].x(), new_points[0].y(), new_points[1].x(), new_points[1].y()]
        line2 = [new_points[2].x(), new_points[2].y(), new_points[3].x(), new_points[3].y()]
        self.measurement_lines[measurement_id] = [line1, line2]
        for idx, label in enumerate(self.measurement_labels):
            if label.get("id") == measurement_id:
                self.measurement_labels[idx] = self._build_measurement_label(
                    measurement_id, line1, line2, new_length_um, new_width_um
                )
                break
        else:
            self.measurement_labels.append(
                self._build_measurement_label(measurement_id, line1, line2, new_length_um, new_width_um)
            )
        self.update_display_lines()

        self.measure_status_label.setText(self.tr("Click to measure next"))
        self.measure_status_label.setStyleSheet("color: #27ae60; font-weight: bold; font-size: 9pt;")

    def show_measurement_preview(self, measurement):
        """Show preview for a specific measurement."""
        if hasattr(self, "calibration_apply_btn"):
            self.calibration_apply_btn.setVisible(False)
        # Check if we have point coordinates
        if (measurement.get('p1_x') is not None and
            measurement.get('p1_y') is not None and
            measurement.get('p2_x') is not None and
            measurement.get('p2_y') is not None and
            measurement.get('p3_x') is not None and
            measurement.get('p3_y') is not None and
            measurement.get('p4_x') is not None and
            measurement.get('p4_y') is not None):

            # Reconstruct points
            from PySide6.QtCore import QPointF
            points = [
                QPointF(measurement['p1_x'], measurement['p1_y']),
                QPointF(measurement['p2_x'], measurement['p2_y']),
                QPointF(measurement['p3_x'], measurement['p3_y']),
                QPointF(measurement['p4_x'], measurement['p4_y'])
            ]

            # Update preview with measurement ID for editing
            self.spore_preview.set_spore(
                self.current_pixmap,
                points,
                measurement['length_um'],
                measurement['width_um'] or 0,
                self.microns_per_pixel,
                measurement['id']
            )
        else:
            # No point data available for this measurement
            self.spore_preview.clear()

    def on_measurement_selected(self):
        """Handle measurement selection from table."""
        selected_rows = self.measurements_table.selectedIndexes()
        if not selected_rows:
            self.spore_preview.clear()
            self._clear_measurement_highlight()
            return

        row = selected_rows[0].row()
        if row < len(self.measurements_cache):
            measurement = self.measurements_cache[row]
            measurement_type = measurement.get("measurement_type") or "spore"
            if hasattr(self, "measure_category_combo"):
                idx = self.measure_category_combo.findData(measurement_type)
                if idx >= 0:
                    self._measure_category_sync = True
                    self.measure_category_combo.setCurrentIndex(idx)
                    self._measure_category_sync = False
            image_id = measurement.get('image_id')
            if image_id and image_id != self.current_image_id:
                image_data = ImageDB.get_image(image_id)
                if image_data:
                    self.load_image_record(image_data, refresh_table=False)
            self.show_measurement_preview(measurement)
            self._highlight_selected_measurement(measurement)

    def update_measurements_table(self):
        """Update the measurements table."""
        if not self.current_image_id and not self.active_observation_id:
            self.measurements_table.setRowCount(0)
            self.spore_preview.clear()
            self.measurements_cache = []
            return

        image_labels = {}
        if self.active_observation_id:
            images = ImageDB.get_images_for_observation(self.active_observation_id)
            image_labels = {img['id']: f"Image {idx + 1}" for idx, img in enumerate(images)}
            measurements = MeasurementDB.get_measurements_for_observation(self.active_observation_id)
        else:
            measurements = MeasurementDB.get_measurements_for_image(self.current_image_id)
            if self.current_image_id:
                image_labels[self.current_image_id] = "Image 1"

        self.measurements_cache = measurements
        self.measurements_table.setRowCount(len(measurements))

        for row, measurement in enumerate(measurements):
            image_label = image_labels.get(measurement.get('image_id'), "Image ?")
            image_num = image_label.replace("Image ", "")
            image_item = QTableWidgetItem(image_num)
            image_item.setData(Qt.UserRole, measurement['id'])
            self.measurements_table.setItem(row, 0, image_item)

            category = self.normalize_measurement_category(measurement.get("measurement_type"))
            category_label = self.format_measurement_category(category)[:6]
            self.measurements_table.setItem(row, 1, QTableWidgetItem(category_label))

            # Length
            length = measurement['length_um']
            self.measurements_table.setItem(row, 2, QTableWidgetItem(f"{length:.2f}"))

            # Width
            width = measurement['width_um'] or 0
            self.measurements_table.setItem(row, 3, QTableWidgetItem(f"{width:.2f}"))

            # Q
            q = length / width if width > 0 else 0
            self.measurements_table.setItem(row, 4, QTableWidgetItem(f"{q:.2f}"))

        # Update gallery view only when visible
        if self.is_analysis_visible() and not self._suppress_gallery_update:
            self.refresh_gallery_filter_options()
            self.schedule_gallery_refresh()
        self.update_statistics()

    def normalize_measurement_category(self, category):
        """Normalize measurement categories for filtering."""
        if not category or category == "manual":
            return "spore"
        return str(category).lower()

    def format_measurement_category(self, category):
        """Format measurement categories for display."""
        labels = {
            "spore": "Spore",
            "basidia": "Basidia",
            "pleurocystidia": "Pleurocystidia",
            "cheilocystidia": "Cheilocystidia",
            "caulocystidia": "Caulocystidia",
            "other": "Other"
        }
        return labels.get(category, str(category).replace("_", " ").title())

    def refresh_gallery_filter_options(self):
        """Refresh gallery filter dropdown based on observation measurements."""
        if not hasattr(self, "gallery_filter_combo"):
            return

        current = self.gallery_filter_combo.currentData()
        self.gallery_filter_combo.blockSignals(True)
        self.gallery_filter_combo.clear()
        self.gallery_filter_combo.addItem("All", "all")

        if self.active_observation_id:
            raw_types = MeasurementDB.get_measurement_types_for_observation(self.active_observation_id)
            normalized = []
            for entry in raw_types:
                category = self.normalize_measurement_category(entry)
                if category not in normalized:
                    normalized.append(category)

            order = ["spore", "basidia", "pleurocystidia", "cheilocystidia", "caulocystidia", "other"]
            ordered = [cat for cat in order if cat in normalized]
            for category in normalized:
                if category not in ordered:
                    ordered.append(category)

            for category in ordered:
                self.gallery_filter_combo.addItem(
                    self.format_measurement_category(category),
                    category
                )

        self.gallery_filter_combo.blockSignals(False)
        desired = self._pending_gallery_category
        if desired is None:
            desired = self._load_gallery_settings().get("measurement_type")
        if not desired:
            desired = current
        if desired and self.gallery_filter_combo.findData(desired) >= 0:
            self.gallery_filter_combo.setCurrentIndex(self.gallery_filter_combo.findData(desired))
        else:
            idx = self.gallery_filter_combo.findData("spore")
            if idx >= 0:
                self.gallery_filter_combo.setCurrentIndex(idx)
        self._pending_gallery_category = None

    def is_analysis_visible(self):
        """Return True if the Analysis tab is active."""
        return hasattr(self, "tab_widget") and self.tab_widget.currentIndex() == 2

    def on_tab_changed(self, index):
        """Handle tab changes for analysis/measure."""
        if index in (1, 2) and hasattr(self, "observations_tab"):
            selected = self.observations_tab.get_selected_observation()
            if selected:
                obs_id, display_name = selected
                if self.active_observation_id != obs_id:
                    self.on_observation_selected(
                        obs_id,
                        display_name,
                        switch_tab=False,
                        suppress_gallery=True
                    )
        if index == 2:
            self.apply_gallery_settings()
            self.refresh_gallery_filter_options()
            self.schedule_gallery_refresh()

    def schedule_gallery_refresh(self):
        """Coalesce multiple refresh requests into a single gallery update."""
        self._gallery_refresh_pending = True
        if self._gallery_refresh_timer is None:
            self._gallery_refresh_timer = QTimer(self)
            self._gallery_refresh_timer.setSingleShot(True)
            self._gallery_refresh_timer.timeout.connect(self._run_scheduled_gallery_refresh)
        # debounce rapid callers
        self._gallery_refresh_timer.start(50)

    def _run_scheduled_gallery_refresh(self):
        if not self._gallery_refresh_pending:
            return
        if self._gallery_refresh_in_progress:
            return
        now = time.perf_counter()
        if now - self._gallery_last_refresh_time < 0.2:
            self._gallery_refresh_timer.start(100)
            return
        self._gallery_refresh_pending = False
        self.update_gallery()

    def get_gallery_measurements(self):
        """Get measurements to show in the gallery."""
        if self.active_observation_id:
            measurements = MeasurementDB.get_measurements_for_observation(self.active_observation_id)
        elif self.current_image_id:
            measurements = MeasurementDB.get_measurements_for_image(self.current_image_id)
        else:
            return []

        category = None
        if hasattr(self, "gallery_filter_combo"):
            category = self.gallery_filter_combo.currentData()

        if category and category != "all":
            measurements = [
                m for m in measurements
                if self.normalize_measurement_category(m.get("measurement_type")) == category
            ]

        return measurements

    def get_measurement_pixmap(self, measurement, pixmap_cache):
        """Get the pixmap for a measurement, cached by path."""
        image_path = measurement.get('image_filepath') or self.current_image_path
        if not image_path:
            return None

        if image_path == self.current_image_path and self.current_pixmap:
            return self.current_pixmap

        if image_path not in pixmap_cache:
            pixmap_cache[image_path] = QPixmap(image_path)
        return pixmap_cache[image_path]

    def update_gallery(self):
        """Update the gallery grid with all measured items."""
        from PySide6.QtWidgets import QLabel as QLabel2, QFrame, QVBoxLayout, QToolButton
        from PySide6.QtCore import QPointF

        if not self.is_analysis_visible():
            return
        if self._gallery_refresh_in_progress:
            return

        self._gallery_refresh_in_progress = True
        t0 = time.perf_counter()
        t_fetch = t0
        t_fetch_done = t0
        t_plot = t0
        t_loop_start = t0
        total = 0

        progress = QProgressDialog("Updating gallery...", None, 0, 0, self)
        progress.setWindowTitle("Gallery")
        progress.setCancelButton(None)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setWindowModality(Qt.ApplicationModal)
        progress.show()
        QApplication.processEvents()

        try:
            t_fetch = time.perf_counter()
            category = self.gallery_filter_combo.currentData() if hasattr(self, "gallery_filter_combo") else None
            if category != self._last_gallery_category:
                self.gallery_filter_mode = None
                self.gallery_filter_value = None
                self.gallery_filter_ids = set()
                self._last_gallery_category = category

            image_labels = {}
            if self.active_observation_id:
                images = ImageDB.get_images_for_observation(self.active_observation_id)
                image_labels = {img['id']: f"Image {idx + 1}" for idx, img in enumerate(images)}
            self.gallery_image_labels = image_labels

            # Clear existing gallery items
            while self.gallery_grid.count():
                item = self.gallery_grid.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            all_measurements = self.get_gallery_measurements()
            t_fetch_done = time.perf_counter()
            self.update_graph_plots(all_measurements)
            t_plot = time.perf_counter()
            measurements = self._filter_gallery_measurements(all_measurements)
            if not measurements:
                return

            total = len(measurements)
            progress.setRange(0, total)

            # Get orient checkbox state
            orient = hasattr(self, 'orient_checkbox') and self.orient_checkbox.isChecked()
            uniform_scale = hasattr(self, 'uniform_scale_checkbox') and self.uniform_scale_checkbox.isChecked()

            # Grid parameters
            items_per_row = self.gallery_columns_spin.value() if hasattr(self, "gallery_columns_spin") else 4
            thumbnail_size = 200
            pixmap_cache = {}
            image_color_cache = {}
            display_index = 1

            uniform_length_um = None
            if uniform_scale:
                for measurement in measurements:
                    length_um = measurement.get("length_um")
                    if length_um is None:
                        continue
                    if uniform_length_um is None or length_um > uniform_length_um:
                        uniform_length_um = length_um
            t_loop_start = time.perf_counter()
            for idx, measurement in enumerate(measurements, start=1):
                # Check if we have point coordinates
                if not all(measurement.get(f'p{i}_{axis}') is not None
                          for i in range(1, 5) for axis in ['x', 'y']):
                    continue

                pixmap = self.get_measurement_pixmap(measurement, pixmap_cache)
                if not pixmap or pixmap.isNull():
                    continue

                measurement_id = measurement['id']

                # Reconstruct points
                points = [
                    QPointF(measurement['p1_x'], measurement['p1_y']),
                    QPointF(measurement['p2_x'], measurement['p2_y']),
                    QPointF(measurement['p3_x'], measurement['p3_y']),
                    QPointF(measurement['p4_x'], measurement['p4_y'])
                ]

                # Get extra rotation for this measurement
                extra_rotation = measurement.get("gallery_rotation") or self.gallery_rotations.get(measurement_id, 0)
                image_id = measurement.get('image_id')
                stored_color = None
                mpp = None
                if image_id:
                    if image_id not in image_color_cache:
                        image_data = ImageDB.get_image(image_id)
                        image_color_cache[image_id] = (
                            {
                                "measure_color": image_data.get('measure_color') if image_data else None,
                                "mpp": image_data.get('scale_microns_per_pixel') if image_data else None
                            }
                        )
                    cached = image_color_cache[image_id]
                    stored_color = cached.get("measure_color") if cached else None
                    mpp = cached.get("mpp") if cached else None
                measure_color = QColor(stored_color) if stored_color else self.default_measure_color
                uniform_length_px = None
                if uniform_scale and uniform_length_um:
                    if not mpp or mpp <= 0:
                        p1 = QPointF(measurement['p1_x'], measurement['p1_y'])
                        p2 = QPointF(measurement['p2_x'], measurement['p2_y'])
                        p3 = QPointF(measurement['p3_x'], measurement['p3_y'])
                        p4 = QPointF(measurement['p4_x'], measurement['p4_y'])
                        line1_len = math.hypot(p2.x() - p1.x(), p2.y() - p1.y())
                        line2_len = math.hypot(p4.x() - p3.x(), p4.y() - p3.y())
                        length_px = max(line1_len, line2_len)
                        length_um = measurement.get("length_um")
                        if length_px > 0 and length_um:
                            mpp = float(length_um) / float(length_px)
                    if mpp and mpp > 0:
                        uniform_length_px = float(uniform_length_um) / float(mpp)

                # Create thumbnail
                thumbnail = self.create_spore_thumbnail(
                    pixmap,
                    points,
                    measurement['length_um'],
                    measurement['width_um'] or 0,
                    thumbnail_size,
                    display_index,
                    orient=orient,
                    extra_rotation=extra_rotation,
                    uniform_length_px=uniform_length_px,
                    color=measure_color
                )

                if thumbnail:
                    # Create container frame for thumbnail + rotate button
                    container = QFrame()
                    container.setFixedSize(thumbnail_size, thumbnail_size)
                    container_layout = QVBoxLayout(container)
                    container_layout.setContentsMargins(0, 0, 0, 0)
                    container_layout.setSpacing(0)

                    # Create label for thumbnail
                    label = QLabel2()
                    label.setPixmap(thumbnail)
                    label.setFixedSize(thumbnail_size, thumbnail_size)
                    label.setStyleSheet("border: 2px solid #3498db; background: white;")
                    label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
                    container_layout.addWidget(label)

                    if orient:
                        # Add rotate button overlay in bottom-right corner
                        rotate_btn = QToolButton(container)
                        rotate_btn.setIcon(QIcon(str(Path(__file__).parent.parent / "assets" / "icons" / "rotate.svg")))
                        rotate_btn.setToolTip("Rotate 180")
                        rotate_btn.setProperty("instant_tooltip", True)
                        rotate_btn.installEventFilter(self)
                        rotate_btn.setFixedSize(24, 24)
                        rotate_btn.setIconSize(QSize(22, 22))
                        rotate_btn.setStyleSheet(
                            "QToolButton { background: transparent; border: none; }"
                            "QToolButton:hover { background-color: rgba(0, 0, 0, 0.08); }"
                        )
                        rotate_btn.move(thumbnail_size - 28, thumbnail_size - 28)
                        rotate_btn.show()
                        rotate_btn.clicked.connect(
                            lambda checked, mid=measurement_id: self.rotate_gallery_thumbnail(mid)
                        )
                        rotate_btn.raise_()

                    link_btn = QToolButton(container)
                    link_btn.setIcon(QIcon(str(Path(__file__).parent.parent / "assets" / "icons" / "link.svg")))
                    link_label = image_labels.get(image_id, "Image ?")
                    link_btn.setToolTip(link_label)
                    link_btn.setProperty("instant_tooltip", True)
                    link_btn.installEventFilter(self)
                    link_btn.setFixedSize(24, 24)
                    link_btn.setIconSize(QSize(22, 22))
                    link_btn.setStyleSheet(
                        "QToolButton { background: transparent; border: none; }"
                        "QToolButton:hover { background-color: rgba(0, 0, 0, 0.08); }"
                    )
                    link_btn.move(4, 4)
                    link_btn.show()
                    link_btn.clicked.connect(
                        lambda checked, mid=measurement_id: self.open_measurement_from_gallery(mid)
                    )
                    link_btn.raise_()

                # Add to grid
                row = (display_index - 1) // items_per_row
                col = (display_index - 1) % items_per_row
                self.gallery_grid.addWidget(container, row, col)
                display_index += 1
                if idx % 10 == 0 or idx == total:
                    progress.setLabelText(f"Updating gallery... ({idx}/{total})")
                    progress.setValue(idx)
                    QApplication.processEvents()
        finally:
            progress.hide()
            t_end = time.perf_counter()
            self._gallery_last_refresh_time = t_end
            self._gallery_refresh_in_progress = False
            if self._gallery_refresh_pending:
                self.schedule_gallery_refresh()

    def _filter_gallery_measurements(self, measurements):
        """Apply gallery selection filter to measurements."""
        if not measurements:
            return measurements
        if self.gallery_filter_mode == "points" and self.gallery_filter_ids:
            return [m for m in measurements if m.get("id") in self.gallery_filter_ids]
        if self.gallery_filter_mode == "bin" and self.gallery_filter_value:
            metric, min_val, max_val = self.gallery_filter_value
            filtered = []
            for m in measurements:
                length = m.get("length_um")
                width = m.get("width_um")
                if length is None or width is None or width <= 0:
                    continue
                if metric == "L":
                    value = length
                elif metric == "W":
                    value = width
                else:
                    value = length / width
                if min_val <= value <= max_val:
                    filtered.append(m)
            return filtered
        return measurements

    def clear_gallery_filter(self):
        """Clear the gallery selection filter."""
        self.gallery_filter_mode = None
        self.gallery_filter_value = None
        self.gallery_filter_ids = set()
        self._update_gallery_filter_label()
        self.schedule_gallery_refresh()

    def update_graph_plots(self, measurements):
        """Update analysis graphs from measurement data."""
        if not hasattr(self, "gallery_plot_figure"):
            return

        plot_settings = getattr(self, "gallery_plot_settings", {}) or {}
        bins = int(plot_settings.get("bins", 8))
        show_ci = bool(plot_settings.get("ci", True))
        show_legend = bool(plot_settings.get("legend", False))
        show_avg_q = bool(plot_settings.get("avg_q", True))
        show_q_minmax = bool(plot_settings.get("q_minmax", True))

        lengths = []
        widths = []
        measurement_ids = []
        measurement_image_ids = []
        for m in measurements or []:
            length = m.get("length_um")
            width = m.get("width_um")
            if length is None or width is None or width <= 0:
                continue
            lengths.append(float(length))
            widths.append(float(width))
            measurement_ids.append(m.get("id"))
            measurement_image_ids.append(m.get("image_id"))

        self.gallery_plot_figure.clear()
        gs = self.gallery_plot_figure.add_gridspec(2, 3, height_ratios=[3, 1], hspace=0.3, wspace=0.3)
        ax_scatter = self.gallery_plot_figure.add_subplot(gs[0, :])
        ax_len = self.gallery_plot_figure.add_subplot(gs[1, 0])
        ax_wid = self.gallery_plot_figure.add_subplot(gs[1, 1])
        ax_q = self.gallery_plot_figure.add_subplot(gs[1, 2])
        self.gallery_plot_figure.subplots_adjust(top=0.98, bottom=0.1)

        stats = self._stats_from_measurements(lengths, widths)
        spore_stats = None
        if self.active_observation_id:
            spore_stats = MeasurementDB.get_statistics_for_observation(
                self.active_observation_id,
                measurement_category="spore"
            )
        if hasattr(self, "gallery_stats_label"):
            if spore_stats:
                self.gallery_stats_label.setText(self.format_literature_string(spore_stats))
            else:
                self.gallery_stats_label.setText("")

        if not lengths:
            self.gallery_scatter_id_map = {}
            self.gallery_hist_patches = {}
            ax_scatter.text(0.5, 0.5, "No measurements", ha="center", va="center")
            ax_scatter.set_axis_off()
            ax_len.set_axis_off()
            ax_wid.set_axis_off()
            ax_q.set_axis_off()
            self.gallery_plot_canvas.draw()
            return

        L = np.asarray(lengths)
        W = np.asarray(widths)
        category = self.gallery_filter_combo.currentData() if hasattr(self, "gallery_filter_combo") else None
        normalized = self.normalize_measurement_category(category) if category else None
        show_q = normalized == "spore"
        Q = L / W
        if category and category != "all":
            category_label = self.format_measurement_category(category)
        elif category == "all":
            category_label = "All measurements"
        else:
            category_label = "Measurements"

        self.gallery_hist_patches = {}
        self.gallery_scatter = None
        self.gallery_scatter_id_map = {}
        ax_scatter.set_xlabel(self.tr("Length (μm)"))
        ax_scatter.set_ylabel(self.tr("Width (μm)"))

        image_labels = getattr(self, "gallery_image_labels", {}) or {}
        image_color_map = {}
        hist_color = "#3498db"

        if show_legend and image_labels:
            grouped = {}
            for length, width, measurement_id, image_id in zip(
                L, W, measurement_ids, measurement_image_ids
            ):
                grouped.setdefault(image_id, {"L": [], "W": [], "ids": []})
                grouped[image_id]["L"].append(length)
                grouped[image_id]["W"].append(width)
                grouped[image_id]["ids"].append(measurement_id)

            for image_id in image_labels.keys():
                if image_id not in grouped:
                    continue
                label = image_labels.get(image_id, f"Image {image_id}")
                color = image_color_map.get(image_id) or ax_scatter._get_lines.get_next_color()
                image_color_map[image_id] = color
                data = grouped[image_id]
                collection = ax_scatter.scatter(
                    data["L"], data["W"], s=20, alpha=0.8, picker=5, label=label, color=color
                )
                self.gallery_scatter_id_map[collection] = data["ids"]
            for image_id, data in grouped.items():
                if image_id in image_labels:
                    continue
                color = image_color_map.get(image_id) or ax_scatter._get_lines.get_next_color()
                image_color_map[image_id] = color
                collection = ax_scatter.scatter(
                    data["L"], data["W"], s=20, alpha=0.8, picker=5, label=f"Image {image_id}", color=color
                )
                self.gallery_scatter_id_map[collection] = data["ids"]
            if category_label:
                ax_scatter.plot([], [], marker="o", color=hist_color, linestyle="", label=category_label)
        else:
            self.gallery_scatter = ax_scatter.scatter(
                L, W, s=20, alpha=0.8, picker=5, color=hist_color, label=category_label
            )
            self.gallery_scatter_id_map[self.gallery_scatter] = measurement_ids

        max_len = float(np.max(L))
        min_len = float(np.min(L))
        min_w = float(np.min(W))
        if show_q and show_avg_q:
            avg_q = float(np.mean(Q))
            max_w = float(np.max(W))
            line_w = np.array([min_w, max_w])
            line_l = avg_q * line_w
            ax_scatter.plot(line_l, line_w, linestyle="--", color="#7f8c8d", label=f"Avg Q={avg_q:.1f}")

        if show_q and show_q_minmax:
            q_min = float(np.min(Q))
            q_max = float(np.max(Q))
            if q_min > 0:
                start_x = max(min_len, min_w * q_min)
                if start_x < max_len:
                    ax_scatter.plot([start_x, max_len], [start_x / q_min, max_len / q_min],
                                    color="black", linewidth=1.0, label="Q min/max")
            if q_max > 0:
                start_x = max(min_len, min_w * q_max)
                if start_x < max_len:
                    ax_scatter.plot([start_x, max_len], [start_x / q_max, max_len / q_max],
                                    color="black", linewidth=1.0)

        if show_ci and len(L) >= 3:
            ellipse = self._confidence_ellipse_points(L, W, confidence=0.95)
            if ellipse is not None:
                ex, ey = ellipse
                ax_scatter.plot(ex, ey, color="#e74c3c", linewidth=1.5, label="95% ellipse")

        ref_l_min = self.reference_values.get("length_min")
        ref_l_max = self.reference_values.get("length_max")
        ref_l_avg = self.reference_values.get("length_p50")
        ref_l_p05 = self.reference_values.get("length_p05")
        ref_l_p50 = self.reference_values.get("length_p50")
        ref_l_p95 = self.reference_values.get("length_p95")
        ref_w_min = self.reference_values.get("width_min")
        ref_w_max = self.reference_values.get("width_max")
        ref_w_avg = self.reference_values.get("width_p50")
        ref_w_p05 = self.reference_values.get("width_p05")
        ref_w_p50 = self.reference_values.get("width_p50")
        ref_w_p95 = self.reference_values.get("width_p95")
        ref_q_min = self.reference_values.get("q_min")
        ref_q_max = self.reference_values.get("q_max")
        ref_q_avg = self.reference_values.get("q_p50")

        def _fallback(low, mid_low, mid_high, high):
            left = low if low is not None else mid_low
            right = high if high is not None else mid_high
            if left is None and right is not None:
                left = right
            if right is None and left is not None:
                right = left
            return left, right

        l_left, l_right = _fallback(ref_l_min, ref_l_p05, ref_l_p95, ref_l_max)
        w_bottom, w_top = _fallback(ref_w_min, ref_w_p05, ref_w_p95, ref_w_max)

        x_min = plot_settings.get("x_min")
        x_max = plot_settings.get("x_max")
        y_min = plot_settings.get("y_min")
        y_max = plot_settings.get("y_max")
        if x_min is not None or x_max is not None:
            ax_scatter.set_xlim(left=x_min, right=x_max)
        if y_min is not None or y_max is not None:
            ax_scatter.set_ylim(bottom=y_min, top=y_max)

        if l_left is not None and l_right is not None and w_bottom is not None and w_top is not None:
            rect = Rectangle(
                (l_left, w_bottom),
                max(0.0, l_right - l_left),
                max(0.0, w_top - w_bottom),
                fill=False,
                edgecolor="#2c3e50",
                linewidth=1.5,
                linestyle=":"
            )
            ax_scatter.add_patch(rect)
            ax_scatter.plot([], [], color="#2c3e50", linestyle=":", label="Ref min/max")

        y0 = w_bottom if w_bottom is not None else min_w
        y1 = w_top if w_top is not None else float(np.max(W))
        x0 = l_left if l_left is not None else min_len
        x1 = l_right if l_right is not None else float(np.max(L))

        def _vline(x, color, linestyle, label=None):
            if x is None:
                return
            ax_scatter.plot([x, x], [y0, y1], color=color, linestyle=linestyle, linewidth=1.0, label=label)

        def _hline(y, color, linestyle, label=None):
            if y is None:
                return
            ax_scatter.plot([x0, x1], [y, y], color=color, linestyle=linestyle, linewidth=1.0, label=label)

        _vline(ref_l_min, "#2c3e50", ":", label="Ref min/max")
        _vline(ref_l_max, "#2c3e50", ":")
        _hline(ref_w_min, "#2c3e50", ":")
        _hline(ref_w_max, "#2c3e50", ":")
        _vline(ref_l_p05, "#e74c3c", ":")
        if ref_l_p95 is not None:
            y95 = y1
            if ref_l_max is not None and ref_w_p95 is not None:
                y95 = ref_w_p95
            ax_scatter.plot([ref_l_p95, ref_l_p95], [y0, y95],
                            color="#e74c3c", linestyle=":", linewidth=1.0)
        _hline(ref_w_p05, "#e74c3c", ":")
        if ref_w_p95 is not None:
            x95 = x1
            if ref_w_max is not None and ref_l_p95 is not None:
                x95 = ref_l_p95
            ax_scatter.plot([x0, x95], [ref_w_p95, ref_w_p95],
                            color="#e74c3c", linestyle=":", linewidth=1.0)

        if ref_l_avg is not None and ref_w_avg is not None:
            ref_radius = 0.03 * max(float(np.max(L)), float(np.max(W)), ref_l_avg, ref_w_avg)
            circ = Circle((ref_l_avg, ref_w_avg), ref_radius, fill=False, edgecolor="#27ae60", linewidth=1.5)
            ax_scatter.add_patch(circ)
            ax_scatter.plot([], [], color="#27ae60", label="Ref avg")

        if show_q:
            ref_line_max = ref_l_max if ref_l_max is not None else float(np.max(L))
            if show_q_minmax:
                if ref_q_min is not None and ref_q_min > 0:
                    start_x = max(min_len, min_w * ref_q_min)
                    if start_x < ref_line_max:
                        ax_scatter.plot([start_x, ref_line_max], [start_x / ref_q_min, ref_line_max / ref_q_min],
                                        color="#2c3e50", linestyle=":")
                if ref_q_max is not None and ref_q_max > 0:
                    start_x = max(min_len, min_w * ref_q_max)
                    if start_x < ref_line_max:
                        ax_scatter.plot([start_x, ref_line_max], [start_x / ref_q_max, ref_line_max / ref_q_max],
                                        color="#2c3e50", linestyle=":")
            if show_avg_q and ref_q_avg is not None and ref_q_avg > 0:
                start_x = max(min_len, min_w * ref_q_avg)
                if start_x < ref_line_max:
                    ax_scatter.plot([start_x, ref_line_max], [start_x / ref_q_avg, ref_line_max / ref_q_avg],
                                    color="#8e44ad", linestyle="-.", label=f"Ref Q={ref_q_avg:.1f}")

        handles, labels = ax_scatter.get_legend_handles_labels()
        if labels:
            ax_scatter.legend(loc="best", fontsize=8)

        l_bins = np.histogram_bin_edges(L, bins=bins)
        w_bins = np.histogram_bin_edges(W, bins=bins)
        q_bins = np.histogram_bin_edges(Q, bins=bins) if show_q else None

        if show_legend and image_labels:
            grouped = {}
            for length, width, measurement_id, image_id in zip(
                L, W, measurement_ids, measurement_image_ids
            ):
                grouped.setdefault(image_id, {"L": [], "W": [], "Q": []})
                grouped[image_id]["L"].append(length)
                grouped[image_id]["W"].append(width)
            if show_q:
                for length, width, image_id in zip(L, W, measurement_image_ids):
                    grouped.setdefault(image_id, {"L": [], "W": [], "Q": []})
                    grouped[image_id]["Q"].append(length / width)

            for image_id in image_labels.keys():
                if image_id not in grouped:
                    continue
                color = image_color_map.get(image_id) or ax_scatter._get_lines.get_next_color()
                image_color_map[image_id] = color
                data = grouped[image_id]
                _, l_bins, l_patches = ax_len.hist(data["L"], bins=l_bins, color=color, alpha=0.35)
                _, w_bins, w_patches = ax_wid.hist(data["W"], bins=w_bins, color=color, alpha=0.35)
                if show_q:
                    _, q_bins, q_patches = ax_q.hist(data["Q"], bins=q_bins, color=color, alpha=0.35)
                for i, patch in enumerate(l_patches):
                    patch.set_picker(True)
                    self.gallery_hist_patches[patch] = ("L", l_bins[i], l_bins[i + 1])
                for i, patch in enumerate(w_patches):
                    patch.set_picker(True)
                    self.gallery_hist_patches[patch] = ("W", w_bins[i], w_bins[i + 1])
                if show_q:
                    for i, patch in enumerate(q_patches):
                        patch.set_picker(True)
                        self.gallery_hist_patches[patch] = ("Q", q_bins[i], q_bins[i + 1])
        else:
            _, l_bins, l_patches = ax_len.hist(L, bins=l_bins, color=hist_color)
            ax_len.set_ylabel("Count")
            for i, patch in enumerate(l_patches):
                patch.set_picker(True)
                self.gallery_hist_patches[patch] = ("L", l_bins[i], l_bins[i + 1])

            _, w_bins, w_patches = ax_wid.hist(W, bins=w_bins, color=hist_color)
            for i, patch in enumerate(w_patches):
                patch.set_picker(True)
                self.gallery_hist_patches[patch] = ("W", w_bins[i], w_bins[i + 1])

            if show_q:
                _, q_bins, q_patches = ax_q.hist(Q, bins=q_bins, color=hist_color)
                for i, patch in enumerate(q_patches):
                    patch.set_picker(True)
                    self.gallery_hist_patches[patch] = ("Q", q_bins[i], q_bins[i + 1])
        if ref_l_p05 is not None:
            ax_len.axvline(ref_l_p05, color="#e74c3c", linestyle=":", linewidth=1.2)
        if ref_l_p95 is not None:
            ax_len.axvline(ref_l_p95, color="#e74c3c", linestyle=":", linewidth=1.2)
        if ref_w_p05 is not None:
            ax_wid.axvline(ref_w_p05, color="#e74c3c", linestyle=":", linewidth=1.2)
        if ref_w_p95 is not None:
            ax_wid.axvline(ref_w_p95, color="#e74c3c", linestyle=":", linewidth=1.2)
        if ref_l_min is not None:
            ax_len.axvline(ref_l_min, color="#2c3e50", linestyle=":", linewidth=1.0)
        if ref_l_max is not None:
            ax_len.axvline(ref_l_max, color="#2c3e50", linestyle=":", linewidth=1.0)
        if ref_w_min is not None:
            ax_wid.axvline(ref_w_min, color="#2c3e50", linestyle=":", linewidth=1.0)
        if ref_w_max is not None:
            ax_wid.axvline(ref_w_max, color="#2c3e50", linestyle=":", linewidth=1.0)
        ax_len.set_xlabel(self.tr("Length (μm)"))
        ax_len.set_ylabel("Count")
        ax_wid.set_xlabel(self.tr("Width (μm)"))
        if show_q:
            ax_q.set_xlabel("Q (L/W)")
        else:
            ax_q.set_axis_off()

        self.gallery_plot_canvas.draw()

    def export_graph_plot_svg(self):
        """Export analysis graphs to an SVG file."""
        if not hasattr(self, "gallery_plot_figure"):
            return
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export Plot",
            "",
            "SVG Files (*.svg)"
        )
        if not filename:
            return
        if not filename.lower().endswith(".svg"):
            filename = f"{filename}.svg"
        try:
            self.gallery_plot_figure.savefig(filename, format="svg")
            self.measure_status_label.setText(f"✓ Plot exported to {Path(filename).name}")
            self.measure_status_label.setStyleSheet("color: #27ae60; font-weight: bold; font-size: 9pt;")
        except Exception as exc:
            QMessageBox.warning(self, "Export Failed", str(exc))

    def on_gallery_plot_pick(self, event):
        """Handle pick events from gallery plots."""
        scatter_map = getattr(self, "gallery_scatter_id_map", {})
        if event.artist in scatter_map:
            indices = getattr(event, "ind", [])
            selected_ids = set()
            ids = scatter_map.get(event.artist, [])
            for idx in indices:
                if idx < len(ids):
                    measurement_id = ids[idx]
                    if measurement_id:
                        selected_ids.add(measurement_id)
            if selected_ids:
                self.gallery_filter_mode = "points"
                self.gallery_filter_value = None
                self.gallery_filter_ids = selected_ids
                self._update_gallery_filter_label()
                self.schedule_gallery_refresh()
            return

        if hasattr(self, "gallery_hist_patches") and event.artist in self.gallery_hist_patches:
            metric, min_val, max_val = self.gallery_hist_patches[event.artist]
            self.gallery_filter_mode = "bin"
            self.gallery_filter_value = (metric, min_val, max_val)
            self.gallery_filter_ids = set()
            self._update_gallery_filter_label()
            self.schedule_gallery_refresh()

    def _update_gallery_filter_label(self):
        if not hasattr(self, "gallery_filter_label"):
            return
        label = ""
        if self.gallery_filter_mode == "bin" and self.gallery_filter_value:
            metric, min_val, max_val = self.gallery_filter_value
            name_map = {"L": self.tr("Length"), "W": self.tr("Width"), "Q": "Q"}
            name = name_map.get(metric, metric)
            label = f"{name}: {min_val:.2f} - {max_val:.2f}"
        self.gallery_filter_label.setText(label)

    def _get_measurement_by_id(self, measurement_id):
        """Load a measurement record by id."""
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM spore_measurements WHERE id = ?', (measurement_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def open_measurement_from_gallery(self, measurement_id):
        """Open a measurement in the Measure tab from the gallery."""
        if self.measurement_active:
            self.stop_measurement()
        measurement = self._get_measurement_by_id(measurement_id)
        if not measurement:
            return
        self._suppress_gallery_update = True
        try:
            image_id = measurement.get("image_id")
            if image_id and image_id != self.current_image_id:
                image_data = ImageDB.get_image(image_id)
                if image_data:
                    self.load_image_record(image_data, refresh_table=True)
            else:
                self.update_measurements_table()
        finally:
            self._suppress_gallery_update = False
        self.select_measurement_in_table(measurement_id)
        if hasattr(self, "tab_widget"):
            self.tab_widget.setCurrentIndex(1)

    def _highlight_selected_measurement(self, measurement):
        if self.measurement_active or not measurement:
            self._clear_measurement_highlight()
            return
        measurement_id = measurement.get("id")
        if not measurement_id:
            self._clear_measurement_highlight()
            return
        if self.measure_mode == "lines":
            indices = getattr(self, "_line_index_map", {}).get(measurement_id, [])
            self.image_label.set_selected_line_indices(indices)
            self.image_label.set_selected_rect_index(-1)
        else:
            rect_index = getattr(self, "_rect_index_map", {}).get(measurement_id, -1)
            self.image_label.set_selected_rect_index(rect_index)
            self.image_label.set_selected_line_indices([])

    def _clear_measurement_highlight(self):
        if hasattr(self, "image_label"):
            self.image_label.set_selected_rect_index(-1)
            self.image_label.set_selected_line_indices([])

    def _confidence_ellipse_points(self, x, y, confidence=0.95, n_points=300):
        """Return ellipse points for a confidence region."""
        if len(x) < 3 or len(y) < 3:
            return None
        chi2_map = {
            0.90: 4.605170185988092,
            0.95: 5.991464547107979,
            0.99: 9.210340371976184,
        }
        chi2_val = chi2_map.get(confidence)
        if chi2_val is None:
            return None

        mean = np.array([np.mean(x), np.mean(y)])
        cov = np.cov(x, y, ddof=1)
        eigvals, eigvecs = np.linalg.eigh(cov)
        order = np.argsort(eigvals)[::-1]
        eigvals = eigvals[order]
        eigvecs = eigvecs[:, order]
        axis_lengths = np.sqrt(eigvals * chi2_val)

        t = np.linspace(0, 2 * math.pi, n_points)
        circle = np.vstack((np.cos(t), np.sin(t)))
        ellipse = (eigvecs @ (axis_lengths[:, None] * circle)) + mean[:, None]
        return ellipse[0, :], ellipse[1, :]

    def _stats_from_measurements(self, lengths, widths):
        """Compute stats dictionary from length/width lists."""
        if not lengths:
            return None
        lengths = np.asarray(lengths)
        widths = np.asarray(widths) if widths else np.asarray([])
        stats = {
            "count": int(len(lengths)),
            "length_mean": float(np.mean(lengths)),
            "length_std": float(np.std(lengths)),
            "length_min": float(np.min(lengths)),
            "length_max": float(np.max(lengths)),
            "length_p5": float(np.percentile(lengths, 5)),
            "length_p95": float(np.percentile(lengths, 95)),
        }
        if widths.size:
            ratios = lengths[:len(widths)] / widths
            stats.update({
                "width_mean": float(np.mean(widths)),
                "width_std": float(np.std(widths)),
                "width_min": float(np.min(widths)),
                "width_max": float(np.max(widths)),
                "width_p5": float(np.percentile(widths, 5)),
                "width_p95": float(np.percentile(widths, 95)),
                "ratio_mean": float(np.mean(ratios)),
                "ratio_min": float(np.min(ratios)),
                "ratio_max": float(np.max(ratios)),
                "ratio_p5": float(np.percentile(ratios, 5)),
                "ratio_p95": float(np.percentile(ratios, 95)),
            })
        return stats

    def rotate_gallery_thumbnail(self, measurement_id):
        """Rotate a gallery thumbnail by 180 degrees."""
        current = self.gallery_rotations.get(measurement_id, 0)
        new_rotation = (current + 180) % 360
        self.gallery_rotations[measurement_id] = new_rotation
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE spore_measurements SET gallery_rotation = ? WHERE id = ?',
            (new_rotation, measurement_id)
        )
        conn.commit()
        conn.close()
        self.schedule_gallery_refresh()


    def create_spore_thumbnail(self, pixmap, points, length_um, width_um, size,
                               measurement_num=0, orient=False, extra_rotation=0,
                               uniform_length_px=None, color=None):
        """Create a thumbnail image of a single measurement.

        Args:
            pixmap: Source image
            points: List of 4 QPointF measurement points
            length_um: Length in microns
            width_um: Width in microns
            size: Output thumbnail size (square)
            measurement_num: Number to display on thumbnail
            orient: If True, rotate so length axis is vertical
            extra_rotation: Additional rotation in degrees (e.g., 180 for flip)
        """
        from PySide6.QtGui import QPainter, QColor, QPolygonF, QPen, QTransform
        from PySide6.QtCore import QPointF, QRectF
        import math

        if not pixmap:
            return None

        # Calculate center and dimensions
        line1_mid = QPointF((points[0].x() + points[1].x()) / 2, (points[0].y() + points[1].y()) / 2)
        line2_mid = QPointF((points[2].x() + points[3].x()) / 2, (points[2].y() + points[3].y()) / 2)
        center = QPointF((line1_mid.x() + line2_mid.x()) / 2, (line1_mid.y() + line2_mid.y()) / 2)

        # Calculate line lengths
        line1_vec = QPointF(points[1].x() - points[0].x(), points[1].y() - points[0].y())
        line2_vec = QPointF(points[3].x() - points[2].x(), points[3].y() - points[2].y())
        line1_len = math.sqrt(line1_vec.x()**2 + line1_vec.y()**2)
        line2_len = math.sqrt(line2_vec.x()**2 + line2_vec.y()**2)

        # Keep stable orientation based on the first measurement line
        length_px = line1_len
        width_px = line2_len

        # Calculate rotation angle if orient is enabled
        rotation_angle = extra_rotation  # Start with any manual extra rotation
        if orient and line1_len > 0:
            # line1_vec IS the length axis (points[0] to points[1] is the center/length line)
            # We want this axis to be vertical (pointing up or down)
            # atan2(x, -y) gives angle from negative y-axis (up direction)
            current_angle = math.atan2(line1_vec.x(), -line1_vec.y())
            rotation_angle += -math.degrees(current_angle)

        # If we rotate for orient, rotate the crop source and points too
        if abs(rotation_angle) > 0.1:
            center_src = QPointF(pixmap.width() / 2, pixmap.height() / 2)
            transform = QTransform()
            transform.translate(center_src.x(), center_src.y())
            transform.rotate(rotation_angle)
            transform.translate(-center_src.x(), -center_src.y())
            rotated_pixmap = pixmap.transformed(transform, Qt.SmoothTransformation)

            # Transform points into rotated pixmap space
            rotated_points = [transform.map(p) for p in points]

            # Offset if the rotated pixmap origin changed
            src_rect = transform.mapRect(QRectF(0, 0, pixmap.width(), pixmap.height()))
            offset = QPointF(-src_rect.x(), -src_rect.y())
            rotated_points = [p + offset for p in rotated_points]
            pixmap = rotated_pixmap
            points = rotated_points

            # Recompute vectors/center with rotated points
            line1_vec = QPointF(points[1].x() - points[0].x(), points[1].y() - points[0].y())
            line2_vec = QPointF(points[3].x() - points[2].x(), points[3].y() - points[2].y())
            line1_len = math.sqrt(line1_vec.x()**2 + line1_vec.y()**2)
            line2_len = math.sqrt(line2_vec.x()**2 + line2_vec.y()**2)
            line1_mid = QPointF((points[0].x() + points[1].x()) / 2, (points[0].y() + points[1].y()) / 2)
            line2_mid = QPointF((points[2].x() + points[3].x()) / 2, (points[2].y() + points[3].y()) / 2)
            center = QPointF((line1_mid.x() + line2_mid.x()) / 2, (line1_mid.y() + line2_mid.y()) / 2)
            length_px = line1_len
            width_px = line2_len
            rotation_angle = 0

        # Crop parameters
        max_dim = uniform_length_px if uniform_length_px else max(length_px, width_px)
        padding = max_dim * 0.15
        crop_size = max_dim + padding * 2

        # Create crop rectangle
        crop_rect = QRectF(
            center.x() - crop_size / 2,
            center.y() - crop_size / 2,
            crop_size,
            crop_size
        )

        # Ensure within bounds
        crop_rect = crop_rect.intersected(
            QRectF(0, 0, pixmap.width(), pixmap.height())
        )

        # Crop and scale
        cropped = pixmap.copy(crop_rect.toRect())
        scaled = cropped.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        # Draw overlay
        result = QPixmap(size, size)
        result.fill(QColor(236, 240, 241))

        painter = QPainter(result)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        # Calculate center position for drawing
        img_x = (size - scaled.width()) / 2
        img_y = (size - scaled.height()) / 2

        # Apply rotation if needed (orient mode or extra rotation)
        if abs(rotation_angle) > 0.1:
            painter.save()
            painter.translate(size / 2, size / 2)
            painter.rotate(rotation_angle)
            painter.translate(-size / 2, -size / 2)
            painter.drawPixmap(int(img_x), int(img_y), scaled)
            painter.restore()
        else:
            painter.drawPixmap(int(img_x), int(img_y), scaled)

        # Draw rectangle overlay
        length_dir = QPointF(line1_vec.x() / line1_len, line1_vec.y() / line1_len)
        width_dir = QPointF(-length_dir.y(), length_dir.x())
        half_length = length_px / 2
        half_width = width_px / 2

        img_scale = min(
            scaled.width() / cropped.width(),
            scaled.height() / cropped.height()
        )

        # Calculate where the measurement center appears on screen
        # When crop_rect gets clipped by intersected(), the measurement center
        # is no longer at the center of the cropped image
        center_in_crop_x = center.x() - crop_rect.x()
        center_in_crop_y = center.y() - crop_rect.y()
        screen_center = QPointF(
            img_x + center_in_crop_x * img_scale,
            img_y + center_in_crop_y * img_scale
        )

        # Apply rotation to the rectangle overlay as well
        if abs(rotation_angle) > 0.1:
            # Rotate the screen_center around the image center
            rad = math.radians(rotation_angle)
            cos_a, sin_a = math.cos(rad), math.sin(rad)
            cx, cy = size / 2, size / 2
            dx = screen_center.x() - cx
            dy = screen_center.y() - cy
            screen_center = QPointF(
                cx + dx * cos_a - dy * sin_a,
                cy + dx * sin_a + dy * cos_a
            )
            # Also rotate the axis directions
            new_length_dir = QPointF(
                length_dir.x() * cos_a - length_dir.y() * sin_a,
                length_dir.x() * sin_a + length_dir.y() * cos_a
            )
            new_width_dir = QPointF(
                width_dir.x() * cos_a - width_dir.y() * sin_a,
                width_dir.x() * sin_a + width_dir.y() * cos_a
            )
            length_dir = new_length_dir
            width_dir = new_width_dir

        axis_length = QPointF(-length_dir.x(), -length_dir.y())
        axis_width = width_dir
        corners = [
            screen_center + axis_width * (-half_width * img_scale) + axis_length * (-half_length * img_scale),
            screen_center + axis_width * (half_width * img_scale) + axis_length * (-half_length * img_scale),
            screen_center + axis_width * (half_width * img_scale) + axis_length * (half_length * img_scale),
            screen_center + axis_width * (-half_width * img_scale) + axis_length * (half_length * img_scale),
        ]

        stroke_color = QColor(color) if color else QColor(52, 152, 219)
        light_color = QColor(stroke_color)
        light_color = light_color.lighter(130)
        light_color.setAlpha(51)
        light_pen = QPen(light_color, 3)
        thin_pen = QPen(stroke_color, 1)
        painter.setPen(light_pen)
        painter.drawPolygon(QPolygonF(corners))
        painter.setPen(thin_pen)
        painter.drawPolygon(QPolygonF(corners))

        # Draw dimensions
        painter.setPen(stroke_color)
        font = painter.font()
        font.setPointSize(max(8, int(size * 0.045)))
        painter.setFont(font)
        painter.drawText(5, size - 10, f"{length_um:.2f} x {width_um:.2f}")

        painter.end()
        return result

    def export_gallery_composite(self):
        """Export all spore thumbnails as a single composite image."""
        from PySide6.QtWidgets import QFileDialog
        from PySide6.QtGui import QPainter, QColor
        from PySide6.QtCore import QPointF

        measurements = self.get_gallery_measurements()
        if not measurements:
            return

        valid_measurements = [
            m for m in measurements
            if all(m.get(f'p{i}_{axis}') is not None for i in range(1, 5) for axis in ['x', 'y'])
        ]

        if not valid_measurements:
            return

        # Ask user for save location
        default_name = "spore_gallery"
        if self.active_observation_id:
            obs = ObservationDB.get_observation(self.active_observation_id)
            if obs:
                parts = [
                    obs.get("genus") or "",
                    obs.get("species") or obs.get("species_guess") or "",
                    obs.get("date") or ""
                ]
                name = " ".join([p for p in parts if p]).strip()
                name = name.replace(":", "-")
                name = re.sub(r'[<>:"/\\\\|?*]', "_", name)
                name = re.sub(r"\\s+", " ", name).strip()
                if name:
                    default_name = f"{name} - gallery"

        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export Gallery Composite",
            f"{default_name}.png",
            "PNG Images (*.png);;JPEG Images (*.jpg)"
        )

        if not filename:
            return

        # Create composite
        items_per_row = self.gallery_columns_spin.value() if hasattr(self, "gallery_columns_spin") else 4
        thumbnail_size = 200
        thumbnails = []
        image_color_cache = {}
        pixmap_cache = {}

        # Match gallery settings
        orient = hasattr(self, 'orient_checkbox') and self.orient_checkbox.isChecked()
        uniform_scale = hasattr(self, 'uniform_scale_checkbox') and self.uniform_scale_checkbox.isChecked()
        filtered_measurements = self._filter_gallery_measurements(valid_measurements)
        if not filtered_measurements:
            return

        uniform_length_um = None
        if uniform_scale:
            for measurement in filtered_measurements:
                length_um = measurement.get("length_um")
                if length_um is None:
                    continue
                if uniform_length_um is None or length_um > uniform_length_um:
                    uniform_length_um = length_um

        for measurement in filtered_measurements:
            pixmap = self.get_measurement_pixmap(measurement, pixmap_cache)
            if not pixmap or pixmap.isNull():
                continue

            measurement_id = measurement['id']
            extra_rotation = measurement.get("gallery_rotation") or self.gallery_rotations.get(measurement_id, 0)

            points = [
                QPointF(measurement['p1_x'], measurement['p1_y']),
                QPointF(measurement['p2_x'], measurement['p2_y']),
                QPointF(measurement['p3_x'], measurement['p3_y']),
                QPointF(measurement['p4_x'], measurement['p4_y'])
            ]

            image_id = measurement.get('image_id')
            stored_color = None
            mpp = None
            if image_id:
                if image_id not in image_color_cache:
                    image_data = ImageDB.get_image(image_id)
                    image_color_cache[image_id] = (
                        {
                            "measure_color": image_data.get('measure_color') if image_data else None,
                            "mpp": image_data.get('scale_microns_per_pixel') if image_data else None
                        }
                    )
                cached = image_color_cache[image_id]
                stored_color = cached.get("measure_color") if cached else None
                mpp = cached.get("mpp") if cached else None
            measure_color = QColor(stored_color) if stored_color else self.default_measure_color
            uniform_length_px = None
            if uniform_scale and uniform_length_um:
                if not mpp or mpp <= 0:
                    p1 = QPointF(measurement['p1_x'], measurement['p1_y'])
                    p2 = QPointF(measurement['p2_x'], measurement['p2_y'])
                    p3 = QPointF(measurement['p3_x'], measurement['p3_y'])
                    p4 = QPointF(measurement['p4_x'], measurement['p4_y'])
                    line1_len = math.hypot(p2.x() - p1.x(), p2.y() - p1.y())
                    line2_len = math.hypot(p4.x() - p3.x(), p4.y() - p3.y())
                    length_px = max(line1_len, line2_len)
                    length_um = measurement.get("length_um")
                    if length_px > 0 and length_um:
                        mpp = float(length_um) / float(length_px)
                if mpp and mpp > 0:
                    uniform_length_px = float(uniform_length_um) / float(mpp)

            thumbnail = self.create_spore_thumbnail(
                pixmap,
                points,
                measurement['length_um'],
                measurement['width_um'] or 0,
                thumbnail_size,
                len(thumbnails) + 1,
                orient=orient,
                extra_rotation=extra_rotation,
                uniform_length_px=uniform_length_px,
                color=measure_color
            )

            if thumbnail:
                thumbnails.append(thumbnail)

        if not thumbnails:
            return

        num_items = len(thumbnails)
        num_rows = (num_items + items_per_row - 1) // items_per_row

        spacing = 2
        composite_width = items_per_row * thumbnail_size + (items_per_row - 1) * spacing
        composite_height = num_rows * thumbnail_size + (num_rows - 1) * spacing

        composite = QPixmap(composite_width, composite_height)
        composite.fill(QColor(255, 255, 255))

        painter = QPainter(composite)

        for idx, thumbnail in enumerate(thumbnails):
            row = idx // items_per_row
            col = idx % items_per_row
            x = col * (thumbnail_size + spacing)
            y = row * (thumbnail_size + spacing)
            painter.drawPixmap(x, y, thumbnail)

        painter.end()

        # Save composite
        composite.save(filename)
        self.measure_status_label.setText(f"✓ Gallery exported to {Path(filename).name}")
        self.measure_status_label.setStyleSheet("color: #27ae60; font-weight: bold; font-size: 9pt;")

    def export_ml_dataset(self):
        """Trigger ML export from the observations tab."""
        if hasattr(self, "observations_tab"):
            self.observations_tab.export_for_ml()
            return
        QMessageBox.warning(
            self,
            "Export Unavailable",
            "The observations tab is not ready yet."
        )

    def show_export_placeholder(self, target_name):
        """Placeholder for export integrations."""
        QMessageBox.information(
            self,
            "Export Not Implemented",
            f"{target_name} export is not implemented yet."
        )

    def open_profile_dialog(self):
        """Open profile settings dialog."""
        profile = SettingsDB.get_profile()
        dialog = QDialog(self)
        dialog.setWindowTitle("Profile")
        form = QFormLayout(dialog)
        name_input = QLineEdit(profile.get("name", ""))
        email_input = QLineEdit(profile.get("email", ""))
        form.addRow("Name", name_input)
        form.addRow("Email", email_input)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)

        if dialog.exec() == QDialog.Accepted:
            SettingsDB.set_profile(name_input.text().strip(), email_input.text().strip())

    def open_database_settings_dialog(self):
        """Open database settings dialog."""
        dialog = DatabaseSettingsDialog(self)
        if dialog.exec() == QDialog.Accepted:
            self._populate_measure_categories()

    def open_language_settings_dialog(self):
        """Open language settings dialog."""
        dialog = LanguageSettingsDialog(self)
        dialog.exec()

    def apply_vernacular_language_change(self):
        if hasattr(self, "observations_tab"):
            self.observations_tab.apply_vernacular_language_change()
        for widget in QApplication.topLevelWidgets():
            if widget is self:
                continue
            if hasattr(widget, "apply_vernacular_language_change"):
                try:
                    widget.apply_vernacular_language_change()
                except Exception:
                    pass

    def set_ui_language(self, code):
        """Persist the UI language and prompt for restart."""
        SettingsDB.set_setting("ui_language", code)
        update_app_settings({"ui_language": code})
        QMessageBox.information(
            self,
            self.tr("Language"),
            self.tr("Language change will apply after restart.")
        )

    def _populate_measure_categories(self):
        categories = SettingsDB.get_list_setting(
            "measure_categories",
            ["Spore", "Basidia", "Pleurocystidia", "Cheilocystidia", "Caulocystidia", "Other"]
        )
        if not hasattr(self, "measure_category_combo"):
            return
        current = self.measure_category_combo.currentData()
        self.measure_category_combo.blockSignals(True)
        self.measure_category_combo.clear()
        for label in categories:
            if not label:
                continue
            self.measure_category_combo.addItem(label, label.strip().lower())
        self.measure_category_combo.blockSignals(False)
        if current:
            idx = self.measure_category_combo.findData(current)
            if idx >= 0:
                self.measure_category_combo.setCurrentIndex(idx)

    def on_gallery_thumbnail_setting_changed(self):
        """Persist gallery settings and refresh thumbnails."""
        self._save_gallery_settings()
        self.schedule_gallery_refresh()

    def on_gallery_plot_setting_changed(self):
        """Persist gallery settings and refresh plots only."""
        self._save_gallery_settings()
        self.update_graph_plots_only()

    def open_gallery_plot_settings(self):
        """Open plot settings dialog for analysis charts."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Plot settings")
        dialog.setModal(True)

        layout = QFormLayout(dialog)
        layout.setLabelAlignment(Qt.AlignLeft)

        settings = getattr(self, "gallery_plot_settings", {}) or {}

        bins_spin = QSpinBox()
        bins_spin.setRange(3, 50)
        bins_spin.setValue(int(settings.get("bins", 8)))
        layout.addRow("Bins:", bins_spin)

        ci_checkbox = QCheckBox(self.tr("Confidence interval (95%)"))
        ci_checkbox.setChecked(bool(settings.get("ci", True)))
        layout.addRow("", ci_checkbox)

        legend_checkbox = QCheckBox(self.tr("Image legend"))
        legend_checkbox.setChecked(bool(settings.get("legend", False)))
        layout.addRow("", legend_checkbox)

        avg_q_checkbox = QCheckBox(self.tr("Plot Avg Q"))
        avg_q_checkbox.setChecked(bool(settings.get("avg_q", True)))
        layout.addRow("", avg_q_checkbox)

        q_minmax_checkbox = QCheckBox(self.tr("Plot Q min/max"))
        q_minmax_checkbox.setChecked(bool(settings.get("q_minmax", True)))
        layout.addRow("", q_minmax_checkbox)

        def _build_limit_spin():
            spin = QDoubleSpinBox()
            spin.setRange(-1e9, 1e9)
            spin.setDecimals(4)
            spin.setSpecialValueText("Auto")
            return spin

        x_min_spin = _build_limit_spin()
        x_max_spin = _build_limit_spin()
        y_min_spin = _build_limit_spin()
        y_max_spin = _build_limit_spin()

        def _apply_limit_value(spin, value):
            if value is None:
                spin.setValue(spin.minimum())
            else:
                spin.setValue(float(value))

        _apply_limit_value(x_min_spin, settings.get("x_min"))
        _apply_limit_value(x_max_spin, settings.get("x_max"))
        _apply_limit_value(y_min_spin, settings.get("y_min"))
        _apply_limit_value(y_max_spin, settings.get("y_max"))

        layout.addRow("X min:", x_min_spin)
        layout.addRow("X max:", x_max_spin)
        layout.addRow("Y min:", y_min_spin)
        layout.addRow("Y max:", y_max_spin)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec() != QDialog.Accepted:
            return

        def _read_limit_value(spin):
            return None if spin.value() == spin.minimum() else float(spin.value())

        self.gallery_plot_settings = {
            "bins": int(bins_spin.value()),
            "ci": bool(ci_checkbox.isChecked()),
            "legend": bool(legend_checkbox.isChecked()),
            "avg_q": bool(avg_q_checkbox.isChecked()),
            "q_minmax": bool(q_minmax_checkbox.isChecked()),
            "x_min": _read_limit_value(x_min_spin),
            "x_max": _read_limit_value(x_max_spin),
            "y_min": _read_limit_value(y_min_spin),
            "y_max": _read_limit_value(y_max_spin),
        }

        self._save_gallery_settings()
        self.update_graph_plots_only()

    def _gallery_settings_key(self):
        if not self.active_observation_id:
            return None
        return f"gallery_settings_{self.active_observation_id}"

    def _load_gallery_settings(self):
        key = self._gallery_settings_key()
        if not key:
            return {}
        raw = SettingsDB.get_setting(key)
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def _collect_gallery_settings(self):
        plot_settings = getattr(self, "gallery_plot_settings", {}) or {}
        return {
            "measurement_type": self.gallery_filter_combo.currentData() if hasattr(self, "gallery_filter_combo") else None,
            "bins": int(plot_settings.get("bins", 8)),
            "ci": bool(plot_settings.get("ci", True)),
            "legend": bool(plot_settings.get("legend", False)),
            "avg_q": bool(plot_settings.get("avg_q", True)),
            "q_minmax": bool(plot_settings.get("q_minmax", True)),
            "x_min": plot_settings.get("x_min"),
            "x_max": plot_settings.get("x_max"),
            "y_min": plot_settings.get("y_min"),
            "y_max": plot_settings.get("y_max"),
            "columns": self.gallery_columns_spin.value() if hasattr(self, "gallery_columns_spin") else 4,
            "orient": bool(self.orient_checkbox.isChecked()) if hasattr(self, "orient_checkbox") else False,
            "uniform_scale": bool(self.uniform_scale_checkbox.isChecked()) if hasattr(self, "uniform_scale_checkbox") else False,
        }

    def _save_gallery_settings(self):
        key = self._gallery_settings_key()
        if not key:
            return
        settings = self._collect_gallery_settings()
        SettingsDB.set_setting(key, json.dumps(settings))

    def apply_gallery_settings(self):
        settings = self._load_gallery_settings()
        if not settings:
            return
        self.gallery_plot_settings = {
            "bins": int(settings.get("bins", self.gallery_plot_settings.get("bins", 8))),
            "ci": bool(settings.get("ci", self.gallery_plot_settings.get("ci", True))),
            "legend": bool(settings.get("legend", self.gallery_plot_settings.get("legend", False))),
            "avg_q": bool(settings.get("avg_q", self.gallery_plot_settings.get("avg_q", True))),
            "q_minmax": bool(settings.get("q_minmax", self.gallery_plot_settings.get("q_minmax", True))),
            "x_min": settings.get("x_min"),
            "x_max": settings.get("x_max"),
            "y_min": settings.get("y_min"),
            "y_max": settings.get("y_max"),
        }
        if hasattr(self, "gallery_columns_spin"):
            self.gallery_columns_spin.blockSignals(True)
            self.gallery_columns_spin.setValue(int(settings.get("columns", self.gallery_columns_spin.value())))
            self.gallery_columns_spin.blockSignals(False)
        if hasattr(self, "orient_checkbox"):
            self.orient_checkbox.blockSignals(True)
            self.orient_checkbox.setChecked(bool(settings.get("orient", False)))
            self.orient_checkbox.blockSignals(False)
        if hasattr(self, "uniform_scale_checkbox"):
            self.uniform_scale_checkbox.blockSignals(True)
            self.uniform_scale_checkbox.setChecked(bool(settings.get("uniform_scale", False)))
            self.uniform_scale_checkbox.blockSignals(False)
        if settings.get("measurement_type"):
            self._pending_gallery_category = settings.get("measurement_type")

    def update_graph_plots_only(self):
        """Update analysis graphs without rebuilding thumbnails."""
        if not self.is_analysis_visible():
            return
        all_measurements = self.get_gallery_measurements()
        self.update_graph_plots(all_measurements)
    def export_database_bundle(self):
        """Export DB and data folders as a zip file."""
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export Database",
            "MycoLog_DB.zip",
            "Zip Files (*.zip)"
        )
        if not filename:
            return
        if not filename.lower().endswith(".zip"):
            filename += ".zip"
        try:
            export_db_bundle(filename)
            QMessageBox.information(self, "Export Complete", f"Saved to {filename}")
        except Exception as exc:
            QMessageBox.warning(self, "Export Failed", str(exc))

    def import_database_bundle(self):
        """Import DB and data from a shared zip file."""
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Import Database",
            "",
            "Zip Files (*.zip)"
        )
        if not filename:
            return
        try:
            summary = import_db_bundle(filename)
            QMessageBox.information(
                self,
                "Import Complete",
                f"Imported {summary.get('observations', 0)} observations, "
                f"{summary.get('images', 0)} images, "
                f"{summary.get('measurements', 0)} measurements."
            )
            if hasattr(self, "observations_tab"):
                self.observations_tab.refresh_observations()
        except Exception as exc:
            QMessageBox.warning(self, "Import Failed", str(exc))



    def delete_measurement(self, measurement_id):
        """Delete a measurement and its associated lines."""
        MeasurementDB.delete_measurement(measurement_id)

        # Remove only the lines for this measurement
        if measurement_id in self.measurement_lines:
            del self.measurement_lines[measurement_id]
        self.measurement_labels = [
            label for label in self.measurement_labels
            if label.get("id") != measurement_id
        ]

        self.update_display_lines()
        self.update_measurements_table()
        self.update_statistics()
        self.spore_preview.clear()
        self.measure_status_label.setText(self.tr("Measurement deleted"))
        self.measure_status_label.setStyleSheet("color: #e67e22; font-weight: bold; font-size: 9pt;")

    def update_statistics(self):
        """Update the statistics display."""
        stats = {}
        if self.current_image_id:
            stats = MeasurementDB.get_statistics_for_image(
                self.current_image_id,
                measurement_category='spore'
            )
        elif self.active_observation_id:
            stats = MeasurementDB.get_statistics_for_observation(
                self.active_observation_id,
                measurement_category='spore'
            )

        if hasattr(self, "stats_table"):
            self.stats_table.update_stats(stats)

        if self.active_observation_id:
            obs_stats = MeasurementDB.get_statistics_for_observation(
                self.active_observation_id,
                measurement_category='spore'
            )
            if obs_stats:
                ObservationDB.update_spore_statistics(
                    self.active_observation_id,
                    self.format_literature_string(obs_stats)
                )
            else:
                ObservationDB.update_spore_statistics(self.active_observation_id, None)

    def format_literature_string(self, stats):
        """Format the literature string for spore statistics."""
        if not stats:
            return ""

        lit_format = (
            f"{self.tr('Spores:')} ({stats['length_min']:.1f}-){stats['length_p5']:.1f}-"
            f"{stats['length_p95']:.1f}(-{stats['length_max']:.1f}) um"
        )

        if 'width_mean' in stats and stats.get('width_mean', 0) > 0:
            lit_format += (
                f" x ({stats['width_min']:.1f}-){stats['width_p5']:.1f}-"
                f"{stats['width_p95']:.1f}(-{stats['width_max']:.1f}) um"
            )
            lit_format += (
                f", Q = ({stats['ratio_min']:.1f}-){stats['ratio_p5']:.1f}-"
                f"{stats['ratio_p95']:.1f}(-{stats['ratio_max']:.1f})"
            )
            lit_format += f", Qm = {stats['ratio_mean']:.1f}"

        lit_format += f", n = {stats['count']}"
        return lit_format

    def _update_preview_title(self):
        if not hasattr(self, "preview_group"):
            return
        label = "Measurement Preview"
        if hasattr(self, "measure_category_combo"):
            category = self.measure_category_combo.currentData()
            if category:
                label = f"{self.format_measurement_category(category)} Preview"
        self.preview_group.setTitle(label)

    def _show_loading(self, message="Loading..."):
        """Show a blocking loading indicator."""
        if self.loading_dialog is None:
            dlg = QProgressDialog(message, None, 0, 0, self)
            dlg.setWindowTitle(message)
            dlg.setWindowModality(Qt.ApplicationModal)
            dlg.setCancelButton(None)
            dlg.setMinimumDuration(0)
            dlg.setAutoClose(False)
            dlg.setAutoReset(False)
            self.loading_dialog = dlg
        else:
            self.loading_dialog.setLabelText(message)
            self.loading_dialog.setWindowTitle(message)
        self.loading_dialog.show()
        QApplication.processEvents()

    def _hide_loading(self):
        """Hide the loading indicator."""
        if self.loading_dialog is not None:
            self.loading_dialog.hide()

    def _question_yes_no(self, title, text, default_yes=True):
        """Show a localized Yes/No confirmation dialog."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle(title)
        box.setText(text)
        yes_btn = box.addButton(self.tr("Yes"), QMessageBox.YesRole)
        no_btn = box.addButton(self.tr("No"), QMessageBox.NoRole)
        box.setDefaultButton(yes_btn if default_yes else no_btn)
        box.exec()
        return box.clickedButton() == yes_btn

    def _maybe_rescale_current_image(self, old_scale, new_scale):
        """Prompt to rescale previous measurements for the current image."""
        if self.suppress_scale_prompt:
            return True
        if not self.current_image_id or not old_scale or not new_scale:
            return True
        if abs(new_scale - old_scale) < 1e-6:
            return True
        measurements = MeasurementDB.get_measurements_for_image(self.current_image_id)
        if not measurements:
            return True
        has_points = any(
            all(m.get(f"p{i}_{axis}") is not None for i in range(1, 5) for axis in ("x", "y"))
            for m in measurements
        )
        if not has_points:
            return True
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle(self.tr("Changing image scale"))
        box.setText(self.tr("Changing image scale: This will update previous measurements to match the new scale."))
        ok_btn = box.addButton(self.tr("OK"), QMessageBox.AcceptRole)
        box.addButton(self.tr("Cancel"), QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() != ok_btn:
            return False

        conn = get_connection()
        cursor = conn.cursor()
        for m in measurements:
            if not all(m.get(f"p{i}_{axis}") is not None for i in range(1, 5) for axis in ("x", "y")):
                continue
            p1 = QPointF(m["p1_x"], m["p1_y"])
            p2 = QPointF(m["p2_x"], m["p2_y"])
            p3 = QPointF(m["p3_x"], m["p3_y"])
            p4 = QPointF(m["p4_x"], m["p4_y"])
            dist1 = math.hypot(p2.x() - p1.x(), p2.y() - p1.y()) * new_scale
            dist2 = math.hypot(p4.x() - p3.x(), p4.y() - p3.y()) * new_scale
            length_um = max(dist1, dist2)
            width_um = min(dist1, dist2)
            q_value = length_um / width_um if width_um > 0 else 0
            cursor.execute(
                'UPDATE spore_measurements SET length_um = ?, width_um = ?, notes = ? WHERE id = ?',
                (length_um, width_um, f"Q={q_value:.1f}", m["id"])
            )
        conn.commit()
        conn.close()

        self.load_measurement_lines()
        self.update_measurements_table()
        self.update_statistics()
        return True

    def _handle_reference_plot(self, data):
        """Plot reference values without saving."""
        self.reference_values = data
        self.update_graph_plots_only()

    def _handle_reference_save(self, data):
        """Save reference values and update plot."""
        if not data.get("genus") or not data.get("species"):
            QMessageBox.warning(self, "Missing Species", "Please enter genus and species to save.")
            return
        ReferenceDB.set_reference(data)
        return

    def load_reference_values(self):
        """Load reference values for the active observation."""
        self.reference_values = {}
        if not self.active_observation_id:
            return
        obs = ObservationDB.get_observation(self.active_observation_id)
        if not obs:
            return
        genus = obs.get("genus")
        species = obs.get("species")
        if not (genus and species):
            return
        ref = ReferenceDB.get_reference(genus, species)
        if ref:
            self.reference_values = ref

    def open_reference_values_dialog(self):
        """Open the reference values dialog and save data."""
        if not self.active_observation_id:
            QMessageBox.warning(self, "No Observation", "Select an observation first.")
            return
        ref_data = dict(self.reference_values) if self.reference_values else {}
        dialog = ReferenceValuesDialog(
            ref_data.get("genus") or "",
            ref_data.get("species") or "",
            ref_data,
            self
        )
        dialog.plot_requested.connect(self._handle_reference_plot)
        dialog.save_requested.connect(self._handle_reference_save)
        dialog.exec()


    def on_observation_selected(self, observation_id, display_name, switch_tab=True, suppress_gallery=False):
        """Handle observation selection from the Observations tab."""
        previous_suppress = self._suppress_gallery_update
        if suppress_gallery:
            self._suppress_gallery_update = True
        try:
            self._on_observation_selected_impl(
                observation_id,
                display_name,
                switch_tab=switch_tab,
                schedule_gallery=not suppress_gallery
            )
        finally:
            if suppress_gallery:
                self._suppress_gallery_update = previous_suppress
        if suppress_gallery and self.is_analysis_visible():
            self.schedule_gallery_refresh()

    def _on_observation_selected_impl(self, observation_id, display_name, switch_tab=True, schedule_gallery=True):
        """Internal handler for observation selection."""
        self.active_observation_id = observation_id
        self.active_observation_name = display_name

        # Update the image info label to show active observation
        if hasattr(self, "image_info_label"):
            self.image_info_label.setText(f"Active: {display_name}")
        self.clear_current_image_display()
        self.update_observation_header(observation_id)
        observation = ObservationDB.get_observation(observation_id)
        self.auto_threshold = observation.get("auto_threshold") if observation else None
        self.load_reference_values()
        self._compute_observation_max_radius(observation_id)
        self.apply_gallery_settings()
        self.refresh_gallery_filter_options()
        if schedule_gallery and self.is_analysis_visible():
            self.schedule_gallery_refresh()
        self.update_measurements_table()
        self.refresh_observation_images()
        if self.observation_images:
            self.goto_image_index(0)

        # Switch to the Measure tab
        if switch_tab:
            self.tab_widget.setCurrentIndex(1)

    def load_image_for_observation(self):
        """Load microscope images and link them to the active observation."""
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Open Microscope Image", "",
            "Images (*.png *.jpg *.jpeg *.tif *.tiff *.heic *.heif);;All Files (*)"
        )

        if not paths:
            return

        output_dir = get_images_dir() / "imports"
        output_dir.mkdir(parents=True, exist_ok=True)
        last_image_data = None
        for path in paths:
            converted_path = maybe_convert_heic(path, output_dir)
            if converted_path is None:
                QMessageBox.warning(
                    self,
                    "HEIC Conversion Failed",
                    f"Could not convert {Path(path).name} to JPEG."
                )
                continue

            objective_name = self.get_objective_name_for_storage()
            calibration_id = CalibrationDB.get_active_calibration_id(objective_name) if objective_name else None
            image_id = ImageDB.add_image(
                observation_id=self.active_observation_id,
                filepath=converted_path,
                image_type='microscope',
                scale=self.microns_per_pixel,
                objective_name=objective_name,
                contrast=SettingsDB.get_setting(
                    "contrast_default",
                    SettingsDB.get_list_setting("contrast_options", ["BF", "DF", "DIC", "Phase"])[0]
                ),
                calibration_id=calibration_id
            )

            image_data = ImageDB.get_image(image_id)
            stored_path = image_data.get("filepath") if image_data else converted_path

            try:
                generate_all_sizes(stored_path, image_id)
            except Exception as e:
                print(f"Warning: Could not generate thumbnails: {e}")

            last_image_data = ImageDB.get_image(image_id)
            cleanup_import_temp_file(path, converted_path, stored_path, output_dir)

        if last_image_data:
            self.load_image_record(last_image_data, refresh_table=True)
            self.refresh_observation_images(select_image_id=last_image_data['id'])

    def on_image_selected(self, image_id, observation_id, display_name):
        """Handle image selection from the Observations tab - load the image."""
        self.active_observation_id = observation_id
        self.active_observation_name = display_name
        self.update_observation_header(observation_id)
        observation = ObservationDB.get_observation(observation_id)
        self.auto_threshold = observation.get("auto_threshold") if observation else None
        self._compute_observation_max_radius(observation_id)
    
        # Get image data from database
        image_data = ImageDB.get_image(image_id)
        if not image_data:
            return
    
        self.load_image_record(image_data, display_name=display_name, refresh_table=True)
        filename = Path(self.current_image_path).name
    
        # Switch to Measure tab
        self.tab_widget.setCurrentIndex(1)
    
        self.measure_status_label.setText("")
        if hasattr(self, "measure_gallery"):
            self.measure_gallery.select_image(image_id)
    
    def enter_calibration_mode(self, dialog):
        """Enter calibration mode for 2-point scale calibration."""
        if not self.current_pixmap:
            self.measure_status_label.setText(self.tr("Load an image first to calibrate"))
            self.measure_status_label.setStyleSheet("color: #e74c3c; font-weight: bold; font-size: 9pt;")
            return

        self.calibration_mode = True
        self.calibration_dialog = dialog
        self.calibration_points = []

        # Clear any existing preview
        self.image_label.clear_preview_line()

        self.measure_status_label.setText(self.tr("CALIBRATION: Click first point on scale bar"))
        self.measure_status_label.setStyleSheet("color: #e67e22; font-weight: bold; font-size: 9pt;")

    def handle_calibration_click(self, pos):
        """Handle clicks during calibration mode."""
        self.calibration_points.append(pos)

        if len(self.calibration_points) == 1:
            # First point - show preview line
            self.image_label.set_preview_line(pos)
            self.measure_status_label.setText(self.tr("CALIBRATION: Click second point on scale bar"))
            self.measure_status_label.setStyleSheet("color: #e67e22; font-weight: bold; font-size: 9pt;")

        elif len(self.calibration_points) == 2:
            # Second point - calculate distance
            p1 = self.calibration_points[0]
            p2 = self.calibration_points[1]
            dx = p2.x() - p1.x()
            dy = p2.y() - p1.y()
            distance_pixels = math.sqrt(dx**2 + dy**2)

            # Store the calibration line for display
            self.calibration_distance_pixels = distance_pixels

            # Show the calibration line on the image (as a temporary measurement line)
            calib_line = [p1.x(), p1.y(), p2.x(), p2.y()]
            self.image_label.set_measurement_lines([calib_line])
            self.image_label.clear_preview_line()

            # Show calibration preview in the spore preview widget
            self.show_calibration_preview(p1, p2, distance_pixels)

            if getattr(self.calibration_dialog, "auto_apply", False):
                self.apply_calibration_scale()
                self.measure_status_label.setText(self.tr("Scale calibrated"))
                self.measure_status_label.setStyleSheet("color: #27ae60; font-weight: bold; font-size: 9pt;")
                return

            self.measure_status_label.setText(
                self.tr("Calibration: {pixels:.1f} pixels - Click '{label}' to apply").format(
                    pixels=distance_pixels,
                    label=self.tr("Set Scale")
                )
            )
            self.measure_status_label.setStyleSheet("color: #e67e22; font-weight: bold; font-size: 9pt;")

    def show_calibration_preview(self, p1, p2, distance_pixels):
        """Show calibration preview with Set Scale button."""
        # Create a simple preview showing the measured distance
        # We'll use the spore preview widget but configure it for calibration
        if self.current_pixmap:
            # Create fake 4-point measurement (the calibration line doubled)
            points = [p1, p2, p1, p2]

            # Temporarily disconnect the dimensions_changed signal
            try:
                self.spore_preview.dimensions_changed.disconnect(self.on_dimensions_changed)
            except:
                pass

            # Set the preview
            self.spore_preview.set_spore(
                self.current_pixmap,
                points,
                distance_pixels,  # Show pixels as "length"
                0,  # No width
                1.0,  # 1:1 scale for display
                None  # No measurement ID
            )

            self.preview_group.setTitle(self.tr("Calibration preview"))
            if hasattr(self, "calibration_apply_btn"):
                self.calibration_apply_btn.setVisible(True)

    def apply_calibration_scale(self):
        """Apply the calibration scale from preview."""
        # Clear the calibration line
        self.image_label.set_measurement_lines([])

        # Exit calibration mode
        self.calibration_mode = False

        # Send distance to calibration dialog
        if self.calibration_dialog and hasattr(self, 'calibration_distance_pixels'):
            if hasattr(self.calibration_dialog, "apply_scale"):
                self.calibration_dialog.apply_scale(self.calibration_distance_pixels)
            else:
                self.calibration_dialog.set_calibration_distance(self.calibration_distance_pixels)

        # Clean up
        self.calibration_points = []
        self.spore_preview.clear()
        if hasattr(self, "calibration_apply_btn"):
            self.calibration_apply_btn.setVisible(False)

        # Reconnect the dimensions_changed signal
        self.spore_preview.dimensions_changed.connect(self.on_dimensions_changed)
        self._update_preview_title()


class ExportImageDialog(QDialog):
    """Dialog to configure export size and quality."""

    def __init__(self, base_width, base_height, scale_percent, fmt, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export Image")
        self.base_width = base_width
        self.base_height = base_height
        self.format = fmt
        self._updating = False
        self._init_ui(scale_percent, fmt)

    def _init_ui(self, scale_percent, fmt):
        layout = QFormLayout(self)
        layout.setSpacing(8)

        self.scale_input = QDoubleSpinBox()
        self.scale_input.setRange(1.0, 400.0)
        self.scale_input.setDecimals(1)
        self.scale_input.setValue(scale_percent)
        self.scale_input.valueChanged.connect(self.on_scale_changed)
        layout.addRow("Scale %:", self.scale_input)

        self.width_input = QSpinBox()
        self.width_input.setRange(1, 100000)
        self.width_input.setValue(int(self.base_width * scale_percent / 100.0))
        self.width_input.valueChanged.connect(self.on_width_changed)
        layout.addRow("Width:", self.width_input)

        self.height_input = QSpinBox()
        self.height_input.setRange(1, 100000)
        self.height_input.setValue(int(self.base_height * scale_percent / 100.0))
        self.height_input.valueChanged.connect(self.on_height_changed)
        layout.addRow("Height:", self.height_input)

        self.quality_input = QSpinBox()
        self.quality_input.setRange(1, 10)
        self.quality_input.setValue(9)
        layout.addRow("JPEG quality (1-10):", self.quality_input)

        if fmt == "jpg":
            self.quality_input.setValue(9)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def on_scale_changed(self, value):
        if self._updating:
            return
        self._updating = True
        width = int(self.base_width * value / 100.0)
        height = int(self.base_height * value / 100.0)
        self.width_input.setValue(max(1, width))
        self.height_input.setValue(max(1, height))
        self._updating = False

    def on_width_changed(self, value):
        if self._updating or self.base_width <= 0:
            return
        self._updating = True
        scale = (value / self.base_width) * 100.0
        height = int(self.base_height * scale / 100.0)
        self.scale_input.setValue(max(1.0, scale))
        self.height_input.setValue(max(1, height))
        self._updating = False

    def on_height_changed(self, value):
        if self._updating or self.base_height <= 0:
            return
        self._updating = True
        scale = (value / self.base_height) * 100.0
        width = int(self.base_width * scale / 100.0)
        self.scale_input.setValue(max(1.0, scale))
        self.width_input.setValue(max(1, width))
        self._updating = False

    def get_settings(self):
        return {
            "scale_percent": float(self.scale_input.value()),
            "width": int(self.width_input.value()),
            "height": int(self.height_input.value()),
            "quality": int(self.quality_input.value()) * 10,
            "format": self.format
        }

        self.measure_status_label.setText(self.tr("Scale calibrated - check dialog for result"))
        self.measure_status_label.setStyleSheet("color: #27ae60; font-weight: bold; font-size: 9pt;")
