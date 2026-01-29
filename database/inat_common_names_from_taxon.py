import csv
import time
from requests.exceptions import RequestException
import requests
from collections import defaultdict
from pathlib import Path

TAXON_FILE = "taxon.txt"
OUT_CSV = "vernacular_inat_mushroosm.csv"

# Target filters
ASCO_ORDERS = {"pezizales", "morchellales", "helvellales", "tuberales"}
BASIDIO_CLASS_ALLOW = {"agaricomycetes"}

# Output columns (order matters)
OUTPUT_LANGS = ["en", "de", "fr", "es", "da", "sv", "no", "fi", "pl", "pt", "it"]

# Map iNaturalist lexicon/parameterized_lexicon to output columns
LEXICON_TO_CODE = {
    "english": "en",
    "german": "de",
    "french": "fr",
    "spanish": "es",
    "danish": "da",
    "swedish": "sv",
    "norwegian": "no",
    "finnish": "fi",
    "polish": "pl",
    "portuguese": "pt",
    "brazilian-portuguese": "pt",
    "portuguese-brazil": "pt",
    "portuguese-brazilian": "pt",
    "italian": "it",
}

API_BASE = "https://api.inaturalist.org/v1"
WEB_BASE = "https://www.inaturalist.org"
HEADERS = {
    "User-Agent": "MycoLog/1.0 (local script; contact: sigmund.aas@gmail.com)",
    "Accept-Encoding": "gzip",
}

REQUEST_DELAY = 0.05
MAX_RETRIES = 3
BACKOFF_BASE = 5.0
CSV_FIELD_LIMIT = 1024 * 1024 * 10  # 10 MB


def _set_csv_field_limit() -> None:
    try:
        csv.field_size_limit(CSV_FIELD_LIMIT)
    except OverflowError:
        csv.field_size_limit(2147483647)


def fetch_taxon_id(session: requests.Session, name: str) -> int | None:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(
                f"{API_BASE}/taxa",
                params={"q": name, "per_page": 5},
                headers=HEADERS,
                timeout=30
            )
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                if not results:
                    return None
                for item in results:
                    if item.get("name") == name:
                        return item.get("id")
                return results[0].get("id")
        except RequestException as exc:
            print(f"  Taxa lookup failed (attempt {attempt}/{MAX_RETRIES}): {exc}")
        time.sleep(BACKOFF_BASE * attempt)
    return None


def fetch_taxon_names(session: requests.Session, taxon_id: int) -> list[dict]:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(
                f"{WEB_BASE}/taxon_names.json",
                params={"taxon_id": taxon_id},
                headers=HEADERS,
                timeout=30
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict):
                    return data.get("results", [])
                return data
        except RequestException as exc:
            print(f"  Taxon names lookup failed (attempt {attempt}/{MAX_RETRIES}): {exc}")
        time.sleep(BACKOFF_BASE * attempt)
    return []


def normalize_lexicon(entry: dict) -> str:
    lex = (entry.get("parameterized_lexicon") or entry.get("lexicon") or "").strip().lower()
    return lex


def iter_taxa():
    with open(TAXON_FILE, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            phylum = (row.get("phylum") or "").strip().lower()
            order = (row.get("order") or "").strip().lower()
            tax_class = (row.get("class") or "").strip().lower()
            if phylum == "ascomycota":
                if order not in ASCO_ORDERS:
                    continue
            elif phylum == "basidiomycota":
                if tax_class not in BASIDIO_CLASS_ALLOW:
                    continue
            else:
                continue
            rank = (row.get("taxonRank") or "").strip().lower()
            if rank != "species":
                continue
            name = (row.get("scientificName") or "").strip()
            if not name:
                continue
            yield name


def main() -> None:
    _set_csv_field_limit()
    names = sorted(set(iter_taxa()))
    total = len(names)
    print(f"Found {total} taxa in Ascomycota/Basidiomycota")

    results = defaultdict(lambda: defaultdict(set))
    out_header = ["scientificName"] + OUTPUT_LANGS

    out_path = Path(OUT_CSV)
    done = set()
    if out_path.exists():
        try:
            with open(out_path, encoding="utf-8", newline="") as f_in:
                reader = csv.reader(f_in)
                header = next(reader, None)
                if header and header[0] == "scientificName":
                    for row in reader:
                        if row and row[0]:
                            done.add(row[0])
        except Exception as exc:
            print(f"Failed to read existing CSV for resume: {exc}")
    remaining = [n for n in names if n not in done]
    if done:
        print(f"Resuming: {len(done)} already written, {len(remaining)} remaining")

    with requests.Session() as session, open(OUT_CSV, "a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if not done:
            writer.writerow(out_header)
            f.flush()

        for idx, sci in enumerate(remaining, start=1):
            print(f"[{idx}/{len(remaining)}] {sci}")
            taxon_id = fetch_taxon_id(session, sci)
            if not taxon_id:
                print("  No taxon ID found")
                writer.writerow([sci] + [""] * len(OUTPUT_LANGS))
                f.flush()
                time.sleep(REQUEST_DELAY)
                continue

            print(f"  Taxon ID: {taxon_id}")
            entries = fetch_taxon_names(session, taxon_id)
            print(f"  Names returned: {len(entries)}")

            for entry in entries:
                lex = normalize_lexicon(entry)
                if lex not in LEXICON_TO_CODE:
                    continue
                name = entry.get("name")
                if name:
                    results[LEXICON_TO_CODE[lex]][sci].add(name)

            row = [sci]
            for code in OUTPUT_LANGS:
                row.append("; ".join(sorted(results[code].get(sci, []))))
            writer.writerow(row)
            f.flush()

            time.sleep(REQUEST_DELAY)

    print(f"Wrote {OUT_CSV}")


if __name__ == "__main__":
    main()
