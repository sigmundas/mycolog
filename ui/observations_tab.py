# ui/observations_tab.py
"""Observations tab for managing mushroom observations and photos."""
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                                QTableWidget, QTableWidgetItem, QHeaderView,
                                QDialog, QFormLayout, QLineEdit, QTextEdit,
                                QDateTimeEdit, QFileDialog, QLabel, QMessageBox,
                                QSplitter, QRadioButton, QButtonGroup,
                                QComboBox,
                                QListWidget, QListWidgetItem, QGroupBox, QCheckBox,
                                QDoubleSpinBox, QTabWidget, QDialogButtonBox, QCompleter,
                                QSizePolicy, QAbstractItemView, QFrame)
from PySide6.QtCore import Signal, Qt, QDateTime, QStringListModel, QEvent
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtCore import QUrl
from pathlib import Path
import sqlite3
from database.models import ObservationDB, ImageDB, MeasurementDB, SettingsDB, CalibrationDB
from database.schema import get_images_dir, load_objectives
from utils.thumbnail_generator import get_thumbnail_path, generate_all_sizes
from utils.image_utils import cleanup_import_temp_file
from utils.exif_reader import get_image_metadata
from utils.heic_converter import maybe_convert_heic
from utils.ml_export import export_coco_format, get_export_summary
from datetime import datetime
import re
from utils.vernacular_utils import (
    normalize_vernacular_language,
    common_name_display_label,
    resolve_vernacular_db_path,
)
from .image_gallery_widget import ImageGalleryWidget
from .image_import_dialog import ImageImportDialog, ImageImportResult, AIGuessWorker


def _parse_observation_datetime(value: str | None) -> QDateTime | None:
    if not value:
        return None
    for fmt in ("yyyy-MM-dd HH:mm", "yyyy-MM-dd HH:mm:ss"):
        dt_value = QDateTime.fromString(value, fmt)
        if dt_value.isValid():
            return dt_value
    dt_value = QDateTime.fromString(value, Qt.ISODate)
    return dt_value if dt_value.isValid() else None


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

        params = {"lat": lat, "lng": lon, "radius": radius_km}
        if species_name:
            taxon_id = self._inat_taxon_id(species_name)
            params["taxon_id"] = taxon_id
        return "https://www.inaturalist.org/observations?" + urlencode(params)

    def open_inaturalist_map(self, lat, lon, species_name):
        """Open iNaturalist observations map for the selected species."""
        import webbrowser
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
                try:
                    if species_name:
                        taxon_id = self._artskart_taxon_id(species_name)
                        url = self._artskart_link(taxon_id, lat, lon)
                    else:
                        url = self._artskart_base_link(lat, lon)
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

    # Signal emitted when observation is selected (id, display_name, switch_tab)
    observation_selected = Signal(int, str, bool)
    # Signal emitted when an image is selected to open in Measure tab
    image_selected = Signal(int, int, str)  # image_id, observation_id, display_name

    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_observation_id = None
        self.map_helper = MapServiceHelper(self)
        self._ai_suggestions_cache: dict[int, dict] = {}
        self.init_ui()
        self.refresh_observations()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Top buttons
        button_layout = QHBoxLayout()

        new_btn = QPushButton(self.tr("New Observation"))
        new_btn.setObjectName("primaryButton")
        new_btn.clicked.connect(self.create_new_observation)
        button_layout.addWidget(new_btn)

        self.rename_btn = QPushButton(self.tr("Edit"))
        self.rename_btn.setEnabled(False)
        self.rename_btn.clicked.connect(self.edit_observation)
        button_layout.addWidget(self.rename_btn)

        self.delete_btn = QPushButton(self.tr("Delete"))
        self.delete_btn.setEnabled(False)
        self.delete_btn.setStyleSheet(
            "QPushButton { background-color: #e74c3c; color: white; font-weight: bold; }"
            "QPushButton:hover { background-color: #c0392b; }"
            "QPushButton:pressed { background-color: #a93226; }"
        )
        self.delete_btn.clicked.connect(self.delete_selected_observation)
        button_layout.addWidget(self.delete_btn)

        refresh_btn = QPushButton(self.tr("Refresh DB"))
        refresh_btn.clicked.connect(self.refresh_observations)
        button_layout.addWidget(refresh_btn)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(self.tr("Search observations..."))
        self.search_input.textChanged.connect(self.refresh_observations)
        button_layout.addWidget(self.search_input)

        self.needs_id_filter = QCheckBox(self.tr("Needs ID only"))
        self.needs_id_filter.stateChanged.connect(self.refresh_observations)
        button_layout.addWidget(self.needs_id_filter)

        button_layout.addStretch()

        layout.addLayout(button_layout)

        # Splitter for table and detail view
        splitter = QSplitter(Qt.Vertical)

        # Observations table
        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels([
            self.tr("ID"),
            self.tr("Genus"),
            self.tr("Species"),
            self._common_name_column_title(),
            self._spore_stats_column_title(),
            self.tr("Needs ID"),
            self.tr("Date"),
            self.tr("Location"),
            self.tr("Map")
        ])

        # Set column properties
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.Stretch)
        header.setSectionResizeMode(8, QHeaderView.ResizeToContents)

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

        # Image gallery (collapsible) in a resizable splitter.
        self.gallery_widget = ImageGalleryWidget(
            self.tr("Images"),
            self,
            show_delete=True,
            show_badges=True,
            min_height=50,
            default_height=180,
        )
        self.gallery_widget.imageClicked.connect(self._on_gallery_image_clicked)
        self.gallery_widget.deleteRequested.connect(self._confirm_delete_image)

        detail_layout.addWidget(self.gallery_widget)

        splitter.addWidget(self.detail_widget)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([600, 180])

        layout.addWidget(splitter)

    def refresh_observations(self):
        """Load all observations from database."""
        previous_id = self.selected_observation_id
        observations = ObservationDB.get_all_observations()
        self._vernacular_cache = {}
        self._table_vernacular_db = self._get_vernacular_db_for_active_language()
        self._update_table_headers()
        common_name_map = self._build_common_name_map(observations)
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

            # Common name (language-specific)
            common_name = self._lookup_common_name(obs, common_name_map)
            display_name = common_name
            if not display_name:
                genus_raw = (obs.get('genus') or '').strip()
                species_raw = (obs.get('species') or '').strip()
                if genus_raw and species_raw:
                    display_name = f"- ({genus_raw} {species_raw})"
                else:
                    display_name = "-"
            self.table.setItem(row, 3, QTableWidgetItem(display_name))

            # Spore stats (simplified)
            spore_short = self._format_spore_stats_short(obs.get("spore_statistics"))
            self.table.setItem(row, 4, QTableWidgetItem(spore_short or "-"))

            needs_id = not (obs.get('genus') and obs.get('species'))
            needs_item = SortableTableWidgetItem(self.tr("Yes") if needs_id else "")
            needs_item.setData(Qt.UserRole, 1 if needs_id else 0)
            self.table.setItem(row, 5, needs_item)

            # Date
            self.table.setItem(row, 6, QTableWidgetItem(obs['date'] or '-'))

            # Location
            self.table.setItem(row, 7, QTableWidgetItem(obs['location'] or '-'))

            # Map link
            lat = obs.get('gps_latitude')
            lon = obs.get('gps_longitude')
            has_coords = lat is not None and lon is not None
            map_item = SortableTableWidgetItem("" if has_coords else "-")
            map_item.setData(Qt.UserRole, 1 if has_coords else 0)
            map_item.setFlags(map_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 8, map_item)
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
                self.table.setCellWidget(row, 8, map_label)

        # Clear detail view
        self.rename_btn.setEnabled(False)
        self.delete_btn.setEnabled(False)
        self.gallery_widget.clear()
        self.selected_observation_id = None

        if previous_id:
            for row, obs in enumerate(observations):
                if obs['id'] == previous_id:
                    self.table.selectRow(row)
                    self.selected_observation_id = previous_id
                    self.on_selection_changed()
                    break

    def _get_vernacular_db_for_active_language(self):
        lang = normalize_vernacular_language(SettingsDB.get_setting("vernacular_language", "no"))
        db_path = resolve_vernacular_db_path(lang)
        if not db_path:
            return None
        return VernacularDB(db_path, language_code=lang)

    def _build_common_name_map(self, observations: list[dict]) -> dict[tuple[str, str], str | None]:
        """Pre-build a cache of all common names for the observations."""
        if not self._table_vernacular_db:
            return {}
        
        # Collect all unique genus+species combinations from observations
        taxa = set()
        for obs in observations:
            genus = self._normalize_taxon_text(obs.get("genus"))
            species = self._normalize_taxon_text(obs.get("species"))
            if not genus or not species:
                guess = self._normalize_taxon_text(obs.get("species_guess"))
                parts = guess.split() if guess else []
                if len(parts) >= 2:
                    genus, species = parts[0], parts[1]
            if genus and species:
                taxa.add((genus, species))
        
        if not taxa:
            return {}
        
        # Fetch all common names in one database session
        name_map: dict[tuple[str, str], str | None] = {}
        for genus, species in taxa:
            try:
                name_map[(genus, species)] = self._table_vernacular_db.vernacular_from_taxon(genus, species)
            except Exception:
                name_map[(genus, species)] = None
        
        return name_map

    def get_ai_suggestions_for_observation(self, obs_id: int) -> dict | None:
        """Return cached AI suggestion state for the given observation id."""
        return self._ai_suggestions_cache.get(obs_id)

    def _remap_ai_state_to_images(
        self,
        ai_state: dict | None,
        image_results: list[ImageImportResult],
    ) -> dict | None:
        if not ai_state:
            return None
        predictions = ai_state.get("predictions") or {}
        selected = ai_state.get("selected") or {}
        prev_paths = ai_state.get("paths") or []
        if not isinstance(predictions, dict) or not isinstance(selected, dict):
            return None
        new_paths = [item.filepath for item in image_results]
        new_index_by_path = {path: idx for idx, path in enumerate(new_paths) if path}
        new_predictions: dict[int, list] = {}
        new_selected: dict[int, dict] = {}
        for old_idx, preds in predictions.items():
            try:
                old_index = int(old_idx)
            except (TypeError, ValueError):
                continue
            old_path = prev_paths[old_index] if 0 <= old_index < len(prev_paths) else None
            new_index = new_index_by_path.get(old_path)
            if new_index is not None:
                new_predictions[new_index] = preds
        for old_idx, sel in selected.items():
            try:
                old_index = int(old_idx)
            except (TypeError, ValueError):
                continue
            old_path = prev_paths[old_index] if 0 <= old_index < len(prev_paths) else None
            new_index = new_index_by_path.get(old_path)
            if new_index is not None:
                new_selected[new_index] = sel
        selected_index = ai_state.get("selected_index")
        new_selected_index = None
        if selected_index is not None:
            try:
                old_index = int(selected_index)
            except (TypeError, ValueError):
                old_index = None
            if old_index is not None and 0 <= old_index < len(prev_paths):
                old_path = prev_paths[old_index]
                new_selected_index = new_index_by_path.get(old_path)
        return {
            "predictions": new_predictions,
            "selected": new_selected,
            "selected_index": new_selected_index,
            "paths": new_paths,
        }

    def _lookup_common_name(self, obs: dict, name_map: dict[tuple[str, str], str | None]) -> str | None:
        """Look up common name from the pre-built cache."""
        stored_name = self._normalize_taxon_text(obs.get("common_name"))
        if stored_name:
            return stored_name
        genus = self._normalize_taxon_text(obs.get("genus"))
        species = self._normalize_taxon_text(obs.get("species"))
        
        if not genus or not species:
            guess = self._normalize_taxon_text(obs.get("species_guess"))
            parts = guess.split() if guess else []
            if len(parts) >= 2:
                genus, species = parts[0], parts[1]
        
        if not genus or not species:
            return None
        
        # Use the pre-built cache - no database access needed here!
        return name_map.get((genus, species))

    def _normalize_taxon_text(self, value: str | None) -> str:
        if not value:
            return ""
        try:
            import unicodedata
            text = unicodedata.normalize("NFKC", str(value))
        except Exception:
            text = str(value)
        text = text.replace("\u00a0", " ")
        text = text.strip()
        if text.startswith("?"):
            text = text.lstrip("?").strip()
        return " ".join(text.split())

    def _common_name_column_title(self) -> str:
        lang = normalize_vernacular_language(SettingsDB.get_setting("vernacular_language", "no"))
        base = self.tr("Common name")
        return common_name_display_label(lang, base)

    def _spore_stats_column_title(self) -> str:
        lang = (SettingsDB.get_setting("ui_language", "en") or "en").lower()
        return "Sporer" if lang.startswith("nb") or lang.startswith("no") else "Spores"

    def _update_table_headers(self) -> None:
        if not hasattr(self, "table"):
            return
        item = self.table.horizontalHeaderItem(3)
        if item:
            item.setText(self._common_name_column_title())
        spore_item = self.table.horizontalHeaderItem(4)
        if spore_item:
            spore_item.setText(self._spore_stats_column_title())

    def _format_spore_stats_short(self, stats: str | None) -> str | None:
        if not stats:
            return None
        text = str(stats)
        length_seg = None
        width_seg = None
        match_len = re.search(r"Spores?:\\s*([^,]+?)\\s*um\\s*x", text, re.IGNORECASE)
        match_wid = re.search(r"\\s*x\\s*([^,]+?)\\s*um", text, re.IGNORECASE)
        if match_len:
            length_seg = match_len.group(1)
        if match_wid:
            width_seg = match_wid.group(1)

        def _extract_p05_p95(segment: str | None) -> tuple[str | None, str | None]:
            if not segment:
                return None, None
            nums = re.findall(r"[0-9]+(?:\\.[0-9]+)?", segment)
            if len(nums) >= 3:
                return nums[1], nums[2]
            if len(nums) == 2:
                return nums[0], nums[1]
            return None, None

        l5, l95 = _extract_p05_p95(length_seg)
        w5, w95 = _extract_p05_p95(width_seg)
        if not l5 or not l95 or not w5 or not w95:
            return None

        qm_match = re.search(r"Qm\\s*=\\s*([0-9]+(?:\\.[0-9]+)?)", text)
        qm = qm_match.group(1) if qm_match else None
        qm_short = None
        if qm:
            try:
                qm_short = f"{float(qm):.1f}"
            except ValueError:
                qm_short = qm

        base = f"{l5}-{l95} x {w5}-{w95}"
        if qm_short:
            return f"{base} Q={qm_short}"
        return base

    def apply_vernacular_language_change(self) -> None:
        self._table_vernacular_db = self._get_vernacular_db_for_active_language()
        self._vernacular_cache = {}
        self._update_table_headers()
        self.refresh_observations()

    def _question_yes_no(self, title, text, default_yes=False):
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

    def _confirm_delete_image(self, image_id):
        """Confirm and delete an image (and measurements if present)."""
        measurements = self._get_measurements_for_image(image_id)
        if measurements:
            prompt = self.tr("Delete image and associated measurements?")
        else:
            prompt = self.tr("Delete image?")

        confirmed = self._question_yes_no(
            self.tr("Confirm Delete"),
            prompt,
            default_yes=False
        )
        if confirmed:
            ImageDB.delete_image(image_id)
            self.refresh_observations()

    def _on_gallery_image_clicked(self, image_id, _filepath):
        """Handle thumbnail click - emit signal to open in Measure tab."""
        if self.selected_observation_id and image_id:
            obs = ObservationDB.get_observation(self.selected_observation_id)
            if obs:
                genus = obs.get('genus') or ''
                species = obs.get('species') or obs.get('species_guess') or 'sp.'
                display_name = f"{genus} {species} {obs['date'] or ''}".strip()
                self.image_selected.emit(image_id, self.selected_observation_id, display_name)

    def on_selection_changed(self):
        """Update detail view when selection changes."""
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            self.rename_btn.setEnabled(False)
            self.delete_btn.setEnabled(False)
            self.gallery_widget.clear()
            self.selected_observation_id = None
            return

        row = selected_rows[0].row()
        obs_id = int(self.table.item(row, 0).text())
        self.selected_observation_id = obs_id

        # Get observation details
        observations = ObservationDB.get_all_observations()
        obs = next((o for o in observations if o['id'] == obs_id), None)

        if obs:
            self.rename_btn.setEnabled(True)
            self.delete_btn.setEnabled(True)

            # Populate image browser
            self.gallery_widget.set_observation_id(obs_id)
            self.set_selected_as_active(switch_tab=False)

    def on_row_double_clicked(self, item):
        """Double-click to open edit dialog for the observation."""
        self.edit_observation()

    def set_selected_as_active(self, switch_tab=True):
        """Set the selected observation as active, optionally switching to Measure tab."""
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return

        row = selected_rows[0].row()
        obs_id = int(self.table.item(row, 0).text())
        genus = self.table.item(row, 1).text()
        species = self.table.item(row, 2).text()
        date = self.table.item(row, 6).text()
        display_name = f"{genus} {species} {date}"

        # Emit signal to set as active observation
        self.observation_selected.emit(obs_id, display_name, switch_tab)

    def get_selected_observation(self):
        """Return (observation_id, display_name) for current selection."""
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return None
        row = selected_rows[0].row()
        obs_id = int(self.table.item(row, 0).text())
        genus = self.table.item(row, 1).text()
        species = self.table.item(row, 2).text()
        date = self.table.item(row, 6).text()
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

        obs_dt = _parse_observation_datetime(observation.get("date"))
        obs_lat = observation.get("gps_latitude")
        obs_lon = observation.get("gps_longitude")

        existing_images = ImageDB.get_images_for_observation(obs_id)
        image_results = self._build_import_results_from_images(existing_images)

        ai_taxon = None
        ai_state = self._remap_ai_state_to_images(
            self._ai_suggestions_cache.get(obs_id),
            image_results,
        )
        while True:
            dialog = ObservationDetailsDialog(
                self,
                observation=observation,
                image_results=image_results,
                allow_edit_images=True,
                suggested_taxon=ai_taxon,
                ai_state=ai_state,
            )
            if dialog.exec():
                ai_state = dialog.get_ai_state()
                self._ai_suggestions_cache[obs_id] = ai_state
                data = dialog.get_data()
                ObservationDB.update_observation(
                    obs_id,
                    genus=data.get('genus'),
                    species=data.get('species'),
                    common_name=data.get('common_name'),
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

                self._apply_import_results_to_observation(
                    obs_id,
                    image_results,
                    existing_images=existing_images
                )

                self.refresh_observations()
                for row, obs in enumerate(ObservationDB.get_all_observations()):
                    if obs['id'] == obs_id:
                        self.table.selectRow(row)
                        self.selected_observation_id = obs_id
                        self.on_selection_changed()
                        break
                return

            if dialog.request_edit_images:
                ai_state = dialog.get_ai_state()
                self._ai_suggestions_cache[obs_id] = ai_state
                image_dialog = ImageImportDialog(
                    self,
                    import_results=image_results,
                    observation_datetime=obs_dt,
                    observation_lat=obs_lat,
                    observation_lon=obs_lon,
                )
                if image_dialog.exec():
                    image_results = image_dialog.import_results
                    ai_taxon = image_dialog.get_ai_selected_taxon()
                    ai_state = self._remap_ai_state_to_images(ai_state, image_results)
                continue
            ai_state = dialog.get_ai_state()
            self._ai_suggestions_cache[obs_id] = ai_state
            return

    def create_new_observation(self):
        """Show dialog to create new observation."""
        image_results: list[ImageImportResult] = []
        primary_index = None
        while True:
            image_dialog = ImageImportDialog(self, import_results=image_results or None)
            if not image_dialog.exec():
                return
            image_results = image_dialog.import_results
            primary_index = image_dialog.primary_index

            ai_taxon = image_dialog.get_ai_selected_taxon()
            dialog = ObservationDetailsDialog(
                self,
                image_results=image_results,
                primary_index=primary_index,
                allow_edit_images=True,
                suggested_taxon=ai_taxon,
            )
            if dialog.exec():
                obs_data = dialog.get_data()
                profile = SettingsDB.get_profile()
                author = profile.get("name")
                if author:
                    obs_data["author"] = author

                obs_id = ObservationDB.create_observation(**obs_data)
                self._apply_import_results_to_observation(obs_id, image_results)

                self.refresh_observations()
                for row, obs in enumerate(ObservationDB.get_all_observations()):
                    if obs['id'] == obs_id:
                        self.table.selectRow(row)
                        self.selected_observation_id = obs_id
                        self.on_selection_changed()
                        break
                return

            if dialog.request_edit_images:
                continue
            return

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
        confirmed = self._question_yes_no(
            self.tr("Confirm Delete"),
            self.tr("Delete observation '{species}'?\n\nThis will also delete all associated images and measurements.").format(
                species=species
            ),
            default_yes=False
        )
        if confirmed:
            ObservationDB.delete_observation(obs_id)
            self.refresh_observations()

    def _build_import_results_from_images(self, images: list[dict]) -> list[ImageImportResult]:
        results: list[ImageImportResult] = []
        for img in images:
            if not img:
                continue
            meta = {}
            filepath = img.get("filepath")
            if filepath:
                meta = get_image_metadata(filepath)
            dt = meta.get("datetime")
            captured_at = QDateTime(dt) if dt else None
            exif_has_gps = meta.get("latitude") is not None or meta.get("longitude") is not None
            crop_x1 = img.get("ai_crop_x1")
            crop_y1 = img.get("ai_crop_y1")
            crop_x2 = img.get("ai_crop_x2")
            crop_y2 = img.get("ai_crop_y2")
            ai_crop_box = None
            if all(v is not None for v in (crop_x1, crop_y1, crop_x2, crop_y2)):
                ai_crop_box = (float(crop_x1), float(crop_y1), float(crop_x2), float(crop_y2))
            crop_w = img.get("ai_crop_source_w")
            crop_h = img.get("ai_crop_source_h")
            ai_crop_source_size = None
            if crop_w is not None and crop_h is not None:
                ai_crop_source_size = (int(crop_w), int(crop_h))
            gps_source = bool(img.get("gps_source")) if img.get("gps_source") is not None else False
            scale_value = img.get("scale_microns_per_pixel")
            objective_name = img.get("objective_name")
            custom_scale = None
            if scale_value is not None and (objective_name == "Custom" or not objective_name):
                try:
                    custom_scale = float(scale_value)
                except (TypeError, ValueError):
                    custom_scale = None
            results.append(
                ImageImportResult(
                    filepath=filepath,
                    image_id=img.get("id"),
                    image_type=img.get("image_type") or "field",
                    objective=objective_name if objective_name != "Custom" else None,
                    custom_scale=custom_scale,
                    contrast=img.get("contrast"),
                    mount_medium=img.get("mount_medium"),
                    sample_type=img.get("sample_type"),
                    captured_at=captured_at,
                    exif_has_gps=exif_has_gps,
                    ai_crop_box=ai_crop_box,
                    ai_crop_source_size=ai_crop_source_size,
                    gps_source=gps_source,
                )
            )
        return results

    def _apply_import_results_to_observation(
        self,
        obs_id: int,
        results: list[ImageImportResult],
        existing_images: list[dict] | None = None,
    ) -> None:
        objectives = load_objectives()
        output_dir = get_images_dir() / "imports"
        output_dir.mkdir(parents=True, exist_ok=True)

        existing_ids = {img.get("id") for img in (existing_images or []) if img.get("id")}
        result_ids = {res.image_id for res in results if res.image_id}
        removed_ids = existing_ids - result_ids
        for image_id in removed_ids:
            ImageDB.delete_image(image_id)

        for result in results:
            image_type = result.image_type or "field"
            objective_key = result.objective
            contrast = result.contrast
            mount_medium = result.mount_medium
            sample_type = result.sample_type

            scale = None
            objective_name = None
            if image_type == "microscope":
                if result.custom_scale:
                    scale = float(result.custom_scale)
                    objective_name = "Custom"
                elif objective_key and objective_key in objectives:
                    scale = float(objectives[objective_key]["microns_per_pixel"])
                    objective_name = objective_key

            if result.image_id:
                ImageDB.update_image(
                    result.image_id,
                    image_type=image_type,
                    objective_name=objective_name,
                    scale=scale,
                    contrast=contrast,
                    mount_medium=mount_medium,
                    sample_type=sample_type,
                    ai_crop_box=result.ai_crop_box,
                    ai_crop_source_size=result.ai_crop_source_size,
                    gps_source=result.gps_source,
                )
                continue

            filepath = result.filepath
            if not filepath:
                continue
            final_path = maybe_convert_heic(filepath, output_dir)
            if final_path is None:
                continue
            # Get the active calibration_id for this objective
            calibration_id = None
            if objective_name:
                calibration_id = CalibrationDB.get_active_calibration_id(objective_name)
            image_id = ImageDB.add_image(
                observation_id=obs_id,
                filepath=final_path,
                image_type=image_type,
                scale=scale,
                objective_name=objective_name,
                contrast=contrast,
                mount_medium=mount_medium,
                sample_type=sample_type,
                calibration_id=calibration_id,
                ai_crop_box=result.ai_crop_box,
                ai_crop_source_size=result.ai_crop_source_size,
                gps_source=result.gps_source,
            )

            stored_path = final_path
            try:
                image_data = ImageDB.get_image(image_id)
                stored_path = image_data.get("filepath") if image_data else final_path
                generate_all_sizes(stored_path, image_id)
            except Exception as e:
                print(f"Warning: Could not generate thumbnails for {final_path}: {e}")
            cleanup_import_temp_file(filepath, final_path, stored_path, output_dir)


class ObservationDetailsDialog(QDialog):
    """Dialog for creating or editing an observation after image import."""

    def __init__(
        self,
        parent=None,
        observation=None,
        image_results: list[ImageImportResult] | None = None,
        primary_index: int | None = None,
        allow_edit_images: bool = False,
        suggested_taxon: dict | None = None,
        ai_state: dict | None = None,
    ):
        super().__init__(parent)
        self.observation = observation
        self.edit_mode = observation is not None
        self.image_results = image_results or []
        self.primary_index = primary_index
        self.allow_edit_images = allow_edit_images
        self.request_edit_images = False
        self.suggested_taxon = suggested_taxon
        self.map_helper = MapServiceHelper(self)
        self.setWindowTitle("Edit Observation" if self.edit_mode else "New Observation")
        self.setModal(True)
        self.setMinimumSize(900, 720)
        self._observation_datetime = _parse_observation_datetime(
            observation.get("date") if observation else None
        )
        self.image_files = []
        self.image_metadata = []
        self.image_settings = []
        self.selected_image_index = -1
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
        self.vernacular_db = None
        self._vernacular_model = None
        self._vernacular_completer = None
        self._genus_model = None
        self._genus_completer = None
        self._species_model = None
        self._species_completer = None
        self._suppress_taxon_autofill = False
        self._last_genus = ""
        self._last_species = ""
        self._ai_predictions_by_index: dict[int, list[dict]] = {}
        self._ai_selected_by_index: dict[int, dict] = {}
        self._ai_selected_taxon: dict | None = None
        self._ai_thread = None
        self._ai_selected_index: int | None = None
        self._apply_ai_state(ai_state)
        self.init_ui()
        if self.edit_mode:
            self._load_existing_observation()
        else:
            self._apply_primary_metadata()
        self._apply_suggested_taxon()
        self._sync_taxon_cache()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)

        # ===== OBSERVATION DETAILS SECTION =====
        details_group = QGroupBox(self.tr("Observation Details"))
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
        self.datetime_input.setMaximumWidth(250)
        datetime_layout.addWidget(self.datetime_input)
        datetime_layout.addStretch()
        details_layout.addRow(self.tr("Date & time:"), datetime_container)

        # Location (text)
        self.location_input = QLineEdit()
        self.location_input.setPlaceholderText("e.g., Bymarka, Trondheim")
        details_layout.addRow(self.tr("Location:"), self.location_input)

        gps_container = QWidget()
        gps_container_layout = QVBoxLayout(gps_container)
        gps_container_layout.setContentsMargins(0, 0, 0, 0)
        gps_container_layout.setSpacing(2)

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
        self.map_btn = QPushButton(self.tr("  Map  "))
        self.map_btn.setToolTip("Open location in Google Maps")
        self.map_btn.setMinimumWidth(70)
        self.map_btn.clicked.connect(self.open_map)
        self.map_btn.setEnabled(False)  # Disabled until GPS coordinates are set
        gps_layout.addWidget(self.map_btn)

        # Enable map button when coordinates are manually changed
        self.lat_input.valueChanged.connect(self._update_map_button)
        self.lon_input.valueChanged.connect(self._update_map_button)

        gps_layout.addStretch()
        gps_container_layout.addLayout(gps_layout)

        # GPS info label (shows source of coordinates)
        self.gps_info_label = QLabel("")
        self.gps_info_label.setStyleSheet("color: #7f8c8d; font-size: 9pt;")
        gps_container_layout.addWidget(self.gps_info_label)

        details_layout.addRow("GPS:", gps_container)

        # Habitat
        self.habitat_input = QLineEdit()
        self.habitat_input.setPlaceholderText(self.tr("e.g., Spruce forest"))
        details_layout.addRow(self.tr("Habitat:"), self.habitat_input)

        # Notes
        self.notes_input = QTextEdit()
        self.notes_input.setMaximumHeight(60)
        self.notes_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.notes_input.setFrameStyle(QFrame.StyledPanel | QFrame.Sunken)
        self.notes_input.setStyleSheet("QTextEdit { border: 1px solid #bdc3c7; border-radius: 3px; }")
        self.notes_input.setPlaceholderText(self.tr("Any additional notes..."))
        details_layout.addRow(self.tr("Notes:"), self.notes_input)

        details_group.setLayout(details_layout)
        main_layout.addWidget(details_group)

        # ===== TAXONOMY SECTION =====
        taxonomy_group = QGroupBox(self.tr("Taxonomy"))
        taxonomy_layout = QHBoxLayout(taxonomy_group)
        taxonomy_layout.setContentsMargins(8, 8, 8, 8)
        taxonomy_layout.setSpacing(8)

        taxonomy_split = QSplitter(Qt.Horizontal)
        taxonomy_split.setChildrenCollapsible(False)

        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        # Taxonomy tab widget (Species vs Unknown)
        self.taxonomy_tabs = QTabWidget()
        self.taxonomy_tabs.setMinimumHeight(120)
        self.taxonomy_tabs.currentChanged.connect(self.on_taxonomy_tab_changed)

        # Tab 1: Identified (vernacular + genus/species)
        identified_tab = QWidget()
        identified_layout = QVBoxLayout(identified_tab)
        identified_layout.setContentsMargins(8, 8, 8, 8)
        identified_layout.setSpacing(6)

        vern_row = QHBoxLayout()
        self.vernacular_label = QLabel(self._vernacular_label())
        vern_row.addWidget(self.vernacular_label)
        self.vernacular_input = QLineEdit()
        self.vernacular_input.setPlaceholderText(self._vernacular_placeholder())
        vern_row.addWidget(self.vernacular_input, 1)
        identified_layout.addLayout(vern_row)

        genus_row = QHBoxLayout()
        genus_row.addWidget(QLabel("Genus:"))
        self.genus_input = QLineEdit()
        self.genus_input.setPlaceholderText("e.g., Flammulina")
        genus_row.addWidget(self.genus_input, 1)
        identified_layout.addLayout(genus_row)

        species_row = QHBoxLayout()
        species_row.addWidget(QLabel("Species:"))
        self.species_input = QLineEdit()
        self.species_input.setPlaceholderText("e.g., velutipes")
        species_row.addWidget(self.species_input, 1)
        identified_layout.addLayout(species_row)

        uncertain_row = QHBoxLayout()
        self.uncertain_checkbox = QCheckBox(self.tr("Uncertain"))
        self.uncertain_checkbox.setToolTip(
            "Check this if you're not confident about the identification"
        )
        uncertain_row.addWidget(self.uncertain_checkbox)
        uncertain_row.addStretch()
        identified_layout.addLayout(uncertain_row)

        self.taxonomy_tabs.addTab(identified_tab, self.tr("Species"))

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

        self.taxonomy_tabs.addTab(unknown_tab, self.tr("Unknown"))

        left_layout.addWidget(self.taxonomy_tabs)
        taxonomy_split.addWidget(left_container)

        self.ai_group = self._build_ai_suggestions_group()
        taxonomy_split.addWidget(self.ai_group)
        taxonomy_split.setStretchFactor(0, 7)
        taxonomy_split.setStretchFactor(1, 3)
        taxonomy_split.setSizes([700, 300])

        taxonomy_layout.addWidget(taxonomy_split)
        main_layout.addWidget(taxonomy_group)

        # ===== IMAGES SUMMARY (BOTTOM) =====
        self.image_gallery = ImageGalleryWidget(
            self.tr("Images"),
            self,
            show_delete=False,
            show_badges=False,
            min_height=60,
            default_height=160,
            thumbnail_size=110,
        )
        self._gps_source_index = self._resolve_gps_source_index()
        items = []
        for idx, item in enumerate(self.image_results):
            thumb_preview = None
            if item.image_id:
                thumb_preview = get_thumbnail_path(item.image_id, "224x224")
                if thumb_preview and not Path(thumb_preview).exists():
                    thumb_preview = None
            gps_match = idx == self._gps_source_index and item.exif_has_gps
            items.append(
                {
                    "id": item.image_id,
                    "filepath": item.filepath,
                    "preview_path": thumb_preview or item.preview_path or item.filepath,
                    "image_number": idx + 1,
                    "crop_box": item.ai_crop_box,
                    "crop_source_size": item.ai_crop_source_size,
                    "gps_tag_text": self.tr("GPS") if gps_match else None,
                    "gps_tag_highlight": gps_match,
                }
            )
        self.image_gallery.set_items(items)
        self.image_gallery.imageClicked.connect(self._on_gallery_image_clicked)
        self.image_gallery.imageSelected.connect(self._on_gallery_image_clicked)
        main_layout.addWidget(self.image_gallery)

        # ===== BOTTOM BUTTONS =====
        bottom_buttons = QHBoxLayout()
        if self.allow_edit_images:
            edit_label = self.tr("Edit Images") if self.edit_mode else self.tr("Back to Images")
            edit_btn = QPushButton(edit_label)
            edit_btn.setMinimumHeight(35)
            edit_btn.clicked.connect(self._on_edit_images_clicked)
            bottom_buttons.addWidget(edit_btn)
        bottom_buttons.addStretch()
        cancel_btn = QPushButton(self.tr("Cancel"))
        cancel_btn.setMinimumHeight(35)
        cancel_btn.clicked.connect(self.reject)
        bottom_buttons.addWidget(cancel_btn)
        create_btn = QPushButton(
            self.tr("Save Observation") if self.edit_mode else self.tr("Create Observation")
        )
        create_btn.setObjectName("primaryButton")
        create_btn.setMinimumHeight(35)
        create_btn.clicked.connect(self.accept)
        bottom_buttons.addWidget(create_btn)
        main_layout.addLayout(bottom_buttons)

        self._setup_vernacular_autocomplete()

        self.on_taxonomy_tab_changed(self.taxonomy_tabs.currentIndex())
        self._select_initial_ai_image()
        self._update_ai_controls_state()
        self._update_ai_table()
        self._update_datetime_width()

    def _build_ai_suggestions_group(self) -> QGroupBox:
        ai_group = QGroupBox(self.tr("AI suggestions"))
        ai_layout = QVBoxLayout(ai_group)
        ai_layout.setContentsMargins(6, 6, 6, 6)

        ai_controls = QHBoxLayout()
        self.ai_guess_btn = QPushButton(self.tr("Guess"))
        self.ai_guess_btn.setToolTip(self.tr("Send image to Artsorakelet"))
        self.ai_guess_btn.clicked.connect(self._on_ai_guess_clicked)
        self.ai_crop_btn = QPushButton(self.tr("Crop"))
        self.ai_crop_btn.setToolTip(self.tr("Crop not available yet"))
        self.ai_crop_btn.clicked.connect(self._on_ai_crop_clicked)
        self.ai_guess_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.ai_crop_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        ai_controls.addWidget(self.ai_guess_btn)
        ai_controls.addWidget(self.ai_crop_btn)
        ai_controls.setStretch(0, 1)
        ai_controls.setStretch(1, 1)
        ai_layout.addLayout(ai_controls)

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

        self.ai_copy_btn = QPushButton(self.tr("Copy to taxonomy"))
        self.ai_copy_btn.clicked.connect(self._on_ai_copy_to_taxonomy)
        self.ai_copy_btn.setVisible(False)
        ai_layout.addWidget(self.ai_copy_btn)

        return ai_group

    def _apply_ai_state(self, ai_state: dict | None) -> None:
        if not ai_state:
            return
        predictions = ai_state.get("predictions")
        selected = ai_state.get("selected")
        selected_index = ai_state.get("selected_index")
        if isinstance(predictions, dict):
            remapped: dict[int, list] = {}
            for key, value in predictions.items():
                try:
                    remapped[int(key)] = value
                except (TypeError, ValueError):
                    continue
            self._ai_predictions_by_index = remapped
        if isinstance(selected, dict):
            remapped_selected: dict[int, dict] = {}
            for key, value in selected.items():
                try:
                    remapped_selected[int(key)] = value
                except (TypeError, ValueError):
                    continue
            self._ai_selected_by_index = remapped_selected
        if isinstance(selected_index, int):
            self._ai_selected_index = selected_index

    def get_ai_state(self) -> dict:
        return {
            "predictions": dict(self._ai_predictions_by_index),
            "selected": dict(self._ai_selected_by_index),
            "selected_index": self._ai_selected_index,
            "paths": [item.filepath for item in self.image_results],
        }

    def _select_initial_ai_image(self) -> None:
        index = self._current_ai_index()
        if index is None:
            return
        self._ai_selected_index = index
        if 0 <= index < len(self.image_results):
            path = self.image_results[index].filepath
            if path:
                self.image_gallery.select_paths([path])
        self._update_ai_controls_state()
        self._update_ai_table()

    def _current_ai_index(self) -> int | None:
        if self._ai_selected_index is not None:
            if 0 <= self._ai_selected_index < len(self.image_results):
                return self._ai_selected_index
            self._ai_selected_index = None
        if self.primary_index is not None and 0 <= self.primary_index < len(self.image_results):
            return self.primary_index
        if self.image_results:
            return 0
        return None

    def _on_gallery_image_clicked(self, _image_id, path: str) -> None:
        if not path:
            return
        for idx, item in enumerate(self.image_results):
            if item.filepath == path:
                self._ai_selected_index = idx
                self.image_gallery.select_paths([path])
                self._update_ai_controls_state()
                self._update_ai_table()
                return

    def _update_ai_controls_state(self) -> None:
        if not hasattr(self, "ai_guess_btn"):
            return
        index = self._current_ai_index()
        enable = False
        if index is not None and 0 <= index < len(self.image_results):
            image_type = (self.image_results[index].image_type or "field").strip().lower()
            enable = image_type == "field"
        if self._ai_thread is not None:
            enable = False
        self.ai_guess_btn.setEnabled(enable)
        self.ai_crop_btn.setEnabled(enable)

    def _update_ai_table(self) -> None:
        if not hasattr(self, "ai_table"):
            return
        index = self._current_ai_index()
        self.ai_table.setRowCount(0)
        if index is None:
            self._set_ai_copy_visible(False)
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
            self._set_ai_copy_visible(False)

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

    def _on_ai_selection_changed(self) -> None:
        index = self._current_ai_index()
        if index is None:
            return
        selected_items = self.ai_table.selectedItems()
        if not selected_items:
            self._ai_selected_taxon = None
            self._set_ai_status(None)
            self._set_ai_copy_visible(False)
            return
        row_item = self.ai_table.item(self.ai_table.currentRow(), 0)
        if not row_item:
            return
        pred = row_item.data(Qt.UserRole) or {}
        self._ai_selected_by_index[index] = pred
        self._ai_selected_taxon = pred.get("taxon") or {}
        self._set_ai_status(None)
        self._set_ai_copy_visible(True)

    def _set_ai_status(self, text: str | None, color: str = "#7f8c8d") -> None:
        if not hasattr(self, "ai_status_label"):
            return
        if not text:
            self.ai_status_label.setText("")
            return
        self.ai_status_label.setText(text)
        self.ai_status_label.setStyleSheet(f"color: {color}; font-size: 9pt;")
        self._set_ai_copy_visible(False)

    def _set_ai_copy_visible(self, visible: bool) -> None:
        if hasattr(self, "ai_copy_btn"):
            self.ai_copy_btn.setVisible(bool(visible))

    def _extract_genus_species_from_taxon(self, taxon: dict) -> tuple[str | None, str | None]:
        if not isinstance(taxon, dict):
            return None, None
        genus = taxon.get("genus") or taxon.get("genusName") or taxon.get("genus_name")
        species = (
            taxon.get("species")
            or taxon.get("specificEpithet")
            or taxon.get("specific_epithet")
        )
        if genus and species:
            return str(genus).strip(), str(species).strip()
        sci = taxon.get("scientificName") or taxon.get("scientific_name") or taxon.get("name")
        if sci and isinstance(sci, str):
            parts = sci.strip().split()
            if len(parts) >= 2:
                return parts[0], parts[1]
        return None, None

    def _on_ai_copy_to_taxonomy(self) -> None:
        taxon = self._ai_selected_taxon or {}
        genus, species = self._extract_genus_species_from_taxon(taxon)
        if not genus or not species:
            self._set_ai_status(self.tr("Could not parse genus/species from AI suggestion."), "#e67e22")
            return
        if hasattr(self, "taxonomy_tabs"):
            self.taxonomy_tabs.setCurrentIndex(0)
        if hasattr(self, "unknown_checkbox") and self.unknown_checkbox.isChecked():
            self.unknown_checkbox.setChecked(False)
        self._suppress_taxon_autofill = True
        if hasattr(self, "genus_input"):
            self.genus_input.setText(genus)
        if hasattr(self, "species_input"):
            self.species_input.setText(species)
        if hasattr(self, "vernacular_input"):
            self.vernacular_input.clear()
        self._suppress_taxon_autofill = False
        if self.vernacular_db:
            self._update_vernacular_suggestions_for_taxon()
            self._maybe_set_vernacular_from_taxon()
        else:
            vernacular = self._preferred_vernacular_from_taxon(taxon)
            if vernacular and hasattr(self, "vernacular_input") and not self.vernacular_input.text().strip():
                self.vernacular_input.setText(vernacular)
        self._set_ai_status(self.tr("Copied to taxonomy."), "#27ae60")

    def _on_ai_crop_clicked(self) -> None:
        return

    def _on_ai_guess_clicked(self) -> None:
        try:
            index = self._current_ai_index()
            if index is None or index < 0 or index >= len(self.image_results):
                return
            result = self.image_results[index]
            image_type = (result.image_type or "field").strip().lower()
            if image_type != "field":
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
            crop_box = getattr(result, "ai_crop_box", None)
            self._ai_thread = AIGuessWorker(index, image_path, crop_box, temp_dir, max_dim=1600, parent=self)
            self._ai_thread.resultReady.connect(self._on_ai_guess_finished)
            self._ai_thread.error.connect(self._on_ai_guess_error)
            self._ai_thread.finished.connect(self._ai_thread.deleteLater)
            self._ai_thread.finished.connect(self._on_ai_thread_finished)
            self._ai_thread.start()
        except Exception as exc:
            self._set_ai_status(self.tr("AI guess failed: {message}").format(message=str(exc)), "#e74c3c")
            if hasattr(self, "ai_guess_btn"):
                self.ai_guess_btn.setEnabled(True)
                self.ai_guess_btn.setText(self.tr("Guess"))

    def _on_ai_thread_finished(self) -> None:
        self._ai_thread = None
        if hasattr(self, "ai_guess_btn"):
            self.ai_guess_btn.setText(self.tr("Guess"))
        self._update_ai_controls_state()

    def closeEvent(self, event):
        if self._ai_thread is not None:
            try:
                self._ai_thread.quit()
                self._ai_thread.wait(1000)
            except Exception:
                pass
        super().closeEvent(event)

    def _on_ai_guess_finished(
        self,
        index: int,
        predictions: list,
        _box: object,
        _warnings: object,
        _temp_path: str,
    ) -> None:
        self._ai_predictions_by_index[index] = predictions or []
        self._update_ai_table()
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

    def _on_edit_images_clicked(self):
        self.request_edit_images = True
        self.reject()

    def _apply_primary_metadata(self):
        if not self.image_results:
            return
        result = self._primary_result()
        if not result:
            return
        if result.captured_at:
            self.datetime_input.setDateTime(result.captured_at)
        if result.gps_latitude is not None:
            self.lat_input.setValue(result.gps_latitude)
        if result.gps_longitude is not None:
            self.lon_input.setValue(result.gps_longitude)
        source_name = ""
        if getattr(self, "_gps_source_index", None) is not None:
            idx = self._gps_source_index
            if idx is not None and 0 <= idx < len(self.image_results):
                source_name = Path(self.image_results[idx].filepath).name if self.image_results[idx].filepath else ""
        if not source_name:
            source_name = Path(result.filepath).name if result.filepath else ""
        if result.gps_latitude is not None or result.gps_longitude is not None:
            self.gps_info_label.setText(
                self.tr("From: {source}").format(source=source_name) if source_name else ""
            )
        else:
            self.gps_info_label.setText("")
        self._update_map_button()

    def _apply_suggested_taxon(self):
        if not self.suggested_taxon:
            return
        if not hasattr(self, "genus_input") or not hasattr(self, "species_input"):
            return
        if self.genus_input.text().strip() or self.species_input.text().strip():
            return
        genus = self.suggested_taxon.get("genus")
        species = self.suggested_taxon.get("species")
        if not genus or not species:
            return
        self._suppress_taxon_autofill = True
        self.genus_input.setText(genus)
        self.species_input.setText(species)
        self._suppress_taxon_autofill = False
        if hasattr(self, "vernacular_input") and not self.vernacular_input.text().strip():
            vernacular = self._preferred_vernacular_from_taxon(self.suggested_taxon.get("taxon") or {})
            if vernacular:
                self._suppress_taxon_autofill = True
                self.vernacular_input.setText(vernacular)
                self._suppress_taxon_autofill = False
        if self.vernacular_db:
            self._update_vernacular_suggestions_for_taxon()
            self._maybe_set_vernacular_from_taxon()

    def _preferred_vernacular_from_taxon(self, taxon: dict) -> str | None:
        if not isinstance(taxon, dict):
            return None
        vernacular_names = taxon.get("vernacularNames") or {}
        lang = normalize_vernacular_language(SettingsDB.get_setting("vernacular_language", "no"))
        if isinstance(vernacular_names, dict) and lang:
            name = vernacular_names.get(lang)
            if name:
                return str(name)
        name = taxon.get("vernacularName")
        if name:
            return str(name)
        return None

    def _primary_result(self) -> ImageImportResult | None:
        if self.primary_index is not None and 0 <= self.primary_index < len(self.image_results):
            return self.image_results[self.primary_index]
        for item in self.image_results:
            if item.captured_at or item.gps_latitude is not None or item.gps_longitude is not None:
                return item
        return self.image_results[0] if self.image_results else None

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
            self.thumbnail_label.setText(self.tr("No image selected"))
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
                prompt = self.tr("Delete image and associated measurements?")
            else:
                prompt = self.tr("Delete image?")
        else:
            prompt = self.tr("Remove image from this observation?")

        confirmed = self._question_yes_no(
            self.tr("Confirm Delete"),
            prompt,
            default_yes=False
        )
        if not confirmed:
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
            self.thumbnail_label.setText(self.tr("No image selected"))
            if hasattr(self, "delete_image_btn"):
                self.delete_image_btn.setEnabled(False)

    def _question_yes_no(self, title, text, default_yes=False):
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
            common_name = None
            working_title = self.title_input.text().strip() or "Unknown"
        else:
            genus = self.genus_input.text().strip() or None
            species = self.species_input.text().strip() or None
            common_name = self.vernacular_input.text().strip() or None
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
            'common_name': common_name,
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
        if hasattr(self, "vernacular_input"):
            self.vernacular_input.setEnabled(not is_unknown)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_datetime_width()

    def _update_datetime_width(self):
        """Keep Date & Time at half the dialog width."""
        if hasattr(self, "datetime_input"):
            target = max(220, int(self.width() * 0.5))
            self.datetime_input.setFixedWidth(target)

    def _resolve_gps_source_index(self) -> int | None:
        source_idx = None
        for idx, item in enumerate(self.image_results):
            if getattr(item, "gps_source", False):
                source_idx = idx
                break
        if source_idx is not None:
            for i, item in enumerate(self.image_results):
                item.gps_source = i == source_idx
            return source_idx
        if not self._observation_datetime:
            return None
        for idx, item in enumerate(self.image_results):
            if item.exif_has_gps and self._matches_observation_datetime(item.captured_at):
                return idx
        return None

    def _matches_observation_datetime(self, dt: QDateTime | None) -> bool:
        if not dt or not self._observation_datetime:
            return False
        if not dt.isValid() or not self._observation_datetime.isValid():
            return False
        obs_minutes = int(self._observation_datetime.toSecsSinceEpoch() / 60)
        img_minutes = int(dt.toSecsSinceEpoch() / 60)
        return obs_minutes == img_minutes

    def _vernacular_label(self) -> str:
        lang = normalize_vernacular_language(SettingsDB.get_setting("vernacular_language", "no"))
        base = self.tr("Common name")
        return f"{common_name_display_label(lang, base)}:"

    def _vernacular_placeholder(self) -> str:
        lang = normalize_vernacular_language(SettingsDB.get_setting("vernacular_language", "no"))
        if lang == "no":
            return self.tr("e.g., Kantarell")
        if lang == "de":
            return self.tr("e.g., Pfifferling")
        if lang == "fr":
            return self.tr("e.g., Girolle")
        if lang == "es":
            return self.tr("e.g., Rebozuelo")
        if lang == "da":
            return self.tr("e.g., Kantarel")
        if lang == "sv":
            return self.tr("e.g., Kantarell")
        if lang == "fi":
            return self.tr("e.g., Kantarelli")
        if lang == "pl":
            return self.tr("e.g., Kurka")
        if lang == "pt":
            return self.tr("e.g., Cantarelo")
        if lang == "it":
            return self.tr("e.g., Gallinaccio")
        return self.tr("e.g., Chanterelle")

    def apply_vernacular_language_change(self) -> None:
        if hasattr(self, "vernacular_label"):
            self.vernacular_label.setText(self._vernacular_label())
        if hasattr(self, "vernacular_input"):
            self.vernacular_input.setPlaceholderText(self._vernacular_placeholder())
        lang = normalize_vernacular_language(SettingsDB.get_setting("vernacular_language", "no"))
        db_path = resolve_vernacular_db_path(lang)
        if not db_path:
            return
        if self.vernacular_db and self.vernacular_db.db_path == db_path:
            self.vernacular_db.language_code = lang
        else:
            self.vernacular_db = VernacularDB(db_path, language_code=lang)
        self._maybe_set_vernacular_from_taxon()

    def _setup_vernacular_autocomplete(self):
        """Wire vernacular lookup/completion if taxonomy DB is available."""
        if not hasattr(self, "vernacular_input"):
            return
        lang = normalize_vernacular_language(SettingsDB.get_setting("vernacular_language", "no"))
        db_path = resolve_vernacular_db_path(lang)
        if not db_path:
            return
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

        self._genus_model = QStringListModel()
        self._genus_completer = QCompleter(self._genus_model, self)
        self._genus_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._genus_completer.setCompletionMode(QCompleter.PopupCompletion)
        self.genus_input.setCompleter(self._genus_completer)
        self._genus_completer.activated.connect(self._on_genus_selected)
        self.genus_input.textChanged.connect(self._on_genus_text_changed)
        self.genus_input.editingFinished.connect(self._on_genus_editing_finished)

        self._species_model = QStringListModel()
        self._species_completer = QCompleter(self._species_model, self)
        self._species_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._species_completer.setCompletionMode(QCompleter.PopupCompletion)
        self.species_input.setCompleter(self._species_completer)
        self._species_completer.activated.connect(self._on_species_selected)
        self.species_input.textChanged.connect(self._on_species_text_changed)
        self.species_input.editingFinished.connect(self._on_species_editing_finished)

        self.genus_input.installEventFilter(self)
        self.species_input.installEventFilter(self)

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
            self.vernacular_input.setPlaceholderText(self._vernacular_placeholder())
            return
        preview = "; ".join(suggestions[:4])
        self.vernacular_input.setPlaceholderText(f"{self.tr('e.g.,')} {preview}")

    def _set_species_placeholder_from_suggestions(self, suggestions: list[str]) -> None:
        if not hasattr(self, "species_input"):
            return
        if not suggestions:
            self.species_input.setPlaceholderText("e.g., velutipes")
            return
        preview = "; ".join(suggestions[:4])
        self.species_input.setPlaceholderText(f"{self.tr('e.g.,')} {preview}")

    def _on_vernacular_selected(self, name):
        # Hide the popup after selection
        if self._vernacular_completer:
            self._vernacular_completer.popup().hide()
        
        if not self.vernacular_db:
            return
        taxon = self.vernacular_db.taxon_from_vernacular(name)
        if taxon:
            genus, species, _family = taxon
            current_genus = self.genus_input.text().strip()
            current_species = self.species_input.text().strip()
            if current_genus and current_species:
                return
            self._suppress_taxon_autofill = True
            if not current_genus:
                self.genus_input.setText(genus)
            if not current_species:
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
            current_genus = self.genus_input.text().strip()
            current_species = self.species_input.text().strip()
            if current_genus and current_species:
                return
            self._suppress_taxon_autofill = True
            if not current_genus:
                self.genus_input.setText(genus)
            if not current_species:
                self.species_input.setText(species)
            self._suppress_taxon_autofill = False
            self._sync_taxon_cache()

    def _on_genus_text_changed(self, text):
        if not self.vernacular_db:
            return
        if self._suppress_taxon_autofill:
            return
        text = text.strip()
        suggestions = self.vernacular_db.suggest_genus(text)
        
        # If text exactly matches a single suggestion, clear the model to prevent popup
        if len(suggestions) == 1 and suggestions[0].lower() == text.lower():
            self._genus_model.setStringList([])
            if self._genus_completer:
                self._genus_completer.popup().hide()
        else:
            self._genus_model.setStringList(suggestions)
        
        if not text:
            self._suppress_taxon_autofill = True
            self.species_input.clear()
            self._suppress_taxon_autofill = False
            self._species_model.setStringList([])
            # Reset species completer filtering
            if self._species_completer:
                self._species_completer.setCompletionPrefix("")
            self._set_species_placeholder_from_suggestions([])
            return

        # Reset species completer filtering when genus changes
        if self._species_completer and not self.species_input.hasFocus():
            self._species_completer.setCompletionPrefix("")
        
        if not self.species_input.text().strip():
            species_suggestions = self.vernacular_db.suggest_species(text, "")
            self._set_species_placeholder_from_suggestions(species_suggestions)

    def _on_genus_editing_finished(self):
        if not self.vernacular_db or self._suppress_taxon_autofill:
            return
        self._handle_taxon_change()
        self._maybe_set_vernacular_from_taxon()
        genus = self.genus_input.text().strip()
        if genus and not self.species_input.text().strip():
            species_suggestions = self.vernacular_db.suggest_species(genus, "")
            self._set_species_placeholder_from_suggestions(species_suggestions)

    def _on_genus_selected(self, genus):
        # Hide the popup after selection
        if self._genus_completer:
            self._genus_completer.popup().hide()
        
        if not self.vernacular_db:
            return
        if self.species_input.text().strip():
            return
        species_suggestions = self.vernacular_db.suggest_species(str(genus).strip(), "")
        self._set_species_placeholder_from_suggestions(species_suggestions)

    def _on_species_selected(self, species):
        """Handle species selection from completer."""
        # Hide the popup after selection
        if self._species_completer:
            self._species_completer.popup().hide()
        
        # Update vernacular name suggestions
        if self.vernacular_db:
            self._maybe_set_vernacular_from_taxon()

    def _on_species_editing_finished(self):
        if not self.vernacular_db or self._suppress_taxon_autofill:
            return
        self._handle_taxon_change()
        self._maybe_set_vernacular_from_taxon()

    def _on_species_text_changed(self, text):
        if not self.vernacular_db:
            return
        if self._suppress_taxon_autofill:
            return
        genus = self.genus_input.text().strip()
        if not genus:
            self._species_model.setStringList([])
            return
        suggestions = self.vernacular_db.suggest_species(genus, text.strip())
        
        # If text exactly matches a single suggestion, clear the model to prevent popup
        if len(suggestions) == 1 and suggestions[0].lower() == text.strip().lower():
            self._species_model.setStringList([])
            if self._species_completer:
                self._species_completer.popup().hide()
        else:
            self._species_model.setStringList(suggestions)
        
        if text.strip():
            self._maybe_set_vernacular_from_taxon()

    def _handle_taxon_change(self):
        if not hasattr(self, "_last_genus"):
            self._sync_taxon_cache()
            return
        genus = self.genus_input.text().strip()
        species = self.species_input.text().strip()
        if genus != self._last_genus or species != self._last_species:
            current_common = self.vernacular_input.text().strip()
            if current_common and self.vernacular_db and genus and species:
                suggestions = self.vernacular_db.suggest_vernacular_for_taxon(
                    genus=genus,
                    species=species
                )
                matches = any(
                    name.strip().lower() == current_common.lower()
                    for name in suggestions
                )
                if not matches:
                    self._suppress_taxon_autofill = True
                    self.vernacular_input.clear()
                    self._suppress_taxon_autofill = False
                    # Reset vernacular completer filtering after clearing
                    if self._vernacular_completer:
                        self._vernacular_completer.setCompletionPrefix("")
        self._last_genus = genus
        self._last_species = species

    def _sync_taxon_cache(self):
        self._last_genus = self.genus_input.text().strip()
        self._last_species = self.species_input.text().strip()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.FocusIn and self.vernacular_db:
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
                suggestions = self.vernacular_db.suggest_genus(text)
                self._genus_model.setStringList(suggestions)
                if suggestions:
                    self._genus_completer.complete()
            elif obj == self.species_input:
                genus = self.genus_input.text().strip()
                if genus:
                    text = self.species_input.text().strip()
                    suggestions = self.vernacular_db.suggest_species(genus, text)
                    self._species_model.setStringList(suggestions)
                    if suggestions:
                        self._species_completer.complete()
        return super().eventFilter(obj, event)

    def _maybe_set_vernacular_from_taxon(self):
        if not self.vernacular_db:
            return
        if not hasattr(self, "vernacular_input"):
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

    def get_files(self):
        """Return selected image files."""
        return [item.filepath for item in self.image_results]

    def get_image_settings(self):
        """Return image settings (type and objective for each image)."""
        settings = []
        for item in self.image_results:
            settings.append({
                "image_type": item.image_type,
                "objective": item.objective,
                "contrast": item.contrast,
                "mount_medium": item.mount_medium,
                "sample_type": item.sample_type,
            })
        return settings

    def get_image_entries(self):
        """Return images with settings for saving."""
        entries = []
        for item in self.image_results:
            entries.append({
                "image_id": item.image_id,
                "filepath": item.filepath,
                "image_type": item.image_type or "field",
                "objective": item.objective,
                "contrast": item.contrast,
                "mount_medium": item.mount_medium,
                "sample_type": item.sample_type
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
        obs = self.observation or {}

        date_str = obs.get("date")
        if date_str:
            dt = _parse_observation_datetime(date_str)
            if dt and dt.isValid():
                self.datetime_input.setDateTime(dt)

        genus = obs.get("genus") or ""
        species = obs.get("species") or ""
        if genus or species:
            self.taxonomy_tabs.setCurrentIndex(0)
            self.genus_input.setText(genus)
            self.species_input.setText(species)
            self.uncertain_checkbox.setChecked(bool(obs.get("uncertain", 0)))
            if hasattr(self, "vernacular_input"):
                self.vernacular_input.setText(obs.get("common_name") or "")
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
        self._maybe_set_vernacular_from_taxon()


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

        self.unknown_checkbox = QCheckBox(self.tr("Unknown"))
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
        self.species_input.setPlaceholderText("e.g., velutipes")
        self.species_input.setText(self.observation.get('species') or "")
        layout.addRow("Species:", self.species_input)

        self.uncertain_checkbox = QCheckBox(self.tr("Uncertain identification"))
        self.uncertain_checkbox.setChecked(bool(self.observation.get('uncertain', 0)))
        layout.addRow("", self.uncertain_checkbox)

        button_layout = QHBoxLayout()
        save_btn = QPushButton(self.tr("Save"))
        save_btn.setObjectName("primaryButton")
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton(self.tr("Cancel"))
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


# Helpers for vernacular language lookup are in utils.vernacular_utils.


def _normalize_taxon_text_impl(self, value: str | None) -> str:
    if not value:
        return ""
    try:
        import unicodedata
        text = unicodedata.normalize("NFKC", str(value))
    except Exception:
        text = str(value)
    text = text.replace("\u00a0", " ")
    text = text.strip()
    if text.startswith("?"):
        text = text.lstrip("?").strip()
    return " ".join(text.split())


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
