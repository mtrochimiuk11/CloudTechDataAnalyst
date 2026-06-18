"""
Scrapowanie ze strony:
    https://en.wikipedia.org/wiki/List_of_cider_brands

To pojedyncza tabela (Name, Town, Country, Type, Notes). Zapisujemy:
    brand    <- Name (pełna, kanoniczna nazwa)
    keywords <- warianty okrojone na słowach-dopiskach (pełna + cięcia), '|'
    town     <- Town
    country  <- Country
    type     <- Type
Kolumny town/country/type zostają surowe — do późniejszego użycia jako
optional keywords. Notes pomijamy.

Zależności:
    pip install requests pandas lxml
"""

import re
import csv
from io import StringIO
from pathlib import Path

import requests
import pandas as pd

# ------------------- KONFIGURACJA -------------------
URL = "https://en.wikipedia.org/wiki/List_of_cider_brands"

# Mapowanie: kolumna w tabeli -> kolumna w wyniku (dopasowanie po nagłówku,
# bez wielkości liter, więc odporne na kolejność kolumn).
COLUMNS = {"name": "brand", "town": "town", "country": "country", "type": "type"}

# Generyczne słowa-dopiski okrajane z nazw (całe słowo, bez wielkości liter).
# 'by' ucina ogon typu "... by <producent>" (np. "Scrumpy Jack by Bulmer").
STRIP_WORDS = {"cider", "cyder", "cidre", "perry", "hard", "soft", "dry", "by"}

MIN_LEN = 3          # odrzucaj warianty okrojone krótsze niż tyle znaków

OUTPUT_NAME = "cider_brands.csv"
DEDUP = True
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
# ----------------------------------------------------


def clean_brand(s: str) -> str:
    s = re.sub(r"\[[^\]]*\]", "", str(s))    # przypisy [1]
    s = re.sub(r"\([^)]*\)", "", s)          # nawiasy, np. "(see Bulmers)"
    return re.sub(r"\s+", " ", s).strip()


def clean_cell(s) -> str:
    if pd.isna(s):
        return ""
    s = re.sub(r"\[[^\]]*\]", "", str(s))
    return re.sub(r"\s+", " ", s).strip()


def make_keywords(name: str):
    """Pełna nazwa + warianty okrojone na słowach-dopiskach."""
    tokens = name.split()
    low = [re.sub(r"[^\w]", "", t.lower()) for t in tokens]

    keywords = [name]                                        # pełna zawsze
    idxs = [i for i, t in enumerate(low) if t in STRIP_WORDS]
    for i in sorted(idxs, reverse=True):                     # od najdłuższego
        cut = " ".join(tokens[:i]).strip()
        if not cut:                          # dopisek na początku -> usuń słowo
            cut = " ".join(tokens[:i] + tokens[i + 1:]).strip()
        if len(cut) >= MIN_LEN:
            keywords.append(cut)

    seen, out = set(), []
    for k in keywords:
        k = re.sub(r"\s+", " ", k).strip()
        kl = k.lower()
        if k and kl not in seen:
            seen.add(kl)
            out.append(k)
    return out


def pick_table(tables):
    for df in tables:
        cols = [str(c).strip().lower() for c in df.columns]
        if "name" in cols:
            return df
    raise SystemExit("Nie znaleziono tabeli z kolumną 'Name'.")


def scrape(url: str) -> pd.DataFrame:
    html = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (data-task)"}).text
    df = pick_table(pd.read_html(StringIO(html)))

    lower = {str(c).strip().lower(): c for c in df.columns}
    missing = [k for k in COLUMNS if k not in lower]
    if missing:
        raise SystemExit(f"Brak kolumn {missing}. Dostępne: {list(df.columns)}")

    out = pd.DataFrame({target: df[lower[src]] for src, target in COLUMNS.items()})

    out["brand"] = out["brand"].map(clean_brand)
    for col in ("town", "country", "type"):
        out[col] = out[col].map(clean_cell)

    out = out[out["brand"] != ""]
    if DEDUP:
        out = out.drop_duplicates(subset="brand", keep="first")
    out = out.reset_index(drop=True)

    out["keywords"] = out["brand"].map(lambda b: "|".join(make_keywords(b)))
    return out


def main():
    df = scrape(URL)
    cols = ["brand", "keywords", "town", "country", "type"]
    df = df[cols]

    print(f"Znaleziono {len(df)} marek")
    print(df.to_string(index=False))

    DATA_DIR.mkdir(exist_ok=True)
    out = DATA_DIR / OUTPUT_NAME
    df.to_csv(out, index=False, quoting=csv.QUOTE_MINIMAL)
    print(f"\nZapisano do {out}")


if __name__ == "__main__":
    main()