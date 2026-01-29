#!/usr/bin/env python3
"""
Build a multi-language SQLite DB from a CSV of vernacular names.

CSV columns:
  scientificName,en,de,fr,es,da,sv,no,fi,pl,pt,it

Multiple names are separated by ';' in each cell.

Norwegian (no) names come from Artsdatabanken artsnavnebase:
https://ipt.artsdatabanken.no/resource?r=artsnavnebase
The source files (taxon.txt + vernacularname.txt) are merged here. The other
10 languages come from iNaturalist via the CSV produced by
inat_common_names_from_taxon.py.
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path
from typing import Iterable


DEFAULT_LANGS = ["en", "de", "fr", "es", "da", "sv", "no", "fi", "pl", "pt", "it"]
DEFAULT_INPUT_CSV = "vernacular_inat_11lang.csv"
DEFAULT_OUTPUT_DB = "vernacular_multilanguage.sqlite3"
DEFAULT_NO_TAXON = "taxon.txt"
DEFAULT_NO_VERNACULAR = "vernacularname.txt"


def _set_csv_field_limit() -> None:
    try:
        csv.field_size_limit(1024 * 1024 * 10)
    except OverflowError:
        csv.field_size_limit(2147483647)


def _split_names(raw: str) -> list[str]:
    if not raw:
        return []
    items = []
    for part in raw.split(";"):
        name = part.strip()
        if name:
            items.append(name)
    return items


def _parse_scientific_name(value: str) -> tuple[str, str] | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    parts = text.replace("\u00a0", " ").split()
    if len(parts) < 2:
        return None
    genus = parts[0].strip().strip(",")
    species = parts[1].strip().strip(",")
    if not genus or not species:
        return None
    return genus, species


def _normalize_taxon(genus: str, species: str) -> tuple[str, str]:
    genus = genus.strip()
    species = species.strip()
    if genus:
        genus = genus[0].upper() + genus[1:]
    if species:
        species = species.lower()
    return genus, species


def create_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")

    conn.executescript(
        """
        DROP TABLE IF EXISTS vernacular_min;
        DROP TABLE IF EXISTS taxon_min;

        CREATE TABLE taxon_min (
            taxon_id         INTEGER PRIMARY KEY,
            genus            TEXT NOT NULL,
            specific_epithet TEXT NOT NULL,
            family           TEXT
        );

        CREATE TABLE vernacular_min (
            vernacular_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            taxon_id          INTEGER NOT NULL,
            language_code     TEXT NOT NULL,
            vernacular_name   TEXT NOT NULL,
            is_preferred_name INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (taxon_id) REFERENCES taxon_min(taxon_id)
        );

        CREATE UNIQUE INDEX idx_vern_unique
            ON vernacular_min(taxon_id, language_code, vernacular_name);

        CREATE INDEX idx_taxon_genus ON taxon_min(genus);
        CREATE INDEX idx_taxon_genus_species ON taxon_min(genus, specific_epithet);
        CREATE INDEX idx_vern_lang_name ON vernacular_min(language_code, vernacular_name);
        CREATE INDEX idx_vern_taxon_lang ON vernacular_min(taxon_id, language_code);
        """
    )


def _insert_vernacular_rows(conn: sqlite3.Connection, rows: list[tuple[int, str, str, int]]) -> None:
    if not rows:
        return
    conn.executemany(
        """
        INSERT INTO vernacular_min
            (taxon_id, language_code, vernacular_name, is_preferred_name)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(taxon_id, language_code, vernacular_name)
        DO UPDATE SET is_preferred_name = CASE
            WHEN excluded.is_preferred_name > vernacular_min.is_preferred_name
            THEN excluded.is_preferred_name
            ELSE vernacular_min.is_preferred_name
        END
        """,
        rows,
    )


def _insert_taxon(conn: sqlite3.Connection, taxon_id: int, genus: str, species: str, family: str | None) -> None:
    conn.execute(
        "INSERT INTO taxon_min (taxon_id, genus, specific_epithet, family) VALUES (?, ?, ?, ?)",
        (taxon_id, genus, species, family),
    )


def _parse_bool(value: str | None) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _load_art_taxa(taxon_path: Path) -> tuple[dict[str, tuple[str, str, str | None]], int, int]:
    taxa: dict[str, tuple[str, str, str | None]] = {}
    total = 0
    valid = 0
    with taxon_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            total += 1
            taxon_id = (row.get("id") or "").strip()
            if not taxon_id:
                continue
            if (row.get("taxonRank") or "").strip().lower() != "species":
                continue
            status = (row.get("taxonomicStatus") or "").strip().lower()
            if status != "valid":
                continue
            genus = (row.get("genus") or "").strip()
            species = (row.get("specificEpithet") or "").strip()
            if not genus or not species:
                continue
            genus, species = _normalize_taxon(genus, species)
            family = (row.get("family") or "").strip() or None
            taxa[taxon_id] = (genus, species, family)
            valid += 1
    return taxa, total, valid


def _merge_norwegian_from_arts(
    conn: sqlite3.Connection,
    get_taxon_id,
    taxon_path: Path,
    vernacular_path: Path,
) -> None:
    if not taxon_path.exists() or not vernacular_path.exists():
        print("Norwegian source files not found, skipping merge.")
        return

    taxa, total, valid = _load_art_taxa(taxon_path)
    print(f"Artsnavnebase taxa: {valid} valid entries out of {total} total")
    if not taxa:
        print("No taxa loaded from artsnavnebase taxon.txt")
        return

    batch: list[tuple[int, str, str, int]] = []
    conn.execute("BEGIN;")
    with vernacular_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            taxon_id = (row.get("id") or "").strip()
            if not taxon_id:
                continue
            if (row.get("countryCode") or "").strip().upper() != "NO":
                continue
            name = (row.get("vernacularName") or "").strip()
            if not name:
                continue
            taxon = taxa.get(taxon_id)
            if not taxon:
                continue
            genus, species, family = taxon
            db_taxon_id = get_taxon_id(genus, species, family)
            is_pref = 1 if _parse_bool(row.get("isPreferredName")) else 0
            batch.append((db_taxon_id, "no", name, is_pref))
            if len(batch) >= 5000:
                _insert_vernacular_rows(conn, batch)
                batch.clear()

    if batch:
        _insert_vernacular_rows(conn, batch)
        batch.clear()

    conn.commit()


def build_db(csv_path: Path, out_db: Path, no_taxon: Path | None, no_names: Path | None) -> None:
    _set_csv_field_limit()
    if out_db.exists():
        out_db.unlink()

    conn = sqlite3.connect(out_db)
    conn.row_factory = sqlite3.Row
    try:
        create_schema(conn)
        taxon_cache: dict[tuple[str, str], int] = {}
        next_taxon_id = 1

        def get_taxon_id(genus: str, species: str, family: str | None = None) -> int:
            nonlocal next_taxon_id
            key = (genus, species)
            if key in taxon_cache:
                if family:
                    conn.execute(
                        "UPDATE taxon_min SET family = COALESCE(family, ?) WHERE taxon_id = ?",
                        (family, taxon_cache[key]),
                    )
                return taxon_cache[key]
            taxon_id = next_taxon_id
            next_taxon_id += 1
            _insert_taxon(conn, taxon_id, genus, species, family)
            taxon_cache[key] = taxon_id
            return taxon_id

        # -------- CSV import --------
        use_arts_no = bool(no_taxon and no_names and no_taxon.exists() and no_names.exists())

        total_rows = 0
        valid_rows = 0
        empty_rows = 0

        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                raise ValueError(f"No header found in {csv_path}")

            fieldnames = [name.strip() for name in reader.fieldnames if name]
            if "scientificName" not in fieldnames:
                raise ValueError("CSV missing required column: scientificName")

            lang_columns = [f for f in fieldnames if f != "scientificName"]
            if not lang_columns:
                lang_columns = list(DEFAULT_LANGS)

            batch: list[tuple[int, str, str, int]] = []
            BATCH = 5000

            conn.execute("BEGIN;")
            for row in reader:
                total_rows += 1
                sci = (row.get("scientificName") or "").strip()
                parsed = _parse_scientific_name(sci)
                if not parsed:
                    continue
                valid_rows += 1
                genus, species = _normalize_taxon(*parsed)
                taxon_id = get_taxon_id(genus, species, None)

                has_any = False
                for lang in lang_columns:
                    if _split_names((row.get(lang) or "")):
                        has_any = True
                        break
                if not has_any:
                    empty_rows += 1

                for lang in lang_columns:
                    lang_code = (lang or "").strip().lower()
                    if not lang_code:
                        continue
                    if lang_code == "no" and use_arts_no:
                        continue
                    names = _split_names((row.get(lang) or ""))
                    if not names:
                        continue
                    for idx, name in enumerate(names):
                        batch.append((taxon_id, lang_code, name, 1 if idx == 0 else 0))
                    if len(batch) >= BATCH:
                        _insert_vernacular_rows(conn, batch)
                        batch.clear()

            if batch:
                _insert_vernacular_rows(conn, batch)
                batch.clear()

            conn.commit()

        print(f"CSV rows: {total_rows} total, {valid_rows} valid scientific names")
        print(f"CSV rows without any translations: {empty_rows}")

        # -------- Norwegian merge from artsnavnebase --------
        if use_arts_no:
            _merge_norwegian_from_arts(conn, get_taxon_id, no_taxon, no_names)
        else:
            print("Norwegian sources not found, skipping merge.")

        conn.execute("VACUUM;")

        taxa_n = conn.execute("SELECT COUNT(*) FROM taxon_min").fetchone()[0]
        vern_n = conn.execute("SELECT COUNT(*) FROM vernacular_min").fetchone()[0]
        lang_n = conn.execute("SELECT COUNT(DISTINCT language_code) FROM vernacular_min").fetchone()[0]
        print(f"Created: {out_db}")
        print(f"taxon_min rows: {taxa_n}")
        print(f"vernacular_min rows: {vern_n}")
        print(f"languages: {lang_n}")

    finally:
        conn.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=DEFAULT_INPUT_CSV, help="Input CSV file")
    ap.add_argument("--out", default=DEFAULT_OUTPUT_DB, help="Output SQLite DB")
    ap.add_argument(
        "--no-taxon",
        default=DEFAULT_NO_TAXON,
        help="Artsdatabanken taxon.txt (optional, preferred Norwegian source)",
    )
    ap.add_argument(
        "--no-vernacular",
        default=DEFAULT_NO_VERNACULAR,
        help="Artsdatabanken vernacularname.txt (optional, preferred Norwegian source)",
    )
    args = ap.parse_args()

    csv_path = Path(args.csv).resolve()
    out_db = Path(args.out).resolve()
    no_taxon = Path(args.no_taxon).resolve() if args.no_taxon else None
    no_names = Path(args.no_vernacular).resolve() if args.no_vernacular else None

    if not csv_path.exists():
        raise SystemExit(f"Missing CSV: {csv_path}")

    build_db(csv_path, out_db, no_taxon, no_names)


if __name__ == "__main__":
    main()
