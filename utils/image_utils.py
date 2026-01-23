"""Image processing utilities."""
from pathlib import Path
from PIL import Image
from PySide6.QtGui import QPixmap
from typing import Optional


def load_image(image_path: str) -> Optional[Image.Image]:
    """
    Load an image from disk.

    Args:
        image_path: Path to the image file

    Returns:
        PIL Image object or None if loading fails
    """
    try:
        return Image.open(image_path)
    except Exception as e:
        print(f"Error loading image {image_path}: {e}")
        return None


def scale_image(pixmap: QPixmap, max_width: int, max_height: int) -> QPixmap:
    """
    Scale a QPixmap to fit within specified dimensions while maintaining aspect ratio.

    Args:
        pixmap: The QPixmap to scale
        max_width: Maximum width
        max_height: Maximum height

    Returns:
        Scaled QPixmap
    """
    from PySide6.QtCore import Qt
    return pixmap.scaled(max_width, max_height, Qt.KeepAspectRatio)


def is_raw_format(image_path: str) -> bool:
    """
    Check if the image is a RAW format.

    Args:
        image_path: Path to the image file

    Returns:
        True if the file is a RAW format
    """
    from config import RAW_FORMATS
    return Path(image_path).suffix.lower() in RAW_FORMATS
