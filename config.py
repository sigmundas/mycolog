"""Application configuration settings."""
from pathlib import Path
from platformdirs import user_data_dir

# Database settings
DB_NAME = "mushrooms.db"
_app_dir = Path(user_data_dir("MycoLog", appauthor=False, roaming=True))
DB_PATH = _app_dir / DB_NAME

# UI settings
WINDOW_TITLE = "MycoLog"
WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 800
IMAGE_DISPLAY_WIDTH = 1100
IMAGE_DISPLAY_HEIGHT = 700

# Measurement defaults
DEFAULT_SCALE = 0.5  # microns per pixel

# Supported image formats
SUPPORTED_FORMATS = "Images (*.png *.jpg *.jpeg *.tif *.tiff *.NEF *.ORF)"
RAW_FORMATS = ('.nef', '.orf', '.cr2', '.arw')
