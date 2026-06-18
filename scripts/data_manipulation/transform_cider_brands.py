#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Transformacja marek cydru do NAJOGOLNIEJSZEGO keywordu dla estymatora.

Wejscie:  data/cider_brands.csv                       (kolumny `brand`, `keywords`, `town`, `country`, `type`)
Wyjscie:  data/transformed/cider_brands_transformed.csv  (kolumny `brand`, `town`, `country`, `type`, `keyword`)

Sytuacja identyczna jak w transform_liqueur_brands.py: kolumna `keywords` zostala
wczesniej wygenerowana ze `brand` przez odcinanie generycznych slow-dopiskow
(cider, cyder, ...). Warianty rozdzielone '|' sa uporzadkowane od najbardziej
szczegolowego (pelna nazwa = keywords[0], rowne `brand`) do najbardziej ogolnego
(keywords[-1]). Przyklad:
    "Woodchuck Hard Cider" -> "Woodchuck Hard Cider|Woodchuck Hard|Woodchuck"

STRATEGIA (lejek recall-first)
------------------------------
Bierzemy TYLKO NAJOGOLNIEJSZY wariant (ostatni element '|') jako tania "sonde":
sprawdzamy estymatorem, czy marka w ogole wystepuje w korpusie URL. Dopiero dla
trafien w kolejnym kroku buduje sie wezsze zapytania z wczesniejszych wariantow
kolumny `keywords`. Dlatego produkujemy JEDEN keyword na marke.

ZABEZPIECZENIE (jak w likierach -- tu profilaktyczne)
----------------------------------------------------
Gdyby ostatni element po slugify byl czystym generykiem (GENERYKI_KONCOWE), bierzemy
PIERWSZY element (pelna nazwe). W cider_brands.csv taki przypadek NIE wystepuje
(np. "K Cider" slugify'uje sie do "k-cider", nie "cider"), ale guard zostawiamy
dla spojnosci i odpornosci.

Kolumny `town`, `country`, `type` sa przepuszczane 1:1 (passthrough) -- pozniej
zrodlo slow `optional` przy budowie zapytan.

Reguly slugify (jak w pozostalych transformerach): apostrofy usuwane i sklejane
("Doc's" -> "docs", "Willie Smith's" -> "willie-smiths"), nawiasy usuwane,
diakrytyki przez NFKD + mapa SPECJALNE dla liter nierozkladalnych ("Miłosławski"
-> "miloslawski"), reszta znakow niealfanumerycznych -> '-'. Tu NIE rozbijamy
'&'/'/' na osobne warianty (lejek = jedna sonda na marke).

Uruchomienie (z dowolnego cwd -- sciezki liczone wzgledem __file__):
    python3 scripts/data_manipulation/transform_cider_brands.py
"""

import csv
import re
import unicodedata
from pathlib import Path

# --- KONFIGURACJA ---
# Skrypt lezy w scripts/data_manipulation/, wiec do katalogu glownego repo trzeba
# wejsc trzy poziomy w gore (tak samo jak scrapery w scripts/scraping/).
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
PLIK_WEJSCIOWY = DATA_DIR / "cider_brands.csv"
KATALOG_WYJSCIOWY = DATA_DIR / "transformed"
PLIK_WYJSCIOWY = KATALOG_WYJSCIOWY / "cider_brands_transformed.csv"
# Kolumny przepuszczane 1:1 (passthrough).
KOLUMNY_PASSTHROUGH = ["town", "country", "type"]

# Czyste generyki, ktore NIE moga byc samodzielna "nazwa" -- jesli ostatni wariant
# slugify'uje sie do jednego z nich, bierzemy pierwszy element (pelna marke).
GENERYKI_KONCOWE = {"cider", "cyder", "cidre", "liqueur", "liqueurs", "cream", "coffee"}

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


def keyword_z_elementu(element: str) -> str:
    """Slugify pojedynczego wariantu: usun nawiasy i apostrofy, potem slugify."""
    element = re.sub(r"\([^)]*\)", " ", element)
    element = element.replace("'", "").replace("’", "")
    return slugify(element)


def wybierz_ogolny(keywords_raw: str) -> str:
    """Zwraca najogolniejszy wariant z kolumny `keywords` (z guardem na generyki)."""
    czesci = [c.strip() for c in keywords_raw.split("|") if c.strip()]
    if not czesci:
        return ""
    ogolny = czesci[-1]
    # Guard: ostatni element to czysty generyk -> bierzemy pelna nazwe (pierwszy).
    if slugify(ogolny) in GENERYKI_KONCOWE:
        ogolny = czesci[0]
    return ogolny


def main() -> None:
    KATALOG_WYJSCIOWY.mkdir(exist_ok=True)

    with PLIK_WEJSCIOWY.open(encoding="utf-8-sig", newline="") as f:
        czytnik = csv.DictReader(f)
        rekordy = [w for w in czytnik if (w.get("brand") or "").strip()]

    wiersze_wyjsciowe = []
    widziane = set()  # deduplikacja par (brand, keyword)
    for rek in rekordy:
        brand = rek["brand"].strip()
        keywords_raw = (rek.get("keywords") or brand).strip()
        passthrough = {k: (rek.get(k) or "").strip() for k in KOLUMNY_PASSTHROUGH}

        keyword = keyword_z_elementu(wybierz_ogolny(keywords_raw))
        if not keyword:
            continue
        klucz = (brand, keyword)
        if klucz not in widziane:
            widziane.add(klucz)
            wiersze_wyjsciowe.append({"brand": brand, **passthrough, "keyword": keyword})

    fieldnames = ["brand"] + KOLUMNY_PASSTHROUGH + ["keyword"]
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
