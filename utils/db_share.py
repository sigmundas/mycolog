"""Helpers for exporting/importing shared database bundles."""
import sqlite3
import zipfile
import tempfile
import shutil
from pathlib import Path

from database.schema import DATABASE_PATH, get_connection


def _safe_copy(src: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.exists():
        shutil.copy2(src, dest)
    return dest


def export_database_bundle(zip_path: str) -> None:
    """Export the database and data folders to a zip file."""
    db_dir = DATABASE_PATH.parent
    images_dir = db_dir / "images"
    thumbs_dir = db_dir / "thumbnails"
    db_path = DATABASE_PATH

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if db_path.exists():
            zf.write(db_path, arcname="mushrooms.db")
        if images_dir.exists():
            for path in images_dir.rglob("*"):
                if path.is_file():
                    zf.write(path, arcname=str(Path("images") / path.relative_to(images_dir)))
        if thumbs_dir.exists():
            for path in thumbs_dir.rglob("*"):
                if path.is_file():
                    zf.write(path, arcname=str(Path("thumbnails") / path.relative_to(thumbs_dir)))


def import_database_bundle(zip_path: str) -> dict:
    """Import observations/images/measurements from a bundle into the current DB."""
    temp_dir = Path(tempfile.mkdtemp())
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(temp_dir)

        src_db_path = temp_dir / "mushrooms.db"
        if not src_db_path.exists():
            raise FileNotFoundError("No mushrooms.db found in bundle.")

        src_images_dir = temp_dir / "images"
        src_thumbs_dir = temp_dir / "thumbnails"
        dest_db_dir = DATABASE_PATH.parent
        dest_images_dir = dest_db_dir / "images"
        dest_thumbs_dir = dest_db_dir / "thumbnails"

        src_conn = sqlite3.connect(src_db_path)
        src_conn.row_factory = sqlite3.Row
        src_cur = src_conn.cursor()

        dest_conn = get_connection()
        dest_conn.row_factory = sqlite3.Row
        dest_cur = dest_conn.cursor()

        obs_map = {}
        img_map = {}
        meas_map = {}

        src_cur.execute("SELECT * FROM observations ORDER BY id")
        for row in src_cur.fetchall():
            data = dict(row)
            data.pop("id", None)
            columns = [k for k in data.keys()]
            values = [data[k] for k in columns]
            placeholders = ", ".join(["?"] * len(columns))
            dest_cur.execute(
                f"INSERT INTO observations ({', '.join(columns)}) VALUES ({placeholders})",
                values
            )
            obs_map[row["id"]] = dest_cur.lastrowid

        src_cur.execute("SELECT * FROM images ORDER BY id")
        for row in src_cur.fetchall():
            data = dict(row)
            old_image_id = data.pop("id", None)
            old_obs_id = data.get("observation_id")
            if old_obs_id in obs_map:
                data["observation_id"] = obs_map[old_obs_id]

            src_path = Path(data.get("filepath", ""))
            dest_path = None
            if src_path and src_images_dir in src_path.parents:
                rel = src_path.relative_to(src_images_dir)
                dest_path = dest_images_dir / rel
            elif src_path:
                dest_path = dest_images_dir / src_path.name

            if dest_path:
                _safe_copy(src_path, dest_path)
                data["filepath"] = str(dest_path)

            columns = [k for k in data.keys()]
            values = [data[k] for k in columns]
            placeholders = ", ".join(["?"] * len(columns))
            dest_cur.execute(
                f"INSERT INTO images ({', '.join(columns)}) VALUES ({placeholders})",
                values
            )
            img_map[old_image_id] = dest_cur.lastrowid

        src_cur.execute("SELECT * FROM spore_measurements ORDER BY id")
        for row in src_cur.fetchall():
            data = dict(row)
            old_id = data.pop("id", None)
            old_image_id = data.get("image_id")
            if old_image_id in img_map:
                data["image_id"] = img_map[old_image_id]
            columns = [k for k in data.keys()]
            values = [data[k] for k in columns]
            placeholders = ", ".join(["?"] * len(columns))
            dest_cur.execute(
                f"INSERT INTO spore_measurements ({', '.join(columns)}) VALUES ({placeholders})",
                values
            )
            meas_map[old_id] = dest_cur.lastrowid

        src_cur.execute("SELECT * FROM thumbnails ORDER BY id")
        for row in src_cur.fetchall():
            data = dict(row)
            data.pop("id", None)
            old_image_id = data.get("image_id")
            if old_image_id in img_map:
                data["image_id"] = img_map[old_image_id]
            src_thumb = Path(data.get("filepath", ""))
            dest_thumb = None
            if src_thumb and src_thumbs_dir in src_thumb.parents:
                rel = src_thumb.relative_to(src_thumbs_dir)
                dest_thumb = dest_thumbs_dir / rel
            elif src_thumb:
                dest_thumb = dest_thumbs_dir / src_thumb.name
            if dest_thumb:
                _safe_copy(src_thumb, dest_thumb)
                data["filepath"] = str(dest_thumb)
            columns = [k for k in data.keys()]
            values = [data[k] for k in columns]
            placeholders = ", ".join(["?"] * len(columns))
            dest_cur.execute(
                f"INSERT OR REPLACE INTO thumbnails ({', '.join(columns)}) VALUES ({placeholders})",
                values
            )

        src_cur.execute("SELECT * FROM spore_annotations ORDER BY id")
        for row in src_cur.fetchall():
            data = dict(row)
            data.pop("id", None)
            old_image_id = data.get("image_id")
            old_meas_id = data.get("measurement_id")
            if old_image_id in img_map:
                data["image_id"] = img_map[old_image_id]
            if old_meas_id in meas_map:
                data["measurement_id"] = meas_map[old_meas_id]
            columns = [k for k in data.keys()]
            values = [data[k] for k in columns]
            placeholders = ", ".join(["?"] * len(columns))
            dest_cur.execute(
                f"INSERT INTO spore_annotations ({', '.join(columns)}) VALUES ({placeholders})",
                values
            )

        dest_conn.commit()
        return {
            "observations": len(obs_map),
            "images": len(img_map),
            "measurements": len(meas_map)
        }
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
