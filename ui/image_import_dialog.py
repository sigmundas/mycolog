"""Dialog for preparing images before creating an observation."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QDateTime, QDate, QTime, Signal, QPointF, QCoreApplication, QObject, QThread, Slot
from PySide6.QtGui import QPixmap, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QStackedLayout,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
    QDialogButtonBox,
    QProgressBar,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
)

from database.schema import load_objectives, get_images_dir
from database.models import SettingsDB
from utils.vernacular_utils import normalize_vernacular_language
from utils.exif_reader import get_image_metadata, get_exif_data, get_gps_coordinates
from utils.heic_converter import maybe_convert_heic
from .image_gallery_widget import ImageGalleryWidget
from .zoomable_image_widget import ZoomableImageLabel


@dataclass
class ImageImportResult:
    filepath: str
    preview_path: Optional[str] = None
    image_id: Optional[int] = None
    image_type: str = "field"
    objective: Optional[str] = None
    custom_scale: Optional[float] = None
    contrast: Optional[str] = None
    mount_medium: Optional[str] = None
    sample_type: Optional[str] = None
    captured_at: Optional[QDateTime] = None
    gps_latitude: Optional[float] = None
    gps_longitude: Optional[float] = None
    gps_source: Optional[str] = None
    needs_scale: bool = False
    exif_has_gps: bool = False


class AIGuessWorker(QObject):
    finished = Signal(int, list, object, object, str)
    error = Signal(int, str)

    def __init__(
        self,
        index: int,
        image_path: str,
        crop_box: tuple[float, float, float, float] | None,
        temp_dir: Path,
        max_dim: int = 1600,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.index = index
        self.image_path = image_path
        self.crop_box = crop_box
        self.temp_dir = temp_dir
        self.max_dim = max_dim

    @Slot()
    def run(self) -> None:
        try:
            from uuid import uuid4
            from PIL import Image
            import requests

            img = Image.open(self.image_path)
            orig_w, orig_h = img.size
            crop_x1 = 0.0
            crop_y1 = 0.0
            crop_w = float(orig_w)
            crop_h = float(orig_h)
            requires_resize = self.max_dim and max(img.size) > self.max_dim
            extension = Path(self.image_path).suffix.lower()
            requires_convert = extension not in {".jpg", ".jpeg"} or img.mode not in {"RGB", "L"}
            if self.crop_box:
                x1, y1, x2, y2 = self.crop_box
                crop_x1 = max(0.0, min(float(orig_w), x1 * float(orig_w)))
                crop_y1 = max(0.0, min(float(orig_h), y1 * float(orig_h)))
                crop_x2 = max(0.0, min(float(orig_w), x2 * float(orig_w)))
                crop_y2 = max(0.0, min(float(orig_h), y2 * float(orig_h)))
                crop_w = max(1.0, crop_x2 - crop_x1)
                crop_h = max(1.0, crop_y2 - crop_y1)
                img = img.crop((crop_x1, crop_y1, crop_x2, crop_y2))
                requires_convert = True

            if requires_resize:
                scale = self.max_dim / max(img.size)
                new_size = (max(1, int(img.size[0] * scale)), max(1, int(img.size[1] * scale)))
                img = img.resize(new_size, Image.LANCZOS)
                requires_convert = True

            send_path = Path(self.image_path)
            temp_path = None
            if requires_convert:
                if img.mode not in {"RGB", "L"}:
                    img = img.convert("RGB")
                self.temp_dir.mkdir(parents=True, exist_ok=True)
                temp_path = self.temp_dir / f"ai_guess_{uuid4().hex}.jpg"
                img.save(temp_path, "JPEG", quality=90)
                send_path = temp_path

            url = "https://ai.artsdatabanken.no"

            def _post_with_field(field_name: str):
                with open(send_path, "rb") as handle:
                    return requests.post(
                        url,
                        files={field_name: (send_path.name, handle, "image/jpeg")},
                        headers={"User-Agent": "MycoLog/AI"},
                        timeout=30,
                    )

            response = _post_with_field("image")
            if response.status_code != 200:
                response = _post_with_field("file")
            if response.status_code != 200:
                detail = (response.text or "").strip()
                if detail:
                    detail = detail.replace("\n", " ").strip()
                    detail = detail[:200]
                suffix = f" - {detail}" if detail else ""
                raise Exception(f"API request failed: {response.status_code}{suffix}")

            data = response.json()
            predictions = [
                p for p in data.get("predictions", [])
                if p.get("taxon", {}).get("vernacularName") != "*** Utdatert versjon ***"
            ]

            warnings = data.get("warnings")
            self.finished.emit(self.index, predictions, None, warnings, str(temp_path or ""))
        except Exception as exc:
            self.error.emit(self.index, str(exc))
class ImageImportDialog(QDialog):
    """Prepare images before creating or editing an observation."""

    continueRequested = Signal(list)
    CUSTOM_OBJECTIVE_KEY = "__custom__"

    def __init__(
        self,
        parent=None,
        image_paths: Optional[list[str]] = None,
        import_results: Optional[list[ImageImportResult]] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Prepare Images"))
        self.setModal(True)
        self.setMinimumSize(1200, 800)
        self.resize(1500, 900)

        self.objectives = self._load_objectives()
        self.default_objective = self._get_default_objective()
        self.contrast_options = SettingsDB.get_list_setting(
            "contrast_options",
            ["BF", "DF", "DIC", "Phase"]
        )
        self.contrast_default = SettingsDB.get_setting(
            "contrast_default",
            self.contrast_options[0] if self.contrast_options else "BF"
        )
        self.mount_options = SettingsDB.get_list_setting(
            "mount_options",
            ["Not set", "Water", "KOH", "Melzer", "Congo Red", "Cotton Blue"]
        )
        self.mount_default = SettingsDB.get_setting(
            "mount_default",
            self.mount_options[0] if self.mount_options else "Not set"
        )
        self.sample_options = SettingsDB.get_list_setting(
            "sample_options",
            ["Not set", "Fresh", "Dried", "Spore print"]
        )
        self.sample_default = SettingsDB.get_setting(
            "sample_default",
            self.sample_options[0] if self.sample_options else "Not set"
        )

        self.image_paths: list[str] = []
        self.import_results: list[ImageImportResult] = []
        self.selected_index: int | None = None
        self.selected_indices: list[int] = []
        self.primary_index: int | None = None
        self._loading_form = False
        self._temp_preview_paths: set[str] = set()
        self._custom_scale: float | None = None
        self._current_exif_datetime: QDateTime | None = None
        self._current_exif_lat: float | None = None
        self._current_exif_lon: float | None = None
        self._current_exif_path: str | None = None
        self._pixmap_cache: dict[str, QPixmap] = {}
        self._pixmap_cache_is_preview: dict[str, bool] = {}
        self._max_preview_dim = 1600
        self._unset_datetime = QDateTime(QDate(1900, 1, 1), QTime(0, 0))
        self._observation_datetime: QDateTime | None = None
        self._observation_lat: float | None = None
        self._observation_lon: float | None = None
        self._observation_source_index: int | None = None
        self._converted_import_paths: set[str] = set()
        self._accepted = False
        self._setting_from_image_source = False
        self._last_settings_action: str | None = None
        self._ai_predictions_by_index: dict[int, list[dict]] = {}
        self._ai_selected_by_index: dict[int, dict] = {}
        self._ai_selected_taxon: dict | None = None
        self._ai_crop_boxes: dict[int, tuple[float, float, float, float]] = {}
        self._ai_crop_active = False
        self._ai_thread: QThread | None = None
        self._ai_worker: QObject | None = None

        self._build_ui()
        if import_results:
            self.set_import_results(import_results)
        elif image_paths:
            self.add_images(image_paths)

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)

        content_row = QHBoxLayout()
        content_row.setSpacing(10)

        left_panel = self._build_left_panel()
        left_panel.setFixedWidth(240)
        left_panel.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        content_row.addWidget(left_panel, 0)

        center_container = QWidget()
        center_layout = QVBoxLayout(center_container)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(8)

        self.gallery = ImageGalleryWidget(
            self.tr("Images"),
            self,
            show_delete=False,
            show_badges=False,
            min_height=60,
            default_height=180,
            thumbnail_size=140,
        )
        self.gallery.set_multi_select(True)
        self.gallery.imageClicked.connect(self._on_gallery_clicked)
        self.gallery.selectionChanged.connect(self._on_gallery_selection_changed)
        self.delete_shortcut = QShortcut(QKeySequence.Delete, self)
        self.delete_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        self.delete_shortcut.activated.connect(self._on_remove_selected)

        center_splitter = QSplitter(Qt.Vertical)
        center_splitter.setChildrenCollapsible(False)
        center_splitter.addWidget(self._build_center_panel())
        center_splitter.addWidget(self.gallery)
        center_splitter.setStretchFactor(0, 4)
        center_splitter.setStretchFactor(1, 1)
        center_splitter.setSizes([700, 220])

        center_layout.addWidget(center_splitter, 1)
        content_row.addWidget(center_container, 1)

        self.details_panel = self._build_right_panel()
        content_row.addWidget(self.details_panel, 0)
        main_layout.addLayout(content_row, 1)

    def _build_left_panel(self) -> QWidget:
        container = QWidget()
        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        add_btn = QPushButton(self.tr("Add Images..."))
        add_btn.clicked.connect(self._on_add_images_clicked)
        outer.addWidget(add_btn)
        self.import_progress = QProgressBar()
        self.import_progress.setVisible(False)
        self.import_progress.setRange(0, 1)
        self.import_progress.setFormat(self.tr("Loading images... %p%"))
        outer.addWidget(self.import_progress)

        panel = QGroupBox(self.tr("Image settings"))
        layout = QVBoxLayout(panel)
        layout.setSpacing(8)

        type_group = QGroupBox(self.tr("Image type"))
        type_layout = QHBoxLayout(type_group)
        self.image_type_group = QButtonGroup(self)
        self.field_radio = QRadioButton(self.tr("Field"))
        self.micro_radio = QRadioButton(self.tr("Micro"))
        self.image_type_group.addButton(self.field_radio)
        self.image_type_group.addButton(self.micro_radio)
        self.field_radio.setChecked(True)
        self.image_type_group.buttonClicked.connect(self._on_settings_changed)
        type_layout.addWidget(self.field_radio)
        type_layout.addWidget(self.micro_radio)
        layout.addWidget(type_group)

        self.scale_group = QGroupBox(self.tr("Scale"))
        scale_layout = QVBoxLayout(self.scale_group)
        self.objective_combo = QComboBox()
        self._populate_objectives()
        self.objective_combo.currentIndexChanged.connect(self._on_settings_changed)
        scale_layout.addWidget(self.objective_combo)
        calibrate_btn = QPushButton(self.tr("Set scale..."))
        calibrate_btn.clicked.connect(self._open_calibration_dialog)
        scale_layout.addWidget(calibrate_btn)
        layout.addWidget(self.scale_group)

        contrast_group = QGroupBox(self.tr("Contrast"))
        contrast_layout = QVBoxLayout(contrast_group)
        self.contrast_combo = QComboBox()
        self.contrast_combo.addItems(self.contrast_options)
        if self.contrast_default:
            idx = self.contrast_combo.findText(self.contrast_default)
            if idx >= 0:
                self.contrast_combo.setCurrentIndex(idx)
        self.contrast_combo.currentIndexChanged.connect(self._on_settings_changed)
        contrast_layout.addWidget(self.contrast_combo)
        layout.addWidget(contrast_group)

        mount_group = QGroupBox(self.tr("Mount"))
        mount_layout = QVBoxLayout(mount_group)
        self.mount_combo = QComboBox()
        self.mount_combo.addItems(self.mount_options)
        if self.mount_default:
            idx = self.mount_combo.findText(self.mount_default)
            if idx >= 0:
                self.mount_combo.setCurrentIndex(idx)
        self.mount_combo.currentIndexChanged.connect(self._on_settings_changed)
        mount_layout.addWidget(self.mount_combo)
        layout.addWidget(mount_group)

        sample_group = QGroupBox(self.tr("Sample type"))
        sample_layout = QVBoxLayout(sample_group)
        self.sample_combo = QComboBox()
        self.sample_combo.addItems(self.sample_options)
        if self.sample_default:
            idx = self.sample_combo.findText(self.sample_default)
            if idx >= 0:
                self.sample_combo.setCurrentIndex(idx)
        self.sample_combo.currentIndexChanged.connect(self._on_settings_changed)
        sample_layout.addWidget(self.sample_combo)
        layout.addWidget(sample_group)

        layout.addStretch()
        self.settings_hint_label = QLabel("")
        self.settings_hint_label.setWordWrap(True)
        self.settings_hint_label.setStyleSheet("color: #7f8c8d; font-size: 9pt;")
        layout.addWidget(self.settings_hint_label)
        apply_row = QHBoxLayout()
        self.apply_all_btn = QPushButton(self.tr("Apply to all"))
        self.apply_all_btn.clicked.connect(self._apply_to_all)
        apply_row.addWidget(self.apply_all_btn)
        layout.addLayout(apply_row)
        outer.addWidget(panel, 1)
        return container

    def _build_center_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        self.preview_stack = QStackedLayout()

        self.preview = ZoomableImageLabel()
        self.preview.setMinimumHeight(420)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.set_pan_without_shift(True)
        self.preview.clicked.connect(self._on_preview_clicked)
        self.preview.cropChanged.connect(self._on_ai_crop_changed)

        self.preview_message = QLabel(self.tr("Multiple images selected"))
        self.preview_message.setAlignment(Qt.AlignCenter)
        self.preview_message.setStyleSheet("color: #7f8c8d; font-size: 12pt;")

        self.preview_stack.addWidget(self.preview)
        self.preview_stack.addWidget(self.preview_message)
        layout.addLayout(self.preview_stack, 1)
        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QGroupBox(self.tr("Import details"))
        panel.setMinimumWidth(300)
        panel.setMaximumWidth(380)
        panel.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        layout = QVBoxLayout(panel)

        current_group = QGroupBox(self.tr("Current image"))
        current_layout = QFormLayout(current_group)
        self.exif_datetime_label = QLabel("--")
        self.exif_camera_label = QLabel("--")
        self.exif_iso_label = QLabel("--")
        self.exif_shutter_label = QLabel("--")
        self.exif_aperture_label = QLabel("--")
        self.exif_lat_label = QLabel("Lat: --")
        self.exif_lon_label = QLabel("Lon: --")
        self.exif_map_btn = QPushButton(self.tr("Map"))
        self.exif_map_btn.clicked.connect(self._open_current_image_map)
        self.exif_map_btn.setEnabled(False)

        current_layout.addRow(self.tr("Date & time:"), self.exif_datetime_label)
        current_layout.addRow(self.tr("Camera:"), self.exif_camera_label)
        current_layout.addRow(self.tr("ISO:"), self.exif_iso_label)
        current_layout.addRow(self.tr("Shutter:"), self.exif_shutter_label)
        current_layout.addRow(self.tr("F-stop:"), self.exif_aperture_label)

        gps_values = QVBoxLayout()
        gps_values.addWidget(self.exif_lat_label)
        gps_values.addWidget(self.exif_lon_label)
        gps_row = QHBoxLayout()
        gps_row.addLayout(gps_values, 1)
        gps_row.addWidget(self.exif_map_btn)
        current_layout.addRow(self.tr("GPS:"), gps_row)
        layout.addWidget(current_group)

        obs_group = QGroupBox(self.tr("Time and GPS"))
        obs_layout = QFormLayout(obs_group)

        datetime_container = QWidget()
        datetime_layout = QVBoxLayout(datetime_container)
        datetime_layout.setContentsMargins(0, 0, 0, 0)
        datetime_layout.setSpacing(4)
        datetime_row = QHBoxLayout()
        datetime_label = QLabel(self.tr("Date & time:"))
        self.datetime_input = QDateTimeEdit()
        self.datetime_input.setMinimumDateTime(self._unset_datetime)
        self.datetime_input.setSpecialValueText("--")
        self.datetime_input.setCalendarPopup(True)
        self.datetime_input.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.datetime_input.dateTimeChanged.connect(self._on_metadata_changed)
        self.datetime_input.setDateTime(self._unset_datetime)
        datetime_row.addWidget(datetime_label)
        datetime_row.addWidget(self.datetime_input, 1)
        datetime_layout.addLayout(datetime_row)
        datetime_layout.addSpacing(6)
        obs_layout.addRow("", datetime_container)

        gps_container = QWidget()
        gps_container_layout = QVBoxLayout(gps_container)
        gps_container_layout.setContentsMargins(0, 0, 0, 0)
        gps_container_layout.setSpacing(4)
        gps_lat_row = QHBoxLayout()
        self.lat_input = QDoubleSpinBox()
        self.lat_input.setRange(-90.0, 90.0)
        self.lat_input.setDecimals(6)
        self.lat_input.setSpecialValueText("--")
        self.lat_input.setValue(self.lat_input.minimum())
        self.lat_input.valueChanged.connect(self._on_metadata_changed)
        gps_lat_row.addWidget(QLabel(self.tr("Lat:")))
        gps_lat_row.addWidget(self.lat_input)
        gps_container_layout.addLayout(gps_lat_row)
        gps_lon_row = QHBoxLayout()
        self.lon_input = QDoubleSpinBox()
        self.lon_input.setRange(-180.0, 180.0)
        self.lon_input.setDecimals(6)
        self.lon_input.setSpecialValueText("--")
        self.lon_input.setValue(self.lon_input.minimum())
        self.lon_input.valueChanged.connect(self._on_metadata_changed)
        gps_lon_row.addWidget(QLabel(self.tr("Lon:")))
        gps_lon_row.addWidget(self.lon_input)
        gps_container_layout.addLayout(gps_lon_row)
        gps_container_layout.addSpacing(6)
        self.set_from_image_btn = QPushButton(self.tr("Set from current image"))
        self.set_from_image_btn.clicked.connect(self._set_observation_gps_from_image)
        gps_container_layout.addWidget(self.set_from_image_btn, alignment=Qt.AlignLeft)
        obs_layout.addRow(self.tr("GPS:"), gps_container)

        layout.addWidget(obs_group)

        ai_group = QGroupBox(self.tr("AI suggestions"))
        ai_layout = QVBoxLayout(ai_group)
        ai_layout.setContentsMargins(6, 6, 6, 6)
        ai_controls = QHBoxLayout()
        self.ai_guess_btn = QPushButton(self.tr("Guess"))
        self.ai_guess_btn.setToolTip(self.tr("Send image to Artsorakelet"))
        self.ai_guess_btn.clicked.connect(self._on_ai_guess_clicked)
        self.ai_crop_btn = QPushButton(self.tr("Crop"))
        self.ai_crop_btn.setToolTip(self.tr("Draw a crop area for AI"))
        self.ai_crop_btn.clicked.connect(self._on_ai_crop_clicked)
        self.ai_guess_btn.setEnabled(False)
        self.ai_crop_btn.setEnabled(False)
        self.ai_guess_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.ai_crop_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        ai_controls.addWidget(self.ai_guess_btn)
        ai_controls.addWidget(self.ai_crop_btn)
        ai_controls.setStretch(0, 1)
        ai_controls.setStretch(1, 1)
        ai_layout.addLayout(ai_controls)
        self._set_ai_crop_active(False)

        self.ai_table = QTableWidget(0, 3)
        self.ai_table.setHorizontalHeaderLabels([self.tr("Suggested species"), "Match", "Link"])
        self.ai_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.ai_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.ai_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.ai_table.verticalHeader().setVisible(False)
        self.ai_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.ai_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.ai_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.ai_table.setMinimumHeight(140)
        self.ai_table.setStyleSheet(
            "QTableWidget::item:selected { background-color: #1f5aa6; color: white; font-weight: bold; }"
            "QTableWidget::item:selected:!active { background-color: #2f74c0; color: white; font-weight: bold; }"
        )
        self.ai_table.itemSelectionChanged.connect(self._on_ai_selection_changed)
        ai_layout.addWidget(self.ai_table)

        self.ai_status_label = QLabel("")
        self.ai_status_label.setWordWrap(True)
        self.ai_status_label.setStyleSheet("color: #7f8c8d; font-size: 9pt;")
        ai_layout.addWidget(self.ai_status_label)

        layout.addWidget(ai_group)

        layout.addStretch(1)
        action_row = QHBoxLayout()
        action_row.addStretch()
        self.cancel_btn = QPushButton(self.tr("Cancel"))
        self.cancel_btn.clicked.connect(self.reject)
        self.next_btn = QPushButton(self.tr("Continue"))
        self.next_btn.clicked.connect(self._accept_continue)
        action_row.addWidget(self.cancel_btn)
        action_row.addWidget(self.next_btn)
        layout.addLayout(action_row)
        return panel

    def _populate_objectives(self) -> None:
        self.objective_combo.clear()
        self.objective_combo.addItem(self.tr("Not set"), None)
        if self._custom_scale is not None:
            self.objective_combo.addItem(self.tr("Custom"), self.CUSTOM_OBJECTIVE_KEY)
        for key in sorted(self.objectives.keys()):
            self.objective_combo.addItem(key, key)
        if self.default_objective:
            idx = self.objective_combo.findText(self.default_objective)
            if idx >= 0:
                self.objective_combo.setCurrentIndex(idx)

    def _open_calibration_dialog(self) -> None:
        from .calibration_dialog import CalibrationDialog

        dialog = CalibrationDialog(self)
        dialog.select_custom_tab()
        dialog.calibration_saved.connect(self._on_calibration_saved)
        if dialog.exec():
            self.objectives = self._load_objectives()
            self.default_objective = self._get_default_objective()
            self._populate_objectives()

    def _on_calibration_saved(self, objective: dict) -> None:
        if not isinstance(objective, dict):
            return
        custom_scale = objective.get("microns_per_pixel")
        is_custom = str(objective.get("magnification") or "").lower() == "custom"
        if is_custom and isinstance(custom_scale, (int, float)):
            self._custom_scale = float(custom_scale)
            self._populate_objectives()
            idx = self.objective_combo.findData(self.CUSTOM_OBJECTIVE_KEY)
            if idx >= 0:
                self.objective_combo.setCurrentIndex(idx)

    def _load_objectives(self):
        return load_objectives()

    def _get_default_objective(self):
        for key, obj in self.objectives.items():
            if obj.get("is_default"):
                return key
        if self.objectives:
            return sorted(self.objectives.keys())[0]
        return None

    def _current_selection_indices(self) -> list[int]:
        if self.selected_indices:
            return [idx for idx in self.selected_indices if idx is not None]
        if self.selected_index is not None:
            return [self.selected_index]
        return []

    def _update_scale_group_state(self) -> None:
        if not hasattr(self, "scale_group"):
            return
        indices = self._current_selection_indices()
        if not indices:
            self.scale_group.setEnabled(False)
            return
        enable = all(
            self.import_results[idx].image_type == "microscope"
            for idx in indices
            if 0 <= idx < len(self.import_results)
        )
        self.scale_group.setEnabled(enable)

    def _update_set_from_image_button_state(self) -> None:
        if not hasattr(self, "set_from_image_btn"):
            return
        indices = self._current_selection_indices()
        if len(indices) != 1:
            self.set_from_image_btn.setEnabled(False)
            return
        idx = indices[0]
        if idx < 0 or idx >= len(self.import_results):
            self.set_from_image_btn.setEnabled(False)
            return
        if self.import_results[idx].image_type == "microscope":
            self.set_from_image_btn.setEnabled(False)
            return
        has_exif_data = (
            self._current_exif_datetime is not None
            or self._current_exif_lat is not None
            or self._current_exif_lon is not None
        )
        self.set_from_image_btn.setEnabled(has_exif_data)

    def _current_single_index(self) -> int | None:
        indices = self._current_selection_indices()
        if len(indices) == 1:
            return indices[0]
        return None

    def _update_ai_controls_state(self) -> None:
        if not hasattr(self, "ai_guess_btn"):
            return
        index = self._current_single_index()
        enable = False
        if index is not None and 0 <= index < len(self.import_results):
            enable = self.import_results[index].image_type == "field"
        if self._ai_thread is not None:
            enable = False
        self.ai_guess_btn.setEnabled(enable)
        self.ai_crop_btn.setEnabled(enable)
        if not enable and self._ai_crop_active:
            self._set_ai_crop_active(False)

    def _update_ai_table(self) -> None:
        if not hasattr(self, "ai_table"):
            return
        index = self._current_single_index()
        self.ai_table.setRowCount(0)
        if index is None:
            return
        predictions = self._ai_predictions_by_index.get(index, [])
        for row, pred in enumerate(predictions):
            taxon = pred.get("taxon", {})
            display_name = self._format_ai_taxon_name(taxon)
            confidence = pred.get("probability", 0.0)
            name_item = QTableWidgetItem(display_name)
            name_item.setData(Qt.UserRole, pred)
            conf_item = QTableWidgetItem(f"{confidence:.1%}")
            link_widget = self._build_adb_link_widget(self._ai_prediction_link(pred, taxon))
            self.ai_table.insertRow(row)
            self.ai_table.setItem(row, 0, name_item)
            self.ai_table.setItem(row, 1, conf_item)
            if link_widget:
                self.ai_table.setCellWidget(row, 2, link_widget)
        if predictions:
            selected = self._ai_selected_by_index.get(index)
            if selected:
                for row in range(self.ai_table.rowCount()):
                    item = self.ai_table.item(row, 0)
                    if item and item.data(Qt.UserRole) == selected:
                        self.ai_table.selectRow(row)
                        break
            else:
                self.ai_table.selectRow(0)
        else:
            self._ai_selected_taxon = None

    def _update_ai_overlay(self) -> None:
        if not hasattr(self, "preview"):
            return
        index = self._current_single_index()
        preview_pixmap = getattr(self.preview, "original_pixmap", None)
        if index is not None and preview_pixmap:
            width = preview_pixmap.width()
            height = preview_pixmap.height()
            crop_box = self._ai_crop_boxes.get(index)
            if crop_box and width > 0 and height > 0:
                self.preview.set_crop_box(
                    (crop_box[0] * width, crop_box[1] * height, crop_box[2] * width, crop_box[3] * height)
                )
            else:
                self.preview.set_crop_box(None)
        else:
            self.preview.set_crop_box(None)
        self.preview.set_overlay_boxes([])

    def _format_ai_taxon_name(self, taxon: dict) -> str:
        scientific = taxon.get("scientificName") or taxon.get("scientific_name") or taxon.get("name") or ""
        vernacular = ""
        vernacular_names = taxon.get("vernacularNames") or {}
        lang = normalize_vernacular_language(SettingsDB.get_setting("vernacular_language", "no"))
        if isinstance(vernacular_names, dict) and lang:
            vernacular = vernacular_names.get(lang, "")
        if not vernacular:
            vernacular = taxon.get("vernacularName") or ""
        return vernacular or scientific or self.tr("Unknown")

    def _ai_prediction_link(self, pred: dict, taxon: dict) -> str | None:
        if isinstance(pred, dict):
            for key in ("infoURL", "infoUrl", "info_url"):
                value = pred.get(key)
                if isinstance(value, str) and value.startswith("http"):
                    return value
        if not isinstance(taxon, dict):
            return None
        for key in ("url", "link", "href", "uri"):
            value = taxon.get(key)
            if isinstance(value, str) and value.startswith("http"):
                return value
        taxon_id = (
            taxon.get("taxonId")
            or taxon.get("taxon_id")
            or taxon.get("TaxonId")
            or taxon.get("id")
        )
        if taxon_id:
            return f"https://artsdatabanken.no/Taxon/{taxon_id}"
        return "https://artsdatabanken.no"

    def _build_adb_link_widget(self, url: str | None) -> QLabel | None:
        if not url:
            return None
        label = QLabel(f'<a href="{url}">AdB</a>')
        label.setTextFormat(Qt.RichText)
        label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        label.setOpenExternalLinks(True)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("QLabel { padding: 2px 6px; }")
        return label

    def _extract_genus_species(self, taxon: dict) -> tuple[str | None, str | None]:
        scientific = taxon.get("scientificName") or taxon.get("scientific_name") or taxon.get("name") or ""
        parts = [p for p in scientific.replace("/", " ").split() if p]
        if len(parts) >= 2:
            return parts[0], parts[1]
        return None, None

    def get_ai_selected_taxon(self) -> dict | None:
        if not self._ai_selected_taxon:
            return None
        genus, species = self._extract_genus_species(self._ai_selected_taxon)
        if not genus or not species:
            return None
        return {
            "genus": genus,
            "species": species,
            "taxon": self._ai_selected_taxon,
        }

    def _on_ai_selection_changed(self) -> None:
        index = self._current_single_index()
        if index is None:
            return
        selected_items = self.ai_table.selectedItems()
        if not selected_items:
            self._ai_selected_taxon = None
            self._set_ai_status(None)
            return
        row_item = self.ai_table.item(self.ai_table.currentRow(), 0)
        if not row_item:
            return
        pred = row_item.data(Qt.UserRole) or {}
        self._ai_selected_by_index[index] = pred
        self._ai_selected_taxon = pred.get("taxon") or {}
        self._set_ai_status(self.tr("Applied selected species."), "#27ae60")

    def _set_ai_crop_active(self, active: bool) -> None:
        self._ai_crop_active = bool(active)
        if hasattr(self, "preview"):
            self.preview.set_crop_mode(self._ai_crop_active)
        if hasattr(self, "ai_crop_btn"):
            if self._ai_crop_active:
                self.ai_crop_btn.setStyleSheet(
                    "background-color: #e74c3c; color: white; font-weight: bold;"
                )
            else:
                self.ai_crop_btn.setStyleSheet(
                    "background-color: #3498db; color: white; font-weight: bold;"
                )

    def _on_ai_crop_clicked(self) -> None:
        index = self._current_single_index()
        if index is None:
            return
        if index in self._ai_crop_boxes:
            self._ai_crop_boxes.pop(index, None)
            if hasattr(self, "preview"):
                self.preview.set_crop_box(None)
            self._set_ai_crop_active(True)
            self._update_ai_controls_state()
            return
        if self._ai_crop_active:
            self._set_ai_crop_active(False)
            return
        self._set_ai_crop_active(True)

    def _on_ai_crop_changed(self, box: tuple[float, float, float, float] | None) -> None:
        index = self._current_single_index()
        if index is None:
            return
        if box and getattr(self.preview, "original_pixmap", None):
            width = self.preview.original_pixmap.width()
            height = self.preview.original_pixmap.height()
            if width > 0 and height > 0:
                x1, y1, x2, y2 = box
                norm_box = (
                    max(0.0, min(1.0, x1 / width)),
                    max(0.0, min(1.0, y1 / height)),
                    max(0.0, min(1.0, x2 / width)),
                    max(0.0, min(1.0, y2 / height)),
                )
                self._ai_crop_boxes[index] = norm_box
            else:
                self._ai_crop_boxes.pop(index, None)
        else:
            self._ai_crop_boxes.pop(index, None)
        if self._ai_crop_active:
            self._set_ai_crop_active(False)
        self._update_ai_controls_state()

    def _on_ai_guess_clicked(self) -> None:
        index = self._current_single_index()
        if index is None:
            return
        if index < 0 or index >= len(self.import_results):
            return
        result = self.import_results[index]
        if result.image_type != "field":
            self._set_ai_status(self.tr("AI guess only works for field photos"), "#e74c3c")
            return
        image_path = result.filepath
        if not image_path:
            return
        if self._ai_thread is not None:
            return
        self.ai_guess_btn.setEnabled(False)
        self.ai_guess_btn.setText(self.tr("AI guessing..."))
        self._set_ai_status(self.tr("Sending image to Artsdatabanken AI..."), "#3498db")
        temp_dir = get_images_dir() / "imports"
        crop_box = self._ai_crop_boxes.get(index)
        self._ai_thread = QThread(self)
        self._ai_worker = AIGuessWorker(index, image_path, crop_box, temp_dir, max_dim=1600)
        self._ai_worker.moveToThread(self._ai_thread)
        self._ai_thread.started.connect(self._ai_worker.run)
        self._ai_worker.finished.connect(self._on_ai_guess_finished)
        self._ai_worker.error.connect(self._on_ai_guess_error)
        self._ai_worker.finished.connect(self._ai_thread.quit)
        self._ai_worker.finished.connect(self._ai_worker.deleteLater)
        self._ai_worker.error.connect(self._ai_thread.quit)
        self._ai_worker.error.connect(self._ai_worker.deleteLater)
        self._ai_thread.finished.connect(self._ai_thread.deleteLater)
        self._ai_thread.finished.connect(self._on_ai_thread_finished)
        self._ai_thread.start()

    def _on_ai_thread_finished(self) -> None:
        self._ai_thread = None
        self._ai_worker = None
        if hasattr(self, "ai_guess_btn"):
            self.ai_guess_btn.setText(self.tr("AI guess"))
        self._update_ai_controls_state()

    def _on_ai_guess_finished(
        self,
        index: int,
        predictions: list,
        _box: object,
        _warnings: object,
        temp_path: str,
    ) -> None:
        if temp_path:
            self._temp_preview_paths.add(temp_path)
        self._ai_predictions_by_index[index] = predictions or []
        self._update_ai_table()
        self._update_ai_overlay()
        if predictions:
            self._set_ai_status(self.tr("AI suggestion updated"), "#27ae60")
        else:
            self._set_ai_status(self.tr("No AI suggestions found"), "#7f8c8d")
        self._update_ai_controls_state()

    def _on_ai_guess_error(self, _index: int, message: str) -> None:
        if "500" in message:
            hint = self.tr("AI guess failed: server error (500). Try again later.")
        else:
            hint = self.tr("AI guess failed: {message}").format(message=message)
        self._set_ai_status(hint, "#e74c3c")
        self._update_ai_controls_state()

    def _seed_observation_metadata(self) -> None:
        if self._observation_datetime is None:
            for result in self.import_results:
                if result.captured_at:
                    self._observation_datetime = result.captured_at
                    break
        if self._observation_lat is None or self._observation_lon is None:
            for result in self.import_results:
                if result.gps_latitude is not None or result.gps_longitude is not None:
                    self._observation_lat = result.gps_latitude
                    self._observation_lon = result.gps_longitude
                    break

    def _sync_observation_metadata_inputs(self) -> None:
        self._loading_form = True
        if self._observation_datetime:
            self.datetime_input.setDateTime(self._observation_datetime)
        else:
            self.datetime_input.setDateTime(self._unset_datetime)
        if self._observation_lat is not None:
            self.lat_input.setValue(self._observation_lat)
        else:
            self.lat_input.setValue(self.lat_input.minimum())
        if self._observation_lon is not None:
            self.lon_input.setValue(self._observation_lon)
        else:
            self.lon_input.setValue(self.lon_input.minimum())
        self._loading_form = False

    def _update_observation_metadata_from_inputs(self) -> None:
        dt_value = self.datetime_input.dateTime()
        self._observation_datetime = None if dt_value == self._unset_datetime else dt_value
        lat = self.lat_input.value()
        self._observation_lat = None if lat == self.lat_input.minimum() else lat
        lon = self.lon_input.value()
        self._observation_lon = None if lon == self.lon_input.minimum() else lon

    def _set_settings_hint(self, text: str | None, color: str) -> None:
        if not hasattr(self, "settings_hint_label"):
            return
        if not text:
            self.settings_hint_label.setText("")
            return
        self.settings_hint_label.setText(text)
        self.settings_hint_label.setStyleSheet(f"color: {color}; font-size: 9pt;")

    def _set_ai_status(self, text: str | None, color: str = "#7f8c8d") -> None:
        if not hasattr(self, "ai_status_label"):
            return
        if not text:
            self.ai_status_label.setText("")
            return
        self.ai_status_label.setText(text)
        self.ai_status_label.setStyleSheet(f"color: {color}; font-size: 9pt;")

    def _update_settings_hint_for_indices(self, indices: list[int], action: str | None = None) -> None:
        if not indices:
            return
        action_map = {
            "scale": (self.tr("Scale applied"), "to"),
            "contrast": (self.tr("Contrast changed"), "for"),
            "mount": (self.tr("Mount changed"), "for"),
            "sample": (self.tr("Sample type changed"), "for"),
            "image_type": (self.tr("Image type changed"), "for"),
        }
        base, prep = action_map.get(action, (self.tr("Settings applied"), "to"))
        total = len(self.import_results)
        if total > 0 and len(indices) == total and total > 1:
            message = self.tr("{base} {prep} all images").format(base=base, prep=prep)
        elif len(indices) > 1:
            message = self.tr("{base} {prep} selected images").format(base=base, prep=prep)
        else:
            index = indices[0]
            message = self.tr("{base} {prep} image {num}").format(base=base, prep=prep, num=index + 1)
        self._set_settings_hint(message, "#27ae60")

    def _on_add_images_clicked(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            self.tr("Select Images"),
            "",
            self.tr("Images (*.png *.jpg *.jpeg *.tif *.tiff *.heic *.heif);;All Files (*)"),
        )
        if paths:
            self.add_images(paths)

    def add_images(self, paths: list[str]) -> None:
        import_dir = get_images_dir() / "imports"
        import_dir.mkdir(parents=True, exist_ok=True)
        if getattr(self, "import_progress", None) and len(paths) > 1:
            self.import_progress.setRange(0, len(paths))
            self.import_progress.setValue(0)
            self.import_progress.setVisible(True)
            QCoreApplication.processEvents()
        for path in paths:
            if not path:
                continue
            converted_path = maybe_convert_heic(path, import_dir)
            if converted_path and converted_path != path:
                self._converted_import_paths.add(converted_path)
                path = converted_path
            self.image_paths.append(path)
            meta = get_image_metadata(path)
            preview_path = path
            self._cache_pixmap(preview_path or path)
            has_exif_gps = meta.get("latitude") is not None or meta.get("longitude") is not None
            result = ImageImportResult(
                filepath=path,
                preview_path=preview_path or path,
                captured_at=None,
                gps_latitude=None,
                gps_longitude=None,
                gps_source=None,
                exif_has_gps=has_exif_gps,
            )
            self.import_results.append(result)
            if getattr(self, "import_progress", None) and self.import_progress.isVisible():
                self.import_progress.setValue(self.import_progress.value() + 1)
                QCoreApplication.processEvents()
        if getattr(self, "import_progress", None) and self.import_progress.isVisible():
            self.import_progress.setVisible(False)
        self._refresh_gallery()
        self._update_summary()
        self._seed_observation_metadata()
        self._sync_observation_metadata_inputs()
        self._update_scale_group_state()
        self._update_set_from_image_button_state()
        self._update_ai_controls_state()
        if self.selected_index is None and self.image_paths:
            self._select_image(0)

    def set_import_results(self, results: list[ImageImportResult]) -> None:
        self.import_results = []
        self.image_paths = []
        for result in results:
            if not result:
                continue
            if not result.preview_path:
                result.preview_path = result.filepath
            if not getattr(result, "exif_has_gps", False) and result.filepath:
                meta = get_image_metadata(result.filepath)
                result.exif_has_gps = meta.get("latitude") is not None or meta.get("longitude") is not None
            self._cache_pixmap(result.preview_path or result.filepath)
            self.import_results.append(result)
            self.image_paths.append(result.filepath)
        self._refresh_gallery()
        self._update_summary()
        self._seed_observation_metadata()
        self._sync_observation_metadata_inputs()
        self._update_scale_group_state()
        self._update_set_from_image_button_state()
        self._update_ai_controls_state()
        if self.image_paths:
            self._select_image(0)

    def _on_gallery_clicked(self, _, path: str) -> None:
        if not path:
            return
        if len(self.selected_indices) > 1:
            self._show_multi_selection_state()
            return
        try:
            index = self.image_paths.index(path)
        except ValueError:
            return
        self._select_image(index)

    def _on_gallery_selection_changed(self, paths: list[str]) -> None:
        indices = []
        for path in paths:
            try:
                indices.append(self.image_paths.index(path))
            except ValueError:
                continue
        self.selected_indices = sorted(set(indices))
        if len(self.selected_indices) > 1:
            self.selected_index = None
            self._show_multi_selection_state()
            self._update_scale_group_state()
            self._update_set_from_image_button_state()
            self._update_ai_controls_state()
            self._update_ai_table()
            self._update_ai_overlay()
        elif len(self.selected_indices) == 1:
            self._select_image(self.selected_indices[0], sync_gallery=False)
        else:
            self._update_scale_group_state()
            self._update_set_from_image_button_state()
            self._update_ai_controls_state()
            self._update_ai_table()
            self._update_ai_overlay()

    def _select_image(self, index: int, sync_gallery: bool = True) -> None:
        if index < 0 or index >= len(self.image_paths):
            return
        if self._ai_crop_active:
            self._set_ai_crop_active(False)
        self._set_ai_status(None)
        self.selected_index = index
        self.primary_index = index
        result = self.import_results[index]
        preview_path = result.preview_path or result.filepath
        if sync_gallery:
            self.gallery.select_paths([result.filepath])
        pixmap = self._get_cached_pixmap(preview_path) if preview_path else None
        preview_scaled = self._pixmap_cache_is_preview.get(preview_path or "", False)
        if pixmap and not pixmap.isNull():
            self.preview.set_image_sources(pixmap, result.filepath, preview_scaled)
        else:
            self.preview.set_image(None)
        self.preview_stack.setCurrentWidget(self.preview)
        self._load_result_into_form(result)
        self._update_current_image_exif(result)
        self._update_scale_group_state()
        self._update_set_from_image_button_state()
        self._update_ai_controls_state()
        self._update_ai_table()
        self._update_ai_overlay()

    def _load_result_into_form(self, result: ImageImportResult) -> None:
        self._loading_form = True
        if result.image_type == "microscope":
            self.micro_radio.setChecked(True)
        else:
            self.field_radio.setChecked(True)
        if result.custom_scale:
            self._custom_scale = result.custom_scale
            self._populate_objectives()
            idx = self.objective_combo.findData(self.CUSTOM_OBJECTIVE_KEY)
            if idx >= 0:
                self.objective_combo.setCurrentIndex(idx)
        elif result.objective:
            idx = self.objective_combo.findText(result.objective)
            if idx >= 0:
                self.objective_combo.setCurrentIndex(idx)
        else:
            self.objective_combo.setCurrentIndex(0)
        if result.contrast:
            idx = self.contrast_combo.findText(result.contrast)
            if idx >= 0:
                self.contrast_combo.setCurrentIndex(idx)
        if result.mount_medium:
            idx = self.mount_combo.findText(result.mount_medium)
            if idx >= 0:
                self.mount_combo.setCurrentIndex(idx)
        if result.sample_type:
            idx = self.sample_combo.findText(result.sample_type)
            if idx >= 0:
                self.sample_combo.setCurrentIndex(idx)
        self._loading_form = False
        self._sync_observation_metadata_inputs()

    def _on_settings_changed(self) -> None:
        if self.selected_index is None and not self.selected_indices:
            return
        if getattr(self, "_loading_form", False):
            return
        sender = self.sender()
        action = None
        if sender is self.objective_combo:
            action = "scale"
        elif sender is self.contrast_combo:
            action = "contrast"
        elif sender is self.mount_combo:
            action = "mount"
        elif sender is self.sample_combo:
            action = "sample"
        elif sender in (self.field_radio, self.micro_radio):
            action = "image_type"
        self._last_settings_action = action
        indices = self.selected_indices or [self.selected_index]
        self._apply_settings_to_indices(indices, action)

    def _on_metadata_changed(self, *_args) -> None:
        if self.selected_index is None and not self.selected_indices:
            return
        if getattr(self, "_loading_form", False):
            return
        if getattr(self, "_setting_from_image_source", False):
            return
        self._setting_from_image_source = False
        indices = self.selected_indices or [self.selected_index]
        self._apply_metadata_to_indices(indices)

    def _apply_settings_to_index(self, index: int) -> None:
        if index < 0 or index >= len(self.import_results):
            return
        result = self.import_results[index]
        result.image_type = "microscope" if self.micro_radio.isChecked() else "field"
        selected_objective = self.objective_combo.currentData()
        if selected_objective == self.CUSTOM_OBJECTIVE_KEY and self._custom_scale:
            result.custom_scale = self._custom_scale
            result.objective = None
        else:
            result.custom_scale = None
            result.objective = selected_objective or None
        result.contrast = self.contrast_combo.currentText() or None
        result.mount_medium = self.mount_combo.currentText() or None
        result.sample_type = self.sample_combo.currentText() or None
        result.needs_scale = (
            result.image_type == "microscope"
            and not result.objective
            and not result.custom_scale
        )
        self._refresh_gallery()
        self._update_summary()

    def _apply_settings_to_indices(self, indices: list[int | None], action: str | None = None) -> None:
        applied = []
        for idx in indices:
            if idx is None:
                continue
            self._apply_settings_to_index(idx)
            applied.append(idx)
        if applied:
            self._update_settings_hint_for_indices(applied, action or self._last_settings_action)
        self._update_scale_group_state()
        self._update_set_from_image_button_state()
        self._update_ai_controls_state()

    def _apply_metadata_to_index(self, index: int) -> None:
        if index < 0 or index >= len(self.import_results):
            return
        result = self.import_results[index]
        dt_value = self.datetime_input.dateTime()
        result.captured_at = None if dt_value == self._unset_datetime else dt_value
        lat = self.lat_input.value()
        result.gps_latitude = None if lat == self.lat_input.minimum() else lat
        lon = self.lon_input.value()
        result.gps_longitude = None if lon == self.lon_input.minimum() else lon
        source = Path(result.filepath).name if result.filepath else ""
        if result.gps_latitude is not None or result.gps_longitude is not None:
            result.gps_source = source or result.gps_source
        else:
            result.gps_source = None

    def _apply_metadata_to_indices(self, indices: list[int | None]) -> None:
        self._update_observation_metadata_from_inputs()
        if not self._setting_from_image_source:
            self._observation_source_index = None
        for idx in indices:
            if idx is None:
                continue
            self._apply_metadata_to_index(idx)
        if indices:
            self._refresh_gallery()

    def _cache_pixmap(self, path: str) -> None:
        if not path or path in self._pixmap_cache:
            return
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return
        w = pixmap.width()
        h = pixmap.height()
        max_dim = self._max_preview_dim
        is_preview = False
        if max(w, h) > max_dim:
            pixmap = pixmap.scaled(
                max_dim,
                max_dim,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            is_preview = True
        self._pixmap_cache[path] = pixmap
        self._pixmap_cache_is_preview[path] = is_preview

    def _get_cached_pixmap(self, path: str) -> QPixmap | None:
        if not path:
            return None
        pixmap = self._pixmap_cache.get(path)
        if pixmap is not None:
            if path not in self._pixmap_cache_is_preview:
                self._pixmap_cache_is_preview[path] = False
            return pixmap
        self._cache_pixmap(path)
        return self._pixmap_cache.get(path)

    def _apply_to_all(self) -> None:
        if not self.import_results:
            return
        self._apply_settings_to_indices(list(range(len(self.import_results))))

    def _apply_to_selected(self) -> None:
        indices = self.selected_indices or ([self.selected_index] if self.selected_index is not None else [])
        if not indices:
            return
        self._apply_settings_to_indices(indices)
        self._apply_metadata_to_indices(indices)

    def _set_observation_gps_from_image(self) -> None:
        if (
            self._current_exif_lat is None
            and self._current_exif_lon is None
            and self._current_exif_datetime is None
        ):
            return
        self._setting_from_image_source = True
        if self._current_exif_datetime is not None:
            self._observation_datetime = self._current_exif_datetime
            self.datetime_input.setDateTime(self._current_exif_datetime)
        if self._current_exif_lat is not None:
            self.lat_input.setValue(self._current_exif_lat)
        else:
            self.lat_input.setValue(self.lat_input.minimum())
        if self._current_exif_lon is not None:
            self.lon_input.setValue(self._current_exif_lon)
        else:
            self.lon_input.setValue(self.lon_input.minimum())
        self._update_observation_metadata_from_inputs()
        indices = self.selected_indices or ([self.selected_index] if self.selected_index is not None else [])
        if indices:
            self._observation_source_index = indices[0]
            self._apply_metadata_to_indices(indices)
        self._setting_from_image_source = False
        self._set_settings_hint(
            self.tr("Observation date and GPS set based on current image"),
            "#27ae60",
        )

    def _update_summary(self) -> None:
        if not hasattr(self, "summary_label"):
            return
        total = len(self.import_results)
        if total == 0:
            self.summary_label.setText(self.tr("No images added."))
            return
        microscope_count = sum(1 for item in self.import_results if item.image_type == "microscope")
        missing_scale = sum(1 for item in self.import_results if item.needs_scale)
        self.summary_label.setText(
            self.tr("Images: {total}\nMicroscope: {micro}\nMissing scale: {missing}").format(
                total=total,
                micro=microscope_count,
                missing=missing_scale,
            )
        )

    def _update_current_image_exif(self, result: ImageImportResult) -> None:
        path = result.filepath
        self._current_exif_path = path
        exif = get_exif_data(path) if path else {}
        meta = get_image_metadata(path) if path else {}
        dt = meta.get("datetime")
        if not dt and result.preview_path and result.preview_path != result.filepath:
            meta_preview = get_image_metadata(result.preview_path)
            dt = meta_preview.get("datetime")
        if dt:
            self._current_exif_datetime = QDateTime(dt)
            self.exif_datetime_label.setText(self._current_exif_datetime.toString("yyyy-MM-dd HH:mm"))
        else:
            self._current_exif_datetime = None
            self.exif_datetime_label.setText("--")

        make = exif.get("Make") or ""
        model = exif.get("Model") or ""
        camera = " ".join(str(part).strip() for part in (make, model) if part).strip()
        self.exif_camera_label.setText(camera if camera else "--")

        iso = exif.get("ISOSpeedRatings") or exif.get("PhotographicSensitivity")
        if isinstance(iso, (list, tuple)):
            iso = iso[0] if iso else None
        self.exif_iso_label.setText(str(iso) if iso else "--")

        exposure = exif.get("ExposureTime") or exif.get("ShutterSpeedValue")
        exposure_text = self._format_exposure(exposure)
        self.exif_shutter_label.setText(exposure_text or "--")

        fnum = exif.get("FNumber") or exif.get("ApertureValue")
        fnum_text = self._format_aperture(fnum)
        self.exif_aperture_label.setText(fnum_text or "--")

        lat = meta.get("latitude")
        lon = meta.get("longitude")
        if (lat is None or lon is None) and path:
            lat2, lon2 = get_gps_coordinates(path)
            lat = lat if lat is not None else lat2
            lon = lon if lon is not None else lon2
        self._current_exif_lat = lat
        self._current_exif_lon = lon
        lat_text = f"Lat: {lat:.6f}" if lat is not None else "Lat: --"
        lon_text = f"Lon: {lon:.6f}" if lon is not None else "Lon: --"
        self.exif_lat_label.setText(lat_text)
        self.exif_lon_label.setText(lon_text)
        self.exif_map_btn.setEnabled(lat is not None and lon is not None)
        self._update_set_from_image_button_state()

    def _utm_from_latlon(self, lat, lon):
        """Convert WGS84 lat/lon to EUREF89 / UTM 33N."""
        try:
            from pyproj import Transformer
        except Exception as exc:
            QMessageBox.warning(
                self,
                self.tr("Missing Dependency"),
                self.tr("pyproj is required for UTM conversions. Install it and try again.")
            )
            raise exc
        transformer = Transformer.from_crs("EPSG:4326", "EPSG:25833", always_xy=True)
        easting, northing = transformer.transform(lon, lat)
        return easting, northing

    def _artskart_base_link(self, lat, lon, zoom=12, bg="topo2"):
        easting, northing = self._utm_from_latlon(lat, lon)
        return (
            f"https://artskart.artsdatabanken.no/app/#map/"
            f"{easting:.0f},{northing:.0f}/{zoom}/background/{bg}"
        )

    def _inat_map_link(self, lat, lon, radius_km):
        from urllib.parse import urlencode

        return (
            "https://www.inaturalist.org/observations?"
            + urlencode({"lat": lat, "lng": lon, "radius": radius_km})
        )

    def _clear_current_image_exif(self) -> None:
        self._current_exif_path = None
        self._current_exif_datetime = None
        self._current_exif_lat = None
        self._current_exif_lon = None
        self.exif_datetime_label.setText("--")
        self.exif_camera_label.setText("--")
        self.exif_iso_label.setText("--")
        self.exif_shutter_label.setText("--")
        self.exif_aperture_label.setText("--")
        self.exif_lat_label.setText("Lat: --")
        self.exif_lon_label.setText("Lon: --")
        self.exif_map_btn.setEnabled(False)

    def _show_multi_selection_state(self) -> None:
        self.preview.set_image(None)
        self.preview_stack.setCurrentWidget(self.preview_message)
        self._clear_current_image_exif()
        self._update_set_from_image_button_state()
        if self._ai_crop_active:
            self._set_ai_crop_active(False)
        self._set_ai_status(None)
        self._update_ai_controls_state()
        self._update_ai_table()
        self._update_ai_overlay()

    def _format_exposure(self, value) -> str | None:
        if value is None:
            return None
        num, den = self._split_ratio(value)
        if num is None or den in (None, 0):
            try:
                val = float(value)
            except Exception:
                return None
            return f"{val:.3f}s" if val >= 0.01 else f"1/{int(round(1 / val))}"
        if num == 0:
            return None
        if num < den:
            return f"1/{int(round(den / num))}"
        return f"{num / den:.2f}s"

    def _format_aperture(self, value) -> str | None:
        if value is None:
            return None
        num, den = self._split_ratio(value)
        if num is None or den in (None, 0):
            try:
                val = float(value)
            except Exception:
                return None
            return f"f/{val:.1f}"
        return f"f/{(num / den):.1f}"

    @staticmethod
    def _split_ratio(value):
        if isinstance(value, tuple) and len(value) == 2:
            return value[0], value[1]
        if hasattr(value, "numerator") and hasattr(value, "denominator"):
            return value.numerator, value.denominator
        return None, None

    def _open_current_image_map(self) -> None:
        if self._current_exif_lat is None or self._current_exif_lon is None:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr("Open Map"))
        dialog.setModal(True)

        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(self.tr("Choose a map service:")))
        list_widget = QListWidget()
        services = ["Google Maps", "Kilden", "Artskart", "Norge i Bilder", "iNaturalist"]
        for service in services:
            list_widget.addItem(QListWidgetItem(service))
        list_widget.setCurrentRow(0)
        layout.addWidget(list_widget)

        buttons = QDialogButtonBox(QDialogButtonBox.Open | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        list_widget.itemDoubleClicked.connect(lambda _: dialog.accept())
        if dialog.exec() != QDialog.Accepted:
            return

        selected_item = list_widget.currentItem()
        if not selected_item:
            return
        selection = selected_item.text()
        lat = self._current_exif_lat
        lon = self._current_exif_lon

        try:
            if selection == "Google Maps":
                url = f"https://www.google.com/maps?q={lat},{lon}"
            elif selection == "Kilden":
                easting, northing = self._utm_from_latlon(lat, lon)
                url = (
                    "https://kilden.nibio.no/?topic=arealinformasjon"
                    f"&zoom=14&x={easting:.2f}&y={northing:.2f}&bgLayer=graatone"
                )
            elif selection == "Norge i Bilder":
                easting, northing = self._utm_from_latlon(lat, lon)
                url = (
                    "https://www.norgeibilder.no/"
                    f"?x={easting:.0f}&y={northing:.0f}&level=17&utm=33"
                    "&projects=&layers=&plannedOmlop=0&plannedGeovekst=0"
                )
            elif selection == "Artskart":
                url = self._artskart_base_link(lat, lon)
            else:
                url = self._inat_map_link(lat, lon, 50.0)
        except Exception as exc:
            QMessageBox.warning(self, self.tr("Map Lookup Failed"), str(exc))
            return

        import webbrowser
        webbrowser.open(url)

    def _refresh_gallery(self) -> None:
        selected = self.gallery.selected_paths() if hasattr(self, "gallery") else []
        items = []
        for idx, result in enumerate(self.import_results):
            badges = []
            if result.image_type == "microscope":
                detail = result.objective or (self.tr("Custom") if result.custom_scale else self.tr("Micro"))
                if result.contrast:
                    detail = f"{detail} {result.contrast}"
                badges.append(detail)
                if result.needs_scale:
                    badges.append(self.tr("(!) needs scale"))
            else:
                badges.append(self.tr("Field"))
            is_source = self._observation_source_index == idx
            gps_tag = self.tr("GPS") if result.exif_has_gps else None
            gps_highlight = is_source and result.exif_has_gps
            items.append(
                {
                    "id": result.image_id,
                    "filepath": result.filepath,
                    "preview_path": result.preview_path or result.filepath,
                    "image_number": idx + 1,
                    "badges": badges,
                    "gps_tag_text": gps_tag,
                    "gps_tag_highlight": gps_highlight,
                }
            )
        self.gallery.set_items(items)
        if selected:
            self.gallery.select_paths(selected)

    def _on_remove_selected(self) -> None:
        if not self.selected_indices:
            return
        removed_numbers = [idx + 1 for idx in self.selected_indices if idx is not None]
        removed_indices = sorted(idx for idx in self.selected_indices if idx is not None)
        for idx in sorted(self.selected_indices, reverse=True):
            if 0 <= idx < len(self.import_results):
                del self.import_results[idx]
                del self.image_paths[idx]
        if removed_indices:
            self._remap_ai_indices(removed_indices)
        self.selected_indices = []
        self.selected_index = None
        self.primary_index = None
        self._refresh_gallery()
        self._update_summary()
        if removed_numbers:
            if len(removed_numbers) == 1:
                message = self.tr("Image {num} deleted").format(num=removed_numbers[0])
            else:
                message = self.tr("Deleted {count} images").format(count=len(removed_numbers))
            self._set_settings_hint(message, "#e74c3c")
        if self.image_paths:
            self._select_image(0)

    def _remap_ai_indices(self, removed_indices: list[int]) -> None:
        def new_index(old_index: int) -> int:
            shift = 0
            for removed in removed_indices:
                if removed < old_index:
                    shift += 1
            return old_index - shift

        def remap_dict(source: dict[int, object]) -> dict[int, object]:
            remapped = {}
            for old_index, value in source.items():
                if old_index in removed_indices:
                    continue
                remapped[new_index(old_index)] = value
            return remapped

        self._ai_predictions_by_index = remap_dict(self._ai_predictions_by_index)
        self._ai_selected_by_index = remap_dict(self._ai_selected_by_index)
        self._ai_crop_boxes = remap_dict(self._ai_crop_boxes)
        self._ai_selected_taxon = None

    def _accept_continue(self) -> None:
        self._apply_to_selected()
        self._accepted = True
        self.continueRequested.emit(self.import_results)
        self.accept()

    def enter_calibration_mode(self, dialog):
        if not getattr(self, "preview", None) or not self.preview.original_pixmap:
            return
        if hasattr(self, "ai_crop_btn") and self.ai_crop_btn.isChecked():
            self.ai_crop_btn.setChecked(False)
        if hasattr(self.preview, "ensure_full_resolution"):
            self.preview.ensure_full_resolution()
        self.calibration_dialog = dialog
        self.calibration_points = []
        self._calibration_mode = True
        self.preview.clear_preview_line()

    def _on_preview_clicked(self, pos):
        if not getattr(self, "_calibration_mode", False):
            return
        self.calibration_points.append(pos)
        if len(self.calibration_points) == 1:
            self.preview.set_preview_line(pos)
            return
        if len(self.calibration_points) == 2:
            p1, p2 = self.calibration_points
            dx = p2.x() - p1.x()
            dy = p2.y() - p1.y()
            distance = (dx * dx + dy * dy) ** 0.5
            if distance <= 0:
                self.calibration_points = []
                return
            perp_x = -dy / distance
            perp_y = dx / distance
            half_width = max(6.0, distance * 0.05)
            mid = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
            p3 = QPointF(mid.x() - perp_x * half_width, mid.y() - perp_y * half_width)
            p4 = QPointF(mid.x() + perp_x * half_width, mid.y() + perp_y * half_width)
            self.preview.set_measurement_lines([[p1.x(), p1.y(), p2.x(), p2.y()]])
            self.preview.clear_preview_line()
            self._calibration_mode = False
            if self.calibration_dialog:
                self.calibration_dialog.set_calibration_distance(distance)
                self.calibration_dialog.set_calibration_preview(
                    self.preview.original_pixmap,
                    [p1, p2, p3, p4],
                )
            self.calibration_points = []

    def closeEvent(self, event):
        if self._ai_thread is not None:
            try:
                self._ai_thread.quit()
                self._ai_thread.wait(1000)
            except Exception:
                pass
        for path in list(self._temp_preview_paths):
            try:
                Path(path).unlink(missing_ok=True)
            except Exception:
                pass
        self._temp_preview_paths.clear()
        if not self._accepted:
            for path in list(self._converted_import_paths):
                try:
                    Path(path).unlink(missing_ok=True)
                except Exception:
                    pass
            self._converted_import_paths.clear()
        super().closeEvent(event)
