#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Transformacja marek z The Whisky Exchange do keywordow + normalizacja kategorii.

Wejscie:  data/twe_brands_merged.csv                       (kolumny `brand`, `category`)
Wyjscie:  data/transformed/twe_brands_transformed.csv  (kolumny `brand`, `category`, `keyword`)

To SUROWA lista marek (jak rum_brands.csv), wiec keyword budujemy z pelnej nazwy
`brand` -- logika jak w transform_rum_brands.py, ale BEZ obcinania koncowych
dopiskow (utnij_dopisek). Powod: w tym zbiorze nie ma en-dash / ABV / spacjowanego
myslnika / '/', a jedyne dopasowanie slowa-lacznika to prawdziwa marka
"Ten Minutes by Tractor" -- obcinanie po " by " zepsuloby ja, wiec go nie ma.

Reguly budowy keywordu:
1. Czesc w nawiasie usuwana: "Ketel One (Jenever)" -> "ketel-one".
2. Apostrof (prosty i typograficzny) usuwany, litery sklejane: "JP Wiser's" ->
   "jp-wisers", "Macaloney’s" -> "macaloneys".
3. Znak '&' tworzy DWA warianty: "Lubberhuizen & Raaff" -> "lubberhuizen-raaff"
   ORAZ "lubberhuizen-and-raaff".
4. Ukosnik '/' rozbija na osobne nazwy (w tym zbiorze nie wystepuje).
5. Diakrytyki przez NFKD + mapa SPECJALNE: "Nikka" itd.; "Ñ"->"n", "ä"->"a".
6. Reszta znakow niealfanumerycznych ('.', '-', '+', '@', '°', ',') -> '-';
   wielokrotne '-' sklejane, brzegowe obcinane ("CRN57°" -> "crn57").

Normalizacja kolumny `category` (wymaganie zadania):
   jesli category == "Blended Malt" ALBO zawiera (bez wzgledu na wielkosc liter)
   "whisky" lub "whiskey" -> zamien na "whisky"; w przeciwnym razie zostaw bez zmian.

Uruchomienie (z dowolnego cwd -- sciezki liczone wzgledem __file__):
    python3 scripts/data_manipulation/transform_twe_brands.py
"""

import csv
import re
import unicodedata
from pathlib import Path

# --- KONFIGURACJA ---
# Skrypt lezy w scripts/data_manipulation/, wiec do katalogu glownego repo trzeba
# wejsc trzy poziomy w gore (tak samo jak scrapery w scripts/scraping/).
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
PLIK_WEJSCIOWY = DATA_DIR / "twe_brands_merged.csv"
KATALOG_WYJSCIOWY = DATA_DIR / "transformed"
PLIK_WYJSCIOWY = KATALOG_WYJSCIOWY / "twe_brands_transformed.csv"

# Litery, ktorych NFKD nie rozklada na "litera + znak laczacy" -- mapujemy recznie.
SPECJALNE = {
    "ł": "l", "Ł": "l",
    "ø": "o", "Ø": "o",
    "đ": "d", "Đ": "d",
    "ð": "d", "Ð": "d",
    "þ": "th", "Þ": "th",
    "ß": "ss",
    "æ": "ae", "Æ": "ae",
    "œ": "oe", "Œ": "oe",
    "ı": "i", "İ": "i",
}


def transliteruj(tekst: str) -> str:
    """Zamienia znaki diakrytyczne na odpowiedniki lacinskie (ASCII)."""
    for zrodlo, cel in SPECJALNE.items():
        tekst = tekst.replace(zrodlo, cel)
    nfkd = unicodedata.normalize("NFKD", tekst)
    return "".join(znak for znak in nfkd if not unicodedata.combining(znak))


def slugify(tekst: str) -> str:
    """Sprowadza tekst do keywordu: ASCII, male litery, slowa laczone '-'."""
    tekst = transliteruj(tekst).lower()
    tekst = re.sub(r"[^a-z0-9]+", "-", tekst)
    return tekst.strip("-")


def warianty_keywordow(nazwa: str) -> list:
    """Zwraca liste keywordow dla jednej nazwy (zwykle 1, dla '&'/'/' wiecej)."""
    nazwa = re.sub(r"\([^)]*\)", " ", nazwa)
    nazwa = nazwa.replace("'", "").replace("’", "")

    czesci = [c for c in nazwa.split("/") if c.strip()]
    zrodla = []
    for czesc in czesci:
        if "&" in czesc:
            zrodla.append(czesc.replace("&", " "))
            zrodla.append(czesc.replace("&", " and "))
        else:
            zrodla.append(czesc)

    keywordy = []
    for zrodlo in zrodla:
        keyword = slugify(zrodlo)
        if keyword and keyword not in keywordy:
            keywordy.append(keyword)
    return keywordy


def normalizuj_kategorie(category: str) -> str:
    """'Blended Malt' lub kategoria zawierajaca 'whisky'/'whiskey' -> 'whisky'."""
    c = category.strip()
    if c == "Blended Malt" or "whisky" in c.lower() or "whiskey" in c.lower():
        return "whisky"
    return c


def main() -> None:
    KATALOG_WYJSCIOWY.mkdir(exist_ok=True)

    with PLIK_WEJSCIOWY.open(encoding="utf-8-sig", newline="") as f:
        czytnik = csv.DictReader(f)
        rekordy = [w for w in czytnik if (w.get("brand") or "").strip()]

    wiersze_wyjsciowe = []
    widziane = set()  # deduplikacja trojek (brand, category, keyword)
    for rek in rekordy:
        brand = rek["brand"].strip()
        category = normalizuj_kategorie(rek.get("category") or "")
        for keyword in warianty_keywordow(brand):
            klucz = (brand, category, keyword)
            if klucz not in widziane:
                widziane.add(klucz)
                wiersze_wyjsciowe.append({"brand": brand, "category": category, "keyword": keyword})

    with PLIK_WYJSCIOWY.open("w", encoding="utf-8", newline="") as f:
        # lineterminator="\n" -> czyste koncowki LF; unika stray '\r' w keywordach.
        zapis = csv.DictWriter(f, fieldnames=["brand", "category", "keyword"], lineterminator="\n")
        zapis.writeheader()
        zapis.writerows(wiersze_wyjsciowe)

    print(f"Wczytano nazw:         {len(rekordy)}")
    print(f"Zapisano keywordow:    {len(wiersze_wyjsciowe)}")
    print(f"Plik wyjsciowy:        {PLIK_WYJSCIOWY}")


if __name__ == "__main__":
    main()
