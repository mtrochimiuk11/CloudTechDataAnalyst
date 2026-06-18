"""
Scrapowanie nazw z WIELU krótkich list (<ul>) pogrupowanych pod nagłówkami
(np. wg krajów) — typowe dla stron typu List_of_rum_brands na Wikipedii.

Dla każdej nazwy zapisuje też sekcję (nagłówek), pod którą się znajduje.

Zależności:
    pip install requests beautifulsoup4
"""

import re
import csv
import requests
from bs4 import BeautifulSoup
from pathlib import Path

# folder 'data' w katalogu głównym repo (skrypt leży w scripts/scraping/)
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

# ------------------- KONFIGURACJA -------------------
URL = "https://en.wikipedia.org/wiki/List_of_rum_brands"

# Kontener z treścią artykułu. Bierzemy WSZYSTKIE <ul> w jego obrębie.
CONTENT_SELECTOR = "div.mw-parser-output"

# Nagłówki, na których przerywamy zbieranie (śmieci na końcu artykułu).
# Porównanie jest bez wielkości liter.
STOP_HEADINGS = {"see also", "references", "external links",
                 "notes", "further reading", "bibliography"}

OUTPUT = OUTPUT = DATA_DIR / "rum_brands.csv"
DEDUP = True   # usuń duplikaty nazw zachowując pierwsze wystąpienie
# ----------------------------------------------------


def clean(text: str) -> str:
    """Czyści tekst nazwy: usuwa przypisy [1], nawiasy (...) z zawartością, nadmiarowe spacje."""
    text = re.sub(r"\[[^\]]*\]", "", text)   # przypisy typu [1], [a], [note 2]
    text = re.sub(r"\([^)]*\)", "", text)    # nawiasy z zawartością, np. (rum)
    text = re.sub(r"\s+", " ", text)          # zbędne białe znaki
    return text.strip()


def clean_heading(el) -> str:
    """Tekst nagłówka bez doklejonego '[edit]' i przypisów."""
    text = el.get_text(" ")
    text = re.sub(r"\[\s*edit\s*\]", "", text, flags=re.I)
    return clean(text)


def scrape(url: str):
    html = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (data-task)"}).text
    soup = BeautifulSoup(html, "html.parser")

    content = soup.select_one(CONTENT_SELECTOR)
    if content is None:
        raise SystemExit(f"Nie znaleziono kontenera '{CONTENT_SELECTOR}'.")

    rows = []              # lista krotek (nazwa, sekcja)
    current_section = ""

    # Iterujemy nagłówki i listy w kolejności występowania w dokumencie.
    for el in content.find_all(["h2", "h3", "h4", "ul"]):
        if el.name in ("h2", "h3", "h4"):
            heading = clean_heading(el)
            if heading.lower() in STOP_HEADINGS:
                break                      # koniec treści, dalej są śmieci
            current_section = heading
            continue

        # el to <ul> — bierzemy tylko jego BEZPOŚREDNIE <li>.
        # Zagnieżdżone <ul> zostaną obsłużone osobno (są też w tej pętli),
        # więc każdą pozycję liczymy dokładnie raz.
        for li in el.find_all("li", recursive=False):
            li_copy = li.__copy__()
            for sub in li_copy.find_all(["ul", "ol"]):
                sub.extract()             # usuń tekst podlist z tego <li>
            name = clean(li_copy.get_text(" "))
            if name:
                rows.append((name, current_section))

    return rows


def main():
    rows = scrape(URL)

    if DEDUP:
        seen = set()
        unique = []
        for name, section in rows:
            if name not in seen:
                seen.add(name)
                unique.append((name, section))
        rows = unique

    print(f"Znaleziono {len(rows)} pozycji")
    for name, section in rows:
        print(f"{section:25} | {name}")

    with open(OUTPUT, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["brand", "country"])
        writer.writerows(rows)
    print(f"\nZapisano do {OUTPUT}")


if __name__ == "__main__":
    main()