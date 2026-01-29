#!/usr/bin/env python3
"""
Build a minimal SQLite DB for one language dataset.

Inputs (tab-separated files in same folder by default):
  - taxon.txt
  - vernacularname.txt

Keeps ONLY:
  - genus
  - specificEpithet
  - family
  - vernacularName (+ isPreferredName)

Output:
  - taxonomy_min.sqlite3 (default)

Linking:
  1) If vernacularname.txt has a taxonID column, uses that.
  2) Else assumes vernacularname.id == taxon.taxonID (or taxon.id).
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path
from typing import Iterable, Optional


def detect_column(fieldnames: list[str], *candidates: str) -> Optional[str]:
    s = set(fieldnames)
    for c in candidates:
        if c in s:
            return c
    return None


def _set_csv_field_limit() -> None:
    """Increase CSV field size limit to handle large records."""
    try:
        csv.field_size_limit(1024 * 1024 * 10)  # 10 MB
    except OverflowError:
        csv.field_size_limit(2147483647)


def create_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")

    conn.executescript(
        """
        DROP TABLE IF EXISTS taxon_min;
        DROP TABLE IF EXISTS vernacular_min;

        CREATE TABLE taxon_min (
            taxon_id         INTEGER PRIMARY KEY,  -- join key
            genus            TEXT NOT NULL,
            specific_epithet TEXT NOT NULL,
            family           TEXT
        );

        CREATE TABLE vernacular_min (
            vernacular_id     INTEGER PRIMARY KEY,
            taxon_id          INTEGER NOT NULL,
            vernacular_name   TEXT NOT NULL,
            is_preferred_name INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (taxon_id) REFERENCES taxon_min(taxon_id)
        );

        CREATE INDEX idx_taxon_genus ON taxon_min(genus);
        CREATE INDEX idx_taxon_genus_species ON taxon_min(genus, specific_epithet);

        CREATE INDEX idx_vern_name ON vernacular_min(vernacular_name);
        CREATE INDEX idx_vern_taxon ON vernacular_min(taxon_id);

        DROP VIEW IF EXISTS v_vernacular_to_taxon;
        CREATE VIEW v_vernacular_to_taxon AS
        SELECT
            v.vernacular_name,
            v.is_preferred_name,
            t.taxon_id,
            t.genus,
            t.specific_epithet,
            t.family
        FROM vernacular_min v
        JOIN taxon_min t ON t.taxon_id = v.taxon_id;

        DROP VIEW IF EXISTS v_taxon_to_vernacular;
        CREATE VIEW v_taxon_to_vernacular AS
        SELECT
            t.taxon_id,
            t.genus,
            t.specific_epithet,
            t.family,
            v.vernacular_name,
            v.is_preferred_name
        FROM taxon_min t
        LEFT JOIN vernacular_min v ON v.taxon_id = t.taxon_id;
        """
    )


def build_db(taxon_path: Path, vern_path: Path, out_db: Path) -> None:
    _set_csv_field_limit()
    if out_db.exists():
        out_db.unlink()

    conn = sqlite3.connect(out_db)
    conn.row_factory = sqlite3.Row
    try:
        create_schema(conn)

        # -------- taxon.txt (stream) --------
        f = taxon_path.open("r", encoding="utf-8-sig", newline="")
        try:
            reader = csv.DictReader(f, delimiter="\t")
            if not reader.fieldnames:
                raise ValueError(f"No header found in {taxon_path}")

            fields = reader.fieldnames
            kingdom_col = detect_column(fields, "kingdom")
            taxonid_col = detect_column(fields, "taxonID", "taxonId")
            id_col = detect_column(fields, "id")
            genus_col = detect_column(fields, "genus")
            species_col = detect_column(fields, "specificEpithet")
            family_col = detect_column(fields, "family")

            if not (kingdom_col and genus_col and species_col and (taxonid_col or id_col)):
                raise ValueError(
                    "taxon.txt missing required columns. Need: kingdom, genus, specificEpithet, and taxonID or id."
                )

            conn.execute("BEGIN;")
            batch = []
            fungi_ids: set[int] = set()
            BATCH = 5000

            for row in reader:
                if (row.get(kingdom_col, "") or "").strip() != "Fungi":
                    continue

                tid_s = (row.get(taxonid_col, "") if taxonid_col else "").strip()
                if not tid_s and id_col:
                    tid_s = (row.get(id_col, "") or "").strip()
                if not tid_s.isdigit():
                    continue
                tid = int(tid_s)

                genus = (row.get(genus_col, "") or "").strip()
                species = (row.get(species_col, "") or "").strip()
                if not genus or not species:
                    continue

                family = (row.get(family_col, "") or "").strip() if family_col else ""
                family = family or None

                fungi_ids.add(tid)
                batch.append((tid, genus, species, family))

                if len(batch) >= BATCH:
                    conn.executemany(
                        "INSERT OR REPLACE INTO taxon_min (taxon_id, genus, specific_epithet, family) VALUES (?, ?, ?, ?)",
                        batch,
                    )
                    batch.clear()

            if batch:
                conn.executemany(
                    "INSERT OR REPLACE INTO taxon_min (taxon_id, genus, specific_epithet, family) VALUES (?, ?, ?, ?)",
                    batch,
                )
                batch.clear()

            conn.commit()
        finally:
            f.close()

        # -------- vernacularname.txt (stream or read; stream is fine) --------
        f2 = vern_path.open("r", encoding="utf-8-sig", newline="")
        try:
            reader2 = csv.DictReader(f2, delimiter="\t")
            if not reader2.fieldnames:
                raise ValueError(f"No header found in {vern_path}")

            fields2 = reader2.fieldnames
            vern_id_col = detect_column(fields2, "id")
            vern_name_col = detect_column(fields2, "vernacularName", "vernacular_name")
            vern_taxon_col = detect_column(fields2, "taxonID", "taxonId", "taxon_id")
            pref_col = detect_column(fields2, "isPreferredName", "is_preferred_name")

            if not (vern_id_col and vern_name_col):
                raise ValueError("vernacularname.txt missing required columns: id and vernacularName")

            conn.execute("BEGIN;")
            batch = []
            BATCH = 5000

            # get fungi_ids from DB (so we don't keep a giant python set if you prefer)
            # but set lookup is fast; fungi_ids is just IDs of fungi, not full rows
            # If you expect tens of millions, swap to DB lookup. For 42MB file it’s fine.

            for row in reader2:
                vid_s = (row.get(vern_id_col, "") or "").strip()
                if not vid_s.isdigit():
                    continue
                vid = int(vid_s)

                name = (row.get(vern_name_col, "") or "").strip()
                if not name:
                    continue

                taxon_ref_s = (row.get(vern_taxon_col, "") or "").strip() if vern_taxon_col else vid_s
                if not taxon_ref_s.isdigit():
                    continue
                taxon_id = int(taxon_ref_s)

                # keep only rows that actually link to fungi taxon_min
                if taxon_id not in fungi_ids:
                    continue

                pref_s = (row.get(pref_col, "") or "").strip() if pref_col else ""
                is_pref = 1 if pref_s.lower() in ("true", "1", "yes", "y") else 0

                batch.append((vid, taxon_id, name, is_pref))

                if len(batch) >= BATCH:
                    conn.executemany(
                        """
                        INSERT OR REPLACE INTO vernacular_min
                          (vernacular_id, taxon_id, vernacular_name, is_preferred_name)
                        VALUES (?, ?, ?, ?)
                        """,
                        batch,
                    )
                    batch.clear()

            if batch:
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO vernacular_min
                      (vernacular_id, taxon_id, vernacular_name, is_preferred_name)
                    VALUES (?, ?, ?, ?)
                    """,
                    batch,
                )
                batch.clear()

            conn.commit()
        finally:
            f2.close()

        conn.execute("VACUUM;")

        taxa_n = conn.execute("SELECT COUNT(*) FROM taxon_min").fetchone()[0]
        vern_n = conn.execute("SELECT COUNT(*) FROM vernacular_min").fetchone()[0]
        print(f"Created: {out_db}")
        print(f"taxon_min rows: {taxa_n}")
        print(f"vernacular_min rows: {vern_n}")

    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--taxon", default="taxon.txt")
    ap.add_argument("--vern", default="vernacularname.txt")
    ap.add_argument("--out", default="taxonomy_min.sqlite3")
    args = ap.parse_args()

    taxon_path = Path(args.taxon).resolve()
    vern_path = Path(args.vern).resolve()
    out_db = Path(args.out).resolve()

    if not taxon_path.exists():
        raise SystemExit(f"Missing: {taxon_path}")
    if not vern_path.exists():
        raise SystemExit(f"Missing: {vern_path}")

    build_db(taxon_path, vern_path, out_db)


if __name__ == "__main__":
    main()
