#!/usr/bin/env python3
"""
Dump vernacular vs scientific name to CSV from the minimal SQLite DB.

Input DB schema assumed:
  - taxon_min(taxon_id, genus, specific_epithet, family)
  - vernacular_min(vernacular_id, taxon_id, vernacular_name, is_preferred_name)

Output CSV columns:
  vernacular_name, scientific_name, genus, specific_epithet, family, is_preferred_name

Usage:
  python dump_vernacular_csv.py --db taxonomy_min.sqlite3 --out vernacular_scientific.csv
  python dump_vernacular_csv.py --preferred-only
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="taxonomy_NO.sqlite3", help="SQLite DB file")
    ap.add_argument("--out", default="vernacular_scientific.csv", help="Output CSV file")
    ap.add_argument("--preferred-only", action="store_true", help="Only dump preferred vernacular names")
    ap.add_argument("--delimiter", default=",", help="CSV delimiter (default: ,). Use '\\t' for TSV.")
    args = ap.parse_args()

    db_path = Path(args.db).resolve()
    out_path = Path(args.out).resolve()
    delim = "\t" if args.delimiter == "\\t" else args.delimiter

    if not db_path.exists():
        raise SystemExit(f"Missing DB: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        where = "WHERE v.is_preferred_name = 1" if args.preferred_only else ""
        query = f"""
            SELECT
                v.vernacular_name,
                (t.genus || ' ' || t.specific_epithet) AS scientific_name,
                t.genus,
                t.specific_epithet,
                t.family,
                v.is_preferred_name
            FROM vernacular_min v
            JOIN taxon_min t ON t.taxon_id = v.taxon_id
            {where}
            ORDER BY v.vernacular_name, t.genus, t.specific_epithet
        """

        with out_path.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, delimiter=delim)
            w.writerow(
                [
                    "vernacular_name",
                    "scientific_name",
                    "genus",
                    "specific_epithet",
                    "family",
                    "is_preferred_name",
                ]
            )

            for row in conn.execute(query):
                w.writerow(
                    [
                        row["vernacular_name"],
                        row["scientific_name"],
                        row["genus"],
                        row["specific_epithet"],
                        row["family"],
                        row["is_preferred_name"],
                    ]
                )

        print(f"Wrote: {out_path}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
