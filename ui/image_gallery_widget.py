"""Reusable image thumbnail gallery widget."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from PySide6.QtCore import Qt, Signal, QEvent, QSize
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QFrame,
    QGridLayout,
    QSizePolicy,
)

from database.models import ImageDB, MeasurementDB
from utils.thumbnail_generator import get_thumbnail_path


class ImageGalleryWidget(QGroupBox):
    """Collapsible thumbnail gallery for observations or explicit image lists."""

    imageClicked = Signal(object, str)
    imageSelected = Signal(object, str)
    deleteRequested = Signal(int)

    def __init__(
        self,
        title: str,
        parent: QWidget | None = None,
        show_delete: bool = True,
        show_badges: bool = True,
        thumbnail_size: int = 140,
        min_height: int = 60,
        default_height: int = 140,
    ) -> None:
        super().__init__(title, parent)
        self.setCheckable(False)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._min_height = max(0, int(min_height))
        self._default_height = max(self._min_height, int(default_height))
        self.setMinimumHeight(self._min_height)

        self._show_delete = show_delete
        self._show_badges = show_badges
        self._base_thumb_size = max(80, int(thumbnail_size))
        self._min_thumb_size = 80
        self._thumb_size = self._base_thumb_size
        self._items: list[dict] = []
        self._frames: list[QFrame] = []
        self._selected_id = None
        self._content = QWidget(self)
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(0, 0, 0, 0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.viewport().installEventFilter(self)

        self._container = QWidget()
        self._grid = QHBoxLayout(self._container)
        self._grid.setAlignment(Qt.AlignLeft)
        self._grid.setSpacing(10)
        self._scroll.setWidget(self._container)
        content_layout.addWidget(self._scroll)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._content)

    def clear(self) -> None:
        self._items = []
        self._selected_id = None
        self._clear_widgets()

    def _clear_widgets(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._frames = []

    def set_images(self, image_paths: Iterable[str]) -> None:
        self._items = []
        for idx, path in enumerate(image_paths):
            if path:
                self._items.append(
                    {
                        "id": None,
                        "filepath": str(path),
                        "has_measurements": False,
                        "image_number": idx + 1,
                    }
                )
        self._render()

    def set_observation_id(self, observation_id: int | None) -> None:
        if not observation_id:
            self.clear()
            return
        images = ImageDB.get_images_for_observation(observation_id)
        items = []
        for idx, img in enumerate(images):
            img_id = img.get("id")
            items.append(
                {
                    "id": img_id,
                    "filepath": img.get("filepath"),
                    "has_measurements": self._has_spore_measurements(img_id) if img_id else False,
                    "image_number": idx + 1,
                }
            )
        self._items = items
        self._render()

    def select_image(self, image_id: int | None) -> None:
        self._selected_id = image_id
        for frame in self._frames:
            is_selected = getattr(frame, "image_id", None) == image_id and image_id is not None
            frame.setProperty("selected", is_selected)
            frame.setStyleSheet(self._frame_style(selected=is_selected))

    def _render(self) -> None:
        self._clear_widgets()
        self._thumb_size = self._target_thumb_size()
        for item in self._items:
            frame = self._create_thumbnail_widget(item)
            self._frames.append(frame)
            self._grid.addWidget(frame)
        if self._selected_id is not None:
            self.select_image(self._selected_id)

    def eventFilter(self, obj, event):
        if obj == self._scroll.viewport() and event.type() == QEvent.Resize:
            self._update_thumbnail_sizes()
        return super().eventFilter(obj, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_thumbnail_sizes()

    def sizeHint(self) -> QSize:
        return QSize(320, self._default_height)

    def minimumSizeHint(self) -> QSize:
        return QSize(120, self._min_height)

    def _frame_style(self, selected: bool = False) -> str:
        border = "#2980b9" if selected else "#bdc3c7"
        return (
            "QFrame { border: 2px solid %s; border-radius: 5px; background: white; }"
            "QFrame:hover { border-color: #3498db; }"
        ) % border

    def _create_thumbnail_widget(self, item: dict) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(self._frame_style())
        frame.setFixedSize(self._thumb_size, self._thumb_size)
        frame.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        thumb_label = QLabel()
        thumb_label.setAlignment(Qt.AlignCenter)
        thumb_label.setFixedSize(self._thumb_size, self._thumb_size)

        pixmap = self._load_pixmap(item)
        if pixmap and not pixmap.isNull():
            thumb_label._orig_pixmap = pixmap
            scaled = pixmap.scaled(self._thumb_size, self._thumb_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            thumb_label.setPixmap(scaled)
        else:
            thumb_label.setText("No preview")
            thumb_label.setStyleSheet("color: #7f8c8d;")

        image_container = QWidget()
        image_layout = QGridLayout(image_container)
        image_layout.setContentsMargins(0, 0, 0, 0)
        image_layout.setSpacing(0)
        image_layout.addWidget(thumb_label, 0, 0, alignment=Qt.AlignCenter)

        image_num = item.get("image_number")
        if image_num is not None:
            number_label = QLabel(str(image_num))
            number_label.setStyleSheet(
                "color: #000000; background-color: rgba(255, 255, 255, 77);"
                "font-size: 8pt; padding: 1px 4px; border-radius: 3px; border: none;"
            )
            number_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            image_layout.addWidget(number_label, 0, 0, alignment=Qt.AlignTop | Qt.AlignLeft)

        overlay = QWidget()
        overlay_layout = QHBoxLayout(overlay)
        overlay_layout.setContentsMargins(2, 2, 2, 2)
        overlay_layout.setSpacing(4)
        overlay_layout.addStretch()

        if self._show_badges and item.get("has_measurements"):
            badge = QLabel("M")
            badge.setFixedSize(16, 16)
            badge.setAlignment(Qt.AlignCenter)
            badge.setStyleSheet(
                "background-color: #27ae60; color: white; border-radius: 8px; font-size: 8pt;"
            )
            overlay_layout.addWidget(badge)

        if self._show_delete and item.get("id"):
            delete_btn = QToolButton()
            delete_btn.setText("X")
            delete_btn.setFixedSize(16, 16)
            delete_btn.setStyleSheet(
                "QToolButton { background-color: #e74c3c; color: white; border-radius: 8px; font-size: 8pt; }"
            )
            delete_btn.clicked.connect(lambda _, img_id=item["id"]: self.deleteRequested.emit(img_id))
            overlay_layout.addWidget(delete_btn)

        image_layout.addWidget(overlay, 0, 0, alignment=Qt.AlignTop | Qt.AlignRight)
        layout.addWidget(image_container)

        frame.image_id = item.get("id")
        frame.image_path = item.get("filepath")
        frame.thumb_label = thumb_label
        frame.mousePressEvent = lambda e, img_id=frame.image_id, path=frame.image_path: self._on_click(img_id, path)

        return frame

    def _target_thumb_size(self) -> int:
        viewport_h = self._scroll.viewport().height() if self._scroll else self._base_thumb_size
        target = max(self._min_thumb_size, min(self._base_thumb_size, viewport_h - 16))
        return target

    def _update_thumbnail_sizes(self) -> None:
        if not self._frames:
            return
        new_size = self._target_thumb_size()
        if new_size == self._thumb_size:
            return
        self._thumb_size = new_size
        for frame in self._frames:
            if not hasattr(frame, "thumb_label"):
                continue
            frame.setFixedSize(self._thumb_size, self._thumb_size)
            frame.thumb_label.setFixedSize(self._thumb_size, self._thumb_size)
            pixmap = getattr(frame.thumb_label, "_orig_pixmap", None)
            if isinstance(pixmap, QPixmap) and not pixmap.isNull():
                scaled = pixmap.scaled(self._thumb_size, self._thumb_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                frame.thumb_label.setPixmap(scaled)

    def _load_pixmap(self, item: dict) -> QPixmap | None:
        img_id = item.get("id")
        filepath = item.get("filepath")
        if img_id:
            thumb_path = get_thumbnail_path(img_id, "224x224")
            if thumb_path and Path(thumb_path).exists():
                return QPixmap(thumb_path)
        if filepath:
            return QPixmap(filepath)
        return None

    def _on_click(self, image_id: int | None, filepath: str | None) -> None:
        self._selected_id = image_id
        self.select_image(image_id)
        self.imageClicked.emit(image_id, filepath or "")
        self.imageSelected.emit(image_id, filepath or "")

    def _has_spore_measurements(self, image_id: int) -> bool:
        measurements = MeasurementDB.get_measurements_for_image(image_id)
        for measurement in measurements:
            measurement_type = (measurement.get("measurement_type") or "").lower()
            if measurement_type in ("", "manual", "spore"):
                return True
        return False
