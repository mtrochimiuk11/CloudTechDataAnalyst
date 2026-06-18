#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Transformacja nazw marek wodki do postaci keywordow dla estymatora.

Wejscie:  data/vodka_brands.csv            (kolumna `brand`)
Wyjscie:  data/transformed/vodka_brands_transformed.csv  (kolumny `brand`, `keyword`)

Regul transformacji (uzgodnione pod semantyke estymatora -- patrz CLAUDE.md,
`mode:"m"` traktuje `-` jako dowolny znak niealfanumeryczny):

1. Czesc w nawiasie (nazwa w cyrylicy) jest usuwana:
   "Gold Symphony (Золотая симфония)" -> "gold-symphony".
2. Apostrof jest usuwany, a litery sklejane (tak apostrof zwykle znika w URL-ach):
   "Tito's" -> "titos", "L'Chaim" -> "lchaim".
3. Kropka (np. w skrocie) jest usuwana: "Leopold Bros." -> "leopold-bros".
4. Znak '&' tworzy DWIE pozycje wyjsciowe:
   "Boyd & Blair" -> "boyd-blair" ORAZ "boyd-and-blair".
5. Znaki diakrytyczne zamieniane na litery lacinskie: "Żubrówka" -> "zubrowka",
   "Cîroc" -> "ciroc", "Ström" -> "strom". Litery nierozkladalne przez Unicode
   (np. polskie 'ł') maja wlasne mapowanie w SPECJALNE.
6. Generyczne slowo "Vodka" jest ZACHOWANE w nazwie: "Kors Vodka" -> "kors-vodka".
7. Wszystko malymi literami; spacje i pozostale znaki niealfanumeryczne -> '-';
   wielokrotne '-' sklejane, '-' z brzegow obcinane.

Uruchomienie (z dowolnego cwd -- sciezki liczone wzgledem __file__):
    python3 scripts/data_manipulation/transform_vodka_brands.py
"""

import csv
import re
import unicodedata
from pathlib import Path

# --- KONFIGURACJA ---
# Skrypt lezy w scripts/data_manipulation/, wiec do katalogu glownego repo trzeba
# wejsc trzy poziomy w gore (tak samo jak scrapery w scripts/scraping/).
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
PLIK_WEJSCIOWY = DATA_DIR / "vodka_brands.csv"
KATALOG_WYJSCIOWY = DATA_DIR / "transformed"
PLIK_WYJSCIOWY = KATALOG_WYJSCIOWY / "vodka_brands_transformed.csv"

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
    # 1. Litery nierozkladalne -> reczne mapowanie.
    for zrodlo, cel in SPECJALNE.items():
        tekst = tekst.replace(zrodlo, cel)
    # 2. Rozklad kanoniczny (NFKD) i usuniecie znakow laczacych (diakrytyk).
    nfkd = unicodedata.normalize("NFKD", tekst)
    return "".join(znak for znak in nfkd if not unicodedata.combining(znak))


def slugify(tekst: str) -> str:
    """Sprowadza tekst do keywordu: ASCII, male litery, slowa laczone '-'."""
    tekst = transliteruj(tekst).lower()
    # Cokolwiek poza [a-z0-9] (spacje, kropki, pozostale znaki) -> separator '-'.
    tekst = re.sub(r"[^a-z0-9]+", "-", tekst)
    return tekst.strip("-")


def warianty_keywordow(nazwa: str) -> list:
    """Zwraca liste keywordow dla jednej nazwy marki (zwykle 1, dla '&' -- 2)."""
    # 1. Usun czesc w nawiasie (nazwa w cyrylicy).
    nazwa = re.sub(r"\([^)]*\)", " ", nazwa)
    # 2. Usun apostrofy (prosty i typograficzny) -- litery zostaja sklejone.
    nazwa = nazwa.replace("'", "").replace("’", "")

    # 3. Znak '&' -> dwa warianty zrodlowe; bez '&' -> jeden.
    if "&" in nazwa:
        zrodla = [nazwa.replace("&", " "), nazwa.replace("&", " and ")]
    else:
        zrodla = [nazwa]

    # 4. Slugify kazdego wariantu, z deduplikacja i zachowaniem kolejnosci.
    keywordy = []
    for zrodlo in zrodla:
        keyword = slugify(zrodlo)
        if keyword and keyword not in keywordy:
            keywordy.append(keyword)
    return keywordy


def main() -> None:
    KATALOG_WYJSCIOWY.mkdir(exist_ok=True)

    with PLIK_WEJSCIOWY.open(encoding="utf-8-sig", newline="") as f:
        czytnik = csv.DictReader(f)
        marki = [wiersz["brand"].strip() for wiersz in czytnik if wiersz.get("brand", "").strip()]

    wiersze_wyjsciowe = []
    widziane = set()  # deduplikacja par (brand, keyword)
    for marka in marki:
        for keyword in warianty_keywordow(marka):
            klucz = (marka, keyword)
            if klucz not in widziane:
                widziane.add(klucz)
                wiersze_wyjsciowe.append({"brand": marka, "keyword": keyword})

    with PLIK_WYJSCIOWY.open("w", encoding="utf-8", newline="") as f:
        # lineterminator="\n" -> czyste koncowki LF (jak wejsciowy vodka_brands.csv);
        # unika stray '\r' w keywordach trafiajacych pozniej do zapytan JSON.
        zapis = csv.DictWriter(f, fieldnames=["brand", "keyword"], lineterminator="\n")
        zapis.writeheader()
        zapis.writerows(wiersze_wyjsciowe)

    print(f"Wczytano marek:        {len(marki)}")
    print(f"Zapisano keywordow:    {len(wiersze_wyjsciowe)}")
    print(f"Plik wyjsciowy:        {PLIK_WYJSCIOWY}")


if __name__ == "__main__":
    main()
