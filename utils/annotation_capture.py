"""Annotation capture for ML training data collection."""
import math
import sqlite3
from typing import List, Tuple, Optional
from database.schema import get_connection


def save_spore_annotation(
    image_id: int,
    measurement_id: int,
    points: List,  # List of 4 QPointF objects [p1, p2, p3, p4]
    length_um: float,
    width_um: float,
    image_shape: Tuple[int, int],  # (height, width)
    padding: int = 50,
    annotation_source: str = 'manual'
) -> int:
    """Save a spore measurement as an ML annotation with bounding box.

    The 4 points represent two measurement lines:
    - p1, p2: First measurement line (either length or width)
    - p3, p4: Second measurement line (either width or length)

    Args:
        image_id: Database ID of the image
        measurement_id: Database ID of the spore_measurement
        points: List of 4 QPointF objects representing measurement endpoints
        length_um: Length measurement in microns
        width_um: Width measurement in microns
        image_shape: Tuple of (height, width) of the image
        padding: Padding around the bounding box in pixels
        annotation_source: Source of annotation ('manual', 'auto', etc.)

    Returns:
        annotation_id from database
    """
    if len(points) != 4:
        raise ValueError(f"Expected 4 points, got {len(points)}")

    img_height, img_width = image_shape

    # Extract all point coordinates
    all_x = [p.x() for p in points]
    all_y = [p.y() for p in points]

    # Calculate center point (centroid of all 4 points)
    center_x = sum(all_x) / 4
    center_y = sum(all_y) / 4

    # Calculate bounding box with padding
    min_x = max(0, int(min(all_x) - padding))
    min_y = max(0, int(min(all_y) - padding))
    max_x = min(img_width, int(max(all_x) + padding))
    max_y = min(img_height, int(max(all_y) + padding))

    bbox_x = min_x
    bbox_y = min_y
    bbox_width = max_x - min_x
    bbox_height = max_y - min_y

    # Calculate rotation angle from the length line
    # Use p1-p2 vs p3-p4, pick the longer one as the length line
    dx1 = points[1].x() - points[0].x()
    dy1 = points[1].y() - points[0].y()
    dist1 = math.sqrt(dx1**2 + dy1**2)

    dx2 = points[3].x() - points[2].x()
    dy2 = points[3].y() - points[2].y()
    dist2 = math.sqrt(dx2**2 + dy2**2)

    # Use the longer line for rotation angle (it's the length)
    if dist1 >= dist2:
        rotation_angle = math.atan2(dy1, dx1)
    else:
        rotation_angle = math.atan2(dy2, dx2)

    # Convert to degrees for storage
    rotation_degrees = math.degrees(rotation_angle)

    # Get next spore number for this image
    spore_number = _get_next_spore_number(image_id)

    # Save to database
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO spore_annotations
        (image_id, measurement_id, spore_number, bbox_x, bbox_y, bbox_width, bbox_height,
         center_x, center_y, length_um, width_um, rotation_angle, annotation_source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (image_id, measurement_id, spore_number, bbox_x, bbox_y, bbox_width, bbox_height,
          center_x, center_y, length_um, width_um, rotation_degrees, annotation_source))

    annotation_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return annotation_id


def _get_next_spore_number(image_id: int) -> int:
    """Get the next spore number for an image."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT COALESCE(MAX(spore_number), 0) + 1
        FROM spore_annotations
        WHERE image_id = ?
    ''', (image_id,))

    result = cursor.fetchone()[0]
    conn.close()
    return result


def get_annotations_for_image(image_id: int) -> List[dict]:
    """Get all annotations for an image.

    Args:
        image_id: Database ID of the image

    Returns:
        List of annotation dictionaries
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('''
        SELECT * FROM spore_annotations
        WHERE image_id = ?
        ORDER BY spore_number
    ''', (image_id,))

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def get_annotation_count_for_image(image_id: int) -> int:
    """Get the count of annotations for an image."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT COUNT(*) FROM spore_annotations
        WHERE image_id = ?
    ''', (image_id,))

    count = cursor.fetchone()[0]
    conn.close()
    return count


def delete_annotation(annotation_id: int):
    """Delete an annotation by ID."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('DELETE FROM spore_annotations WHERE id = ?', (annotation_id,))

    conn.commit()
    conn.close()


def delete_annotations_for_measurement(measurement_id: int):
    """Delete all annotations linked to a measurement."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('DELETE FROM spore_annotations WHERE measurement_id = ?', (measurement_id,))

    conn.commit()
    conn.close()


def delete_annotations_for_image(image_id: int):
    """Delete all annotations for an image."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('DELETE FROM spore_annotations WHERE image_id = ?', (image_id,))

    conn.commit()
    conn.close()


def get_total_annotation_count() -> int:
    """Get total count of all annotations in the database."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT COUNT(*) FROM spore_annotations')

    count = cursor.fetchone()[0]
    conn.close()
    return count


def get_images_with_annotations() -> List[dict]:
    """Get list of images that have annotations.

    Returns:
        List of dicts with image_id and annotation_count
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('''
        SELECT image_id, COUNT(*) as annotation_count
        FROM spore_annotations
        GROUP BY image_id
        ORDER BY image_id
    ''')

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]
