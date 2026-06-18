"""
Scrapowanie marek ze strony:
    https://en.wikipedia.org/wiki/List_of_liqueur_brands

Wynik: jeden wiersz na markę, kolumny: category, brand, keywords.
  - category : nagłówek sekcji (kategoria smakowa)
  - brand    : pełna, kanoniczna nazwa
  - keywords : warianty do dopasowywania, rozdzielone '|'
               (pełna nazwa + warianty okrojone + słowa z opisu po przecinku)

Reguły wyciągania nazwy:
  - opis w nawiasie / po półpauzie / po dywizie ze spacją -> ODCINANY,
  - po tym cięciu, część PO pierwszym przecinku to opis: rozbijamy go na
    pojedyncze słowa (bez przedimków) i dorzucamy do keywords,
  - wyjątek: jeśli część przed przecinkiem to destylarnia z SWAP_EXCEPTIONS,
    marką jest część PO przecinku (np. "Black Canyon Distillery, Richardo's
    Decaf Coffee Liqueur" -> brand "Richardo's Decaf Coffee Liqueur"),
  - nazwy z '/' rozbijamy na osobne wiersze ("A/B" -> "A", "B").

Reguły keywords (okrajanie):
  - dla KAŻDEGO słowa-dopiska (STRIP_WORDS) jako całego słowa tworzymy wariant
    = tekst DO tego słowa; dopisek na początku -> fallback "usuń tylko słowo";
    warianty okrojone krótsze niż MIN_LEN znaków odrzucamy, pełną nazwę zawsze
    zostawiamy.

Zależności:
    pip install requests beautifulsoup4
"""

import re
import csv
import requests
from pathlib import Path
from bs4 import BeautifulSoup

# ------------------- KONFIGURACJA -------------------
URL = "https://en.wikipedia.org/wiki/List_of_liqueur_brands"
CONTENT_SELECTOR = "div.mw-parser-output"

STOP_HEADINGS = {"see also", "references", "external links",
                 "notes", "further reading", "bibliography"}

# Generyczne słowa-dopiski okrajane z nazw (porównanie bez wielkości liter,
# tylko jako CAŁE słowo). UWAGA: 'crème'/'creme' tu NIE ma (to rdzeń nazw).
STRIP_WORDS = {"liqueur", "cream", "coffee", "whisky", "whiskey",
               "schnapps", "bitter"}

# Przedimki odfiltrowywane ze słów opisu po przecinku.
ARTICLES = {"a", "an", "the"}

# Wyjątki: część przed przecinkiem to destylarnia, a właściwa marka jest PO
# przecinku. Klucze małymi literami.
SWAP_EXCEPTIONS = {"black canyon distillery"}

MIN_LEN = 3          # odrzucaj warianty/słowa krótsze niż tyle znaków

OUTPUT_NAME = "liqueur_brands.csv"
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

# opis odcinany z nazwy: '(' | półpauza/pauza | dywiz ze spacją PO nim
SEP = re.compile(r"\s*\(|\s*[–—]\s*|\s*-\s+")
# ----------------------------------------------------


def clean_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_name(text: str):
    """Zwraca (rdzeń_nazwy, opis_po_przecinku)."""
    text = re.sub(r"\[[^\]]*\]", "", text)       # przypisy [1]
    text = SEP.split(text, maxsplit=1)[0]        # odetnij opis w nawiasie/po -
    text = clean_ws(text)
    if "," in text:                              # podział po pierwszym przecinku
        core, _, extra = text.partition(",")
        core, extra = clean_ws(core), clean_ws(extra)
        if core.lower() in SWAP_EXCEPTIONS:      # wyjątek: marka jest PO przecinku
            return extra, ""
        return core, extra
    return text, ""


def clean_heading(el) -> str:
    text = el.get_text(" ")
    text = re.sub(r"\[\s*edit\s*\]", "", text, flags=re.I)
    text = re.sub(r"\[[^\]]*\]", "", text)
    return clean_ws(text)


def heading_level(el):
    if el.name and re.fullmatch(r"h[1-6]", el.name):
        return int(el.name[1])
    return None


def split_slash(name: str):
    """'A/B' -> ['A', 'B']; pojedyncza nazwa -> ['A']."""
    return [p.strip() for p in re.split(r"\s*/\s*", name) if p.strip()]


def make_keywords(name: str, extra: str = ""):
    """Pełna nazwa + warianty okrojone + pojedyncze słowa z opisu po przecinku."""
    tokens = name.split()
    low = [re.sub(r"[^\w]", "", t.lower()) for t in tokens]  # do porównań

    keywords = [name]                                        # pełna zawsze
    idxs = [i for i, t in enumerate(low) if t in STRIP_WORDS]
    for i in sorted(idxs, reverse=True):                     # od najdłuższego
        cut = " ".join(tokens[:i]).strip()
        if not cut:                          # dopisek na początku -> usuń słowo
            cut = " ".join(tokens[:i] + tokens[i + 1:]).strip()
        if len(cut) >= MIN_LEN:
            keywords.append(cut)

    # opis po przecinku -> pojedyncze słowa, bez przedimków
    for w in extra.split():
        w = re.sub(r"^\W+|\W+$", "", w)          # obetnij interpunkcję z brzegów
        if not w or w.lower() in ARTICLES:
            continue
        if len(w) >= MIN_LEN:
            keywords.append(w)

    # dedup z zachowaniem kolejności (bez wzgl. na wielkość liter)
    seen, out = set(), []
    for k in keywords:
        k = clean_ws(k)
        kl = k.lower()
        if k and kl not in seen:
            seen.add(kl)
            out.append(k)
    return out


def scrape(url: str):
    html = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (data-task)"}).text
    soup = BeautifulSoup(html, "html.parser")

    content = soup.select_one(CONTENT_SELECTOR)
    if content is None:
        raise SystemExit(f"Nie znaleziono kontenera '{CONTENT_SELECTOR}'.")

    rows = []                       # (category, brand, extra)
    current_category = ""
    for el in content.find_all(["h2", "h3", "h4", "ul"]):
        if heading_level(el) is not None:
            h = clean_heading(el)
            if h.lower() in STOP_HEADINGS:
                break
            current_category = h
            continue
        for li in el.find_all("li", recursive=False):
            li_copy = li.__copy__()
            for sub in li_copy.find_all(["ul", "ol"]):
                sub.extract()
            core, extra = parse_name(li_copy.get_text(" "))
            for brand in split_slash(core):
                rows.append((current_category, brand, extra))
    return rows


def main():
    rows = scrape(URL)

    # dedup po (category, brand) z zachowaniem kolejności
    seen, unique = set(), []
    for cat, brand, extra in rows:
        key = (cat.lower(), brand.lower())
        if brand and key not in seen:
            seen.add(key)
            unique.append((cat, brand, extra))

    print(f"Znaleziono {len(unique)} marek")

    DATA_DIR.mkdir(exist_ok=True)
    out = DATA_DIR / OUTPUT_NAME
    with open(out, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["category", "brand", "keywords"])
        for cat, brand, extra in unique:
            kws = make_keywords(brand, extra)
            writer.writerow([cat, brand, "|".join(kws)])
    print(f"Zapisano do {out}")


if __name__ == "__main__":
    main()