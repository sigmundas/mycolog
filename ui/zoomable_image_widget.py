"""Zoomable and pannable image widget with measurement overlays."""
from PySide6.QtWidgets import QLabel, QWidget, QVBoxLayout
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor, QCursor, QTransform, QPolygonF
from PySide6.QtCore import Qt, QPoint, QRect, QPointF, Signal, QRectF
import math


class ZoomableImageLabel(QLabel):
    """Custom label that supports zoom, pan, and measurement overlays."""

    clicked = Signal(QPointF)  # Emits click position in original image coordinates

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMouseTracking(True)

        # Image data
        self.original_pixmap = None
        self.measurement_lines = []
        self.measurement_rectangles = []
        self.preview_line = None  # Temporary line being drawn
        self.preview_rect = None  # Temporary rectangle preview
        self.objective_text = ""
        self.objective_color = QColor(52, 152, 219)
        self.measure_color = QColor(52, 152, 219)
        self.show_measure_labels = False
        self.measurement_labels = []
        self.show_scale_bar = False
        self.scale_bar_um = 10.0
        self.microns_per_pixel = 0.5
        self.show_measure_overlays = True
        self.hover_rect_index = -1
        self.hover_line_index = -1
        self.selected_rect_index = -1
        self.selected_line_indices = set()
        self.pan_without_shift = False
        self.pan_click_candidate = False
        self.measurement_active = False

        # Zoom and pan state
        self.zoom_level = 1.0
        self.min_zoom = 0.1
        self.max_zoom = 10.0
        self.pan_offset = QPointF(0, 0)

        # Pan interaction state
        self.is_panning = False
        self.pan_start_pos = QPointF()
        self.pan_start_offset = QPointF()

        # Mouse tracking for preview line
        self.current_mouse_pos = None

    def _light_stroke_color(self):
        """Return a lighter, low-opacity version of the measure color."""
        light = QColor(self.measure_color)
        light = light.lighter(130)
        light.setAlpha(51)
        return light

    def _compute_corners_from_lines(self, line1, line2):
        """Compute rectangle corners from two measurement lines."""
        p1 = QPointF(line1[0].x(), line1[0].y())
        p2 = QPointF(line1[1].x(), line1[1].y())
        p3 = QPointF(line2[0].x(), line2[0].y())
        p4 = QPointF(line2[1].x(), line2[1].y())

        length_vec = p2 - p1
        length_len = math.sqrt(length_vec.x() ** 2 + length_vec.y() ** 2)
        width_vec = p4 - p3
        width_len = math.sqrt(width_vec.x() ** 2 + width_vec.y() ** 2)
        if length_len <= 0 or width_len <= 0:
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

    def _draw_rotated_label_outside(self, painter, text, edge, center, padding_px):
        """Draw centered, rotated text along an edge, outside the rectangle."""
        a, b = edge
        dx = b.x() - a.x()
        dy = b.y() - a.y()
        length = math.sqrt(dx * dx + dy * dy)
        if length <= 0:
            return

        angle_deg = math.degrees(math.atan2(dy, dx))
        if angle_deg > 90 or angle_deg < -90:
            angle_deg += 180

        mid = QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2)
        perp_x = -dy / length
        perp_y = dx / length

        metrics = painter.fontMetrics()
        text_w = metrics.horizontalAdvance(text)
        text_h = metrics.height()
        offset = (text_h / 2) + padding_px

        dir_dot = (mid.x() - center.x()) * perp_x + (mid.y() - center.y()) * perp_y
        sign = 1 if dir_dot >= 0 else -1
        label_pos = QPointF(mid.x() + perp_x * offset * sign,
                            mid.y() + perp_y * offset * sign)

        painter.save()
        painter.translate(label_pos.x(), label_pos.y())
        painter.rotate(angle_deg)
        painter.drawText(int(-text_w / 2), int(text_h / 2), text)
        painter.restore()

    def _label_positions_from_lines(self, line1, line2, center, offset):
        """Return label positions using the same logic as the preview widget."""
        corners = self._compute_corners_from_lines(line1, line2)
        if not corners:
            return None, None

        def _offset_from_edge(a, b, center_point):
            mid = QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2)
            dx = b.x() - a.x()
            dy = b.y() - a.y()
            length = math.sqrt(dx * dx + dy * dy)
            if length <= 0:
                return mid
            perp_x = -dy / length
            perp_y = dx / length
            candidate_a = QPointF(mid.x() + perp_x * offset, mid.y() + perp_y * offset)
            candidate_b = QPointF(mid.x() - perp_x * offset, mid.y() - perp_y * offset)
            dist_a = (candidate_a.x() - center_point.x()) ** 2 + (candidate_a.y() - center_point.y()) ** 2
            dist_b = (candidate_b.x() - center_point.x()) ** 2 + (candidate_b.y() - center_point.y()) ** 2
            chosen = candidate_a if dist_a >= dist_b else candidate_b
            if self._point_in_polygon(chosen, corners):
                chosen = QPointF(
                    chosen.x() + perp_x * offset,
                    chosen.y() + perp_y * offset
                )
            return chosen

        left_mid = _offset_from_edge(corners[0], corners[3], center)
        top_mid = _offset_from_edge(corners[0], corners[1], center)
        return left_mid, top_mid

    def set_image(self, pixmap):
        """Set the image to display, fitting it to the widget."""
        self.original_pixmap = pixmap
        self.pan_offset = QPointF(0, 0)
        # Fit image to screen by default
        self.reset_view()

    def set_measurement_lines(self, lines):
        """Set the measurement lines to draw."""
        self.measurement_lines = lines
        self.hover_line_index = -1
        self.update()

    def set_measurement_color(self, color):
        """Set the color for measurement overlays."""
        self.measure_color = QColor(color)
        self.update()

    def set_microns_per_pixel(self, mpp):
        """Set scale for converting microns to pixels."""
        if mpp and mpp > 0:
            self.microns_per_pixel = mpp
        self.update()

    def set_scale_bar(self, show, microns):
        """Toggle and set scale bar size in microns."""
        self.show_scale_bar = bool(show)
        if microns and microns > 0:
            self.scale_bar_um = float(microns)
        self.update()

    def set_measurement_rectangles(self, rectangles):
        """Set the measurement rectangles to draw."""
        self.measurement_rectangles = rectangles
        self.hover_rect_index = -1
        self.update()

    def set_selected_rect_index(self, index):
        self.selected_rect_index = index if index is not None else -1
        self.update()

    def set_selected_line_indices(self, indices):
        self.selected_line_indices = set(indices or [])
        self.update()

    def set_measurement_labels(self, labels):
        """Set label positions and values for measurements."""
        self.measurement_labels = labels
        self.update()

    def set_show_measure_overlays(self, show_overlays):
        """Toggle measurement overlay visibility."""
        self.show_measure_overlays = bool(show_overlays)
        self.update()

    def set_show_measure_labels(self, show_labels):
        """Toggle measurement label display."""
        self.show_measure_labels = show_labels
        self.update()

    def set_pan_without_shift(self, enabled):
        """Allow panning with a plain left-drag (no Shift)."""
        self.pan_without_shift = bool(enabled)

    def set_measurement_active(self, active):
        """Toggle measurement-active border."""
        self.measurement_active = bool(active)
        self.update()

    def set_preview_line(self, start_point):
        """Set the start point for a preview line that follows the mouse."""
        self.preview_line = start_point
        self.update()

    def clear_preview_line(self):
        """Clear the preview line."""
        self.preview_line = None
        self.update()

    def set_preview_rectangle(self, base_start, base_end, width_dir, moving_line):
        """Set preview rectangle data based on a fixed base line and moving side."""
        self.preview_rect = {
            "base_start": base_start,
            "base_end": base_end,
            "width_dir": width_dir,
            "moving_line": moving_line,
        }
        self.update()

    def clear_preview_rectangle(self):
        """Clear the preview rectangle."""
        self.preview_rect = None
        self.update()

    def get_current_mouse_pos(self):
        """Expose the current mouse position in image coordinates."""
        return self.current_mouse_pos

    def set_objective_text(self, text):
        """Set the objective tag text."""
        self.objective_text = text
        self.update()

    def set_objective_color(self, color):
        """Set the objective tag color."""
        self.objective_color = QColor(color)
        self.update()

    def reset_view(self):
        """Reset zoom to fit image within the window."""
        if not self.original_pixmap:
            self.zoom_level = 1.0
            self.pan_offset = QPointF(0, 0)
            self.update()
            return

        # Calculate zoom level to fit image within widget
        widget_width = self.width()
        widget_height = self.height()
        image_width = self.original_pixmap.width()
        image_height = self.original_pixmap.height()

        # Calculate scale to fit while maintaining aspect ratio
        scale_x = widget_width / image_width if image_width > 0 else 1.0
        scale_y = widget_height / image_height if image_height > 0 else 1.0
        self.zoom_level = min(scale_x, scale_y, 1.0)  # Don't zoom in beyond 1.0

        # Reset pan to center
        self.pan_offset = QPointF(0, 0)
        self.update()

    def zoom_in(self):
        """Zoom in by 20%."""
        self.zoom_level = min(self.zoom_level * 1.2, self.max_zoom)
        self.update()

    def zoom_out(self):
        """Zoom out by 20%."""
        self.zoom_level = max(self.zoom_level / 1.2, self.min_zoom)
        self.update()

    def wheelEvent(self, event):
        """Handle mouse wheel for zooming."""
        if not self.original_pixmap:
            return

        # Zoom toward mouse cursor position
        delta = event.angleDelta().y()
        if delta > 0:
            zoom_factor = 1.1
        else:
            zoom_factor = 0.9

        old_zoom = self.zoom_level
        self.zoom_level = max(self.min_zoom, min(self.max_zoom, self.zoom_level * zoom_factor))

        if old_zoom != self.zoom_level:
            # Get mouse position relative to widget center
            cursor_pos = event.position()
            widget_center = QPointF(self.width() / 2, self.height() / 2)

            # Calculate cursor position relative to center + current pan offset
            relative_pos = cursor_pos - widget_center - self.pan_offset

            # Scale the relative position by the zoom change
            zoom_ratio = self.zoom_level / old_zoom
            new_relative_pos = relative_pos * zoom_ratio

            # Update pan offset to keep point under cursor fixed
            self.pan_offset = cursor_pos - widget_center - new_relative_pos

        self.update()

    def mousePressEvent(self, event):
        """Handle mouse press for panning or clicking."""
        if event.button() == Qt.LeftButton:
            if event.modifiers() & Qt.ShiftModifier or self.pan_without_shift:
                # Start panning
                self.is_panning = True
                self.pan_start_pos = event.position()
                self.pan_start_offset = QPointF(self.pan_offset)
                self.setCursor(Qt.ClosedHandCursor)
                self.pan_click_candidate = self.pan_without_shift
            else:
                # Regular click - emit position in original image coordinates
                if self.original_pixmap:
                    orig_pos = self.screen_to_image(event.position())
                    if orig_pos:
                        self.clicked.emit(orig_pos)

    def mouseMoveEvent(self, event):
        """Handle mouse move for panning and preview line."""
        # Track mouse position for preview line
        if self.original_pixmap:
            self.current_mouse_pos = self.screen_to_image(event.position())
            self._update_hover_rect(event.position())
            self._update_hover_lines(event.position())

        if self.is_panning:
            delta = event.position() - self.pan_start_pos
            self.pan_offset = self.pan_start_offset + delta
            if self.pan_click_candidate and delta.manhattanLength() > 3:
                self.pan_click_candidate = False
            self.update()
        else:
            # Update cursor for shift+hover
            if event.modifiers() & Qt.ShiftModifier:
                self.setCursor(Qt.OpenHandCursor)
            else:
                self.setCursor(Qt.ArrowCursor)

            # Update if we have a preview line
            if self.preview_line is not None or self.preview_rect is not None:
                self.update()

    def mouseReleaseEvent(self, event):
        """Handle mouse release."""
        if event.button() == Qt.LeftButton and self.is_panning:
            self.is_panning = False
            self.setCursor(Qt.ArrowCursor)
            if self.pan_click_candidate and self.original_pixmap:
                orig_pos = self.screen_to_image(event.position())
                if orig_pos:
                    self.clicked.emit(orig_pos)
            self.pan_click_candidate = False

    def _update_hover_rect(self, screen_pos):
        """Update which measurement rectangle is under the cursor."""
        if self.measurement_active:
            if self.hover_rect_index != -1:
                self.hover_rect_index = -1
                self.update()
            return
        if not self.measurement_rectangles or not self.original_pixmap:
            if self.hover_rect_index != -1:
                self.hover_rect_index = -1
                self.update()
            return

        image_pos = self.screen_to_image(screen_pos)
        if not image_pos:
            if self.hover_rect_index != -1:
                self.hover_rect_index = -1
                self.update()
            return

        hovered = -1
        for idx, rect in enumerate(self.measurement_rectangles):
            if self._point_in_polygon(image_pos, rect):
                hovered = idx
                break

        if hovered != self.hover_rect_index:
            self.hover_rect_index = hovered
            self.update()

    def _update_hover_lines(self, screen_pos):
        """Update which measurement line is under the cursor."""
        if self.measurement_active:
            if self.hover_line_index != -1:
                self.hover_line_index = -1
                self.update()
            return
        if not self.measurement_lines or not self.original_pixmap:
            if self.hover_line_index != -1:
                self.hover_line_index = -1
                self.update()
            return

        image_pos = self.screen_to_image(screen_pos)
        if not image_pos:
            if self.hover_line_index != -1:
                self.hover_line_index = -1
                self.update()
            return

        threshold = 6.0 / self.zoom_level if self.zoom_level else 6.0
        hovered = -1
        best_dist = threshold
        for idx, line in enumerate(self.measurement_lines):
            p1 = QPointF(line[0], line[1])
            p2 = QPointF(line[2], line[3])
            dist = self._distance_point_to_segment(image_pos, p1, p2)
            if dist <= best_dist:
                best_dist = dist
                hovered = idx

        if hovered != self.hover_line_index:
            self.hover_line_index = hovered
            self.update()

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

    def screen_to_image(self, screen_pos):
        """Convert screen position to original image coordinates."""
        if not self.original_pixmap:
            return None

        # Get the displayed image rect (centered, zoomed)
        display_rect = self.get_display_rect()

        # Check if click is within image
        if not display_rect.contains(screen_pos.toPoint()):
            return None

        # Convert to image coordinates
        x = (screen_pos.x() - display_rect.x()) / self.zoom_level
        y = (screen_pos.y() - display_rect.y()) / self.zoom_level

        # Clamp to image bounds
        if 0 <= x < self.original_pixmap.width() and 0 <= y < self.original_pixmap.height():
            return QPointF(x, y)
        return None

    def get_display_rect(self):
        """Get the rectangle where the image is displayed."""
        if not self.original_pixmap:
            return QRect()

        # Calculate scaled size
        scaled_width = self.original_pixmap.width() * self.zoom_level
        scaled_height = self.original_pixmap.height() * self.zoom_level

        # Center position with pan offset
        label_center = QPointF(self.width() / 2, self.height() / 2)
        x = label_center.x() - scaled_width / 2 + self.pan_offset.x()
        y = label_center.y() - scaled_height / 2 + self.pan_offset.y()

        return QRect(int(x), int(y), int(scaled_width), int(scaled_height))

    def export_annotated_pixmap(self):
        """Render annotations on the original image resolution."""
        if not self.original_pixmap:
            return None

        result = QPixmap(self.original_pixmap.size())
        result.fill(Qt.transparent)

        painter = QPainter(result)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.drawPixmap(0, 0, self.original_pixmap)

        scale_factor = 1.0
        if self.zoom_level and self.zoom_level > 0:
            scale_factor = 1.0 / self.zoom_level

        thin_width = max(1.0, 1.0 * scale_factor)
        wide_width = max(1.0, 3.0 * scale_factor)
        light_color = self._light_stroke_color()
        light_pen = QPen(light_color, wide_width)
        thin_pen = QPen(self.measure_color, thin_width)

        # Draw measurement rectangles
        if self.show_measure_overlays and self.measurement_rectangles:
            for rect in self.measurement_rectangles:
                painter.setPen(light_pen)
                painter.drawPolygon(QPolygonF(rect))
                painter.setPen(thin_pen)
                painter.drawPolygon(QPolygonF(rect))

        # Draw measurement lines
        if self.show_measure_overlays and self.measurement_lines:
            for line in self.measurement_lines:
                p1 = QPointF(line[0], line[1])
                p2 = QPointF(line[2], line[3])
                painter.setPen(light_pen)
                painter.drawLine(p1, p2)
                painter.setPen(thin_pen)
                painter.drawLine(p1, p2)

                dx = p2.x() - p1.x()
                dy = p2.y() - p1.y()
                length = math.sqrt(dx**2 + dy**2)
                if length > 0:
                    perp_x = -dy / length
                    perp_y = dx / length
                    mark_len = 5 * scale_factor
                    painter.drawLine(
                        QPointF(p1.x() - perp_x * mark_len, p1.y() - perp_y * mark_len),
                        QPointF(p1.x() + perp_x * mark_len, p1.y() + perp_y * mark_len)
                    )
                    painter.drawLine(
                        QPointF(p2.x() - perp_x * mark_len, p2.y() - perp_y * mark_len),
                        QPointF(p2.x() + perp_x * mark_len, p2.y() + perp_y * mark_len)
                    )

        # Draw measurement labels
        if self.show_measure_labels and self.measurement_labels:
            font = painter.font()
            font.setPointSize(max(6, int(9 * scale_factor)))
            font.setBold(False)
            painter.setFont(font)
            painter.setPen(self.measure_color)
            offset = 12 * scale_factor
            for label in self.measurement_labels:
                length_um = label.get("length_um")
                width_um = label.get("width_um")
                line1 = label.get("line1")
                line2 = label.get("line2")
                center = label.get("center")
                if (length_um is None or width_um is None or
                        line1 is None or line2 is None or center is None):
                    continue
                p1 = QPointF(line1[0], line1[1])
                p2 = QPointF(line1[2], line1[3])
                p3 = QPointF(line2[0], line2[1])
                p4 = QPointF(line2[2], line2[3])
                corners = self._compute_corners_from_lines((p1, p2), (p3, p4))
                if corners:
                    line1_vec = QPointF(p2.x() - p1.x(), p2.y() - p1.y())
                    line1_len = math.sqrt(line1_vec.x() ** 2 + line1_vec.y() ** 2)
                    if line1_len <= 0:
                        continue
                    line1_dir = QPointF(line1_vec.x() / line1_len, line1_vec.y() / line1_len)

                    edges = [
                        (corners[0], corners[1]),
                        (corners[1], corners[2]),
                        (corners[2], corners[3]),
                        (corners[3], corners[0]),
                    ]
                    best_index = 0
                    best_score = -1.0
                    for idx, edge in enumerate(edges):
                        evec = QPointF(edge[1].x() - edge[0].x(), edge[1].y() - edge[0].y())
                        elen = math.sqrt(evec.x() ** 2 + evec.y() ** 2)
                        if elen <= 0:
                            continue
                        edir = QPointF(evec.x() / elen, evec.y() / elen)
                        score = abs(edir.x() * line1_dir.x() + edir.y() * line1_dir.y())
                        if score > best_score:
                            best_score = score
                            best_index = idx

                    length_edge = edges[best_index]
                    width_edge = edges[(best_index + 1) % 4]
                    self._draw_rotated_label_outside(
                        painter, f"{length_um:.2f}", length_edge, center, 3
                    )
                    self._draw_rotated_label_outside(
                        painter, f"{width_um:.2f}", width_edge, center, 3
                    )

        # Draw scale bar
        if self.show_scale_bar and self.microns_per_pixel > 0:
            bar_um = self.scale_bar_um
            bar_pixels = bar_um / self.microns_per_pixel
            bar_pixels = max(10.0, bar_pixels)
            bar_pixels = min(bar_pixels, self.original_pixmap.width() * 0.6)

            font = painter.font()
            font.setPointSize(max(6, int(9 * scale_factor)))
            font.setBold(False)
            painter.setFont(font)
            label = f"{bar_um:g} \u03bcm"
            metrics = painter.fontMetrics()
            label_w = metrics.horizontalAdvance(label)
            label_h = metrics.height()

            margin = 8 * scale_factor
            pad = 6 * scale_factor
            box_w = max(bar_pixels, label_w) + pad * 2
            box_h = label_h + pad * 2 + 6 * scale_factor
            box_x = self.original_pixmap.width() - box_w - margin
            box_y = self.original_pixmap.height() - box_h - margin

            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255, 23))
            painter.drawRoundedRect(QRectF(box_x, box_y, box_w, box_h), 4, 4)

            bar_x1 = box_x + (box_w - bar_pixels) / 2
            bar_x2 = bar_x1 + bar_pixels
            bar_y = box_y + pad + 4 * scale_factor
            painter.setPen(QPen(QColor(0, 0, 0), max(1.0, 2 * scale_factor)))
            painter.drawLine(QPointF(bar_x1, bar_y), QPointF(bar_x2, bar_y))

            text_x = box_x + (box_w - label_w) / 2
            text_y = box_y + pad + 4 * scale_factor + label_h
            painter.setPen(QColor(0, 0, 0))
            painter.drawText(int(text_x), int(text_y), label)

        painter.end()
        return result

    def paintEvent(self, event):
        """Custom paint event to draw image, overlays, and measurements."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        # Fill background
        painter.fillRect(self.rect(), QColor(236, 240, 241))

        if not self.original_pixmap:
            # Draw placeholder text
            painter.setPen(QColor(127, 140, 141))
            painter.drawText(self.rect(), Qt.AlignCenter, "Load an image to begin")
            painter.end()
            return

        # Get display rectangle
        display_rect = self.get_display_rect()

        # Draw the image
        painter.drawPixmap(display_rect, self.original_pixmap)

        # Draw measurement rectangles
        if self.show_measure_overlays and self.measurement_rectangles:
            light_pen = QPen(self._light_stroke_color(), 3)
            thin_pen = QPen(self.measure_color, 1)
            hover_light = QPen(QColor(231, 76, 60, 90), 5)
            hover_thin = QPen(QColor(231, 76, 60), 2)
            for idx, rect in enumerate(self.measurement_rectangles):
                screen_points = []
                for corner in rect:
                    x = display_rect.x() + corner.x() * self.zoom_level
                    y = display_rect.y() + corner.y() * self.zoom_level
                    screen_points.append(QPointF(x, y))
                painter.setPen(light_pen)
                painter.drawPolygon(QPolygonF(screen_points))
                painter.setPen(thin_pen)
                painter.drawPolygon(QPolygonF(screen_points))
                if idx == self.hover_rect_index or (not self.measurement_active and idx == self.selected_rect_index):
                    painter.setPen(hover_light)
                    painter.drawPolygon(QPolygonF(screen_points))
                    painter.setPen(hover_thin)
                    painter.drawPolygon(QPolygonF(screen_points))

        # Draw measurement lines with perpendicular end marks
        if self.show_measure_overlays and self.measurement_lines:
            light_pen = QPen(self._light_stroke_color(), 3)
            thin_pen = QPen(self.measure_color, 1)
            hover_light = QPen(QColor(231, 76, 60, 90), 5)
            hover_thin = QPen(QColor(231, 76, 60), 2)

            for idx, line in enumerate(self.measurement_lines):
                # Convert original image coordinates to screen coordinates
                p1_x = display_rect.x() + line[0] * self.zoom_level
                p1_y = display_rect.y() + line[1] * self.zoom_level
                p2_x = display_rect.x() + line[2] * self.zoom_level
                p2_y = display_rect.y() + line[3] * self.zoom_level

                # Draw main line (wide + thin)
                painter.setPen(light_pen)
                painter.drawLine(int(p1_x), int(p1_y), int(p2_x), int(p2_y))
                painter.setPen(thin_pen)
                painter.drawLine(int(p1_x), int(p1_y), int(p2_x), int(p2_y))

                # Calculate perpendicular direction
                dx = p2_x - p1_x
                dy = p2_y - p1_y
                length = math.sqrt(dx**2 + dy**2)
                if length > 0:
                    # Normalized perpendicular vector
                    perp_x = -dy / length
                    perp_y = dx / length

                    # End mark length (5 pixels on each side)
                    mark_len = 5

                    # Draw perpendicular marks at both ends
                    painter.drawLine(
                        int(p1_x - perp_x * mark_len), int(p1_y - perp_y * mark_len),
                        int(p1_x + perp_x * mark_len), int(p1_y + perp_y * mark_len)
                    )
                painter.drawLine(
                    int(p2_x - perp_x * mark_len), int(p2_y - perp_y * mark_len),
                    int(p2_x + perp_x * mark_len), int(p2_y + perp_y * mark_len)
                )
                if idx == self.hover_line_index or (
                    not self.measurement_active and idx in self.selected_line_indices
                ):
                    painter.setPen(hover_light)
                    painter.drawLine(int(p1_x), int(p1_y), int(p2_x), int(p2_y))
                    painter.setPen(hover_thin)
                    painter.drawLine(int(p1_x), int(p1_y), int(p2_x), int(p2_y))

        # Draw preview line (from last point to mouse cursor)
        if self.preview_line is not None and self.current_mouse_pos is not None:
            light_pen = QPen(self._light_stroke_color(), 3)
            light_pen.setStyle(Qt.DashLine)
            thin_pen = QPen(self.measure_color, 1)
            thin_pen.setStyle(Qt.DashLine)

            # Convert coordinates to screen
            p1_x = display_rect.x() + self.preview_line.x() * self.zoom_level
            p1_y = display_rect.y() + self.preview_line.y() * self.zoom_level
            p2_x = display_rect.x() + self.current_mouse_pos.x() * self.zoom_level
            p2_y = display_rect.y() + self.current_mouse_pos.y() * self.zoom_level

            painter.setPen(light_pen)
            painter.drawLine(int(p1_x), int(p1_y), int(p2_x), int(p2_y))
            painter.setPen(thin_pen)
            painter.drawLine(int(p1_x), int(p1_y), int(p2_x), int(p2_y))

        # Draw preview rectangle (based on fixed base line and mouse width)
        if self.preview_rect is not None and self.current_mouse_pos is not None:
            light_pen = QPen(self._light_stroke_color(), 3)
            light_pen.setStyle(Qt.DashLine)
            thin_pen = QPen(self.measure_color, 1)
            thin_pen.setStyle(Qt.DashLine)

            base_start = self.preview_rect["base_start"]
            base_end = self.preview_rect["base_end"]
            width_dir = self.preview_rect["width_dir"]
            moving_line = self.preview_rect["moving_line"]

            base_mid = QPointF(
                (base_start.x() + base_end.x()) / 2,
                (base_start.y() + base_end.y()) / 2
            )
            delta = self.current_mouse_pos - base_mid
            width_distance = delta.x() * width_dir.x() + delta.y() * width_dir.y()
            offset = width_dir * width_distance

            if moving_line == "line2":
                line1_start = base_start
                line1_end = base_end
                line2_start = base_start + offset
                line2_end = base_end + offset
            else:
                line2_start = base_start
                line2_end = base_end
                line1_start = base_start + offset
                line1_end = base_end + offset

            corners = [line1_start, line1_end, line2_end, line2_start]
            screen_points = []
            for corner in corners:
                x = display_rect.x() + corner.x() * self.zoom_level
                y = display_rect.y() + corner.y() * self.zoom_level
                screen_points.append(QPointF(x, y))

            painter.setPen(light_pen)
            painter.drawPolygon(QPolygonF(screen_points))
            painter.setPen(thin_pen)
            painter.drawPolygon(QPolygonF(screen_points))

        # Draw measurement labels
        if self.show_measure_labels and self.measurement_labels:
            painter.setPen(self.measure_color)
            font = painter.font()
            font.setPointSize(9)
            font.setBold(False)
            painter.setFont(font)

            for label in self.measurement_labels:
                length_um = label.get("length_um")
                width_um = label.get("width_um")
                line1 = label.get("line1")
                line2 = label.get("line2")
                center = label.get("center")
                if (length_um is None or width_um is None or
                        line1 is None or line2 is None or center is None):
                    continue

                p1 = QPointF(display_rect.x() + line1[0] * self.zoom_level,
                             display_rect.y() + line1[1] * self.zoom_level)
                p2 = QPointF(display_rect.x() + line1[2] * self.zoom_level,
                             display_rect.y() + line1[3] * self.zoom_level)
                p3 = QPointF(display_rect.x() + line2[0] * self.zoom_level,
                             display_rect.y() + line2[1] * self.zoom_level)
                p4 = QPointF(display_rect.x() + line2[2] * self.zoom_level,
                             display_rect.y() + line2[3] * self.zoom_level)
                center_screen = QPointF(display_rect.x() + center.x() * self.zoom_level,
                                        display_rect.y() + center.y() * self.zoom_level)
                corners = self._compute_corners_from_lines((p1, p2), (p3, p4))
                if corners:
                    line1_vec = QPointF(p2.x() - p1.x(), p2.y() - p1.y())
                    line1_len = math.sqrt(line1_vec.x() ** 2 + line1_vec.y() ** 2)
                    if line1_len <= 0:
                        continue
                    line1_dir = QPointF(line1_vec.x() / line1_len, line1_vec.y() / line1_len)

                    edges = [
                        (corners[0], corners[1]),
                        (corners[1], corners[2]),
                        (corners[2], corners[3]),
                        (corners[3], corners[0]),
                    ]
                    best_index = 0
                    best_score = -1.0
                    for idx, edge in enumerate(edges):
                        evec = QPointF(edge[1].x() - edge[0].x(), edge[1].y() - edge[0].y())
                        elen = math.sqrt(evec.x() ** 2 + evec.y() ** 2)
                        if elen <= 0:
                            continue
                        edir = QPointF(evec.x() / elen, evec.y() / elen)
                        score = abs(edir.x() * line1_dir.x() + edir.y() * line1_dir.y())
                        if score > best_score:
                            best_score = score
                            best_index = idx

                    length_edge = edges[best_index]
                    width_edge = edges[(best_index + 1) % 4]
                    self._draw_rotated_label_outside(
                        painter, f"{length_um:.2f}", length_edge, center_screen, 3
                    )
                    self._draw_rotated_label_outside(
                        painter, f"{width_um:.2f}", width_edge, center_screen, 3
                    )

        # Draw objective tag in upper right corner
        if self.objective_text:
            tag_padding = 12
            tag_margin = 10

            font = painter.font()
            font.setPointSize(11)
            font.setBold(True)
            painter.setFont(font)

            metrics = painter.fontMetrics()
            text_width = metrics.horizontalAdvance(self.objective_text)
            text_height = metrics.height()

            tag_rect = QRect(
                self.width() - text_width - tag_padding * 2 - tag_margin,
                tag_margin,
                text_width + tag_padding * 2,
                text_height + tag_padding
            )

            # Draw rounded rectangle background
            painter.setPen(Qt.NoPen)
            tag_color = QColor(self.objective_color)
            tag_color.setAlpha(200)
            painter.setBrush(tag_color)
            painter.drawRoundedRect(tag_rect, 6, 6)

            # Draw text
            painter.setPen(Qt.white)
            painter.drawText(tag_rect, Qt.AlignCenter, self.objective_text)

        # Draw zoom info in lower left corner
        zoom_text = f"Zoom: {self.zoom_level * 100:.0f}%"
        font = painter.font()
        font.setPointSize(9)
        painter.setFont(font)
        zoom_metrics = painter.fontMetrics()
        zoom_height = zoom_metrics.height()

        painter.setPen(QColor(127, 140, 141))
        painter.setFont(font)
        painter.drawText(10, self.height() - 10, zoom_text)

        if self.measurement_active:
            painter.setPen(QPen(QColor("#e74c3c"), 3))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.rect().adjusted(1, 1, -2, -2))

        # Draw scale bar in lower right corner
        if self.show_scale_bar and self.microns_per_pixel > 0:
            bar_um = self.scale_bar_um
            bar_pixels = bar_um / self.microns_per_pixel
            bar_screen = bar_pixels * self.zoom_level
            bar_screen = max(10.0, bar_screen)
            bar_screen = min(bar_screen, display_rect.width() * 0.6)

            font = painter.font()
            font.setPointSize(9)
            font.setBold(False)
            painter.setFont(font)
            label = f"{bar_um:g} \u03bcm"
            metrics = painter.fontMetrics()
            label_w = metrics.horizontalAdvance(label)
            label_h = metrics.height()

            margin = 8
            pad = 6
            box_w = max(bar_screen, label_w) + pad * 2
            box_h = label_h + pad * 2 + 6
            box_x = display_rect.right() - box_w - margin
            box_y = display_rect.bottom() - box_h - margin

            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255, 23))
            painter.drawRoundedRect(QRectF(box_x, box_y, box_w, box_h), 4, 4)

            bar_x1 = box_x + (box_w - bar_screen) / 2
            bar_x2 = bar_x1 + bar_screen
            bar_y = box_y + pad + 4
            painter.setPen(QPen(QColor(0, 0, 0), 2))
            painter.drawLine(int(bar_x1), int(bar_y), int(bar_x2), int(bar_y))

            text_x = box_x + (box_w - label_w) / 2
            text_y = box_y + pad + 4 + label_h
            painter.setPen(QColor(0, 0, 0))
            painter.drawText(int(text_x), int(text_y), label)

        painter.end()
