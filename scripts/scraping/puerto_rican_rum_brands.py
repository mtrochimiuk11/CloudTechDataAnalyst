"""
Scrapowanie marek ze strony:
    https://en.wikipedia.org/wiki/List_of_Puerto_Rican_rums

Strona jest mocno opisowa — marki są w listach <ul><li> wplecionych między
akapity prozy. Zbieranie przerywamy zanim dojdziemy do sekcji końcowych
(External links, References, See also, ...).

Wyciąganie nazwy z pozycji:
  - jeśli <li> ZACZYNA się od linku (np. "<a>Bacardi</a> is produced in..."),
    marką jest tekst tego linku -> "Bacardi";
  - w przeciwnym razie bierzemy tekst do pierwszego separatora: nawiasu '('
    albo myślnika otoczonego spacjami.
Przyklady:
    "Bacardi is produced in Cataño - was originally..."  -> "Bacardi"
    "Don Q (Serrallés) - Puerto Rico's top-selling rum"  -> "Don Q"
    "Ron Castillo - produced by Ron de Castillo y Cia"   -> "Ron Castillo"
    "Ron 738 (LG)"                                       -> "Ron 738"
    "Marin"                                              -> "Marin"

Zależności:
    pip install requests beautifulsoup4
"""

import re
import csv
import requests
from pathlib import Path
from bs4 import BeautifulSoup, NavigableString

# ------------------- KONFIGURACJA -------------------
URL = "https://en.wikipedia.org/wiki/List_of_Puerto_Rican_rums"
CONTENT_SELECTOR = "div.mw-parser-output"

# Nagłówki, na których przerywamy zbieranie (sekcje końcowe).
STOP_HEADINGS = {"see also", "references", "external links",
                 "notes", "further reading", "bibliography"}

OUTPUT_NAME = "puerto_rican_rums.csv"
DEDUP = True

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

# Separator (fallback): pierwszy nawias '(' LUB myślnik otoczony spacjami.
SEP = re.compile(r"\s*\(|\s+[-–—]\s+")
# ----------------------------------------------------


def strip_refs(text: str) -> str:
    return re.sub(r"\[[^\]]*\]", "", text)


def clean_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def clean_heading(el) -> str:
    text = el.get_text(" ")
    text = re.sub(r"\[\s*edit\s*\]", "", text, flags=re.I)
    text = re.sub(r"\[[^\]]*\]", "", text)
    return clean_ws(text)


def leading_link(li):
    """Zwraca <a>, jeśli <li> zaczyna się od linku; inaczej None."""
    for child in li.children:
        if isinstance(child, NavigableString):
            if child.strip():
                return None          # zaczyna się od tekstu, nie linku
            continue                 # pomiń biały znak
        return child if child.name == "a" else None
    return None


def li_to_name(li) -> str:
    a = leading_link(li)
    if a is not None:
        return clean_ws(strip_refs(a.get_text(" ")))
    # fallback: tekst do pierwszego separatora
    text = strip_refs(li.get_text(" "))
    text = SEP.split(text, maxsplit=1)[0]
    return clean_ws(text)


def scrape(url: str):
    html = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (data-task)"}).text
    soup = BeautifulSoup(html, "html.parser")

    content = soup.select_one(CONTENT_SELECTOR)
    if content is None:
        raise SystemExit(f"Nie znaleziono kontenera '{CONTENT_SELECTOR}'.")

    names = []
    for el in content.find_all(["h2", "h3", "h4", "ul"]):
        if el.name in ("h2", "h3", "h4"):
            if clean_heading(el).lower() in STOP_HEADINGS:
                break                # koniec treści, dalej linki/przypisy
            continue
        for li in el.find_all("li", recursive=False):
            li_copy = li.__copy__()
            for sub in li_copy.find_all(["ul", "ol"]):
                sub.extract()
            name = li_to_name(li_copy)
            if name:
                names.append(name)
    return names


def main():
    names = scrape(URL)

    if DEDUP:
        names = list(dict.fromkeys(names))

    print(f"Znaleziono {len(names)} pozycji")
    for n in names:
        print(n)

    DATA_DIR.mkdir(exist_ok=True)
    out = DATA_DIR / OUTPUT_NAME
    with open(out, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["brand"])
        for n in names:
            writer.writerow([n])
    print(f"\nZapisano do {out}")


if __name__ == "__main__":
    main()