"""Database migration script to update schema."""
import sqlite3
import shutil
from database.schema import get_database_path


def backup_database():
    """Create a backup of the database."""
    database_path = get_database_path()
    if database_path.exists():
        backup_path = database_path.with_suffix('.db.backup')
        shutil.copy2(database_path, backup_path)
        print(f"Backup created at: {backup_path}")
        return True
    return False


def migrate_database():
    """Migrate old database schema to new schema."""
    database_path = get_database_path()
    if not database_path.exists():
        print("No database found - will create new one")
        return

    # Backup first
    backup_database()

    conn = sqlite3.connect(database_path)
    cursor = conn.cursor()

    # Check if old schema exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='spore_measurements'")
    if cursor.fetchone():
        # Check if it has the old schema
        cursor.execute("PRAGMA table_info(spore_measurements)")
        columns = [col[1] for col in cursor.fetchall()]

        if 'image_path' in columns and 'image_id' not in columns:
            print("Found old schema with 'image_path' - migrating to new schema...")

            # Create new tables
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    location TEXT,
                    habitat TEXT,
                    species_guess TEXT,
                    notes TEXT,
                    inaturalist_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS images_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    observation_id INTEGER,
                    filepath TEXT NOT NULL,
                    image_type TEXT CHECK(image_type IN ('field', 'microscope')),
                    objective_name TEXT,
                    scale_microns_per_pixel REAL,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (observation_id) REFERENCES observations(id)
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS spore_measurements_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    image_id INTEGER NOT NULL,
                    length_um REAL NOT NULL,
                    width_um REAL,
                    measurement_type TEXT DEFAULT 'manual',
                    notes TEXT,
                    measured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (image_id) REFERENCES images_new(id)
                )
            ''')

            # Migrate data
            # Get all old measurements with their image paths
            cursor.execute('SELECT image_path, length_um, width_um, scale, timestamp FROM spore_measurements')
            old_measurements = cursor.fetchall()

            # Group by image_path
            images_map = {}
            for image_path, length_um, width_um, scale, timestamp in old_measurements:
                if image_path not in images_map:
                    # Create image record
                    cursor.execute('''
                        INSERT INTO images_new (filepath, image_type, scale_microns_per_pixel, created_at)
                        VALUES (?, 'microscope', ?, ?)
                    ''', (image_path, scale, timestamp))
                    images_map[image_path] = cursor.lastrowid

                # Insert measurement
                image_id = images_map[image_path]
                cursor.execute('''
                    INSERT INTO spore_measurements_new (image_id, length_um, width_um, measurement_type, measured_at)
                    VALUES (?, ?, ?, 'manual', ?)
                ''', (image_id, length_um, width_um, timestamp))

            # Drop old tables and rename new ones
            cursor.execute('DROP TABLE IF EXISTS spore_measurements')
            cursor.execute('DROP TABLE IF EXISTS images')
            cursor.execute('ALTER TABLE spore_measurements_new RENAME TO spore_measurements')
            cursor.execute('ALTER TABLE images_new RENAME TO images')

            print(f"Migration complete! Migrated {len(old_measurements)} measurements from {len(images_map)} images")
        else:
            print("Database already has new schema - no migration needed")
    else:
        print("No spore_measurements table found - will create new schema")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    migrate_database()
