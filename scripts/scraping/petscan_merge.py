"""
Pobiera wyniki kilku zapytań PetScan (po ich kodach PSID), scala je,
usuwa duplikaty i zapisuje do jednego pliku CSV.

Obsługuje tryb Wikidata ("Use wiki: Wikidata") — wtedy kolumna `title`
zawiera kod Q, a skrypt deduplikuje po Q. Działa też w trybie zwykłym
(tytuły artykułów).

Zależności:
    pip install requests

Jak używać:
    1. Zapisz każde zapytanie w PetScan (dostanie kod PSID widoczny w URL-u
       jako ?psid=NNNNN) i wpisz te kody na listę PSIDS poniżej.
    2. Uruchom:  python petscan_merge.py
    3. Wynik trafia do pliku OUTPUT (kolumny: wikidata, title, source_psids).
"""

import csv
import io
import re
import sys
import time
import requests
from pathlib import Path

# ------------------- KONFIGURACJA -------------------
PSIDS = ["47721898", "47721897", "47721896", "47721895", "47721894", "47721893", "47721892", "47721890", "47721891", "47722215"]          # <-- wpisz tu swoje kody PSID
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
OUTPUT = DATA_DIR / "alkohole_petscan_merged.csv"
PETSCAN_URL = "https://petscan.wmcloud.org/"
REQUEST_DELAY = 1.0                 # przerwa między zapytaniami (grzeczność wobec narzędzia)
HEADERS = {"User-Agent": "alcohol-taxonomy-merge/1.0 (recruitment task)"}
# ----------------------------------------------------

QID_RE = re.compile(r"^Q\d+$")


def fetch_psid(psid: str) -> str:
    """Pobiera wynik jednego zapytania PetScan jako tekst CSV."""
    params = {"psid": str(psid), "format": "csv", "doit": "1"}
    resp = requests.get(PETSCAN_URL, params=params, headers=HEADERS, timeout=120)
    resp.raise_for_status()
    text = resp.text
    # Gdy PSID jest błędny lub coś padło, PetScan zwraca stronę HTML zamiast CSV.
    if "<html" in text[:300].lower():
        raise ValueError("dostałem HTML zamiast CSV — sprawdź, czy kod PSID jest poprawny")
    return text


def parse_rows(text: str):
    """Zwraca pary (qid, title). W trybie Wikidata qid jest wypełnione,
    a title puste; w trybie zwykłym odwrotnie."""
    reader = csv.DictReader(io.StringIO(text))
    fields = reader.fieldnames or []
    if not fields:
        return []
    # kolumna źródłowa: jawna kolumna z Wikidatą, inaczej "title"
    wd_col = next((c for c in fields if "wikidata" in c.lower()), None)
    title_col = next((c for c in fields if c.lower() == "title"), fields[0])
    src_col = wd_col or title_col

    rows = []
    for r in reader:
        val = (r.get(src_col) or "").strip()
        if not val:
            continue
        if QID_RE.match(val):
            rows.append((val, ""))      # (qid, title)
        else:
            rows.append(("", val))      # zwykły tytuł
    return rows


def norm_key(title: str) -> str:
    """Klucz deduplikacji dla tytułów: podkreślenia=spacje, bez wielkości liter."""
    return title.replace("_", " ").strip().lower()


def main():
    if not PSIDS or PSIDS == ["12345", "23456"]:
        sys.exit("Uzupełnij listę PSIDS swoimi kodami zapytań PetScan.")

    merged = {}  # klucz (qid lub znorm. tytuł) -> {wikidata, title, source_psids}
    for psid in PSIDS:
        try:
            text = fetch_psid(psid)
        except Exception as e:
            print(f"[!] Pominięto PSID {psid}: {e}", file=sys.stderr)
            continue

        rows = parse_rows(text)
        print(f"PSID {psid}: {len(rows)} pozycji")
        for qid, title in rows:
            key = qid if qid else norm_key(title)
            if not key:
                continue
            if key not in merged:
                merged[key] = {"wikidata": qid, "title": title, "source_psids": {str(psid)}}
            else:
                merged[key]["source_psids"].add(str(psid))
                if not merged[key]["wikidata"] and qid:
                    merged[key]["wikidata"] = qid
                if not merged[key]["title"] and title:
                    merged[key]["title"] = title
        time.sleep(REQUEST_DELAY)

    items = sorted(merged.values(), key=lambda d: (d["wikidata"], d["title"].lower()))
    with open(OUTPUT, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["wikidata", "title", "source_psids"])
        for it in items:
            w.writerow([it["wikidata"], it["title"], ";".join(sorted(it["source_psids"]))])

    print(f"\nŁącznie unikalnych pozycji: {len(items)}")
    print(f"Zapisano do {OUTPUT}")


if __name__ == "__main__":
    main()