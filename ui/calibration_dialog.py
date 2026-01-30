"""Calibration dialog for setting microscope objectives."""
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                                QLineEdit, QPushButton, QComboBox, QFormLayout,
                                QGroupBox, QTabWidget, QWidget, QDoubleSpinBox,
                                QCheckBox)
from PySide6.QtCore import Signal, QPointF
from PySide6.QtGui import QPixmap
import json
from database.schema import (
    load_objectives,
    save_objectives,
    get_last_objective_path,
)
from .spore_preview_widget import SporePreviewWidget


class CalibrationDialog(QDialog):
    """Dialog for managing microscope objectives and calibration."""

    calibration_saved = Signal(dict)  # Emits the selected objective data

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Set Scale"))
        self.setMinimumWidth(650)

        self.objectives = self.load_objectives()

        # For custom calibration
        self.calibration_distance_pixels = None
        self.preview_points = []

        self.init_ui()
        self.load_last_used()

    def init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)

        # Tab widget for Fixed Objectives vs Custom Scale
        self.tab_widget = QTabWidget()

        # Tab 1: Fixed Objectives
        objectives_tab = self.create_objectives_tab()
        self.tab_widget.addTab(objectives_tab, self.tr("Fixed Objectives"))

        # Tab 2: Custom Scale
        custom_tab = self.create_custom_scale_tab()
        self.tab_widget.addTab(custom_tab, self.tr("Custom Scale"))

        layout.addWidget(self.tab_widget)

        # OK/Cancel buttons
        ok_cancel_layout = QHBoxLayout()
        ok_cancel_layout.addStretch()

        ok_btn = QPushButton(self.tr("Use This Scale"))
        ok_btn.setObjectName("measureButton")
        ok_btn.clicked.connect(self.accept_and_save)
        ok_cancel_layout.addWidget(ok_btn)

        cancel_btn = QPushButton(self.tr("Cancel"))
        cancel_btn.clicked.connect(self.reject)
        ok_cancel_layout.addWidget(cancel_btn)

        layout.addLayout(ok_cancel_layout)

    def select_custom_tab(self):
        """Select the Custom Scale tab."""
        if hasattr(self, "tab_widget"):
            self.tab_widget.setCurrentIndex(1)

    def create_objectives_tab(self):
        """Create the fixed objectives tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Objective selection group
        select_group = QGroupBox(self.tr("Select Objective"))
        select_layout = QVBoxLayout()

        self.objective_combo = QComboBox()
        self.update_objective_list()
        self.objective_combo.currentIndexChanged.connect(self.on_objective_selected)
        select_layout.addWidget(self.objective_combo)

        select_group.setLayout(select_layout)
        layout.addWidget(select_group)

        # Objective details group
        details_group = QGroupBox(self.tr("Objective Details"))
        details_layout = QFormLayout()

        self.name_input = QLineEdit()
        self.magnification_input = QLineEdit()
        self.microns_per_pixel_input = QLineEdit()
        self.notes_input = QLineEdit()
        self.default_checkbox = QCheckBox(self.tr("Default objective"))
        self.default_checkbox.setToolTip(self.tr("Use this objective as the default for new images"))

        details_layout.addRow(self.tr("Name:"), self.name_input)
        details_layout.addRow(self.tr("Magnification (e.g., 63X):"), self.magnification_input)
        details_layout.addRow(self.tr("Microns per pixel:"), self.microns_per_pixel_input)
        details_layout.addRow(self.tr("Notes:"), self.notes_input)
        details_layout.addRow("", self.default_checkbox)

        details_group.setLayout(details_layout)
        layout.addWidget(details_group)

        # Action buttons
        button_layout = QHBoxLayout()

        save_new_btn = QPushButton(self.tr("Save as New Objective"))
        save_new_btn.clicked.connect(self.save_new_objective)
        button_layout.addWidget(save_new_btn)

        update_btn = QPushButton(self.tr("Update Selected"))
        update_btn.clicked.connect(self.update_selected_objective)
        button_layout.addWidget(update_btn)

        delete_btn = QPushButton(self.tr("Delete Selected"))
        delete_btn.setStyleSheet(
            "QPushButton { background-color: #e74c3c; color: white; font-weight: bold; }"
            "QPushButton:hover { background-color: #c0392b; }"
            "QPushButton:pressed { background-color: #a93226; }"
        )
        delete_btn.clicked.connect(self.delete_selected_objective)
        button_layout.addWidget(delete_btn)

        layout.addLayout(button_layout)
        layout.addStretch()

        return tab

    def create_custom_scale_tab(self):
        """Create the custom scale tab with calibration functionality."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Instructions
        instructions = QLabel(
            self.tr(
                "<b>Custom Scale Calibration</b><br><br>"
                "Use this to set a custom scale when you don't have a predefined objective.<br><br>"
                "<b>To calibrate:</b><br>"
                "1. Load an image with a scale bar<br>"
                "2. Click 'Calibrate' and draw a line along the scale bar<br>"
                "3. Enter the known distance in microns<br>"
                "4. Click 'Use This Scale' to apply"
            )
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet("color: #7f8c8d; padding: 10px;")
        layout.addWidget(instructions)

        # Calibration group
        calib_group = QGroupBox(self.tr("Calibration"))
        calib_layout = QVBoxLayout()

        # Calibrate button
        self.calibrate_btn = QPushButton(self.tr("Calibrate (Draw line on scale bar)"))
        self.calibrate_btn.clicked.connect(self.start_calibration)
        calib_layout.addWidget(self.calibrate_btn)

        # Status label
        self.calib_status_label = QLabel(self.tr("No calibration set"))
        self.calib_status_label.setStyleSheet("color: #7f8c8d;")
        calib_layout.addWidget(self.calib_status_label)

        # Known distance input
        distance_layout = QHBoxLayout()
        distance_layout.addWidget(QLabel(self.tr("Known distance:")))
        self.known_distance_input = QDoubleSpinBox()
        self.known_distance_input.setRange(0.1, 10000)
        self.known_distance_input.setValue(100)
        self.known_distance_input.setSuffix(" um")
        self.known_distance_input.setDecimals(1)
        self.known_distance_input.valueChanged.connect(self.update_custom_scale)
        distance_layout.addWidget(self.known_distance_input)
        distance_layout.addStretch()
        calib_layout.addLayout(distance_layout)

        # Result
        result_layout = QHBoxLayout()
        result_layout.addWidget(QLabel(self.tr("Calculated scale:")))
        self.custom_scale_label = QLabel("-- um/pixel")
        self.custom_scale_label.setStyleSheet("font-weight: bold; color: #3498db;")
        result_layout.addWidget(self.custom_scale_label)
        result_layout.addStretch()
        calib_layout.addLayout(result_layout)

        calib_group.setLayout(calib_layout)
        layout.addWidget(calib_group)

        # Preview/fine-tune widget
        self.preview_group = QGroupBox(self.tr("Calibration preview"))
        preview_layout = QVBoxLayout()
        self.preview_widget = SporePreviewWidget(self)
        self.preview_widget.setMinimumHeight(220)
        self.preview_widget.setMaximumHeight(320)
        self.preview_widget.set_show_dimension_labels(False)
        self.preview_widget.dimensions_changed.connect(self._on_preview_dimensions_changed)
        preview_layout.addWidget(self.preview_widget)
        self.preview_group.setLayout(preview_layout)
        self.preview_group.setVisible(False)
        layout.addWidget(self.preview_group)

        layout.addStretch()
        return tab

    def load_objectives(self):
        """Load objectives from JSON file."""
        return load_objectives()

    def save_objectives(self):
        """Save objectives to JSON file."""
        save_objectives(self.objectives)

    def load_last_used(self):
        """Load the last used objective."""
        last_used_file = get_last_objective_path()
        if last_used_file.exists():
            with open(last_used_file, 'r') as f:
                last_used = json.load(f)
                mag = last_used.get("magnification", "")
                index = self.objective_combo.findData(mag)
                if index >= 0:
                    self.objective_combo.setCurrentIndex(index)

    def save_last_used(self, magnification):
        """Save the last used objective."""
        last_used_file = get_last_objective_path()
        last_used_file.parent.mkdir(parents=True, exist_ok=True)
        with open(last_used_file, 'w') as f:
            json.dump({"magnification": magnification}, f)

    def update_objective_list(self):
        """Update the objective combo box to show Name field."""
        self.objective_combo.clear()
        for mag in sorted(self.objectives.keys()):
            obj = self.objectives[mag]
            # Show the Name field in dropdown, store magnification as data
            display_name = obj.get("name", mag)
            if obj.get("is_default", False):
                display_name += self.tr(" (Default)")
            self.objective_combo.addItem(display_name, mag)

    def on_objective_selected(self):
        """Handle objective selection."""
        mag = self.objective_combo.currentData()  # Get stored magnification key
        if mag and mag in self.objectives:
            obj = self.objectives[mag]
            self.name_input.setText(obj["name"])
            self.magnification_input.setText(obj["magnification"])
            self.microns_per_pixel_input.setText(str(obj["microns_per_pixel"]))
            self.notes_input.setText(obj.get("notes", ""))
            self.default_checkbox.setChecked(obj.get("is_default", False))

    def save_new_objective(self):
        """Save a new objective."""
        mag = self.magnification_input.text().strip()
        if not mag:
            return

        is_default = self.default_checkbox.isChecked()

        # If setting as default, clear default from other objectives
        if is_default:
            for obj_mag in self.objectives:
                self.objectives[obj_mag]["is_default"] = False

        self.objectives[mag] = {
            "name": self.name_input.text().strip(),
            "magnification": mag,
            "microns_per_pixel": float(self.microns_per_pixel_input.text()),
            "notes": self.notes_input.text().strip(),
            "is_default": is_default
        }

        self.save_objectives()
        self.update_objective_list()

        # Select the new objective by finding the data value
        index = self.objective_combo.findData(mag)
        if index >= 0:
            self.objective_combo.setCurrentIndex(index)

    def update_selected_objective(self):
        """Update the currently selected objective."""
        mag = self.objective_combo.currentData()
        if mag and mag in self.objectives:
            is_default = self.default_checkbox.isChecked()

            # If setting as default, clear default from other objectives
            if is_default:
                for obj_mag in self.objectives:
                    self.objectives[obj_mag]["is_default"] = False

            self.objectives[mag] = {
                "name": self.name_input.text().strip(),
                "magnification": self.magnification_input.text().strip(),
                "microns_per_pixel": float(self.microns_per_pixel_input.text()),
                "notes": self.notes_input.text().strip(),
                "is_default": is_default
            }
            self.save_objectives()
            self.update_objective_list()
            # Re-select the updated objective
            index = self.objective_combo.findData(mag)
            if index >= 0:
                self.objective_combo.setCurrentIndex(index)

    def delete_selected_objective(self):
        """Delete the currently selected objective."""
        mag = self.objective_combo.currentData()
        if mag and mag in self.objectives and len(self.objectives) > 1:
            del self.objectives[mag]
            self.save_objectives()
            self.update_objective_list()

    def start_calibration(self):
        """Start the calibration process - hide dialog and enter calibration mode."""
        # Hide the dialog temporarily so user can interact with the image
        self.hide()

        # Notify parent to enter calibration mode
        # The parent will call set_calibration_distance when done
        if hasattr(self.parent(), 'enter_calibration_mode'):
            self.parent().enter_calibration_mode(self)

    def set_calibration_distance(self, distance_pixels):
        """Set the measured distance in pixels from calibration and reshow dialog."""
        self.calibration_distance_pixels = distance_pixels
        self.calib_status_label.setText(
            self.tr("Measured: {pixels:.1f} pixels").format(pixels=distance_pixels)
        )
        self.calib_status_label.setStyleSheet("color: #27ae60; font-weight: bold;")
        self.update_custom_scale()

        # Show the dialog again with updated values
        self.show()
        self.raise_()
        self.activateWindow()

    def set_calibration_preview(self, pixmap: QPixmap, points: list[QPointF]):
        if not pixmap or pixmap.isNull():
            return
        if not points or len(points) != 4:
            return
        self.preview_points = points
        length_px = self._distance(points[0], points[1])
        width_px = self._distance(points[2], points[3])
        self.preview_widget.set_spore(
            pixmap,
            points,
            length_px,
            width_px,
            1.0,
            0
        )
        self.preview_group.setVisible(True)

    def _on_preview_dimensions_changed(self, _measurement_id, new_length_um, _new_width_um, new_points):
        if new_length_um and new_length_um > 0:
            self.calibration_distance_pixels = new_length_um
            self.preview_points = new_points or self.preview_points
            self.calib_status_label.setText(
                self.tr("Measured: {pixels:.1f} pixels").format(pixels=new_length_um)
            )
            self.calib_status_label.setStyleSheet("color: #27ae60; font-weight: bold;")
            self.update_custom_scale()

    @staticmethod
    def _distance(p1: QPointF, p2: QPointF) -> float:
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        return (dx * dx + dy * dy) ** 0.5

    def update_custom_scale(self):
        """Update the calculated scale based on measured pixels and known distance."""
        if self.calibration_distance_pixels and self.calibration_distance_pixels > 0:
            known_distance = self.known_distance_input.value()
            scale = known_distance / self.calibration_distance_pixels
            self.custom_scale_label.setText(f"{scale:.4f} um/pixel")
        else:
            self.custom_scale_label.setText("-- um/pixel")

    def get_custom_scale(self):
        """Get the calculated custom scale value."""
        if self.calibration_distance_pixels and self.calibration_distance_pixels > 0:
            return self.known_distance_input.value() / self.calibration_distance_pixels
        return None

    def accept_and_save(self):
        """Accept dialog and emit the selected objective or custom scale."""
        current_tab = self.tab_widget.currentIndex()

        if current_tab == 0:
            # Fixed Objectives tab
            mag = self.objective_combo.currentData()
            if mag and mag in self.objectives:
                self.save_last_used(mag)
                self.calibration_saved.emit(self.objectives[mag])
                self.accept()
        else:
            # Custom Scale tab
            custom_scale = self.get_custom_scale()
            if custom_scale:
                # Create a custom objective-like dict
                custom_objective = {
                    "name": self.tr("Custom"),
                    "magnification": self.tr("Custom"),
                    "microns_per_pixel": custom_scale,
                    "notes": self.tr(
                        "Calibrated from {pixels:.1f} px = {microns:.1f} um"
                    ).format(
                        pixels=self.calibration_distance_pixels,
                        microns=self.known_distance_input.value()
                    )
                }
                self.calibration_saved.emit(custom_objective)
                self.accept()

    def get_last_used_objective(self):
        """Get the last used objective data, or the default objective if set."""
        # First check for a default objective
        for mag, obj in self.objectives.items():
            if obj.get("is_default", False):
                return obj

        # Fall back to last used
        last_used_file = get_last_objective_path()
        if last_used_file.exists():
            with open(last_used_file, 'r') as f:
                last_used = json.load(f)
                mag = last_used.get("magnification", "")
                if mag in self.objectives:
                    return self.objectives[mag]

        # Return first objective if no last used
        if self.objectives:
            first_mag = sorted(self.objectives.keys())[0]
            return self.objectives[first_mag]

        return None
