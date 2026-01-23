"""HEIC/HEIF conversion helper."""
from pathlib import Path


def convert_heic_to_jpeg(filepath, output_dir):
    """Convert a HEIC/HEIF image to JPEG in output_dir.

    Returns the converted JPEG path as a string, or None on failure.
    """
    try:
        import pillow_heif
        from PIL import Image
    except ImportError:
        return None

    try:
        pillow_heif.register_heif_opener()
        exif_data = None
        try:
            heif_file = pillow_heif.open_heif(filepath)
            exif_data = heif_file.info.get("exif")
            image = heif_file.to_pillow()
        except Exception:
            image = Image.open(filepath)
            exif_data = image.info.get("exif")
        if not exif_data:
            try:
                exif_data = image.getexif().tobytes()
            except Exception:
                exif_data = None
        image = image.convert("RGB")
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        base_name = Path(filepath).stem
        output_path = output_dir / f"{base_name}.jpg"
        counter = 1
        while output_path.exists():
            output_path = output_dir / f"{base_name}_{counter}.jpg"
            counter += 1
        if exif_data:
            image.save(output_path, "JPEG", quality=95, exif=exif_data)
        else:
            image.save(output_path, "JPEG", quality=95)
        return str(output_path)
    except Exception:
        return None


def maybe_convert_heic(filepath, output_dir):
    """Convert HEIC/HEIF files, otherwise return original path."""
    suffix = Path(filepath).suffix.lower()
    if suffix in (".heic", ".heif"):
        return convert_heic_to_jpeg(filepath, output_dir)
    return filepath
