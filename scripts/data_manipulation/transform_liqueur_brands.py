#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Transformacja marek likierow do NAJOGOLNIEJSZEGO keywordu dla estymatora.

Wejscie:  data/liqueur_brands.csv                       (kolumny `category`, `brand`, `keywords`)
Wyjscie:  data/transformed/liqueur_brands_transformed.csv  (kolumny `category`, `brand`, `keyword`)

KONTEKST DANYCH
---------------
Kolumna `keywords` zostala wczesniej wygenerowana ze `brand` przez odcinanie
generycznych slow-dopiskow (liqueur, cream, ...). Jesli marka miala wiecej niz
jeden taki dopisek, powstalo kilka wariantow rozdzielonych '|', uporzadkowanych
od najbardziej szczegolowego (pelna nazwa = keywords[0], rowne `brand`) do
najbardziej ogolnego (keywords[-1]). Przyklad:
    "Cadbury Cream Liqueur" -> "Cadbury Cream Liqueur|Cadbury Cream|Cadbury"

STRATEGIA (lejek recall-first)
------------------------------
Ten skrypt bierze TYLKO NAJOGOLNIEJSZY wariant (ostatni element '|') jako tania
"sonde": sprawdzamy estymatorem, czy marka w ogole wystepuje w korpusie URL.
Dopiero dla marek, ktore zwracaja jakies trafienie, w kolejnym kroku buduje sie
bardziej szczegolowe zapytania z wczesniejszych (wezszych) wariantow kolumny
`keywords`. Dlatego tutaj produkujemy JEDEN keyword na marke.

ZABEZPIECZENIE (wiersze Kamok/Kamora)
-------------------------------------
Dwa wiersze maja nietypowy format "Marka|Pochodzenie|coffee|liqueur" -- ostatni
element to czysty generyk ("liqueur"), a nie nazwa. Gdy ostatni element po
slugify jest czystym generykiem (GENERYKI_KONCOWE), spadamy na PIERWSZY element
(pelna nazwe). Dla 233 wierszy jednoelementowych first == last, wiec guard jest
tam no-opem; rozni sie tylko dla Kamok -> "kamok", Kamora -> "kamora".

Reguly slugify (jak w pozostalych transformerach): apostrofy usuwane i sklejane
("Dooley's" -> "dooleys"), nawiasy usuwane, diakrytyki przez NFKD ("Kahlúa" ->
"kahlua", "Curaçao" -> "curacao"), reszta znakow niealfanumerycznych -> '-'.
Tu NIE rozbijamy '&'/'/' na osobne warianty (lejek = jedna sonda na marke).

Uruchomienie (z dowolnego cwd -- sciezki liczone wzgledem __file__):
    python3 scripts/data_manipulation/transform_liqueur_brands.py
"""

import csv
import re
import unicodedata
from pathlib import Path

# --- KONFIGURACJA ---
# Skrypt lezy w scripts/data_manipulation/, wiec do katalogu glownego repo trzeba
# wejsc trzy poziomy w gore (tak samo jak scrapery w scripts/scraping/).
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
PLIK_WEJSCIOWY = DATA_DIR / "liqueur_brands.csv"
KATALOG_WYJSCIOWY = DATA_DIR / "transformed"
PLIK_WYJSCIOWY = KATALOG_WYJSCIOWY / "liqueur_brands_transformed.csv"

# Czyste generyki, ktore NIE moga byc samodzielna "nazwa" -- jesli ostatni wariant
# slugify'uje sie do jednego z nich, bierzemy pierwszy element (pelna marke).
GENERYKI_KONCOWE = {"liqueur", "liqueurs", "coffee", "cream", "cider"}

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
    widziane = set()  # deduplikacja par (brand, keyword) -- ta sama marka bywa w kilku kategoriach
    for rek in rekordy:
        category = (rek.get("category") or "").strip()
        brand = rek["brand"].strip()
        keywords_raw = (rek.get("keywords") or brand).strip()

        keyword = keyword_z_elementu(wybierz_ogolny(keywords_raw))
        if not keyword:
            continue
        klucz = (brand, keyword)
        if klucz not in widziane:
            widziane.add(klucz)
            wiersze_wyjsciowe.append({"category": category, "brand": brand, "keyword": keyword})

    with PLIK_WYJSCIOWY.open("w", encoding="utf-8", newline="") as f:
        # lineterminator="\n" -> czyste koncowki LF; unika stray '\r' w keywordach.
        zapis = csv.DictWriter(f, fieldnames=["category", "brand", "keyword"], lineterminator="\n")
        zapis.writeheader()
        zapis.writerows(wiersze_wyjsciowe)

    print(f"Wczytano nazw:         {len(rekordy)}")
    print(f"Zapisano keywordow:    {len(wiersze_wyjsciowe)}")
    print(f"Plik wyjsciowy:        {PLIK_WYJSCIOWY}")


if __name__ == "__main__":
    main()
