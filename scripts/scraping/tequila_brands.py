"""
Scrapowanie listy tequili ze strony:
    https://en.wikipedia.org/wiki/List_of_tequilas
Pozycje mają format 'Nazwa (rok)', czasem 'Nazwa (rok) (defunct)'.
Nazwa -> kolumna 'brand', zawartość nawiasów -> 'extraInfo'.

Pomijamy:
  - górną NAWIGACJĘ LITEROWĄ (A, B, C...) — jej <li> zawierają wyłącznie
    linki-kotwice (href zaczyna się od '#'),
  - wszystko PO nagłówku 'See also' (oraz innych końcowych: References,
    External links itd.) — tam są linki spoza listy marek.

Zależności:
    pip install requests beautifulsoup4
"""

import re
import csv
from pathlib import Path
import requests
from bs4 import BeautifulSoup

# ------------------- KONFIGURACJA -------------------
URL = "https://en.wikipedia.org/wiki/List_of_tequilas"
CONTENT_SELECTOR = "div.mw-parser-output"

# Przerwij zbieranie na tych nagłówkach (główny: 'See also').
STOP_HEADINGS = {"see also", "references", "external links",
                 "notes", "further reading", "bibliography"}

OUTPUT_NAME = "tequila_brands.csv"
DEDUP = True
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
# ----------------------------------------------------


def strip_refs(text: str) -> str:
    return re.sub(r"\[[^\]]*\]", "", text)


def clean_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def split_item(text: str):
    """'Nazwa (rok) (defunct)' -> ('Nazwa', 'rok, defunct')."""
    text = strip_refs(text)
    extras = re.findall(r"\(([^)]*)\)", text)
    brand = clean_ws(re.sub(r"\([^)]*\)", "", text))
    extra = ", ".join(clean_ws(e) for e in extras if clean_ws(e))
    return brand, extra


def clean_heading(el) -> str:
    text = el.get_text(" ")
    text = re.sub(r"\[\s*edit\s*\]", "", text, flags=re.I)
    text = re.sub(r"\[[^\]]*\]", "", text)
    return clean_ws(text)


def heading_level(el):
    if el.name and re.fullmatch(r"h[1-6]", el.name):
        return int(el.name[1])
    return None


_NAV_TOKEN = re.compile(r"[0-9A-Za-z]([–—-][0-9A-Za-z])?$")


def is_nav_li(li) -> bool:
    """True dla pozycji nawigacji literowej (kotwice #A, pojedyncze litery)."""
    links = li.find_all("a")
    if links and all((a.get("href") or "").startswith("#") for a in links):
        return True
    txt = clean_ws(strip_refs(li.get_text(" ")))
    return bool(_NAV_TOKEN.fullmatch(txt))      # 'A', '0–9' itp.


def scrape(url: str):
    html = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (data-task)"}).text
    soup = BeautifulSoup(html, "html.parser")

    content = soup.select_one(CONTENT_SELECTOR)
    if content is None:
        raise SystemExit(f"Nie znaleziono kontenera '{CONTENT_SELECTOR}'.")

    rows = []
    for el in content.find_all(["h2", "h3", "h4", "ul"]):
        if heading_level(el) is not None:
            if clean_heading(el).lower() in STOP_HEADINGS:
                break                          # 'See also' itd. -> koniec
            continue
        for li in el.find_all("li", recursive=False):
            if is_nav_li(li):                  # pomiń nawigację literową
                continue
            li_copy = li.__copy__()
            for sub in li_copy.find_all(["ul", "ol"]):
                sub.extract()
            brand, extra = split_item(li_copy.get_text(" "))
            if brand:
                rows.append((brand, extra))
    return rows


def main():
    rows = scrape(URL)

    if DEDUP:
        seen, unique = set(), []
        for r in rows:
            if r[0] not in seen:
                seen.add(r[0])
                unique.append(r)
        rows = unique

    print(f"Znaleziono {len(rows)} pozycji")
    for brand, extra in rows:
        print(f"{brand:35} | {extra}")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = DATA_DIR / OUTPUT_NAME
    with open(out, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["brand", "extraInfo"])
        writer.writerows(rows)
    print(f"\nZapisano do {out}")


if __name__ == "__main__":
    main()