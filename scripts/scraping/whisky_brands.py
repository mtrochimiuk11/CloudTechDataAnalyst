"""
Scrapowanie marek whisky z whiskybase.com -> kolumny Brand, Country,
ale TYLKO dla pozycji, w których kolumny Whiskies i Votes są wypełnione
i mają wartość >= MIN_VALUE.

!!! WAŻNE !!!
whiskybase.com ma detekcję botów (Cloudflare) — zwykły requests zostanie
ZABLOKOWANY. Dlatego używamy Playwright (prawdziwa przeglądarka). Jeśli trafisz
na wyzwanie Cloudflare, uruchom z HEADLESS=False i rozwiąż je ręcznie.
Przed użyciem sprawdź robots.txt oraz regulamin serwisu.

Struktura (potwierdzona z zapisanego HTML): jedna tabela, nagłówki
Brand | Country | Whiskies | Votes | Rating | WB Ranking. Brak paginacji
(~10 tys. wierszy w jednej tabeli) — dlatego całą tabelę czytamy jednym
zapytaniem do DOM, a nie wiersz po wierszu.

Instalacja:
    pip3 install playwright
    playwright install chromium
"""

import csv
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

# ------------------- KONFIGURACJA -------------------
URL = "https://www.whiskybase.com/whiskies/brands"

TABLE_SELECTOR = "table"        # na stronie jest jedna tabela
BRAND_HEADERS = ("brand", "name")     # możliwe nazwy kolumny z marką
COUNTRY_HEADERS = ("country",)        # możliwe nazwy kolumny z krajem
WHISKIES_HEADERS = ("whiskies",)      # kolumna z liczbą butelkowań
VOTES_HEADERS = ("votes",)            # kolumna z liczbą głosów

MIN_VALUE = 10                   # próg dla Whiskies ORAZ Votes

HEADLESS = True                 # False -> zobaczysz przeglądarkę (debug/Cloudflare)
OUTPUT_NAME = "whiskybase_brands.csv"
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
# ----------------------------------------------------


def find_col(headers, candidates):
    """Indeks pierwszej kolumny, której nagłówek pasuje do kandydatów."""
    low = [h.strip().lower() for h in headers]
    for i, h in enumerate(low):
        if any(c in h for c in candidates):
            return i
    return None


def to_int(s: str):
    """'12' -> 12; puste / nie-liczba -> None."""
    s = (s or "").strip()
    return int(s) if s.isdigit() else None


def scrape():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        page = browser.new_page(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0 Safari/537.36")
        )
        page.goto(URL, wait_until="networkidle", timeout=60000)
        page.wait_for_selector(f"{TABLE_SELECTOR} tbody tr", timeout=30000)

        # nagłówki
        headers = page.eval_on_selector_all(
            f"{TABLE_SELECTOR} thead th",
            "els => els.map(e => e.innerText.trim())")
        if not headers:
            headers = page.eval_on_selector_all(
                f"{TABLE_SELECTOR} tr:first-child th, {TABLE_SELECTOR} tr:first-child td",
                "els => els.map(e => e.innerText.trim())")

        # cała tabela jednym zapytaniem (szybko, bez round-tripów per wiersz)
        data = page.eval_on_selector_all(
            f"{TABLE_SELECTOR} tbody tr",
            "rows => rows.map(tr => Array.from(tr.querySelectorAll('td,th'))"
            ".map(c => c.innerText.trim()))")

        browser.close()

    # mapowanie kolumn
    idx = {
        "brand": find_col(headers, BRAND_HEADERS),
        "country": find_col(headers, COUNTRY_HEADERS),
        "whiskies": find_col(headers, WHISKIES_HEADERS),
        "votes": find_col(headers, VOTES_HEADERS),
    }
    if any(v is None for v in idx.values()):
        missing = [k for k, v in idx.items() if v is None]
        sys.exit(f"Nie rozpoznano kolumn {missing}. Dostępne nagłówki: {headers}")

    need = max(idx.values())
    rows = []
    for cells in data:
        if len(cells) <= need:
            continue
        w = to_int(cells[idx["whiskies"]])
        v = to_int(cells[idx["votes"]])
        if w is None or v is None or w < MIN_VALUE or v < MIN_VALUE:
            continue                         # brak wartości lub poniżej progu
        brand = cells[idx["brand"]].strip()
        country = cells[idx["country"]].strip()
        if brand:
            rows.append((brand, country))
    return rows


def main():
    rows = scrape()

    # dedup po (brand, country) z zachowaniem kolejności
    seen, unique = set(), []
    for r in rows:
        if r not in seen:
            seen.add(r)
            unique.append(r)

    print(f"Po filtrze (Whiskies i Votes >= {MIN_VALUE}): {len(unique)} marek")

    DATA_DIR.mkdir(exist_ok=True)
    out = DATA_DIR / OUTPUT_NAME
    with open(out, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Brand", "Country"])
        writer.writerows(unique)
    print(f"Zapisano do {out}")


if __name__ == "__main__":
    main()