"""
Scrapowanie ze strony:
    https://en.wikipedia.org/wiki/List_of_French_rums
Strona jest "organized by location" — zakładamy listy <ul> pod nagłówkami
lokalizacji (Martinique, Guadeloupe, La Réunion, ...). Dla każdej pozycji
zapisujemy też lokalizację (nagłówek), pod którą się znajduje.

!!! WAŻNE — ZWERYFIKUJ STRUKTURĘ W PRZEGLĄDARCE !!!
Nie udało się podejrzeć treści strony narzędziem pobierającym, więc nie ma
pewności, czy dane są w listach <ul> czy w tabelach. Zanim zaufasz wynikom:
  - otwórz stronę, w konsoli wpisz:
        document.querySelectorAll("div.mw-parser-output ul li").length
  - jeśli liczba odpowiada widocznym pozycjom -> ten skrypt jest OK
  - jeśli zwraca 0 albo mało, a dane widać w TABELACH -> napisz, przerobię
    skrypt na pandas.read_html / split komórek

Zależności:
    pip install requests beautifulsoup4
"""

import re
import csv
import requests
from pathlib import Path
from bs4 import BeautifulSoup

# ------------------- KONFIGURACJA -------------------
URL = "https://en.wikipedia.org/wiki/List_of_French_rums"
CONTENT_SELECTOR = "div.mw-parser-output"

STOP_HEADINGS = {"see also", "references", "external links",
                 "notes", "further reading", "bibliography"}

OUTPUT_NAME = "french_rums.csv"
DEDUP = True

# folder 'data' w katalogu głównym repo (skrypt leży w scripts/scraping/)
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
# ----------------------------------------------------


def clean(text: str) -> str:
    text = re.sub(r"\[[^\]]*\]", "", text)   # przypisy [1]
    text = re.sub(r"\([^)]*\)", "", text)    # nawiasy z zawartością
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def clean_heading(el) -> str:
    text = el.get_text(" ")
    text = re.sub(r"\[\s*edit\s*\]", "", text, flags=re.I)
    text = re.sub(r"\[[^\]]*\]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def heading_level(el):
    if el.name and re.fullmatch(r"h[1-6]", el.name):
        return int(el.name[1])
    return None


def scrape(url: str):
    html = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (data-task)"}).text
    soup = BeautifulSoup(html, "html.parser")

    content = soup.select_one(CONTENT_SELECTOR)
    if content is None:
        raise SystemExit(f"Nie znaleziono kontenera '{CONTENT_SELECTOR}'.")

    rows = []
    current_location = ""

    for el in content.find_all(["h2", "h3", "h4", "ul"]):
        if heading_level(el) is not None:
            heading = clean_heading(el)
            if heading.lower() in STOP_HEADINGS:
                break
            current_location = heading
            continue

        for li in el.find_all("li", recursive=False):
            li_copy = li.__copy__()
            for sub in li_copy.find_all(["ul", "ol"]):
                sub.extract()
            name = clean(li_copy.get_text(" "))
            if name:
                rows.append((name, current_location))

    return rows


def main():
    rows = scrape(URL)

    if DEDUP:
        seen = set()
        unique = []
        for name, loc in rows:
            if name not in seen:
                seen.add(name)
                unique.append((name, loc))
        rows = unique

    print(f"Znaleziono {len(rows)} pozycji")
    for name, loc in rows:
        print(f"{loc:20} | {name}")

    DATA_DIR.mkdir(exist_ok=True)
    out = DATA_DIR / OUTPUT_NAME
    with open(out, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "location"])
        writer.writerows(rows)
    print(f"\nZapisano do {out}")


if __name__ == "__main__":
    main()