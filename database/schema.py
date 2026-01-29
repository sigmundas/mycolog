"""Database schema and initialization"""
import json
import sqlite3
from pathlib import Path
from platformdirs import user_data_dir

_app_dir = Path(user_data_dir("MycoLog", appauthor=False, roaming=True))
DATABASE_PATH = _app_dir / "mushrooms.db"
REFERENCE_DATABASE_PATH = _app_dir / "reference_values.db"
SETTINGS_PATH = _app_dir / "app_settings.json"

DEFAULT_OBJECTIVES = {
    "10X": {
        "name": "10X/0.25 Plan achro",
        "magnification": "10X",
        "microns_per_pixel": 0.314,
        "notes": "Leica DM2000, Olympus MFT 1:1",
    },
    "40X": {
        "name": "40X/0.75 Plan fluor",
        "magnification": "40X",
        "microns_per_pixel": 0.07875,
        "notes": "Leica DM2000, Olympus MFT 1:1",
    },
    "100X": {
        "name": "100X/1.25 Plan achro Oil",
        "magnification": "100X",
        "microns_per_pixel": 0.0315,
        "notes": "Leica DM2000, Olympus MFT 1:1",
    },
}


def get_app_dir() -> Path:
    return _app_dir


def get_objectives_path() -> Path:
    return _app_dir / "objectives.json"


def get_last_objective_path() -> Path:
    return _app_dir / "last_objective.json"


def load_objectives() -> dict:
    path = get_objectives_path()
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                return data
        except (OSError, json.JSONDecodeError):
            pass
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(DEFAULT_OBJECTIVES, handle, indent=2)
    return dict(DEFAULT_OBJECTIVES)


def save_objectives(objectives: dict) -> None:
    path = get_objectives_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(objectives, handle, indent=2)

def _load_app_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return {}
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}

def get_app_settings() -> dict:
    return _load_app_settings()

def save_app_settings(settings: dict) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as handle:
        json.dump(settings, handle, indent=2)

def update_app_settings(updates: dict) -> dict:
    settings = _load_app_settings()
    settings.update(updates)
    save_app_settings(settings)
    return settings

def get_database_path() -> Path:
    settings = _load_app_settings()
    folder = settings.get("database_folder")
    if folder:
        return Path(folder) / "mushrooms.db"
    path = settings.get("database_path")
    return Path(path) if path else DATABASE_PATH

def get_reference_database_path() -> Path:
    settings = _load_app_settings()
    folder = settings.get("database_folder")
    if folder:
        return Path(folder) / "reference_values.db"
    path = settings.get("reference_database_path")
    if path:
        return Path(path)
    return get_database_path().parent / "reference_values.db"

def get_images_dir() -> Path:
    settings = _load_app_settings()
    path = settings.get("images_dir")
    if path:
        return Path(path)
    return get_database_path().parent / "images"

def get_connection():
    """Get a connection to the main observation database."""
    db_path = get_database_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(db_path)

def get_reference_connection():
    """Get a connection to the reference values database."""
    ref_path = get_reference_database_path()
    ref_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(ref_path)

def init_reference_database():
    """Initialize the reference values database."""
    ref_path = get_reference_database_path()
    ref_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(ref_path)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reference_values (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            genus TEXT NOT NULL,
            species TEXT NOT NULL,
            source TEXT,
            mount_medium TEXT,
            length_min REAL,
            length_p05 REAL,
            length_p50 REAL,
            length_p95 REAL,
            length_max REAL,
            length_avg REAL,
            width_min REAL,
            width_p05 REAL,
            width_p50 REAL,
            width_p95 REAL,
            width_max REAL,
            width_avg REAL,
            q_min REAL,
            q_p50 REAL,
            q_max REAL,
            q_avg REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()

    _ensure_reference_columns()
    _migrate_reference_values()

def _ensure_reference_columns():
    """Ensure new percentile columns exist in the reference values table."""
    conn = sqlite3.connect(get_reference_database_path())
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(reference_values)")
    existing = {row[1] for row in cursor.fetchall()}
    to_add = {
        "length_p05": "REAL",
        "length_p50": "REAL",
        "length_p95": "REAL",
        "width_p05": "REAL",
        "width_p50": "REAL",
        "width_p95": "REAL",
        "q_p50": "REAL",
    }
    for col, col_type in to_add.items():
        if col not in existing:
            cursor.execute(f"ALTER TABLE reference_values ADD COLUMN {col} {col_type}")
    conn.commit()
    conn.close()

def _migrate_reference_values():
    """Copy legacy reference values from the main database if needed."""
    ref_conn = sqlite3.connect(get_reference_database_path())
    ref_cursor = ref_conn.cursor()
    ref_cursor.execute('SELECT COUNT(*) FROM reference_values')
    ref_count = ref_cursor.fetchone()[0]
    ref_conn.close()

    if ref_count:
        return

    main_conn = sqlite3.connect(get_database_path())
    main_cursor = main_conn.cursor()
    main_cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type = 'table' AND name = 'reference_values'
    """)
    if not main_cursor.fetchone():
        main_conn.close()
        return

    main_cursor.execute("PRAGMA table_info(reference_values)")
    main_cols = {row[1] for row in main_cursor.fetchall()}
    has_p05 = "length_p05" in main_cols
    has_p50 = "length_p50" in main_cols
    has_p95 = "length_p95" in main_cols
    has_wp05 = "width_p05" in main_cols
    has_wp50 = "width_p50" in main_cols
    has_wp95 = "width_p95" in main_cols
    has_qp50 = "q_p50" in main_cols

    if has_p05 or has_p50 or has_p95 or has_wp05 or has_wp50 or has_wp95 or has_qp50:
        main_cursor.execute('''
            SELECT genus, species, source, mount_medium,
                   length_min, length_p05, length_p50, length_p95, length_max, length_avg,
                   width_min, width_p05, width_p50, width_p95, width_max, width_avg,
                   q_min, q_p50, q_max, q_avg, updated_at
            FROM reference_values
        ''')
    else:
        main_cursor.execute('''
            SELECT genus, species, source, mount_medium,
                   length_min, NULL, NULL, NULL, length_max, length_avg,
                   width_min, NULL, NULL, NULL, width_max, width_avg,
                   q_min, NULL, q_max, q_avg, updated_at
            FROM reference_values
        ''')
    rows = main_cursor.fetchall()
    main_conn.close()

    if not rows:
        return

    ref_conn = sqlite3.connect(get_reference_database_path())
    ref_cursor = ref_conn.cursor()
    ref_cursor.executemany('''
        INSERT INTO reference_values (
            genus, species, source, mount_medium,
            length_min, length_p05, length_p50, length_p95, length_max, length_avg,
            width_min, width_p05, width_p50, width_p95, width_max, width_avg,
            q_min, q_p50, q_max, q_avg, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', rows)
    ref_conn.commit()
    ref_conn.close()

def init_database():
    """Initialize the database with required tables"""
    db_path = get_database_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Observations table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            location TEXT,
            habitat TEXT,
            genus TEXT,
            species TEXT,
            common_name TEXT,
            species_guess TEXT,
            uncertain INTEGER DEFAULT 0,
            notes TEXT,
            inaturalist_id INTEGER,
            folder_path TEXT,
            spore_statistics TEXT,
            auto_threshold REAL,
            author TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Add spore_statistics column if it doesn't exist
    try:
        cursor.execute('ALTER TABLE observations ADD COLUMN spore_statistics TEXT')
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Add auto_threshold column if it doesn't exist
    try:
        cursor.execute('ALTER TABLE observations ADD COLUMN auto_threshold REAL')
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Add author column if it doesn't exist
    try:
        cursor.execute('ALTER TABLE observations ADD COLUMN author TEXT')
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Settings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')

    # Add genus column if it doesn't exist (migration for existing DBs)
    try:
        cursor.execute('ALTER TABLE observations ADD COLUMN genus TEXT')
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Add species column if it doesn't exist
    try:
        cursor.execute('ALTER TABLE observations ADD COLUMN species TEXT')
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Add common_name column if it doesn't exist
    try:
        cursor.execute('ALTER TABLE observations ADD COLUMN common_name TEXT')
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Add uncertain column if it doesn't exist
    try:
        cursor.execute('ALTER TABLE observations ADD COLUMN uncertain INTEGER DEFAULT 0')
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Add folder_path column if it doesn't exist
    try:
        cursor.execute('ALTER TABLE observations ADD COLUMN folder_path TEXT')
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Add GPS latitude column if it doesn't exist
    try:
        cursor.execute('ALTER TABLE observations ADD COLUMN gps_latitude REAL')
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Add GPS longitude column if it doesn't exist
    try:
        cursor.execute('ALTER TABLE observations ADD COLUMN gps_longitude REAL')
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Images table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            observation_id INTEGER,
            filepath TEXT NOT NULL,
            image_type TEXT CHECK(image_type IN ('field', 'microscope')),
            micro_category TEXT,
            objective_name TEXT,
            scale_microns_per_pixel REAL,
            mount_medium TEXT,
            sample_type TEXT,
            contrast TEXT,
            measure_color TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (observation_id) REFERENCES observations(id)
        )
    ''')

    # Add micro_category column if it doesn't exist (migration for existing DBs)
    try:
        cursor.execute('ALTER TABLE images ADD COLUMN micro_category TEXT')
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Add objective_name column if it doesn't exist
    try:
        cursor.execute('ALTER TABLE images ADD COLUMN objective_name TEXT')
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Add mount_medium column if it doesn't exist
    try:
        cursor.execute('ALTER TABLE images ADD COLUMN mount_medium TEXT')
    except sqlite3.OperationalError:
        pass

    # Add sample_type column if it doesn't exist
    try:
        cursor.execute('ALTER TABLE images ADD COLUMN sample_type TEXT')
    except sqlite3.OperationalError:
        pass

    # Add contrast column if it doesn't exist
    try:
        cursor.execute('ALTER TABLE images ADD COLUMN contrast TEXT')
    except sqlite3.OperationalError:
        pass

    # Add measure_color column if it doesn't exist
    try:
        cursor.execute('ALTER TABLE images ADD COLUMN measure_color TEXT')
    except sqlite3.OperationalError:
        pass  # Column already exists
    
    # Spore measurements table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS spore_measurements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image_id INTEGER NOT NULL,
            length_um REAL NOT NULL,
            width_um REAL,
            measurement_type TEXT DEFAULT 'manual',
            gallery_rotation INTEGER DEFAULT 0,
            p1_x REAL,
            p1_y REAL,
            p2_x REAL,
            p2_y REAL,
            p3_x REAL,
            p3_y REAL,
            p4_x REAL,
            p4_y REAL,
            notes TEXT,
            measured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (image_id) REFERENCES images(id)
        )
    ''')

    # Add gallery_rotation column if it doesn't exist
    try:
        cursor.execute('ALTER TABLE spore_measurements ADD COLUMN gallery_rotation INTEGER DEFAULT 0')
    except sqlite3.OperationalError:
        pass

    # Thumbnails for efficient loading and ML training
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS thumbnails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image_id INTEGER NOT NULL,
            size_preset TEXT NOT NULL,
            filepath TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (image_id) REFERENCES images(id),
            UNIQUE(image_id, size_preset)
        )
    ''')

    # Spore annotations for ML training (bounding boxes + measurements)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS spore_annotations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image_id INTEGER NOT NULL,
            measurement_id INTEGER,
            spore_number INTEGER,
            bbox_x INTEGER,
            bbox_y INTEGER,
            bbox_width INTEGER,
            bbox_height INTEGER,
            center_x REAL,
            center_y REAL,
            length_um REAL,
            width_um REAL,
            rotation_angle REAL,
            annotation_source TEXT DEFAULT 'manual',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (image_id) REFERENCES images(id),
            FOREIGN KEY (measurement_id) REFERENCES spore_measurements(id)
        )
    ''')

    conn.commit()
    conn.close()

    init_reference_database()
    print(f"Database initialized at {db_path}")

if __name__ == "__main__":
    init_database()
