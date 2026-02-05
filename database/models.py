"""Data access layer for database operations"""
import sqlite3
import shutil
import re
import json
from pathlib import Path
from typing import List, Optional, Tuple
from datetime import datetime
from .schema import get_connection, get_reference_connection, get_images_dir, get_calibrations_dir

_UNSET = object()

# Images directory
def _images_dir() -> Path:
    return get_images_dir()


def sanitize_folder_name(name: str) -> str:
    """Sanitize a string for use as a folder name."""
    if not name:
        return "unknown"
    # Remove or replace invalid characters
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = name.strip('. ')
    return name if name else "unknown"


class ObservationDB:
    """Handle observation database operations"""

    @staticmethod
    def _infer_image_folder(cursor, observation_id: int) -> Optional[str]:
        """Infer the observation folder from stored image paths."""
        cursor.execute('SELECT filepath FROM images WHERE observation_id = ?', (observation_id,))
        rows = cursor.fetchall()
        if not rows:
            return None
        parents = set()
        for row in rows:
            path = row[0]
            if not path:
                continue
            parents.add(str(Path(path).resolve().parent))
        if len(parents) == 1:
            return parents.pop()
        return None

    @staticmethod
    def _move_observation_folder(cursor, observation_id: int, old_folder: str, new_folder: str):
        """Move an observation folder and update image paths."""
        old_path = Path(old_folder)
        new_path = Path(new_folder)
        new_path.parent.mkdir(parents=True, exist_ok=True)

        if not new_path.exists():
            shutil.move(str(old_path), str(new_path))
            ObservationDB._update_image_paths(cursor, observation_id, str(old_path), str(new_path))
            return

        # Merge files into existing folder, updating filepaths individually.
        for item in old_path.iterdir():
            dest = new_path / item.name
            if dest.exists():
                counter = 1
                while dest.exists():
                    dest = new_path / f"{item.stem}_{counter}{item.suffix}"
                    counter += 1
            shutil.move(str(item), str(dest))
            if item.is_file():
                cursor.execute(
                    'UPDATE images SET filepath = ? WHERE filepath = ?',
                    (str(dest), str(item))
                )

        try:
            old_path.rmdir()
        except OSError:
            pass

    @staticmethod
    def create_observation(date: str, genus: str = None, species: str = None,
                          common_name: str = None, location: str = None, habitat: str = None,
                          species_guess: str = None, notes: str = None,
                          uncertain: bool = False, inaturalist_id: int = None,
                          gps_latitude: float = None, gps_longitude: float = None,
                          author: str = None) -> int:
        """Create a new observation and return its ID"""
        conn = get_connection()
        cursor = conn.cursor()

        # Build species_guess from genus/species if not provided
        if not species_guess and (genus or species):
            parts = []
            if genus:
                parts.append(genus)
            if species:
                parts.append(species)
            species_guess = ' '.join(parts)

        # Create folder path: genus/species date-time
        genus_folder = sanitize_folder_name(genus) if genus else "unknown"
        species_name = sanitize_folder_name(species) if species else "sp"
        # Parse date to create folder name (keep spaces for readability, avoid ':' for Windows)
        date_part = date.replace(':', '-') if date else datetime.now().strftime('%Y-%m-%d %H-%M')
        folder_name = f"{species_name} - {date_part}"
        folder_path = str(_images_dir() / genus_folder / folder_name)

        cursor.execute('''
            INSERT INTO observations (date, genus, species, common_name, location, habitat,
                                     species_guess, notes, uncertain, folder_path, inaturalist_id,
                                     gps_latitude, gps_longitude, author)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (date, genus, species, common_name, location, habitat, species_guess, notes,
              1 if uncertain else 0, folder_path, inaturalist_id, gps_latitude,
              gps_longitude, author))

        obs_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return obs_id

    @staticmethod
    def update_observation(observation_id: int, genus: str = None, species: str = None,
                          common_name: str = None, location: str = None, habitat: str = None,
                          notes: str = None, uncertain: bool = None,
                          species_guess: str = None, date: str = None,
                          gps_latitude: float = None, gps_longitude: float = None,
                          allow_nulls: bool = False) -> Optional[str]:
        """Update an observation. Returns new folder path if genus/species changed."""
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get current observation
        cursor.execute('SELECT * FROM observations WHERE id = ?', (observation_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return None

        current = dict(row)
        old_folder_path = current.get('folder_path')

        # Check if genus/species changed
        new_folder_path = None
        genus_changed = genus is not None and genus != current.get('genus')
        species_changed = species is not None and species != current.get('species')

        if genus_changed or species_changed:
            # Build new folder path
            new_genus = genus if genus is not None else current.get('genus')
            new_species = species if species is not None else current.get('species')

            genus_folder = sanitize_folder_name(new_genus) if new_genus else "unknown"
            species_name = sanitize_folder_name(new_species) if new_species else "sp"
            date_part = current['date'].replace(':', '-') if current['date'] else 'unknown'
            folder_name = f"{species_name} - {date_part}"
            new_folder_path = str(_images_dir() / genus_folder / folder_name)

        # Rename folder if it exists (or infer it from image paths)
        inferred_folder = None
        if not old_folder_path or not Path(old_folder_path).exists():
            inferred_folder = ObservationDB._infer_image_folder(cursor, observation_id)
        folder_to_move = old_folder_path if old_folder_path and Path(old_folder_path).exists() else inferred_folder

        if new_folder_path and folder_to_move and folder_to_move != new_folder_path:
            try:
                ObservationDB._move_observation_folder(cursor, observation_id, folder_to_move, new_folder_path)
            except Exception as e:
                print(f"Warning: Could not rename folder: {e}")
                new_folder_path = old_folder_path or folder_to_move  # Keep old path on error

        # Build update query
        updates = []
        values = []

        if allow_nulls or genus is not None:
            updates.append('genus = ?')
            values.append(genus)
        if allow_nulls or species is not None:
            updates.append('species = ?')
            values.append(species)
        if allow_nulls or common_name is not None:
            updates.append('common_name = ?')
            values.append(common_name)
        if allow_nulls or location is not None:
            updates.append('location = ?')
            values.append(location)
        if allow_nulls or habitat is not None:
            updates.append('habitat = ?')
            values.append(habitat)
        if allow_nulls or date is not None:
            updates.append('date = ?')
            values.append(date)
        if allow_nulls or notes is not None:
            updates.append('notes = ?')
            values.append(notes)
        if allow_nulls or uncertain is not None:
            updates.append('uncertain = ?')
            values.append(1 if uncertain else 0)
        if allow_nulls or gps_latitude is not None:
            updates.append('gps_latitude = ?')
            values.append(gps_latitude)
        if allow_nulls or gps_longitude is not None:
            updates.append('gps_longitude = ?')
            values.append(gps_longitude)
        if allow_nulls or species_guess is not None:
            updates.append('species_guess = ?')
            values.append(species_guess)
        if new_folder_path:
            updates.append('folder_path = ?')
            values.append(new_folder_path)

        # Update species_guess based on new genus/species if not explicitly provided
        if not allow_nulls and species_guess is None and (genus is not None or species is not None):
            new_genus = genus if genus is not None else current.get('genus')
            new_species = species if species is not None else current.get('species')
            parts = []
            if new_genus:
                parts.append(new_genus)
            if new_species:
                parts.append(new_species)
            updates.append('species_guess = ?')
            values.append(' '.join(parts) if parts else 'Unknown')

        if updates:
            values.append(observation_id)
            cursor.execute(f'''
                UPDATE observations SET {', '.join(updates)} WHERE id = ?
            ''', values)

        conn.commit()
        conn.close()
        return new_folder_path

    @staticmethod
    def _update_image_paths(cursor, observation_id: int, old_folder: str, new_folder: str):
        """Update image filepaths when folder is renamed."""
        cursor.execute('SELECT id, filepath FROM images WHERE observation_id = ?', (observation_id,))
        rows = cursor.fetchall()

        for row in rows:
            old_path = row[1]
            if old_path and old_folder in old_path:
                new_path = old_path.replace(old_folder, new_folder)
                cursor.execute('UPDATE images SET filepath = ? WHERE id = ?', (new_path, row[0]))
    
    @staticmethod
    def get_all_observations() -> List[dict]:
        """Get all observations"""
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM observations ORDER BY date DESC')
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    @staticmethod
    def get_observation(observation_id: int) -> Optional[dict]:
        """Get a single observation by ID"""
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM observations WHERE id = ?', (observation_id,))
        row = cursor.fetchone()
        conn.close()

        return dict(row) if row else None

    @staticmethod
    def update_spore_statistics(observation_id: int, spore_statistics: str = None):
        """Update stored spore statistics string for an observation."""
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE observations
            SET spore_statistics = ?
            WHERE id = ?
        ''', (spore_statistics, observation_id))

        conn.commit()
        conn.close()

    @staticmethod
    def set_auto_threshold(observation_id: int, auto_threshold: float = None):
        """Store the auto-measure threshold for an observation."""
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE observations
            SET auto_threshold = ?
            WHERE id = ?
        ''', (auto_threshold, observation_id))

        conn.commit()
        conn.close()

    @staticmethod
    def delete_observation(observation_id: int):
        """Delete an observation and all associated images/measurements"""
        conn = get_connection()
        cursor = conn.cursor()

        # Collect image filepaths and observation folder before deleting rows
        cursor.execute('SELECT folder_path FROM observations WHERE id = ?', (observation_id,))
        obs_row = cursor.fetchone()
        folder_path = None
        if obs_row and obs_row[0]:
            folder_path = obs_row[0]

        cursor.execute('SELECT id, filepath FROM images WHERE observation_id = ?', (observation_id,))
        image_rows = cursor.fetchall()

        # First delete all measurements for images of this observation
        cursor.execute('''
            DELETE FROM spore_measurements
            WHERE image_id IN (SELECT id FROM images WHERE observation_id = ?)
        ''', (observation_id,))

        # Delete all images for this observation
        cursor.execute('DELETE FROM images WHERE observation_id = ?', (observation_id,))

        # Delete the observation itself
        cursor.execute('DELETE FROM observations WHERE id = ?', (observation_id,))

        conn.commit()
        conn.close()

        # Remove thumbnails and image files from disk
        images_root = _images_dir()
        for image_id, filepath in image_rows:
            try:
                from utils.thumbnail_generator import delete_thumbnails
                delete_thumbnails(image_id)
            except Exception as e:
                print(f"Warning: Could not delete thumbnails for image {image_id}: {e}")

            if not filepath:
                continue
            try:
                path = Path(filepath).resolve()
                root = images_root.resolve()
                if path.exists() and path.is_relative_to(root):
                    path.unlink()
            except Exception as e:
                print(f"Warning: Could not delete image file {filepath}: {e}")

        # Remove observation folder if it lives under images root
        if folder_path:
            try:
                obs_folder = Path(folder_path).resolve()
                root = images_root.resolve()
                if obs_folder.exists() and obs_folder.is_relative_to(root):
                    shutil.rmtree(obs_folder, ignore_errors=True)
            except Exception as e:
                print(f"Warning: Could not delete observation folder {folder_path}: {e}")

class ImageDB:
    """Handle image database operations"""

    # Microscope image categories
    MICRO_CATEGORIES = [
        'spores',
        'basidia',
        'pleurocystidia',
        'cheilocystidia',
        'caulocystidia',
        'pileipellis',
        'stipitipellis',
        'clamp_connections',
        'other'
    ]

    @staticmethod
    def add_image(observation_id: int, filepath: str, image_type: str,
                  scale: float = None, notes: str = None,
                  micro_category: str = None, objective_name: str = None,
                  measure_color: str = None, mount_medium: str = None,
                  sample_type: str = None, contrast: str = None,
                  calibration_id: int = None,
                  ai_crop_box: tuple[float, float, float, float] | None = None,
                  ai_crop_source_size: tuple[int, int] | None = None,
                  gps_source: bool | None = None,
                  copy_to_folder: bool = True) -> int:
        """Add an image and return its ID.

        Args:
            observation_id: ID of the observation
            filepath: Source filepath of the image
            image_type: 'field' or 'microscope'
            scale: Scale in microns per pixel
            notes: Optional notes
            micro_category: Category for microscope images
            objective_name: Name of the objective used
            copy_to_folder: If True, copy image to observation folder
        """
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        final_filepath = filepath

        # Copy image to observation folder if requested
        if copy_to_folder and observation_id:
            cursor.execute('SELECT folder_path FROM observations WHERE id = ?', (observation_id,))
            row = cursor.fetchone()
            if row and row['folder_path']:
                folder_path = Path(row['folder_path'])
                folder_path.mkdir(parents=True, exist_ok=True)

                source_path = Path(filepath)
                if source_path.exists():
                    # Generate unique filename if needed
                    dest_path = folder_path / source_path.name
                    counter = 1
                    while dest_path.exists():
                        dest_path = folder_path / f"{source_path.stem}_{counter}{source_path.suffix}"
                        counter += 1

                    try:
                        shutil.copy2(filepath, dest_path)
                        final_filepath = str(dest_path)
                    except Exception as e:
                        print(f"Warning: Could not copy image: {e}")

        crop_x1 = crop_y1 = crop_x2 = crop_y2 = None
        if ai_crop_box and len(ai_crop_box) == 4:
            crop_x1, crop_y1, crop_x2, crop_y2 = ai_crop_box
        crop_w = crop_h = None
        if ai_crop_source_size and len(ai_crop_source_size) == 2:
            crop_w, crop_h = ai_crop_source_size
        gps_source_value = None if gps_source is None else (1 if gps_source else 0)

        cursor.execute('''
            INSERT INTO images (observation_id, filepath, image_type, micro_category,
                              objective_name, scale_microns_per_pixel, mount_medium,
                              sample_type, contrast, measure_color, notes, calibration_id,
                              ai_crop_x1, ai_crop_y1, ai_crop_x2, ai_crop_y2,
                              ai_crop_source_w, ai_crop_source_h, gps_source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (observation_id, final_filepath, image_type, micro_category,
              objective_name, scale, mount_medium, sample_type, contrast, measure_color, notes,
              calibration_id, crop_x1, crop_y1, crop_x2, crop_y2, crop_w, crop_h, gps_source_value))

        img_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return img_id

    @staticmethod
    def get_image(image_id: int) -> Optional[dict]:
        """Get a single image by ID"""
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM images WHERE id = ?', (image_id,))
        row = cursor.fetchone()
        conn.close()

        return dict(row) if row else None

    @staticmethod
    def get_images_for_observation(observation_id: int) -> List[dict]:
        """Get all images for an observation"""
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('''
            SELECT * FROM images
            WHERE observation_id = ?
            ORDER BY image_type, micro_category, created_at
        ''', (observation_id,))

        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    @staticmethod
    def get_images_by_type(observation_id: int, image_type: str) -> List[dict]:
        """Get images of a specific type for an observation"""
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('''
            SELECT * FROM images
            WHERE observation_id = ? AND image_type = ?
            ORDER BY micro_category, created_at
        ''', (observation_id, image_type))

        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    @staticmethod
    def update_image(image_id: int, micro_category: str = None,
                     scale: float = None, notes: str = None,
                     objective_name: str = None, filepath: str = None,
                     measure_color: str = None, image_type: str = None,
                     mount_medium: str = None, sample_type: str = None,
                     contrast: str = None, calibration_id: int = None,
                     ai_crop_box: tuple[float, float, float, float] | None | object = _UNSET,
                     ai_crop_source_size: tuple[int, int] | None | object = _UNSET,
                     gps_source: bool | None | object = _UNSET):
        """Update image metadata"""
        conn = get_connection()
        cursor = conn.cursor()

        updates = []
        values = []

        if micro_category is not None:
            updates.append('micro_category = ?')
            values.append(micro_category)
        if scale is not None:
            updates.append('scale_microns_per_pixel = ?')
            values.append(scale)
        if objective_name is not None:
            updates.append('objective_name = ?')
            values.append(objective_name)
        if image_type is not None:
            updates.append('image_type = ?')
            values.append(image_type)
        if mount_medium is not None:
            updates.append('mount_medium = ?')
            values.append(mount_medium)
        if sample_type is not None:
            updates.append('sample_type = ?')
            values.append(sample_type)
        if contrast is not None:
            updates.append('contrast = ?')
            values.append(contrast)
        if filepath is not None:
            updates.append('filepath = ?')
            values.append(filepath)
        if notes is not None:
            updates.append('notes = ?')
            values.append(notes)
        if measure_color is not None:
            updates.append('measure_color = ?')
            values.append(measure_color)
        if calibration_id is not None:
            updates.append('calibration_id = ?')
            values.append(calibration_id)
        if ai_crop_box is not _UNSET:
            crop_x1 = crop_y1 = crop_x2 = crop_y2 = None
            if ai_crop_box and len(ai_crop_box) == 4:
                crop_x1, crop_y1, crop_x2, crop_y2 = ai_crop_box
            updates.extend([
                'ai_crop_x1 = ?',
                'ai_crop_y1 = ?',
                'ai_crop_x2 = ?',
                'ai_crop_y2 = ?',
            ])
            values.extend([crop_x1, crop_y1, crop_x2, crop_y2])
        if ai_crop_source_size is not _UNSET:
            crop_w = crop_h = None
            if ai_crop_source_size and len(ai_crop_source_size) == 2:
                crop_w, crop_h = ai_crop_source_size
            updates.extend(['ai_crop_source_w = ?', 'ai_crop_source_h = ?'])
            values.extend([crop_w, crop_h])
        if gps_source is not _UNSET:
            gps_value = None if gps_source is None else (1 if gps_source else 0)
            updates.append('gps_source = ?')
            values.append(gps_value)

        if updates:
            values.append(image_id)
            cursor.execute(f'''
                UPDATE images SET {', '.join(updates)} WHERE id = ?
            ''', values)

        conn.commit()
        conn.close()

    @staticmethod
    def delete_image(image_id: int):
        """Delete an image and its measurements"""
        conn = get_connection()
        cursor = conn.cursor()

        # Delete measurements first
        cursor.execute('DELETE FROM spore_measurements WHERE image_id = ?', (image_id,))
        # Delete annotations
        cursor.execute('DELETE FROM spore_annotations WHERE image_id = ?', (image_id,))
        # Delete thumbnails
        cursor.execute('DELETE FROM thumbnails WHERE image_id = ?', (image_id,))
        # Delete the image
        cursor.execute('DELETE FROM images WHERE id = ?', (image_id,))

        conn.commit()
        conn.close()

class MeasurementDB:
    """Handle spore measurement database operations"""
    
    @staticmethod
    def add_measurement(image_id: int, length: float, width: float = None,
                       measurement_type: str = 'manual', notes: str = None,
                       points: list = None) -> int:
        """Add a measurement and return its ID

        Args:
            image_id: ID of the image
            length: Length in microns
            width: Width in microns
            measurement_type: Type of measurement
            notes: Optional notes
            points: List of 4 QPointF objects [p1, p2, p3, p4]
        """
        conn = get_connection()
        cursor = conn.cursor()

        if points and len(points) == 4:
            cursor.execute('''
                INSERT INTO spore_measurements
                (image_id, length_um, width_um, measurement_type, notes,
                 p1_x, p1_y, p2_x, p2_y, p3_x, p3_y, p4_x, p4_y)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (image_id, length, width, measurement_type, notes,
                  points[0].x(), points[0].y(),
                  points[1].x(), points[1].y(),
                  points[2].x(), points[2].y(),
                  points[3].x(), points[3].y()))
        else:
            cursor.execute('''
                INSERT INTO spore_measurements (image_id, length_um, width_um, measurement_type, notes)
                VALUES (?, ?, ?, ?, ?)
            ''', (image_id, length, width, measurement_type, notes))

        meas_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return meas_id
    
    @staticmethod
    def get_measurements_for_image(image_id: int) -> List[dict]:
        """Get all measurements for an image"""
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM spore_measurements 
            WHERE image_id = ?
            ORDER BY measured_at
        ''', (image_id,))
        
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    @staticmethod
    def get_measurements_for_observation(observation_id: int) -> List[dict]:
        """Get all measurements for all images in an observation"""
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('''
            SELECT m.*, i.filepath AS image_filepath
            FROM spore_measurements m
            JOIN images i ON m.image_id = i.id
            WHERE i.observation_id = ?
            ORDER BY m.measured_at
        ''', (observation_id,))

        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    @staticmethod
    def get_statistics_for_observation(observation_id: int, measurement_category: str = 'spore') -> dict:
        """Calculate statistics for measurements of an observation."""
        measurements = MeasurementDB.get_measurements_for_observation(observation_id)

        if measurement_category:
            category = measurement_category.lower()
            if category == 'spore':
                measurements = [
                    m for m in measurements
                    if (m.get('measurement_type') in (None, '', 'manual', 'spore'))
                ]
            else:
                measurements = [
                    m for m in measurements
                    if (m.get('measurement_type') or '').lower() == category
                ]

        if not measurements:
            return {}

        lengths = [m['length_um'] for m in measurements]
        widths = [m['width_um'] for m in measurements if m['width_um']]

        import numpy as np

        stats = {
            'count': len(lengths),
            'length_mean': np.mean(lengths),
            'length_std': np.std(lengths),
            'length_min': np.min(lengths),
            'length_max': np.max(lengths),
            'length_p5': np.percentile(lengths, 5),
            'length_p95': np.percentile(lengths, 95),
        }

        if widths:
            ratios = [l/w for l, w in zip(lengths, widths) if w > 0]
            stats.update({
                'width_mean': np.mean(widths),
                'width_std': np.std(widths),
                'width_min': np.min(widths),
                'width_max': np.max(widths),
                'width_p5': np.percentile(widths, 5),
                'width_p95': np.percentile(widths, 95),
                'ratio_mean': np.mean(ratios),
                'ratio_min': np.min(ratios),
                'ratio_max': np.max(ratios),
                'ratio_p5': np.percentile(ratios, 5),
                'ratio_p95': np.percentile(ratios, 95),
            })

        return stats

    @staticmethod
    def get_measurement_types_for_observation(observation_id: int) -> List[str]:
        """Get distinct measurement types for an observation"""
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT DISTINCT m.measurement_type
            FROM spore_measurements m
            JOIN images i ON m.image_id = i.id
            WHERE i.observation_id = ?
            ORDER BY m.measurement_type
        ''', (observation_id,))

        rows = cursor.fetchall()
        conn.close()
        return [row[0] for row in rows]
    
    @staticmethod
    def get_statistics_for_image(image_id: int, measurement_category: str = 'spore') -> dict:
        """Calculate statistics for measurements of an image"""
        measurements = MeasurementDB.get_measurements_for_image(image_id)

        if measurement_category:
            category = measurement_category.lower()
            if category == 'spore':
                measurements = [
                    m for m in measurements
                    if (m.get('measurement_type') in (None, '', 'manual', 'spore'))
                ]
            else:
                measurements = [
                    m for m in measurements
                    if (m.get('measurement_type') or '').lower() == category
                ]

        if not measurements:
            return {}

        lengths = [m['length_um'] for m in measurements]
        widths = [m['width_um'] for m in measurements if m['width_um']]

        import numpy as np

        stats = {
            'count': len(lengths),
            'length_mean': np.mean(lengths),
            'length_std': np.std(lengths),
            'length_min': np.min(lengths),
            'length_max': np.max(lengths),
            'length_p5': np.percentile(lengths, 5),
            'length_p95': np.percentile(lengths, 95),
        }

        if widths:
            ratios = [l/w for l, w in zip(lengths, widths) if w > 0]
            stats.update({
                'width_mean': np.mean(widths),
                'width_std': np.std(widths),
                'width_min': np.min(widths),
                'width_max': np.max(widths),
                'width_p5': np.percentile(widths, 5),
                'width_p95': np.percentile(widths, 95),
                'ratio_mean': np.mean(ratios),
                'ratio_min': np.min(ratios),
                'ratio_max': np.max(ratios),
                'ratio_p5': np.percentile(ratios, 5),
                'ratio_p95': np.percentile(ratios, 95),
            })

        return stats

    @staticmethod
    def delete_measurement(measurement_id: int):
        """Delete a measurement by ID"""
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('DELETE FROM spore_measurements WHERE id = ?', (measurement_id,))

        conn.commit()
        conn.close()


class ReferenceDB:
    """Handle reference spore size values."""

    @staticmethod
    def get_reference(genus: str, species: str, source: str = None, mount_medium: str = None) -> Optional[dict]:
        conn = get_reference_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if source and mount_medium:
            cursor.execute('''
                SELECT * FROM reference_values
                WHERE genus = ? AND species = ? AND source = ? AND mount_medium = ?
                ORDER BY updated_at DESC
                LIMIT 1
            ''', (genus, species, source, mount_medium))
        elif source:
            cursor.execute('''
                SELECT * FROM reference_values
                WHERE genus = ? AND species = ? AND source = ?
                ORDER BY updated_at DESC
                LIMIT 1
            ''', (genus, species, source))
        else:
            cursor.execute('''
                SELECT * FROM reference_values
                WHERE genus = ? AND species = ?
                ORDER BY updated_at DESC
                LIMIT 1
            ''', (genus, species))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def set_reference(values: dict):
        conn = get_reference_connection()
        cursor = conn.cursor()

        cursor.execute('''
            DELETE FROM reference_values
            WHERE genus = ? AND species = ?
              AND (source = ? OR (? IS NULL AND source IS NULL))
              AND (mount_medium = ? OR (? IS NULL AND mount_medium IS NULL))
        ''', (
            values.get("genus"),
            values.get("species"),
            values.get("source"),
            values.get("source"),
            values.get("mount_medium"),
            values.get("mount_medium")
        ))

        cursor.execute('''
            INSERT INTO reference_values (
                genus, species, source, mount_medium,
                length_min, length_p05, length_p50, length_p95, length_max, length_avg,
                width_min, width_p05, width_p50, width_p95, width_max, width_avg,
                q_min, q_p50, q_max, q_avg
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            values.get("genus"),
            values.get("species"),
            values.get("source"),
            values.get("mount_medium"),
            values.get("length_min"),
            values.get("length_p05"),
            values.get("length_p50"),
            values.get("length_p95"),
            values.get("length_max"),
            values.get("length_avg"),
            values.get("width_min"),
            values.get("width_p05"),
            values.get("width_p50"),
            values.get("width_p95"),
            values.get("width_max"),
            values.get("width_avg"),
            values.get("q_min"),
            values.get("q_p50"),
            values.get("q_max"),
            values.get("q_avg")
        ))

        conn.commit()
        conn.close()

    @staticmethod
    def list_genera(prefix: str = "") -> List[str]:
        conn = get_reference_connection()
        cursor = conn.cursor()
        if prefix:
            cursor.execute('''
                SELECT DISTINCT genus FROM reference_values
                WHERE genus LIKE ?
                ORDER BY genus
            ''', (f"{prefix}%",))
        else:
            cursor.execute('''
                SELECT DISTINCT genus FROM reference_values
                ORDER BY genus
            ''')
        rows = cursor.fetchall()
        conn.close()
        return [row[0] for row in rows if row and row[0]]

    @staticmethod
    def list_species(genus: str, prefix: str = "") -> List[str]:
        conn = get_reference_connection()
        cursor = conn.cursor()
        if prefix:
            cursor.execute('''
                SELECT DISTINCT species FROM reference_values
                WHERE genus = ? AND species LIKE ?
                ORDER BY species
            ''', (genus, f"{prefix}%"))
        else:
            cursor.execute('''
                SELECT DISTINCT species FROM reference_values
                WHERE genus = ?
                ORDER BY species
            ''', (genus,))
        rows = cursor.fetchall()
        conn.close()
        return [row[0] for row in rows if row and row[0]]

    @staticmethod
    def list_sources(genus: str, species: str, prefix: str = "") -> List[str]:
        conn = get_reference_connection()
        cursor = conn.cursor()
        if prefix:
            cursor.execute('''
                SELECT DISTINCT source FROM reference_values
                WHERE genus = ? AND species = ? AND source LIKE ?
                ORDER BY source
            ''', (genus, species, f"{prefix}%"))
        else:
            cursor.execute('''
                SELECT DISTINCT source FROM reference_values
                WHERE genus = ? AND species = ?
                ORDER BY source
            ''', (genus, species))
        rows = cursor.fetchall()
        conn.close()
        return [row[0] for row in rows if row and row[0]]

    @staticmethod
    def list_mount_mediums(genus: str, species: str, source: str, prefix: str = "") -> List[str]:
        conn = get_reference_connection()
        cursor = conn.cursor()
        if prefix:
            cursor.execute('''
                SELECT DISTINCT mount_medium FROM reference_values
                WHERE genus = ? AND species = ? AND source = ? AND mount_medium LIKE ?
                ORDER BY mount_medium
            ''', (genus, species, source, f"{prefix}%"))
        else:
            cursor.execute('''
                SELECT DISTINCT mount_medium FROM reference_values
                WHERE genus = ? AND species = ? AND source = ?
                ORDER BY mount_medium
            ''', (genus, species, source))
        rows = cursor.fetchall()
        conn.close()
        return [row[0] for row in rows if row and row[0]]


class SettingsDB:
    """Store simple key/value settings."""

    @staticmethod
    def get_setting(key: str, default: str = None) -> str:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
        row = cursor.fetchone()
        conn.close()
        return row['value'] if row else default

    @staticmethod
    def set_setting(key: str, value: str) -> None:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        ''', (key, value))
        conn.commit()
        conn.close()

    @staticmethod
    def get_list_setting(key: str, default: list) -> list:
        raw = SettingsDB.get_setting(key)
        if not raw:
            return default
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return default
        return data if isinstance(data, list) else default

    @staticmethod
    def set_list_setting(key: str, values: list) -> None:
        SettingsDB.set_setting(key, json.dumps(values))

    @staticmethod
    def get_profile() -> dict:
        return {
            "name": SettingsDB.get_setting("profile_name", ""),
            "email": SettingsDB.get_setting("profile_email", "")
        }

    @staticmethod
    def set_profile(name: str, email: str) -> None:
        SettingsDB.set_setting("profile_name", name or "")
        SettingsDB.set_setting("profile_email", email or "")


class CalibrationDB:
    """Handle calibration database operations for microscope objectives."""

    @staticmethod
    def add_calibration(
        objective_key: str,
        microns_per_pixel: float,
        calibration_date: str = None,
        microns_per_pixel_std: float = None,
        confidence_interval_low: float = None,
        confidence_interval_high: float = None,
        num_measurements: int = None,
        measurements_json: str = None,
        image_filepath: str = None,
        notes: str = None,
        set_active: bool = True,
    ) -> int:
        """Add a new calibration record and return its ID."""
        conn = get_connection()
        cursor = conn.cursor()

        if calibration_date is None:
            calibration_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # If setting as active, deactivate other calibrations for this objective
        if set_active:
            cursor.execute(
                "UPDATE calibrations SET is_active = 0 WHERE objective_key = ?",
                (objective_key,)
            )

        cursor.execute('''
            INSERT INTO calibrations (
                objective_key, calibration_date, microns_per_pixel,
                microns_per_pixel_std, confidence_interval_low, confidence_interval_high,
                num_measurements, measurements_json, image_filepath, notes, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            objective_key, calibration_date, microns_per_pixel,
            microns_per_pixel_std, confidence_interval_low, confidence_interval_high,
            num_measurements, measurements_json, image_filepath, notes,
            1 if set_active else 0
        ))

        calibration_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return calibration_id

    @staticmethod
    def get_calibration(calibration_id: int) -> Optional[dict]:
        """Get a single calibration by ID."""
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM calibrations WHERE id = ?", (calibration_id,))
        row = cursor.fetchone()
        conn.close()

        return dict(row) if row else None

    @staticmethod
    def get_calibrations_for_objective(objective_key: str) -> List[dict]:
        """Get all calibrations for an objective, ordered by date descending."""
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('''
            SELECT * FROM calibrations
            WHERE objective_key = ?
            ORDER BY calibration_date DESC
        ''', (objective_key,))

        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    @staticmethod
    def get_active_calibration(objective_key: str) -> Optional[dict]:
        """Get the active calibration for an objective."""
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('''
            SELECT * FROM calibrations
            WHERE objective_key = ? AND is_active = 1
            ORDER BY calibration_date DESC
            LIMIT 1
        ''', (objective_key,))

        row = cursor.fetchone()
        conn.close()

        return dict(row) if row else None

    @staticmethod
    def get_active_calibration_id(objective_key: str) -> Optional[int]:
        """Get the active calibration ID for an objective, or None if not set."""
        cal = CalibrationDB.get_active_calibration(objective_key)
        return cal.get("id") if cal else None

    @staticmethod
    def set_active_calibration(calibration_id: int) -> None:
        """Set a calibration as active, deactivating others for the same objective."""
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get the objective key for this calibration
        cursor.execute("SELECT objective_key FROM calibrations WHERE id = ?", (calibration_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return

        objective_key = row["objective_key"]

        # Deactivate all calibrations for this objective
        cursor.execute(
            "UPDATE calibrations SET is_active = 0 WHERE objective_key = ?",
            (objective_key,)
        )

        # Activate the specified calibration
        cursor.execute(
            "UPDATE calibrations SET is_active = 1 WHERE id = ?",
            (calibration_id,)
        )

        conn.commit()
        conn.close()

    @staticmethod
    def get_calibration_history(objective_key: str) -> List[dict]:
        """Get calibration history with % difference from the first calibration."""
        calibrations = CalibrationDB.get_calibrations_for_objective(objective_key)
        if not calibrations:
            return []

        # Sort by date ascending to find the first calibration
        sorted_by_date = sorted(calibrations, key=lambda c: c.get("calibration_date", ""))
        first_calibration = sorted_by_date[0] if sorted_by_date else None
        first_value = first_calibration.get("microns_per_pixel") if first_calibration else None

        history = []
        for cal in calibrations:
            cal_copy = dict(cal)
            if first_value and first_value > 0:
                current_value = cal.get("microns_per_pixel", 0)
                if current_value and cal["id"] != first_calibration["id"]:
                    diff_percent = ((current_value - first_value) / first_value) * 100
                    cal_copy["diff_from_first_percent"] = diff_percent
                else:
                    cal_copy["diff_from_first_percent"] = None  # First calibration has no diff
            else:
                cal_copy["diff_from_first_percent"] = None
            history.append(cal_copy)

        return history

    @staticmethod
    def delete_calibration(calibration_id: int) -> None:
        """Delete a calibration by ID."""
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("DELETE FROM calibrations WHERE id = ?", (calibration_id,))

        conn.commit()
        conn.close()

    @staticmethod
    def get_images_using_objective(objective_key: str) -> List[dict]:
        """Get all images that use a specific objective."""
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('''
            SELECT i.*, o.id AS observation_id, o.genus, o.species, o.date
            FROM images i
            LEFT JOIN observations o ON i.observation_id = o.id
            WHERE i.objective_name = ?
        ''', (objective_key,))

        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    @staticmethod
    def get_images_by_calibration(calibration_id: int) -> List[dict]:
        """Get all images that used a specific calibration."""
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('''
            SELECT i.*, o.id AS observation_id, o.genus, o.species, o.common_name, o.date,
                   (SELECT COUNT(*) FROM spore_measurements WHERE image_id = i.id) AS measurement_count
            FROM images i
            LEFT JOIN observations o ON i.observation_id = o.id
            WHERE i.calibration_id = ?
            ORDER BY i.created_at DESC
        ''', (calibration_id,))

        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    @staticmethod
    def get_calibration_usage_summary(objective_key: str) -> List[dict]:
        """Get summary of how many observations/images/measurements use each calibration for an objective."""
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('''
            SELECT
                c.id AS calibration_id,
                c.calibration_date,
                c.microns_per_pixel,
                c.is_active,
                COUNT(DISTINCT i.observation_id) AS observation_count,
                COUNT(DISTINCT i.id) AS image_count,
                COALESCE(SUM(
                    (SELECT COUNT(*) FROM spore_measurements WHERE image_id = i.id)
                ), 0) AS measurement_count
            FROM calibrations c
            LEFT JOIN images i ON i.calibration_id = c.id
            WHERE c.objective_key = ?
            GROUP BY c.id
            ORDER BY c.calibration_date DESC
        ''', (objective_key,))

        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    @staticmethod
    def recalculate_measurements_for_objective(
        objective_key: str,
        old_scale: float,
        new_scale: float
    ) -> int:
        """Recalculate all measurements for images using an objective.

        Returns the number of measurements updated.
        """
        if old_scale <= 0 or new_scale <= 0:
            return 0

        scale_ratio = new_scale / old_scale

        conn = get_connection()
        cursor = conn.cursor()

        # Get all image IDs using this objective
        cursor.execute(
            "SELECT id FROM images WHERE objective_name = ?",
            (objective_key,)
        )
        image_ids = [row[0] for row in cursor.fetchall()]

        if not image_ids:
            conn.close()
            return 0

        # Update scale on images
        cursor.execute(
            "UPDATE images SET scale_microns_per_pixel = ? WHERE objective_name = ?",
            (new_scale, objective_key)
        )

        # Update measurements
        placeholders = ",".join("?" * len(image_ids))
        cursor.execute(f'''
            UPDATE spore_measurements
            SET length_um = length_um * ?,
                width_um = CASE WHEN width_um IS NOT NULL THEN width_um * ? ELSE NULL END
            WHERE image_id IN ({placeholders})
        ''', [scale_ratio, scale_ratio] + image_ids)

        updated_count = cursor.rowcount
        conn.commit()
        conn.close()

        return updated_count

    @staticmethod
    def recalculate_measurements_for_calibration(
        calibration_id: int,
        new_calibration_id: int,
        new_scale: float
    ) -> int:
        """Recalculate measurements for images that used a specific calibration.

        Updates the images to use the new calibration and recalculates their measurements.
        Returns the number of measurements updated.
        """
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get images using the old calibration
        cursor.execute(
            "SELECT id, scale_microns_per_pixel FROM images WHERE calibration_id = ?",
            (calibration_id,)
        )
        images = cursor.fetchall()

        if not images:
            conn.close()
            return 0

        total_updated = 0

        for img in images:
            image_id = img["id"]
            old_scale = img["scale_microns_per_pixel"] or 0

            if old_scale <= 0 or new_scale <= 0:
                continue

            scale_ratio = new_scale / old_scale

            # Update the image's calibration and scale
            cursor.execute(
                "UPDATE images SET calibration_id = ?, scale_microns_per_pixel = ? WHERE id = ?",
                (new_calibration_id, new_scale, image_id)
            )

            # Update measurements for this image
            cursor.execute('''
                UPDATE spore_measurements
                SET length_um = length_um * ?,
                    width_um = CASE WHEN width_um IS NOT NULL THEN width_um * ? ELSE NULL END
                WHERE image_id = ?
            ''', (scale_ratio, scale_ratio, image_id))

            total_updated += cursor.rowcount

        conn.commit()
        conn.close()

        return total_updated
