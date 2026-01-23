"""Reset the database to a fresh state.

WARNING: This will delete all your measurements!
A backup will be created before deletion.
"""
import shutil

from database.schema import get_database_path


def reset_database():
    """Delete the database and create a fresh one."""
    database_path = get_database_path()
    if database_path.exists():
        # Create backup
        backup_path = database_path.with_suffix('.db.old')
        shutil.copy2(database_path, backup_path)
        print(f"Backup created at: {backup_path}")

        # Delete database
        database_path.unlink()
        print("Deleted old database")

    # Initialize fresh database
    from database.schema import init_database
    init_database()
    print("\nFresh database created successfully!")
    print("\nYou can now run the application: python main.py")


if __name__ == "__main__":
    response = input("This will DELETE all measurements and reset the database. Continue? (yes/no): ")
    if response.lower() in ['yes', 'y']:
        reset_database()
    else:
        print("Cancelled.")
