"""Database settings dialog."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QMessageBox,
    QToolBox,
    QListWidget,
    QListWidgetItem,
    QWidget,
)

from database.models import SettingsDB
from database.schema import (
    get_app_settings,
    save_app_settings,
    get_database_path,
    get_images_dir,
    init_database,
)
from database.database_tags import DatabaseTerms


class DatabaseSettingsDialog(QDialog):
    """Dialog for database and image folder settings."""

    TAG_CATEGORIES = (
        ("contrast", "Contrast methods"),
        ("mount", "Mount media"),
        ("sample", "Sample types"),
        ("measure", "Measure categories"),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Database Settings")
        self.setModal(True)
        self.setMinimumWidth(620)
        self.setMinimumHeight(580)
        self._tag_lists: dict[str, QListWidget] = {}
        self._category_order: list[str] = [category for category, _ in self.TAG_CATEGORIES]
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        # Database folder
        self.db_path_input = QLineEdit()
        db_browse = QPushButton(self.tr("Browse"))
        db_browse.clicked.connect(self._browse_db_folder)
        db_row = QHBoxLayout()
        db_row.addWidget(self.db_path_input)
        db_row.addWidget(db_browse)
        form.addRow(self.tr("Database folder:"), db_row)

        # Images folder
        self.images_dir_input = QLineEdit()
        img_browse = QPushButton(self.tr("Browse"))
        img_browse.clicked.connect(self._browse_images_dir)
        img_row = QHBoxLayout()
        img_row.addWidget(self.images_dir_input)
        img_row.addWidget(img_browse)
        form.addRow(self.tr("Images folder:"), img_row)

        # JPEG quality (right under image folder)
        self.resize_quality_input = QSpinBox()
        self.resize_quality_input.setRange(1, 100)
        self.resize_quality_input.setValue(80)
        self.resize_quality_input.setSuffix("%")
        fit_width = self.resize_quality_input.fontMetrics().horizontalAdvance("100%") + 24
        self.resize_quality_input.setMaximumWidth(fit_width)
        form.addRow(self.tr("Resize JPEG quality:"), self.resize_quality_input)

        layout.addLayout(form)

        tags_label = QLabel(self.tr("Microscope tags"))
        tags_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(tags_label)

        hint = QLabel(
            self.tr(
                "One category is visible at a time. "
                "Use Add/Remove custom tag for the active category."
            )
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #7f8c8d; font-size: 9pt;")
        layout.addWidget(hint)

        self.tag_toolbox = QToolBox()
        for category, label in self.TAG_CATEGORIES:
            page = self._build_tag_page(category)
            self.tag_toolbox.addItem(page, self.tr(label))
        layout.addWidget(self.tag_toolbox, 1)

        custom_row = QHBoxLayout()
        self.add_custom_btn = QPushButton(self.tr("Add custom tag"))
        self.add_custom_btn.clicked.connect(self._add_custom_tag)
        self.remove_custom_btn = QPushButton(self.tr("Remove selected"))
        self.remove_custom_btn.clicked.connect(self._remove_selected_custom_tag)
        custom_row.addWidget(self.add_custom_btn)
        custom_row.addWidget(self.remove_custom_btn)
        custom_row.addStretch()
        layout.addLayout(custom_row)

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

    def _build_tag_page(self, category: str):
        page = QWidget(self)
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(8, 8, 8, 8)
        page_layout.setSpacing(6)

        info = QLabel(
            self.tr(
                "Predefined tags can be toggled on/off. "
                "Custom tags are editable and saved as canonical values."
            )
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #7f8c8d; font-size: 9pt;")
        page_layout.addWidget(info)

        tag_list = QListWidget()
        tag_list.setAlternatingRowColors(True)
        page_layout.addWidget(tag_list, 1)
        self._tag_lists[category] = tag_list
        return page

    def _active_category(self) -> str:
        idx = self.tag_toolbox.currentIndex()
        if idx < 0 or idx >= len(self._category_order):
            return self._category_order[0]
        return self._category_order[idx]

    def _active_tag_list(self) -> QListWidget:
        return self._tag_lists[self._active_category()]

    def _populate_category_list(self, category: str, current_tags: list[str]) -> None:
        tag_list = self._tag_lists[category]
        tag_list.clear()

        predefined = DatabaseTerms.default_values(category)
        enabled = set(current_tags)

        for canonical in predefined:
            item = QListWidgetItem(DatabaseTerms.translate(category, canonical))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if canonical in enabled else Qt.Unchecked)
            item.setData(Qt.UserRole, canonical)
            item.setData(Qt.UserRole + 1, "predefined")
            tag_list.addItem(item)

        for canonical in current_tags:
            if canonical in predefined:
                continue
            item = QListWidgetItem(DatabaseTerms.translate(category, canonical))
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            item.setData(Qt.UserRole, canonical)
            item.setData(Qt.UserRole + 1, "custom")
            tag_list.addItem(item)

    def _collect_category_tags(self, category: str) -> list[str]:
        tag_list = self._tag_lists[category]
        values: list[str] = []
        seen: set[str] = set()

        for row in range(tag_list.count()):
            item = tag_list.item(row)
            source = item.data(Qt.UserRole + 1)
            if source == "predefined":
                if item.checkState() != Qt.Checked:
                    continue
                canonical = DatabaseTerms.canonicalize(category, item.data(Qt.UserRole))
            else:
                canonical = DatabaseTerms.custom_to_canonical(item.text())

            if not canonical or canonical in seen:
                continue
            seen.add(canonical)
            values.append(canonical)

        return DatabaseTerms.canonicalize_list(category, values)

    def _add_custom_tag(self) -> None:
        category = self._active_category()
        tag_list = self._active_tag_list()
        item = QListWidgetItem(self.tr("New tag"))
        item.setFlags(item.flags() | Qt.ItemIsEditable)
        item.setData(Qt.UserRole, DatabaseTerms.custom_to_canonical(item.text()))
        item.setData(Qt.UserRole + 1, "custom")
        tag_list.addItem(item)
        tag_list.setCurrentItem(item)
        tag_list.editItem(item)

    def _remove_selected_custom_tag(self) -> None:
        tag_list = self._active_tag_list()
        item = tag_list.currentItem()
        if not item:
            return
        if item.data(Qt.UserRole + 1) != "custom":
            return
        tag_list.takeItem(tag_list.row(item))

    def _load_settings(self):
        settings = get_app_settings()
        db_folder = settings.get("database_folder")
        if not db_folder and settings.get("database_path"):
            db_folder = str(Path(settings.get("database_path")).parent)
        if not db_folder:
            db_folder = str(get_database_path().parent)
        self.db_path_input.setText(db_folder)
        self.images_dir_input.setText(str(settings.get("images_dir") or get_images_dir()))

        for category, _label in self.TAG_CATEGORIES:
            setting_key = DatabaseTerms.setting_key(category)
            defaults = DatabaseTerms.default_values(category)
            current_tags = SettingsDB.get_list_setting(setting_key, defaults)
            current_tags = DatabaseTerms.canonicalize_list(category, current_tags)
            self._populate_category_list(category, current_tags)

        resize_quality = SettingsDB.get_setting("resize_jpeg_quality", 80)
        try:
            resize_quality = int(resize_quality)
        except (TypeError, ValueError):
            resize_quality = 80
        resize_quality = max(1, min(100, resize_quality))
        self.resize_quality_input.setValue(resize_quality)

    def _browse_db_folder(self):
        path = QFileDialog.getExistingDirectory(
            self, "Select Database Folder", self.db_path_input.text()
        )
        if path:
            self.db_path_input.setText(path)

    def _browse_images_dir(self):
        path = QFileDialog.getExistingDirectory(
            self, "Select Images Folder", self.images_dir_input.text()
        )
        if path:
            self.images_dir_input.setText(path)

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

        for category, _label in self.TAG_CATEGORIES:
            setting_key = DatabaseTerms.setting_key(category)
            SettingsDB.set_list_setting(setting_key, self._collect_category_tags(category))

        # Always remember last used values.
        SettingsDB.set_setting("remember_last_used", True)

        SettingsDB.set_setting("resize_jpeg_quality", int(self.resize_quality_input.value()))
        SettingsDB.set_setting("original_storage_mode", "none")
        SettingsDB.set_setting("store_original_images", False)

        self.accept()
