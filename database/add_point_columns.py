"""Add point coordinate columns to spore_measurements table."""
import sqlite3
from database.schema import get_database_path


def migrate():
    """Add point coordinate columns if they don't exist."""
    database_path = get_database_path()
    if not database_path.exists():
        print("Database doesn't exist yet - no migration needed")
        return

    conn = sqlite3.connect(database_path)
    cursor = conn.cursor()

    # Check if columns already exist
    cursor.execute("PRAGMA table_info(spore_measurements)")
    columns = [row[1] for row in cursor.fetchall()]

    if 'p1_x' in columns:
        print("Point columns already exist - no migration needed")
        conn.close()
        return

    print("Adding point coordinate columns...")

    # Add the new columns
    point_columns = ['p1_x', 'p1_y', 'p2_x', 'p2_y', 'p3_x', 'p3_y', 'p4_x', 'p4_y']
    for col in point_columns:
        cursor.execute(f'ALTER TABLE spore_measurements ADD COLUMN {col} REAL')

    conn.commit()
    conn.close()

    print("Migration complete! Point coordinate columns added.")


if __name__ == "__main__":
    migrate()
