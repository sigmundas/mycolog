# ui/observations_tab.py
"""Observations tab for managing mushroom observations and photos."""
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                                QTableWidget, QTableWidgetItem, QHeaderView,
                                QDialog, QFormLayout, QLineEdit, QTextEdit,
                                QDateTimeEdit, QFileDialog, QLabel, QMessageBox,
                                QSplitter, QRadioButton, QButtonGroup, QScrollArea,
                                QGridLayout, QFrame, QComboBox, QToolButton,
                                QListWidget, QListWidgetItem, QGroupBox, QCheckBox,
                                QDoubleSpinBox, QTabWidget, QDialogButtonBox)
from PySide6.QtCore import Signal, Qt, QDateTime
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtCore import QUrl
from pathlib import Path
from database.models import ObservationDB, ImageDB, MeasurementDB, SettingsDB
from database.schema import get_images_dir, load_objectives
from utils.thumbnail_generator import get_thumbnail_path, generate_all_sizes
from utils.heic_converter import maybe_convert_heic
from utils.ml_export import export_coco_format, get_export_summary
from datetime import datetime


class SortableTableWidgetItem(QTableWidgetItem):
    """Table item that prefers UserRole for sorting when available."""

    def __lt__(self, other):
        self_data = self.data(Qt.UserRole)
        other_data = other.data(Qt.UserRole)
        if self_data is None or other_data is None:
            return super().__lt__(other)
        try:
            return self_data < other_data
        except TypeError:
            return str(self_data) < str(other_data)


class MapServiceHelper:
    """Shared map service helpers for observation dialogs."""

    def __init__(self, parent):
        self.parent = parent

    def _utm_from_latlon(self, lat, lon):
        """Convert WGS84 lat/lon to EUREF89 / UTM 33N."""
        try:
            from pyproj import Transformer
        except Exception as exc:
            QMessageBox.warning(
                self.parent,
                "Missing Dependency",
                "pyproj is required for UTM conversions. Install it and try again."
            )
            raise exc
        transformer = Transformer.from_crs("EPSG:4326", "EPSG:25833", always_xy=True)
        easting, northing = transformer.transform(lon, lat)
        return easting, northing

    def _inat_taxon_id(self, species_name):
        try:
            import requests
        except Exception as exc:
            raise RuntimeError("requests is required for iNaturalist lookups.") from exc

        url = "https://api.inaturalist.org/v1/taxa"
        params = {"q": species_name, "rank": "species", "per_page": 1}
        response = requests.get(url, params=params, timeout=20)
        response.raise_for_status()
        data = response.json()
        if not data.get("results"):
            raise ValueError("No taxon found")
        return data["results"][0]["id"]

    def _inat_map_link(self, species_name, lat, lon, radius_km):
        from urllib.parse import urlencode

        taxon_id = self._inat_taxon_id(species_name)
        return (
            "https://www.inaturalist.org/observations?"
            + urlencode({"taxon_id": taxon_id, "lat": lat, "lng": lon, "radius": radius_km})
        )

    def open_inaturalist_map(self, lat, lon, species_name):
        """Open iNaturalist observations map for the selected species."""
        import webbrowser

        if not species_name:
            QMessageBox.warning(
                self.parent,
                "Missing Species",
                "iNaturalist requires a known genus and species."
            )
            return
        try:
            url = self._inat_map_link(species_name, lat, lon, 50.0)
        except Exception as exc:
            QMessageBox.warning(self.parent, "iNaturalist Lookup Failed", str(exc))
            return
        webbrowser.open(url)

    def _artskart_taxon_id(self, scientific_name):
        try:
            import requests
        except Exception as exc:
            raise RuntimeError("requests is required for Artskart lookups.") from exc

        candidates = [
            ("https://artskart.artsdatabanken.no/publicapi/api/taxon/search", {"searchString": scientific_name}),
            ("https://artskart.artsdatabanken.no/publicapi/api/taxon", {"searchString": scientific_name}),
            ("https://artskart.artsdatabanken.no/publicapi/api/taxon/search", {"q": scientific_name}),
            ("https://artskart.artsdatabanken.no/publicapi/api/taxon", {"q": scientific_name}),
            ("https://api.artsdatabanken.no/v1/Taxon/Search", {"searchText": scientific_name}),
            ("https://api.artsdatabanken.no/v1/Taxon/Search", {"q": scientific_name}),
        ]

        last_error = None
        for url, params in candidates:
            try:
                response = requests.get(
                    url,
                    params={**params, "pageSize": 1, "page": 1},
                    timeout=20
                )
                if response.status_code == 404:
                    continue
                if response.status_code == 405:
                    continue
                response.raise_for_status()
                data = response.json()
                if isinstance(data, dict):
                    for key in ("data", "results", "items", "taxa"):
                        if key in data:
                            data = data[key]
                            break
                if not data:
                    last_error = ValueError("No taxon found")
                    continue
                first = data[0] if isinstance(data, list) else data
                taxon_id = None
                if isinstance(first, dict):
                    taxon_id = (
                        first.get("taxonId")
                        or first.get("taxon_id")
                        or first.get("id")
                        or first.get("TaxonId")
                    )
                if taxon_id:
                    return taxon_id
            except Exception as exc:
                last_error = exc

        if last_error:
            raise last_error
        raise ValueError("No taxon found")

    def _artskart_link(self, taxon_id, lat, lon, zoom=12, bg="topo2"):
        from urllib.parse import quote
        import json

        easting, northing = self._utm_from_latlon(lat, lon)
        filt = {
            "TaxonIds": [taxon_id],
            "IncludeSubTaxonIds": True,
            "Found": [2],
            "CenterPoints": True,
            "Style": 1
        }
        filt_s = json.dumps(filt, separators=(",", ":"))
        return (
            f"https://artskart.artsdatabanken.no/app/#map/"
            f"{easting:.0f},{northing:.0f}/{zoom}/background/{bg}/filter/{quote(filt_s)}"
        )

    def _artskart_base_link(self, lat, lon, zoom=12, bg="topo2"):
        easting, northing = self._utm_from_latlon(lat, lon)
        return (
            f"https://artskart.artsdatabanken.no/app/#map/"
            f"{easting:.0f},{northing:.0f}/{zoom}/background/{bg}"
        )

    def show_map_service_dialog(self, lat, lon, species_name):
        """Show a dialog to choose a map service."""
        dialog = QDialog(self.parent)
        dialog.setWindowTitle("Open Map")
        dialog.setModal(True)

        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Choose a map service:"))
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
                if not species_name:
                    QMessageBox.warning(
                        self.parent,
                        "Missing Species",
                        "Artskart requires a known genus and species."
                    )
                    return
                try:
                    taxon_id = self._artskart_taxon_id(species_name)
                    url = self._artskart_link(taxon_id, lat, lon)
                except Exception as exc:
                    QMessageBox.warning(
                        self.parent,
                        "Artskart Lookup Failed",
                        f"{exc}\nOpening map without species filter."
                    )
                    url = self._artskart_base_link(lat, lon)
            else:
                if selection == "iNaturalist":
                    self.open_inaturalist_map(lat, lon, species_name)
                return
        except Exception as exc:
            QMessageBox.warning(self.parent, "Map Lookup Failed", str(exc))
            return

        import webbrowser
        webbrowser.open(url)


class ObservationsTab(QWidget):
    """Tab for viewing and managing observations."""

    # Signal emitted when observation is selected (id, display_name)
    observation_selected = Signal(int, str)
    # Signal emitted when an image is selected to open in Measure tab
    image_selected = Signal(int, int, str)  # image_id, observation_id, display_name

    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_observation_id = None
        self.map_helper = MapServiceHelper(self)
        self.init_ui()
        self.refresh_observations()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Top buttons
        button_layout = QHBoxLayout()

        new_btn = QPushButton("New Observation")
        new_btn.setObjectName("primaryButton")
        new_btn.clicked.connect(self.create_new_observation)
        button_layout.addWidget(new_btn)

        self.select_btn = QPushButton("Load")
        self.select_btn.setEnabled(False)
        self.select_btn.setStyleSheet("background-color: #27ae60;")
        self.select_btn.clicked.connect(self.set_selected_as_active)
        button_layout.addWidget(self.select_btn)

        self.rename_btn = QPushButton("Edit")
        self.rename_btn.setEnabled(False)
        self.rename_btn.clicked.connect(self.edit_observation)
        button_layout.addWidget(self.rename_btn)

        self.delete_btn = QPushButton("Delete")
        self.delete_btn.setEnabled(False)
        self.delete_btn.setStyleSheet("background-color: #e74c3c;")
        self.delete_btn.clicked.connect(self.delete_selected_observation)
        button_layout.addWidget(self.delete_btn)

        refresh_btn = QPushButton("Refresh DB")
        refresh_btn.clicked.connect(self.refresh_observations)
        button_layout.addWidget(refresh_btn)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search observations...")
        self.search_input.textChanged.connect(self.refresh_observations)
        button_layout.addWidget(self.search_input)

        self.needs_id_filter = QCheckBox("Needs ID only")
        self.needs_id_filter.stateChanged.connect(self.refresh_observations)
        button_layout.addWidget(self.needs_id_filter)

        button_layout.addStretch()

        layout.addLayout(button_layout)

        # Splitter for table and detail view
        splitter = QSplitter(Qt.Vertical)

        # Observations table
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "ID", "Genus", "Species", "Needs ID", "Date", "Location", "Map"
        ])

        # Set column properties
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.Stretch)
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)

        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        # Better selection highlight - white text on blue background
        self.table.setStyleSheet("""
            QTableWidget::item:selected {
                background-color: #2980b9;
                color: white;
            }
            QTableWidget::item:selected:!active {
                background-color: #3498db;
                color: white;
            }
        """)
        self.table.itemSelectionChanged.connect(self.on_selection_changed)
        self.table.itemDoubleClicked.connect(self.on_row_double_clicked)
        self.table.setSortingEnabled(True)
        splitter.addWidget(self.table)

        # Detail view (shows selected observation info and images)
        self.detail_widget = QWidget()
        detail_layout = QVBoxLayout(self.detail_widget)
        detail_layout.setContentsMargins(5, 5, 5, 5)
        detail_layout.setSpacing(5)

        # Info label
        self.detail_label = QLabel("")
        self.detail_label.setWordWrap(True)
        self.detail_label.setStyleSheet("font-size: 10pt;")
        detail_layout.addWidget(self.detail_label)

        # Image browser section (single horizontal scroll area for all images)
        self.images_scroll = QScrollArea()
        self.images_scroll.setWidgetResizable(True)
        self.images_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.images_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.images_scroll.setMaximumHeight(260)
        self.images_container = QWidget()
        self.images_grid = QHBoxLayout(self.images_container)
        self.images_grid.setAlignment(Qt.AlignLeft)
        self.images_grid.setSpacing(10)
        self.images_scroll.setWidget(self.images_container)

        detail_layout.addWidget(self.images_scroll)

        splitter.addWidget(self.detail_widget)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

        layout.addWidget(splitter)

    def refresh_observations(self):
        """Load all observations from database."""
        previous_id = self.selected_observation_id
        observations = ObservationDB.get_all_observations()
        if hasattr(self, "needs_id_filter") and self.needs_id_filter.isChecked():
            observations = [
                obs for obs in observations
                if not (obs.get('genus') and obs.get('species'))
            ]
        query = self.search_input.text().strip().lower() if hasattr(self, "search_input") else ""
        if query:
            filtered = []
            for obs in observations:
                for value in obs.values():
                    if value is None:
                        continue
                    if query in str(value).lower():
                        filtered.append(obs)
                        break
            observations = filtered

        self.table.setRowCount(len(observations))

        for row, obs in enumerate(observations):
            # ID
            id_item = SortableTableWidgetItem(str(obs['id']))
            id_item.setData(Qt.UserRole, obs['id'])
            self.table.setItem(row, 0, id_item)

            # Genus (with uncertain indicator)
            genus = obs.get('genus') or '-'
            uncertain = obs.get('uncertain', 0)
            if uncertain:
                genus = f"? {genus}"
            self.table.setItem(row, 1, QTableWidgetItem(genus))

            # Species
            species = obs.get('species') or obs.get('species_guess') or 'sp.'
            self.table.setItem(row, 2, QTableWidgetItem(species))

            needs_id = not (obs.get('genus') and obs.get('species'))
            needs_item = SortableTableWidgetItem("Yes" if needs_id else "")
            needs_item.setData(Qt.UserRole, 1 if needs_id else 0)
            self.table.setItem(row, 3, needs_item)

            # Date
            self.table.setItem(row, 4, QTableWidgetItem(obs['date'] or '-'))

            # Location
            self.table.setItem(row, 5, QTableWidgetItem(obs['location'] or '-'))

            # Map link
            lat = obs.get('gps_latitude')
            lon = obs.get('gps_longitude')
            has_coords = lat is not None and lon is not None
            map_item = SortableTableWidgetItem("" if has_coords else "-")
            map_item.setData(Qt.UserRole, 1 if has_coords else 0)
            map_item.setFlags(map_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 6, map_item)
            if has_coords:
                map_label = QLabel('<a href="#">Map</a>')
                map_label.setTextFormat(Qt.RichText)
                map_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
                map_label.setOpenExternalLinks(False)
                map_label.setAlignment(Qt.AlignCenter)
                species_name = self._build_species_name(obs)
                map_label.linkActivated.connect(
                    lambda _=None, la=lat, lo=lon, sn=species_name: self.show_map_service_dialog(la, lo, sn)
                )
                self.table.setCellWidget(row, 6, map_label)

        # Clear detail view
        self.detail_label.setText("")
        self.select_btn.setEnabled(False)
        self.rename_btn.setEnabled(False)
        self.delete_btn.setEnabled(False)
        self._clear_image_browser()
        self.selected_observation_id = None

        if previous_id:
            for row, obs in enumerate(observations):
                if obs['id'] == previous_id:
                    self.table.selectRow(row)
                    self.selected_observation_id = previous_id
                    self.on_selection_changed()
                    break

    def _get_measurements_for_image(self, image_id):
        """Get measurements for a specific image."""
        return MeasurementDB.get_measurements_for_image(image_id)

    def _build_species_name(self, obs):
        """Return a scientific name when genus/species are known."""
        genus = (obs.get('genus') or '').strip()
        species = (obs.get('species') or '').strip()
        if genus and species:
            return f"{genus} {species}".strip()
        return None

    def show_map_service_dialog(self, lat, lon, species_name):
        """Show a dialog to choose a map service."""
        self.map_helper.show_map_service_dialog(lat, lon, species_name)

    def _has_spore_measurements(self, image_id):
        """Check if an image has any spore measurements."""
        measurements = self._get_measurements_for_image(image_id)
        for measurement in measurements:
            measurement_type = (measurement.get('measurement_type') or '').lower()
            if measurement_type in ('', 'manual', 'spore'):
                return True
        return False

    def _clear_image_browser(self):
        """Clear all thumbnails from the image browser."""
        while self.images_grid.count():
            item = self.images_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _populate_image_browser(self, observation_id):
        """Populate the image browser with thumbnails for the observation."""
        self._clear_image_browser()

        images = ImageDB.get_images_for_observation(observation_id)

        # Add all images to single row
        for img in images:
            thumb_widget = self._create_thumbnail_widget(img)
            self.images_grid.addWidget(thumb_widget)

        # Add "no images" label if empty
        if not images:
            return

    def _create_thumbnail_widget(self, image_data):
        """Create a clickable thumbnail widget for an image."""
        frame = QFrame()
        frame.setFrameStyle(QFrame.Box)
        frame.setStyleSheet("""
            QFrame {
                border: 2px solid #bdc3c7;
                border-radius: 5px;
                background: white;
            }
            QFrame:hover {
                border-color: #3498db;
            }
        """)
        frame.setFixedSize(150, 170)
        frame.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(2)

        # Thumbnail image
        thumb_label = QLabel()
        thumb_label.setAlignment(Qt.AlignCenter)
        thumb_label.setFixedSize(140, 120)

        # Try to load thumbnail
        thumb_path = get_thumbnail_path(image_data['id'], '224x224')
        if thumb_path and Path(thumb_path).exists():
            pixmap = QPixmap(thumb_path)
        else:
            # Fall back to original image
            pixmap = QPixmap(image_data['filepath'])

        if not pixmap.isNull():
            scaled = pixmap.scaled(140, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            thumb_label.setPixmap(scaled)
        else:
            thumb_label.setText("No preview")
            thumb_label.setStyleSheet("color: #7f8c8d;")

        image_container = QWidget()
        image_layout = QGridLayout(image_container)
        image_layout.setContentsMargins(0, 0, 0, 0)
        image_layout.setSpacing(0)
        image_layout.addWidget(thumb_label, 0, 0, alignment=Qt.AlignCenter)

        overlay = QWidget()
        overlay_layout = QHBoxLayout(overlay)
        overlay_layout.setContentsMargins(2, 2, 2, 2)
        overlay_layout.setSpacing(4)
        overlay_layout.addStretch()

        if self._has_spore_measurements(image_data['id']):
            badge = QLabel("M")
            badge.setFixedSize(16, 16)
            badge.setAlignment(Qt.AlignCenter)
            badge.setStyleSheet(
                "background-color: #27ae60; color: white; border-radius: 8px; font-size: 8pt;"
            )
            overlay_layout.addWidget(badge)

        delete_btn = QToolButton()
        delete_btn.setText("X")
        delete_btn.setFixedSize(16, 16)
        delete_btn.setStyleSheet(
            "QToolButton { background-color: #e74c3c; color: white; border-radius: 8px; font-size: 8pt; }"
        )
        delete_btn.clicked.connect(lambda _, img_id=image_data['id']: self._confirm_delete_image(img_id))
        overlay_layout.addWidget(delete_btn)

        image_layout.addWidget(overlay, 0, 0, alignment=Qt.AlignTop | Qt.AlignRight)
        layout.addWidget(image_container)

        # Label with info
        filename = Path(image_data['filepath']).stem[:15]
        info_text = filename

        info_label = QLabel(info_text)
        info_label.setAlignment(Qt.AlignCenter)
        info_label.setStyleSheet("font-size: 8pt; color: #2c3e50;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # Store image data for click handler
        frame.image_data = image_data

        # Make clickable
        frame.mousePressEvent = lambda e, img=image_data: self._on_thumbnail_clicked(img)

        return frame

    def _confirm_delete_image(self, image_id):
        """Confirm and delete an image (and measurements if present)."""
        measurements = self._get_measurements_for_image(image_id)
        if measurements:
            prompt = "Delete image and associated measurements?"
        else:
            prompt = "Delete image?"

        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            prompt,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            ImageDB.delete_image(image_id)
            self.refresh_observations()

    def _on_thumbnail_clicked(self, image_data):
        """Handle thumbnail click - emit signal to open in Measure tab."""
        if self.selected_observation_id:
            # Get observation info for display name
            obs = ObservationDB.get_observation(self.selected_observation_id)
            if obs:
                genus = obs.get('genus') or ''
                species = obs.get('species') or obs.get('species_guess') or 'sp.'
                display_name = f"{genus} {species} {obs['date'] or ''}".strip()
                self.image_selected.emit(
                    image_data['id'],
                    self.selected_observation_id,
                    display_name
                )

    def on_selection_changed(self):
        """Update detail view when selection changes."""
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            self.detail_label.setText("")
            self.select_btn.setEnabled(False)
            self.rename_btn.setEnabled(False)
            self.delete_btn.setEnabled(False)
            self._clear_image_browser()
            self.selected_observation_id = None
            return

        row = selected_rows[0].row()
        obs_id = int(self.table.item(row, 0).text())
        self.selected_observation_id = obs_id

        # Get observation details
        observations = ObservationDB.get_all_observations()
        obs = next((o for o in observations if o['id'] == obs_id), None)

        if obs:
            detail_text = ""
            if obs.get('spore_statistics'):
                detail_text += "<b>Spore Statistics:</b><br>"
                detail_text += (
                    f"<span style='font-family: monospace; color: #2c3e50;'>"
                    f"{obs['spore_statistics']}</span>"
                )

            self.detail_label.setText(detail_text)
            self.select_btn.setEnabled(True)
            self.rename_btn.setEnabled(True)
            self.delete_btn.setEnabled(True)

            # Populate image browser
            self._populate_image_browser(obs_id)

    def on_row_double_clicked(self, item):
        """Double-click to select observation as active."""
        self.set_selected_as_active()

    def set_selected_as_active(self):
        """Set the selected observation as active and switch to Measure tab."""
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return

        row = selected_rows[0].row()
        obs_id = int(self.table.item(row, 0).text())
        genus = self.table.item(row, 1).text()
        species = self.table.item(row, 2).text()
        date = self.table.item(row, 4).text()
        display_name = f"{genus} {species} {date}"

        # Emit signal to set as active observation
        self.observation_selected.emit(obs_id, display_name)

    def get_selected_observation(self):
        """Return (observation_id, display_name) for current selection."""
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return None
        row = selected_rows[0].row()
        obs_id = int(self.table.item(row, 0).text())
        genus = self.table.item(row, 1).text()
        species = self.table.item(row, 2).text()
        date = self.table.item(row, 4).text()
        display_name = f"{genus} {species} {date}"
        return obs_id, display_name

    def edit_observation(self):
        """Edit the selected observation."""
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return

        row = selected_rows[0].row()
        obs_id = int(self.table.item(row, 0).text())
        observation = ObservationDB.get_observation(obs_id)
        if not observation:
            return

        existing_images = ImageDB.get_images_for_observation(obs_id)
        dialog = NewObservationDialog(self, observation=observation, existing_images=existing_images)
        if not dialog.exec():
            return

        data = dialog.get_data()
        ObservationDB.update_observation(
            obs_id,
            genus=data.get('genus'),
            species=data.get('species'),
            species_guess=data.get('species_guess'),
            uncertain=1 if data.get('uncertain') else 0,
            date=data.get('date'),
            location=data.get('location'),
            habitat=data.get('habitat'),
            notes=data.get('notes'),
            gps_latitude=data.get('gps_latitude'),
            gps_longitude=data.get('gps_longitude'),
            allow_nulls=True
        )

        for image_id in getattr(dialog, "deleted_image_ids", set()):
            ImageDB.delete_image(image_id)

        objectives = dialog._load_objectives()
        entries = dialog.get_image_entries()
        output_dir = get_images_dir() / "imports"
        output_dir.mkdir(parents=True, exist_ok=True)

        for entry in entries:
            image_type = entry.get("image_type", "field")
            objective_key = entry.get("objective")
            contrast = entry.get("contrast")
            mount_medium = entry.get("mount_medium")
            sample_type = entry.get("sample_type")

            scale = None
            objective_name = None
            if image_type == "microscope" and objective_key and objective_key in objectives:
                scale = float(objectives[objective_key]["microns_per_pixel"])
                objective_name = objective_key

            if entry.get("image_id"):
                ImageDB.update_image(
                    entry["image_id"],
                    image_type=image_type,
                    objective_name=objective_name,
                    scale=scale,
                    contrast=contrast,
                    mount_medium=mount_medium,
                    sample_type=sample_type
                )
                continue

            filepath = entry.get("filepath")
            if not filepath:
                continue
            final_path = maybe_convert_heic(filepath, output_dir)
            if final_path is None:
                continue
            image_id = ImageDB.add_image(
                observation_id=obs_id,
                filepath=final_path,
                image_type=image_type,
                scale=scale,
                objective_name=objective_name,
                contrast=contrast,
                mount_medium=mount_medium,
                sample_type=sample_type
            )
            try:
                generate_all_sizes(final_path, image_id)
            except Exception as e:
                print(f"Warning: Could not generate thumbnails for {final_path}: {e}")

        self.refresh_observations()
        for row, obs in enumerate(ObservationDB.get_all_observations()):
            if obs['id'] == obs_id:
                self.table.selectRow(row)
                self.selected_observation_id = obs_id
                self.on_selection_changed()
                break

    def create_new_observation(self):
        """Show dialog to create new observation."""
        dialog = NewObservationDialog(self)
        if dialog.exec():
            obs_data = dialog.get_data()
            profile = SettingsDB.get_profile()
            author = profile.get("name")
            if author:
                obs_data["author"] = author

            # Create in database
            obs_id = ObservationDB.create_observation(**obs_data)

            # Import images directly with settings from dialog
            files = dialog.get_files()
            settings = dialog.get_image_settings()
            objectives = dialog._load_objectives()

            output_dir = get_images_dir() / "imports"
            output_dir.mkdir(parents=True, exist_ok=True)
            for i, filepath in enumerate(files):
                final_path = maybe_convert_heic(filepath, output_dir)
                if final_path is None:
                    continue

                img_settings = settings[i] if i < len(settings) else {
                    'image_type': 'field',
                    'objective': None,
                    'contrast': self.contrast_default,
                    'mount_medium': self.mount_default,
                    'sample_type': self.sample_default
                }
                image_type = img_settings.get('image_type', 'field')
                objective_key = img_settings.get('objective')
                contrast = img_settings.get('contrast')
                mount_medium = img_settings.get('mount_medium')
                sample_type = img_settings.get('sample_type')

                scale = None
                objective_name = None
                if image_type == 'microscope' and objective_key and objective_key in objectives:
                    scale = float(objectives[objective_key]["microns_per_pixel"])
                    objective_name = objective_key

                image_id = ImageDB.add_image(
                    observation_id=obs_id,
                    filepath=final_path,
                    image_type=image_type,
                    scale=scale,
                    objective_name=objective_name,
                    contrast=contrast,
                    mount_medium=mount_medium,
                    sample_type=sample_type
                )

                try:
                    generate_all_sizes(final_path, image_id)
                except Exception as e:
                    print(f"Warning: Could not generate thumbnails for {final_path}: {e}")

            # Refresh table
            self.refresh_observations()

            for row, obs in enumerate(ObservationDB.get_all_observations()):
                if obs['id'] == obs_id:
                    self.table.selectRow(row)
                    self.selected_observation_id = obs_id
                    self.on_selection_changed()
                    break

    def export_for_ml(self):
        """Export annotations in COCO format for ML training."""
        # Get export summary first
        summary = get_export_summary()

        if summary['total_annotations'] == 0:
            QMessageBox.warning(
                self, "No Annotations",
                "There are no spore annotations to export.\n\n"
                "Measure some spores first to create training data."
            )
            return

        # Show summary and ask for confirmation
        msg = (
            f"Ready to export ML training data:\n\n"
            f"  Images with annotations: {summary['images_with_annotations']}\n"
            f"  Total annotations: {summary['total_annotations']}\n\n"
            "Select an output directory to continue."
        )

        reply = QMessageBox.question(
            self, "Export for ML",
            msg,
            QMessageBox.Ok | QMessageBox.Cancel,
            QMessageBox.Ok
        )

        if reply != QMessageBox.Ok:
            return

        # Select output directory
        output_dir = QFileDialog.getExistingDirectory(
            self, "Select Output Directory for ML Dataset"
        )

        if not output_dir:
            return

        # Perform export
        try:
            stats = export_coco_format(output_dir)

            # Show success message
            success_msg = (
                f"Export completed!\n\n"
                f"  Images exported: {stats['images_exported']}\n"
                f"  Annotations exported: {stats['annotations_exported']}\n"
                f"  Images skipped: {stats['images_skipped']}\n\n"
                f"Output saved to:\n{output_dir}"
            )

            if stats['errors']:
                success_msg += f"\n\nWarnings: {len(stats['errors'])} issues occurred."

            QMessageBox.information(self, "Export Complete", success_msg)

        except Exception as e:
            QMessageBox.critical(
                self, "Export Failed",
                f"An error occurred during export:\n\n{str(e)}"
            )

    def delete_selected_observation(self):
        """Delete the selected observation after confirmation."""
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return

        row = selected_rows[0].row()
        obs_id = int(self.table.item(row, 0).text())
        species = self.table.item(row, 1).text()

        # Confirm deletion
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete observation '{species}'?\n\nThis will also delete all associated images and measurements.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            ObservationDB.delete_observation(obs_id)
            self.refresh_observations()


class NewObservationDialog(QDialog):
    """Dialog for creating or editing an observation with image-first workflow."""

    def __init__(self, parent=None, observation=None, existing_images=None):
        super().__init__(parent)
        self.observation = observation
        self.existing_images = existing_images or []
        self.edit_mode = observation is not None
        self.map_helper = MapServiceHelper(self)
        self.setWindowTitle("Edit Observation" if self.edit_mode else "New Observation")
        self.setModal(True)
        self.setMinimumSize(900, 700)
        self.image_files = []
        self.image_metadata = []  # List of dicts with datetime, lat, lon, filename
        self.image_settings = []  # List of dicts with image_type, objective
        self.selected_image_index = -1
        self.gps_latitude = None
        self.gps_longitude = None
        self.deleted_image_ids = set()
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
        self.init_ui()
        if self.edit_mode:
            self._load_existing_observation()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)

        # ===== TOP BUTTONS =====
        top_buttons = QHBoxLayout()
        add_images_btn = QPushButton("Add Images...")
        add_images_btn.setObjectName("primaryButton")
        add_images_btn.setMinimumHeight(35)
        add_images_btn.clicked.connect(self.select_images)
        top_buttons.addWidget(add_images_btn)
        self.delete_image_btn = QPushButton("Delete Image")
        self.delete_image_btn.setMinimumHeight(35)
        self.delete_image_btn.setStyleSheet("background-color: #e74c3c;")
        self.delete_image_btn.setEnabled(False)
        self.delete_image_btn.clicked.connect(self.delete_selected_image)
        top_buttons.addWidget(self.delete_image_btn)
        tips_label = QLabel(
            "Select the image you want to use for time stamp and GPS location<br>"
            "You can change the default objective in Settings - Calibration<br>"
            "Add or remove contrast methods, mount and sample types in Settings - Database"
        )
        tips_label.setWordWrap(True)
        tips_label.setStyleSheet("color: #7f8c8d; font-size: 9pt;")
        top_buttons.addWidget(tips_label, 1)
        main_layout.addLayout(top_buttons)

        # ===== IMAGES SECTION (TOP - PROMINENT) =====
        images_group = QGroupBox("Images")
        images_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 11pt; }")
        images_layout = QVBoxLayout()

        # Horizontal layout for table and thumbnail
        images_content = QHBoxLayout()

        # Image table with columns: Filename/Date, Field, Micro, Objective, Contrast, Mount, Sample
        self.image_table = QTableWidget()
        self.image_table.setColumnCount(7)
        self.image_table.setHorizontalHeaderLabels(
            ["Image", "Field", "Micro", "Objective", "Contrast", "Mount", "Sample"]
        )
        self.image_table.setMinimumHeight(180)
        self.image_table.setMaximumHeight(220)
        self.image_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.image_table.setSelectionMode(QTableWidget.SingleSelection)
        self.image_table.itemSelectionChanged.connect(self.on_image_selected)

        # Set row height for better readability
        self.image_table.verticalHeader().setDefaultSectionSize(36)
        self.image_table.verticalHeader().setVisible(False)

        # Column sizing
        header = self.image_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        header.resizeSection(3, 120)  # Objective
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        header.resizeSection(4, 90)   # Contrast
        header.setSectionResizeMode(5, QHeaderView.Fixed)
        header.resizeSection(5, 110)  # Mount
        header.setSectionResizeMode(6, QHeaderView.Fixed)
        header.resizeSection(6, 110)  # Sample

        images_content.addWidget(self.image_table, 3)

        # Thumbnail preview
        self.thumbnail_label = QLabel("No image selected")
        self.thumbnail_label.setAlignment(Qt.AlignCenter)
        self.thumbnail_label.setMinimumSize(180, 150)
        self.thumbnail_label.setMaximumSize(200, 180)
        self.thumbnail_label.setStyleSheet(
            "QLabel { background-color: #ecf0f1; border: 1px solid #bdc3c7; border-radius: 4px; }"
        )
        images_content.addWidget(self.thumbnail_label, 1)

        images_layout.addLayout(images_content)
        images_group.setLayout(images_layout)
        main_layout.addWidget(images_group)

        # ===== OBSERVATION DETAILS SECTION =====
        details_group = QGroupBox("Observation Details")
        details_layout = QFormLayout()
        details_layout.setSpacing(8)

        # Date and time - make prominent but half width
        datetime_container = QWidget()
        datetime_layout = QHBoxLayout(datetime_container)
        datetime_layout.setContentsMargins(0, 0, 0, 0)
        self.datetime_input = QDateTimeEdit()
        self.datetime_input.setDateTime(QDateTime.currentDateTime())
        self.datetime_input.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.datetime_input.setCalendarPopup(True)
        self.datetime_input.setStyleSheet(
            "QDateTimeEdit { font-size: 14pt; font-weight: bold; padding: 8px; }"
        )
        self.datetime_input.setMinimumHeight(40)
        self.datetime_input.setMaximumWidth(250)
        datetime_layout.addWidget(self.datetime_input)
        datetime_layout.addStretch()
        details_layout.addRow("Date && Time:", datetime_container)

        # Taxonomy tab widget (Species vs Unknown)
        self.taxonomy_tabs = QTabWidget()
        self.taxonomy_tabs.setMaximumHeight(80)
        self.taxonomy_tabs.currentChanged.connect(self.on_taxonomy_tab_changed)

        # Tab 1: Identified (genus/species)
        identified_tab = QWidget()
        identified_layout = QHBoxLayout(identified_tab)
        identified_layout.setContentsMargins(8, 8, 8, 8)
        identified_layout.setSpacing(8)

        identified_layout.addWidget(QLabel("Genus:"))
        self.genus_input = QLineEdit()
        self.genus_input.setPlaceholderText("e.g., Flammulina")
        identified_layout.addWidget(self.genus_input, 1)

        identified_layout.addWidget(QLabel("Species:"))
        self.species_input = QLineEdit()
        self.species_input.setPlaceholderText("e.g., elastica")
        identified_layout.addWidget(self.species_input, 1)

        self.uncertain_checkbox = QCheckBox("Uncertain")
        self.uncertain_checkbox.setToolTip(
            "Check this if you're not confident about the identification"
        )
        identified_layout.addWidget(self.uncertain_checkbox)

        self.taxonomy_tabs.addTab(identified_tab, "Species")

        # Tab 2: Unknown (working title only)
        unknown_tab = QWidget()
        unknown_layout = QHBoxLayout(unknown_tab)
        unknown_layout.setContentsMargins(8, 8, 8, 8)
        unknown_layout.setSpacing(8)

        unknown_layout.addWidget(QLabel("Working title:"))
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("e.g., Brown gilled mushroom, Unknown 1")
        unknown_layout.addWidget(self.title_input, 1)
        unknown_layout.addStretch()

        self.taxonomy_tabs.addTab(unknown_tab, "Unknown")

        details_layout.addRow("Taxonomy:", self.taxonomy_tabs)

        # Location (text)
        self.location_input = QLineEdit()
        self.location_input.setPlaceholderText("e.g., Bymarka, Trondheim")
        details_layout.addRow("Location:", self.location_input)

        # GPS Coordinates
        gps_layout = QHBoxLayout()
        gps_layout.addWidget(QLabel("Lat:"))
        self.lat_input = QDoubleSpinBox()
        self.lat_input.setRange(-90.0, 90.0)
        self.lat_input.setDecimals(6)
        self.lat_input.setSpecialValueText("--")
        self.lat_input.setValue(self.lat_input.minimum())
        gps_layout.addWidget(self.lat_input)

        gps_layout.addWidget(QLabel("Lon:"))
        self.lon_input = QDoubleSpinBox()
        self.lon_input.setRange(-180.0, 180.0)
        self.lon_input.setDecimals(6)
        self.lon_input.setSpecialValueText("--")
        self.lon_input.setValue(self.lon_input.minimum())
        gps_layout.addWidget(self.lon_input)

        # Map button - opens location in browser
        self.map_btn = QPushButton("  Map  ")
        self.map_btn.setToolTip("Open location in Google Maps")
        self.map_btn.setMinimumWidth(70)
        self.map_btn.clicked.connect(self.open_map)
        self.map_btn.setEnabled(False)  # Disabled until GPS coordinates are set
        gps_layout.addWidget(self.map_btn)

        # Enable map button when coordinates are manually changed
        self.lat_input.valueChanged.connect(self._update_map_button)
        self.lon_input.valueChanged.connect(self._update_map_button)

        gps_layout.addStretch()
        details_layout.addRow("GPS:", gps_layout)

        # GPS info label (shows source of coordinates)
        self.gps_info_label = QLabel("")
        self.gps_info_label.setStyleSheet("color: #7f8c8d; font-size: 9pt;")
        details_layout.addRow("", self.gps_info_label)

        # Habitat
        self.habitat_input = QLineEdit()
        self.habitat_input.setPlaceholderText("e.g., Spruce forest")
        details_layout.addRow("Habitat:", self.habitat_input)

        # Notes
        self.notes_input = QTextEdit()
        self.notes_input.setMaximumHeight(80)
        self.notes_input.setPlaceholderText("Any additional notes...")
        details_layout.addRow("Notes:", self.notes_input)

        # Info about folder structure
        images_root = get_images_dir()
        info_path = f"{images_root}\\[genus]\\[species] - [date time]"
        info_label = QLabel(
            f"<small><i>Images will be stored in: {info_path}</i></small>"
        )
        info_label.setStyleSheet("color: #7f8c8d;")
        details_layout.addRow("", info_label)

        details_group.setLayout(details_layout)
        main_layout.addWidget(details_group)

        # ===== BOTTOM BUTTONS =====
        bottom_buttons = QHBoxLayout()
        bottom_buttons.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setMinimumHeight(35)
        cancel_btn.clicked.connect(self.reject)
        bottom_buttons.addWidget(cancel_btn)
        create_btn = QPushButton("Save Observation" if self.edit_mode else "Create Observation")
        create_btn.setObjectName("primaryButton")
        create_btn.setMinimumHeight(35)
        create_btn.clicked.connect(self.accept)
        bottom_buttons.addWidget(create_btn)
        main_layout.addLayout(bottom_buttons)

        self.on_taxonomy_tab_changed(self.taxonomy_tabs.currentIndex())
        self._update_datetime_width()

    def select_images(self):
        """Select images and extract EXIF metadata."""
        from utils.exif_reader import get_image_metadata

        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Photos", "",
            "Images (*.png *.jpg *.jpeg *.tif *.tiff *.orf *.nef *.heic *.heif);;All Files (*)"
        )
        if not files:
            return

        # Add to existing files
        for filepath in files:
            if filepath not in self.image_files:
                self.image_files.append(filepath)
                metadata = get_image_metadata(filepath)
                metadata["filepath"] = filepath
                metadata["image_id"] = None
                self.image_metadata.append(metadata)
                # Default settings: field image, default objective
                self.image_settings.append({
                    'image_type': 'field',
                    'objective': self.default_objective,
                    'contrast': self.contrast_default,
                    'mount_medium': self.mount_default,
                    'sample_type': self.sample_default
                })

        self._update_image_table()

        # If this is the first batch of images, auto-populate date/GPS from last image
        if len(self.image_metadata) > 0:
            self._apply_metadata_from_index(len(self.image_metadata) - 1)

    def _update_image_table(self):
        """Update the image table with current images."""
        self.image_table.setRowCount(len(self.image_metadata))

        for row, meta in enumerate(self.image_metadata):
            filename = meta['filename']
            dt = meta.get('datetime')
            if dt:
                date_str = dt.strftime("%Y-%m-%d %H:%M")
                display = f"{filename}\n{date_str}"
            else:
                display = filename

            # Column 0: Filename/Date
            name_item = QTableWidgetItem(display)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.image_table.setItem(row, 0, name_item)

            # Column 1: Field radio button
            field_radio = QRadioButton()
            field_radio.setChecked(self.image_settings[row]['image_type'] == 'field')
            field_radio.toggled.connect(lambda checked, r=row: self._on_image_type_changed(r, 'field', checked))
            field_container = QWidget()
            field_layout = QHBoxLayout(field_container)
            field_layout.addWidget(field_radio)
            field_layout.setAlignment(Qt.AlignCenter)
            field_layout.setContentsMargins(0, 0, 0, 0)
            self.image_table.setCellWidget(row, 1, field_container)

            # Column 2: Micro radio button
            micro_radio = QRadioButton()
            micro_radio.setChecked(self.image_settings[row]['image_type'] == 'microscope')
            micro_radio.toggled.connect(lambda checked, r=row: self._on_image_type_changed(r, 'microscope', checked))
            micro_container = QWidget()
            micro_layout = QHBoxLayout(micro_container)
            micro_layout.addWidget(micro_radio)
            micro_layout.setAlignment(Qt.AlignCenter)
            micro_layout.setContentsMargins(0, 0, 0, 0)
            self.image_table.setCellWidget(row, 2, micro_container)

            # Link the radio buttons
            btn_group = QButtonGroup(self.image_table)
            btn_group.addButton(field_radio, 0)
            btn_group.addButton(micro_radio, 1)

            # Column 3: Objective dropdown
            obj_combo = QComboBox()
            obj_combo.setEnabled(self.image_settings[row]['image_type'] == 'microscope')
            obj_combo.setStyleSheet("""
                QComboBox { padding: 2px 4px; min-height: 24px; }
                QComboBox QAbstractItemView { min-height: 24px; }
            """)
            for mag in sorted(self.objectives.keys()):
                obj = self.objectives[mag]
                obj_combo.addItem(obj.get("name", mag), mag)
            # Set current objective
            current_obj = self.image_settings[row].get('objective', self.default_objective)
            idx = obj_combo.findData(current_obj)
            if idx >= 0:
                obj_combo.setCurrentIndex(idx)
            obj_combo.currentIndexChanged.connect(lambda idx, r=row, c=obj_combo: self._on_objective_changed(r, c))
            self.image_table.setCellWidget(row, 3, obj_combo)

            # Column 4: Contrast dropdown
            contrast_combo = QComboBox()
            contrast_combo.setEnabled(self.image_settings[row]['image_type'] == 'microscope')
            for option in self.contrast_options:
                contrast_combo.addItem(option, option)
            current_contrast = self.image_settings[row].get('contrast', "BF")
            idx = contrast_combo.findData(current_contrast)
            if idx >= 0:
                contrast_combo.setCurrentIndex(idx)
            contrast_combo.currentIndexChanged.connect(lambda idx, r=row, c=contrast_combo: self._on_contrast_changed(r, c))
            self.image_table.setCellWidget(row, 4, contrast_combo)

            # Column 5: Mount medium dropdown
            mount_combo = QComboBox()
            mount_combo.setEnabled(self.image_settings[row]['image_type'] == 'microscope')
            for option in self.mount_options:
                mount_combo.addItem(option, option)
            current_mount = self.image_settings[row].get('mount_medium', "Not set")
            idx = mount_combo.findData(current_mount)
            if idx >= 0:
                mount_combo.setCurrentIndex(idx)
            mount_combo.currentIndexChanged.connect(lambda idx, r=row, c=mount_combo: self._on_mount_changed(r, c))
            self.image_table.setCellWidget(row, 5, mount_combo)

            # Column 6: Sample type dropdown
            sample_combo = QComboBox()
            sample_combo.setEnabled(self.image_settings[row]['image_type'] == 'microscope')
            for option in self.sample_options:
                sample_combo.addItem(option, option)
            current_sample = self.image_settings[row].get('sample_type', "Not set")
            idx = sample_combo.findData(current_sample)
            if idx >= 0:
                sample_combo.setCurrentIndex(idx)
            sample_combo.currentIndexChanged.connect(lambda idx, r=row, c=sample_combo: self._on_sample_changed(r, c))
            self.image_table.setCellWidget(row, 6, sample_combo)

        # Select the last row
        if self.image_table.rowCount() > 0:
            self.image_table.selectRow(self.image_table.rowCount() - 1)

    def _on_image_type_changed(self, row, image_type, checked):
        """Handle image type radio button change."""
        if checked:
            self.image_settings[row]['image_type'] = image_type
            # Enable/disable objective dropdown
            obj_combo = self.image_table.cellWidget(row, 3)
            if obj_combo:
                obj_combo.setEnabled(image_type == 'microscope')
            contrast_combo = self.image_table.cellWidget(row, 4)
            if contrast_combo:
                contrast_combo.setEnabled(image_type == 'microscope')
            mount_combo = self.image_table.cellWidget(row, 5)
            if mount_combo:
                mount_combo.setEnabled(image_type == 'microscope')
            sample_combo = self.image_table.cellWidget(row, 6)
            if sample_combo:
                sample_combo.setEnabled(image_type == 'microscope')

    def _on_objective_changed(self, row, combo):
        """Handle objective dropdown change."""
        self.image_settings[row]['objective'] = combo.currentData()

    def _on_mount_changed(self, row, combo):
        """Handle mount medium change."""
        self.image_settings[row]['mount_medium'] = combo.currentData()

    def _on_contrast_changed(self, row, combo):
        """Handle contrast change."""
        self.image_settings[row]['contrast'] = combo.currentData()

    def _on_sample_changed(self, row, combo):
        """Handle sample type change."""
        self.image_settings[row]['sample_type'] = combo.currentData()

    def on_image_selected(self):
        """Handle image selection in the table."""
        selected_rows = self.image_table.selectionModel().selectedRows()
        if not selected_rows or selected_rows[0].row() >= len(self.image_metadata):
            self.thumbnail_label.setText("No image selected")
            if hasattr(self, "delete_image_btn"):
                self.delete_image_btn.setEnabled(False)
            self.selected_image_index = -1
            return

        selected = selected_rows[0].row()
        self.selected_image_index = selected
        if hasattr(self, "delete_image_btn"):
            self.delete_image_btn.setEnabled(True)
        meta = self.image_metadata[selected]
        filepath = meta['filepath']

        # Show thumbnail - handle HEIC files specially
        pixmap = None
        suffix = Path(filepath).suffix.lower()

        if suffix in ('.heic', '.heif'):
            # Convert HEIC to QPixmap via PIL
            try:
                import pillow_heif
                from PIL import Image
                import io

                pillow_heif.register_heif_opener()
                with Image.open(filepath) as img:
                    # Convert to RGB if needed
                    if img.mode in ('RGBA', 'LA'):
                        background = Image.new('RGB', img.size, (255, 255, 255))
                        background.paste(img, mask=img.split()[-1])
                        img = background
                    elif img.mode != 'RGB':
                        img = img.convert('RGB')

                    # Convert PIL image to QPixmap
                    buffer = io.BytesIO()
                    img.save(buffer, format='JPEG', quality=85)
                    buffer.seek(0)
                    qimage = QImage()
                    qimage.loadFromData(buffer.read())
                    pixmap = QPixmap.fromImage(qimage)
            except Exception as e:
                print(f"Error loading HEIC thumbnail: {e}")
                pixmap = None
        else:
            pixmap = QPixmap(filepath)

        if pixmap and not pixmap.isNull():
            scaled = pixmap.scaled(
                self.thumbnail_label.width() - 10,
                self.thumbnail_label.height() - 10,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.thumbnail_label.setPixmap(scaled)
        else:
            self.thumbnail_label.setText("Preview unavailable")

        # Apply metadata from selected image
        self._apply_metadata_from_index(selected)

    def delete_selected_image(self):
        """Remove the selected image from the dialog."""
        selected_rows = self.image_table.selectionModel().selectedRows()
        if not selected_rows or selected_rows[0].row() >= len(self.image_metadata):
            return

        row = selected_rows[0].row()
        meta = self.image_metadata[row]
        image_id = meta.get("image_id")

        if image_id:
            measurements = MeasurementDB.get_measurements_for_image(image_id)
            if measurements:
                prompt = "Delete image and associated measurements?"
            else:
                prompt = "Delete image?"
        else:
            prompt = "Remove image from this observation?"

        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            prompt,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        if image_id:
            self.deleted_image_ids.add(image_id)

        # Remove from dialog state
        self.image_metadata.pop(row)
        self.image_settings.pop(row)
        if row < len(self.image_files):
            self.image_files.pop(row)

        self.selected_image_index = -1
        self._update_image_table()
        if self.image_table.rowCount() == 0:
            self.thumbnail_label.setText("No image selected")
            if hasattr(self, "delete_image_btn"):
                self.delete_image_btn.setEnabled(False)

    def _apply_metadata_from_index(self, index):
        """Apply date/time and GPS from the image at the given index."""
        if index < 0 or index >= len(self.image_metadata):
            return

        meta = self.image_metadata[index]

        # Set date/time from image EXIF
        if meta.get('datetime'):
            dt = meta['datetime']
            qdt = QDateTime(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)
            self.datetime_input.setDateTime(qdt)

        # Set GPS coordinates if available
        lat = meta.get('latitude')
        lon = meta.get('longitude')

        if lat is not None and lon is not None:
            self.lat_input.setValue(lat)
            self.lon_input.setValue(lon)
            self.gps_latitude = lat
            self.gps_longitude = lon
            self.gps_info_label.setText(f"GPS from: {meta['filename']}")
            self.map_btn.setEnabled(True)
        else:
            self.gps_info_label.setText("No GPS data in selected image")
            self.map_btn.setEnabled(False)

    def _update_map_button(self):
        """Enable/disable the Map button based on whether valid coordinates are entered."""
        lat = self.lat_input.value()
        lon = self.lon_input.value()
        has_coords = lat > self.lat_input.minimum() and lon > self.lon_input.minimum()
        self.map_btn.setEnabled(has_coords)

    def open_map(self):
        """Open the GPS coordinates in a map service."""
        lat = self.lat_input.value()
        lon = self.lon_input.value()

        # Check if we have valid coordinates (not at minimum/special value)
        if lat <= self.lat_input.minimum() or lon <= self.lon_input.minimum():
            return

        genus = self.genus_input.text().strip()
        species = self.species_input.text().strip()
        species_name = f"{genus} {species}".strip() if genus and species else None
        self.map_helper.show_map_service_dialog(lat, lon, species_name)

    def get_data(self):
        """Return observation data as dict."""
        # Check which taxonomy tab is selected (0=Identified, 1=Unknown)
        is_unknown = self.taxonomy_tabs.currentIndex() == 1

        if is_unknown:
            genus = None
            species = None
            working_title = self.title_input.text().strip() or "Unknown"
        else:
            genus = self.genus_input.text().strip() or None
            species = self.species_input.text().strip() or None
            working_title = None

        # Get GPS values (None if at minimum/special value)
        lat = None
        lon = None
        if self.lat_input.value() > self.lat_input.minimum():
            lat = self.lat_input.value()
        if self.lon_input.value() > self.lon_input.minimum():
            lon = self.lon_input.value()

        return {
            'genus': genus,
            'species': species,
            'species_guess': working_title,
            'uncertain': self.uncertain_checkbox.isChecked() if not is_unknown else False,
            'date': self.datetime_input.dateTime().toString("yyyy-MM-dd HH:mm"),
            'location': self.location_input.text().strip() or None,
            'habitat': self.habitat_input.text().strip() or None,
            'notes': self.notes_input.toPlainText().strip() or None,
            'gps_latitude': lat,
            'gps_longitude': lon
        }

    def on_taxonomy_tab_changed(self, index):
        """Disable uncertain when Unknown is selected."""
        is_unknown = index == 1
        self.uncertain_checkbox.setEnabled(not is_unknown)
        if is_unknown:
            self.uncertain_checkbox.setChecked(False)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_datetime_width()

    def _update_datetime_width(self):
        """Keep Date & Time at half the dialog width."""
        if hasattr(self, "datetime_input"):
            target = max(220, int(self.width() * 0.5))
            self.datetime_input.setFixedWidth(target)

    def get_files(self):
        """Return selected image files."""
        return self.image_files

    def get_image_settings(self):
        """Return image settings (type and objective for each image)."""
        return self.image_settings

    def get_image_entries(self):
        """Return images with settings for saving."""
        entries = []
        for idx, meta in enumerate(self.image_metadata):
            settings = self.image_settings[idx] if idx < len(self.image_settings) else {}
            entries.append({
                "image_id": meta.get("image_id"),
                "filepath": meta.get("filepath"),
                "image_type": settings.get("image_type", "field"),
                "objective": settings.get("objective"),
                "contrast": settings.get("contrast"),
                "mount_medium": settings.get("mount_medium"),
                "sample_type": settings.get("sample_type")
            })
        return entries

    def _load_objectives(self):
        """Load objectives from JSON file."""
        return load_objectives()

    def _get_default_objective(self):
        """Get the default objective key."""
        # Check already-loaded objectives for default
        for key, obj in self.objectives.items():
            if obj.get('is_default'):
                return key
        # Return first objective if no default set
        if self.objectives:
            return sorted(self.objectives.keys())[0]
        return None

    def _load_existing_observation(self):
        """Preload observation details and images for editing."""
        from utils.exif_reader import get_image_metadata

        obs = self.observation or {}

        date_str = obs.get("date")
        if date_str:
            dt = QDateTime.fromString(date_str, "yyyy-MM-dd HH:mm")
            if dt.isValid():
                self.datetime_input.setDateTime(dt)

        genus = obs.get("genus") or ""
        species = obs.get("species") or ""
        if genus or species:
            self.taxonomy_tabs.setCurrentIndex(0)
            self.genus_input.setText(genus)
            self.species_input.setText(species)
            self.uncertain_checkbox.setChecked(bool(obs.get("uncertain", 0)))
        else:
            self.taxonomy_tabs.setCurrentIndex(1)
            self.title_input.setText(obs.get("species_guess") or "")
            self.uncertain_checkbox.setChecked(False)

        self.location_input.setText(obs.get("location") or "")
        self.habitat_input.setText(obs.get("habitat") or "")
        self.notes_input.setPlainText(obs.get("notes") or "")

        lat = obs.get("gps_latitude")
        lon = obs.get("gps_longitude")
        if lat is not None:
            self.lat_input.setValue(lat)
        if lon is not None:
            self.lon_input.setValue(lon)
        self._update_map_button()

        if not self.existing_images:
            return

        for img in self.existing_images:
            filepath = img.get("filepath")
            if not filepath:
                continue
            self.image_files.append(filepath)
            metadata = get_image_metadata(filepath)
            metadata["image_id"] = img.get("id")
            if "filepath" not in metadata:
                metadata["filepath"] = filepath
            if "filename" not in metadata:
                metadata["filename"] = Path(filepath).name
            self.image_metadata.append(metadata)
            self.image_settings.append({
                "image_type": img.get("image_type", "field"),
                "objective": img.get("objective_name") or self.default_objective,
                "contrast": img.get("contrast") or self.contrast_default,
                "mount_medium": img.get("mount_medium") or self.mount_default,
                "sample_type": img.get("sample_type") or self.sample_default
            })

        self._update_image_table()


class RenameObservationDialog(QDialog):
    """Dialog for renaming an observation."""

    def __init__(self, observation, parent=None):
        super().__init__(parent)
        self.observation = observation
        self.setWindowTitle("Rename Observation")
        self.setModal(True)
        self.setMinimumWidth(400)
        self.init_ui()

    def init_ui(self):
        layout = QFormLayout(self)
        layout.setSpacing(10)

        self.unknown_checkbox = QCheckBox("Unknown")
        self.unknown_checkbox.toggled.connect(self.on_unknown_toggled)

        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Working title (e.g., Unknown 1)")
        self.title_input.setText(self.observation.get('species_guess') or "")

        unknown_row = QHBoxLayout()
        unknown_row.addWidget(self.unknown_checkbox)
        self.working_title_container = QWidget()
        working_title_layout = QHBoxLayout(self.working_title_container)
        working_title_layout.setContentsMargins(0, 0, 0, 0)
        working_title_layout.setSpacing(6)
        working_title_layout.addWidget(QLabel("Working title:"))
        working_title_layout.addWidget(self.title_input)
        unknown_row.addWidget(self.working_title_container)
        layout.addRow("", unknown_row)

        self.genus_input = QLineEdit()
        self.genus_input.setPlaceholderText("e.g., Flammulina")
        self.genus_input.setText(self.observation.get('genus') or "")
        layout.addRow("Genus:", self.genus_input)

        self.species_input = QLineEdit()
        self.species_input.setPlaceholderText("e.g., elastica")
        self.species_input.setText(self.observation.get('species') or "")
        layout.addRow("Species:", self.species_input)

        self.uncertain_checkbox = QCheckBox("Uncertain identification")
        self.uncertain_checkbox.setChecked(bool(self.observation.get('uncertain', 0)))
        layout.addRow("", self.uncertain_checkbox)

        button_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.setObjectName("primaryButton")
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addStretch()
        button_layout.addWidget(save_btn)
        button_layout.addWidget(cancel_btn)
        layout.addRow(button_layout)

        genus = self.observation.get('genus')
        species = self.observation.get('species')
        guess = self.observation.get('species_guess')
        unknown_checked = bool(guess) and not (genus or species)
        self.unknown_checkbox.setChecked(unknown_checked)
        self.on_unknown_toggled(unknown_checked)

    def get_data(self):
        """Return updated observation data."""
        working_title = self.title_input.text().strip() or None
        if not self.unknown_checkbox.isChecked():
            working_title = None
        return {
            'species_guess': working_title,
            'genus': self.genus_input.text().strip() or None,
            'species': self.species_input.text().strip() or None,
            'uncertain': self.uncertain_checkbox.isChecked()
        }

    def on_unknown_toggled(self, checked):
        """Show working title and disable genus/species when unknown."""
        self.working_title_container.setVisible(checked)
        self.title_input.setEnabled(checked)
        self.genus_input.setEnabled(not checked)
        self.species_input.setEnabled(not checked)
        if checked:
            self.genus_input.clear()
            self.species_input.clear()
