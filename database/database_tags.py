"""Database terms with canonical names and Qt translations."""

import re

from PySide6.QtCore import QCoreApplication


class DatabaseTerms:
    """Translatable database terms for microscopy observations."""
    
    @staticmethod
    def tr(text: str) -> str:
        """Translate text in DatabaseTerms context."""
        return QCoreApplication.translate("DatabaseTerms", text)
    
    # Canonical English names (stored in database)
    CONTRAST_METHODS = ["BF", "DF", "DIC", "Phase"]
    MOUNT_MEDIA = ["Not_set", "Water", "KOH", "NH3", "Melzer", "Glycerine", "Congo_Red", "Cotton_Blue"]
    SAMPLE_TYPES = ["Not_set", "Fresh", "Dried", "Spore_print"]
    MEASURE_CATEGORIES = [
        "Spores", "Field", "Pleurocystidia", 
        "Cheilocystidia", "Caulocystidia", "Other"
    ]
    
    # Display name mappings (for translation)
    CONTRAST_DISPLAY = {
        "BF": "BF", "DF": "DF", "DIC": "DIC", "Phase": "Phase"
    }
    
    MOUNT_DISPLAY = {
        "Not_set": "Not set",
        "Water": "Water",
        "KOH": "KOH",
        "NH3": "NH₃",
        "Melzer": "Melzer",
        "Glycerine": "Glycerine",
        "Congo_Red": "Congo Red",
        "Cotton_Blue": "Cotton Blue"
    }
    
    SAMPLE_DISPLAY = {
        "Not_set": "Not set",
        "Fresh": "Fresh",
        "Dried": "Dried",
        "Spore_print": "Spore print"
    }
    
    MEASURE_DISPLAY = {
        "Spores": "Spores",
        "Field": "Field",
        "Pleurocystidia": "Pleurocystidia",
        "Cheilocystidia": "Cheilocystidia",
        "Caulocystidia": "Caulocystidia",
        "Other": "Other"
    }
    
    @staticmethod
    def _normalize_token(value: str | None) -> str:
        if value is None:
            return ""
        text = str(value).strip().lower()
        if not text:
            return ""
        text = text.translate(str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789"))
        text = text.replace("&", "and")
        text = re.sub(r"[^\w\s-]", "", text)
        text = re.sub(r"[\s_-]+", "", text)
        return text

    @classmethod
    def _build_lookup(cls, display_map: dict[str, str]) -> dict[str, str]:
        lookup: dict[str, str] = {}
        for canonical, display in display_map.items():
            candidates = {
                canonical,
                display,
                canonical.replace("_", " "),
                canonical.replace("_", "-"),
                display.replace(" ", "_"),
            }
            for candidate in candidates:
                norm = cls._normalize_token(candidate)
                if norm:
                    lookup[norm] = canonical
        return lookup

    @staticmethod
    def _fallback_display(value: str | None) -> str:
        if value is None:
            return ""
        return str(value).replace("_", " ").strip()

    @staticmethod
    def _fallback_canonical(value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        return re.sub(r"\s+", "_", text)

    @classmethod
    def canonicalize_contrast(cls, value: str | None) -> str | None:
        if value is None:
            return None
        lookup = cls._build_lookup(cls.CONTRAST_DISPLAY)
        canonical = lookup.get(cls._normalize_token(value))
        return canonical or cls._fallback_canonical(value)

    @classmethod
    def canonicalize_mount(cls, value: str | None) -> str | None:
        if value is None:
            return None
        lookup = cls._build_lookup(cls.MOUNT_DISPLAY)
        canonical = lookup.get(cls._normalize_token(value))
        return canonical or cls._fallback_canonical(value)

    @classmethod
    def canonicalize_sample(cls, value: str | None) -> str | None:
        if value is None:
            return None
        lookup = cls._build_lookup(cls.SAMPLE_DISPLAY)
        canonical = lookup.get(cls._normalize_token(value))
        return canonical or cls._fallback_canonical(value)

    @classmethod
    def canonicalize_measure(cls, value: str | None) -> str | None:
        if value is None:
            return None
        lookup = cls._build_lookup(cls.MEASURE_DISPLAY)
        canonical = lookup.get(cls._normalize_token(value))
        return canonical or cls._fallback_canonical(value)

    @classmethod
    def canonicalize(cls, category: str, value: str | None) -> str | None:
        if category == "contrast":
            return cls.canonicalize_contrast(value)
        if category == "mount":
            return cls.canonicalize_mount(value)
        if category == "sample":
            return cls.canonicalize_sample(value)
        if category == "measure":
            return cls.canonicalize_measure(value)
        return cls._fallback_canonical(value)

    @classmethod
    def custom_to_canonical(cls, value: str | None) -> str | None:
        return cls._fallback_canonical(value)

    @classmethod
    def translate_contrast(cls, canonical_name: str | None) -> str:
        """Get translated display name for contrast method."""
        canonical = cls.canonicalize_contrast(canonical_name)
        display = cls.CONTRAST_DISPLAY.get(canonical or "", cls._fallback_display(canonical_name))
        return cls.tr(display)
    
    @classmethod
    def translate_mount(cls, canonical_name: str | None) -> str:
        """Get translated display name for mount medium."""
        canonical = cls.canonicalize_mount(canonical_name)
        display = cls.MOUNT_DISPLAY.get(canonical or "", cls._fallback_display(canonical_name))
        return cls.tr(display)
    
    @classmethod
    def translate_sample(cls, canonical_name: str | None) -> str:
        """Get translated display name for sample type."""
        canonical = cls.canonicalize_sample(canonical_name)
        display = cls.SAMPLE_DISPLAY.get(canonical or "", cls._fallback_display(canonical_name))
        return cls.tr(display)
    
    @classmethod
    def translate_measure(cls, canonical_name: str | None) -> str:
        """Get translated display name for measure category."""
        canonical = cls.canonicalize_measure(canonical_name)
        display = cls.MEASURE_DISPLAY.get(canonical or "", cls._fallback_display(canonical_name))
        return cls.tr(display)

    @classmethod
    def translate(cls, category: str, canonical_name: str | None) -> str:
        if category == "contrast":
            return cls.translate_contrast(canonical_name)
        if category == "mount":
            return cls.translate_mount(canonical_name)
        if category == "sample":
            return cls.translate_sample(canonical_name)
        if category == "measure":
            return cls.translate_measure(canonical_name)
        return cls.tr(cls._fallback_display(canonical_name))

    @classmethod
    def default_values(cls, category: str) -> list[str]:
        if category == "contrast":
            return list(cls.CONTRAST_METHODS)
        if category == "mount":
            return list(cls.MOUNT_MEDIA)
        if category == "sample":
            return list(cls.SAMPLE_TYPES)
        if category == "measure":
            return list(cls.MEASURE_CATEGORIES)
        return []

    @classmethod
    def setting_key(cls, category: str) -> str:
        mapping = {
            "contrast": "contrast_options",
            "mount": "mount_options",
            "sample": "sample_options",
            "measure": "measure_categories",
        }
        return mapping.get(category, "")

    @classmethod
    def last_used_key(cls, category: str) -> str:
        mapping = {
            "contrast": "last_used_contrast",
            "mount": "last_used_mount",
            "sample": "last_used_sample",
            "measure": "last_used_measure",
        }
        return mapping.get(category, "")

    @classmethod
    def canonicalize_list(cls, category: str, values: list[str] | None) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for value in values or []:
            canonical = cls.canonicalize(category, value)
            if not canonical or canonical in seen:
                continue
            seen.add(canonical)
            cleaned.append(canonical)
        defaults = cls.default_values(category)
        if not cleaned:
            return defaults
        return cleaned
