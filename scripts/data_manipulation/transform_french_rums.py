#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Transformacja nazw rumow francuskich do postaci keywordow dla estymatora.

Wejscie:  data/french_rums.csv                       (kolumny `name`, `location`)
Wyjscie:  data/transformed/french_rums_transformed.csv  (kolumny `name`, `location`, `keyword`)

Kolumna `location` jest przepuszczana 1:1 (passthrough) -- przyda sie pozniej jako
zrodlo slow `optional` przy budowie zapytan do estymatora.

Wariant transform_rum_brands.py -- wspolna logika (apostrofy, nawiasy, '&', '/',
obcinanie dopiskow, diakrytyki, slugify) jest identyczna; rozni sie tylko blok
KONFIGURACJA. Skan znakow potwierdzil: diakrytyki (è, é) rozkladaja sie przez
NFKD, kropki (np. "Rhum J.M." -> "rhum-j-m") i apostrof ("O'Baptiste" ->
"obaptiste") sa obslugiwane, niespacjowany myslnik zostaje ("Saint-Maurice" ->
"saint-maurice"). Generyczne slowo "Rhum" jest ZACHOWANE: "Rhum Clement" ->
"rhum-clement".

Uruchomienie (z dowolnego cwd -- sciezki liczone wzgledem __file__):
    python3 scripts/data_manipulation/transform_french_rums.py
"""

import csv
import re
import unicodedata
from pathlib import Path

# --- KONFIGURACJA ---
# Skrypt lezy w scripts/data_manipulation/, wiec do katalogu glownego repo trzeba
# wejsc trzy poziomy w gore (tak samo jak scrapery w scripts/scraping/).
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
PLIK_WEJSCIOWY = DATA_DIR / "french_rums.csv"
KATALOG_WYJSCIOWY = DATA_DIR / "transformed"
PLIK_WYJSCIOWY = KATALOG_WYJSCIOWY / "french_rums_transformed.csv"
# Kolumna z nazwa marki oraz kolumny przepuszczane 1:1 (passthrough).
KOLUMNA_NAZWY = "name"
KOLUMNY_PASSTHROUGH = ["location"]

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


def utnij_dopisek(nazwa: str) -> str:
    """Obcina koncowy dopisek opisowy/ABV; zwraca sam rdzen nazwy.

    Tnie na najwczesniejszym z markerow: token ABV "<liczba>%", en-dash '\\u2013',
    spacjowany/wiszacy myslnik " - ", slowo-lacznik (" from "/" by "/" at "/
    " home of "). Niespacjowany myslnik (np. "Saint-Maurice") ZOSTAJE.
    """
    pozycje = []
    m = re.search(r"\d+\s*%", nazwa)
    if m:
        pozycje.append(m.start())
    i = nazwa.find("–")
    if i != -1:
        pozycje.append(i)
    m = re.search(r"\s-(?:\s|$)", nazwa)
    if m:
        pozycje.append(m.start())
    m = re.search(r"(?i)\s+(?:from|by|at|home\s+of)\s+", nazwa)
    if m:
        pozycje.append(m.start())
    if pozycje:
        nazwa = nazwa[:min(pozycje)]
    return nazwa


def warianty_keywordow(nazwa: str) -> list:
    """Zwraca liste keywordow dla jednej nazwy (zwykle 1, dla '&'/'/' wiecej)."""
    nazwa = utnij_dopisek(nazwa)
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


def main() -> None:
    KATALOG_WYJSCIOWY.mkdir(exist_ok=True)

    with PLIK_WEJSCIOWY.open(encoding="utf-8-sig", newline="") as f:
        czytnik = csv.DictReader(f)
        rekordy = [w for w in czytnik if (w.get(KOLUMNA_NAZWY) or "").strip()]

    wiersze_wyjsciowe = []
    widziane = set()  # deduplikacja par (nazwa, keyword); passthrough zalezy od nazwy
    for rek in rekordy:
        nazwa = rek[KOLUMNA_NAZWY].strip()
        passthrough = {k: (rek.get(k) or "").strip() for k in KOLUMNY_PASSTHROUGH}
        for keyword in warianty_keywordow(nazwa):
            klucz = (nazwa, keyword)
            if klucz not in widziane:
                widziane.add(klucz)
                wiersze_wyjsciowe.append({KOLUMNA_NAZWY: nazwa, **passthrough, "keyword": keyword})

    fieldnames = [KOLUMNA_NAZWY] + KOLUMNY_PASSTHROUGH + ["keyword"]
    with PLIK_WYJSCIOWY.open("w", encoding="utf-8", newline="") as f:
        # lineterminator="\n" -> czyste koncowki LF; unika stray '\r' w keywordach.
        zapis = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        zapis.writeheader()
        zapis.writerows(wiersze_wyjsciowe)

    print(f"Wczytano nazw:         {len(rekordy)}")
    print(f"Zapisano keywordow:    {len(wiersze_wyjsciowe)}")
    print(f"Plik wyjsciowy:        {PLIK_WYJSCIOWY}")


if __name__ == "__main__":
    main()
