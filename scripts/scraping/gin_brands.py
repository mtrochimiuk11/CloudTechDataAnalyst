"""
Pobranie listy spod nagłówka 'Notable brands' na stronie:
    https://en.wikipedia.org/wiki/Gin
Każda pozycja ma postać 'nazwa – dodatkowe informacje'. Część przed
myślnikiem trafia do kolumny 'brand', część po nim do 'extraInfo'.

Zależności:
    pip install requests beautifulsoup4
"""

import re
import csv
import requests
from bs4 import BeautifulSoup
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

# ------------------- KONFIGURACJA -------------------
URL = "https://en.wikipedia.org/wiki/Gin"
CONTENT_SELECTOR = "div.mw-parser-output"

TARGET_HEADING = "Notable brands"
# False -> wystarczy, że TARGET_HEADING zawiera się w treści nagłówka
EXACT_MATCH = False

OUTPUT = DATA_DIR /  "gin_brands.csv"
DEDUP = True

# Separator nazwa/opis. Na tej stronie to PÓŁPAUZA (–, U+2013), często
# BEZ spacji przed nią, np. "Beefeater– England". Dzielimy więc po
# półpauzie/pauzie niezależnie od spacji, ALBO po zwykłym dywizie, ale
# tylko gdy ma spacje po obu stronach (żeby nie ciąć nazw typu Lind & Lime).
SEP = re.compile(r"(?:\s+-\s+|\s*[\u2013\u2014]\s*)")
# ----------------------------------------------------


def strip_refs(text: str) -> str:
    return re.sub(r"\[[^\]]*\]", "", text)        # przypisy [1], [a]


def clean_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def clean_brand(text: str) -> str:
    text = re.sub(r"\([^)]*\)", "", text)         # usuń nawiasy z NAZWY
    return clean_ws(text)


def split_item(text: str) -> tuple[str, str]:
    text = strip_refs(text)
    parts = SEP.split(text, maxsplit=1)
    brand = clean_brand(parts[0])
    extra = clean_ws(parts[1]) if len(parts) > 1 else ""
    return brand, extra


def clean_heading(el) -> str:
    text = el.get_text(" ")
    text = re.sub(r"\[\s*edit\s*\]", "", text, flags=re.I)
    text = re.sub(r"\[[^\]]*\]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def heading_level(el):
    if el.name and re.fullmatch(r"h[1-6]", el.name):
        return int(el.name[1])
    return None


def matches(heading: str) -> bool:
    h, t = heading.lower(), TARGET_HEADING.lower()
    return h == t if EXACT_MATCH else t in h


def scrape(url: str):
    html = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (data-task)"}).text
    soup = BeautifulSoup(html, "html.parser")

    content = soup.select_one(CONTENT_SELECTOR)
    if content is None:
        raise SystemExit(f"Nie znaleziono kontenera '{CONTENT_SELECTOR}'.")

    rows = []
    collecting = False
    target_level = None
    found = False

    for el in content.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "ul"]):
        level = heading_level(el)

        if level is not None:                      # nagłówek
            if collecting and level <= target_level:
                break                              # koniec sekcji
            if not collecting and matches(clean_heading(el)):
                collecting = True
                found = True
                target_level = level
            continue

        if collecting:                             # <ul> w docelowej sekcji
            for li in el.find_all("li", recursive=False):
                li_copy = li.__copy__()
                for sub in li_copy.find_all(["ul", "ol"]):
                    sub.extract()
                # get_text() bez separatora zachowuje oryginalne odstępy
                # (ważne dla nazw typu "Gilbey's").
                brand, extra = split_item(li_copy.get_text())
                if brand:
                    rows.append((brand, extra))

    if not found:
        raise SystemExit(f"Nie znaleziono nagłówka pasującego do '{TARGET_HEADING}'.")

    return rows


def main():
    rows = scrape(URL)

    if DEDUP:
        seen = set()
        unique = []
        for brand, extra in rows:
            if brand not in seen:
                seen.add(brand)
                unique.append((brand, extra))
        rows = unique

    print(f"Sekcja '{TARGET_HEADING}': znaleziono {len(rows)} pozycji")
    for brand, extra in rows:
        print(f"{brand:30} | {extra}")

    with open(OUTPUT, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["brand", "extraInfo"])
        writer.writerows(rows)
    print(f"\nZapisano do {OUTPUT}")


if __name__ == "__main__":
    main()