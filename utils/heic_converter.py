"""HEIC/HEIF conversion helper."""
from pathlib import Path


def convert_heic_to_jpeg(filepath, output_dir):
    """Convert a HEIC/HEIF image to JPEG in output_dir.

    Returns the converted JPEG path as a string, or None on failure.
    """
    try:
        import pillow_heif
        from PIL import Image, ImageOps
    except ImportError:
        return None

    try:
        pillow_heif.register_heif_opener()
        try:
            heif_file = pillow_heif.open_heif(filepath)
            image = heif_file.to_pillow()
        except Exception:
            image = Image.open(filepath)

        # Apply EXIF orientation to pixels so portrait photos remain portrait
        # on services that ignore EXIF orientation during display.
        image = ImageOps.exif_transpose(image).convert("RGB")

        exif_bytes = None
        try:
            exif = image.getexif()
            if exif:
                # Orientation tag: reset after transposing.
                exif[274] = 1
                exif_bytes = exif.tobytes()
        except Exception:
            exif_bytes = None

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        base_name = Path(filepath).stem
        output_path = output_dir / f"{base_name}.jpg"
        counter = 1
        while output_path.exists():
            output_path = output_dir / f"{base_name}_{counter}.jpg"
            counter += 1
        if exif_bytes:
            image.save(output_path, "JPEG", quality=95, exif=exif_bytes)
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
