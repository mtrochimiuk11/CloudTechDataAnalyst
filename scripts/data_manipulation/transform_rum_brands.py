#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Transformacja nazw marek rumu do postaci keywordow dla estymatora.

Wejscie:  data/rum_brands.csv                       (kolumny `brand`, `country`)
Wyjscie:  data/transformed/rum_brands_transformed.csv  (kolumny `brand`, `country`, `keyword`)

Kolumna `country` jest przepuszczana 1:1 (passthrough) -- przyda sie pozniej jako
zrodlo slow `optional` przy budowie zapytan do estymatora.

Skrypt jest wariantem transform_vodka_brands.py -- wspolna logika (apostrofy,
nawiasy, '&', diakrytyki, slugify) jest identyczna. Roznice wynikaja z danych
wystepujacych w rum_brands.csv (skan znakow potwierdzil ponizsze przypadki):

Reguly transformacji (uzgodnione pod semantyke estymatora -- patrz CLAUDE.md,
`mode:"m"` traktuje `-` jako dowolny znak niealfanumeryczny):

1. KONCOWE DOPISKI/ABV sa OBCINANE przed dalszym przetwarzaniem (roznica vs wodka):
   - en-dash '–' (np. "Stroh – flavored rum" -> "stroh"),
   - spacjowany myslnik " - " lub wiszacy " -" (np. "Piquero - Premium rum spirit
     drink" -> "piquero", "Man Up Rum 55% -" -> "man-up-rum"),
   - token ABV "<liczba>%" (np. "Man Up Rum 55%" -> "man-up-rum"),
   - slowo-lacznik wprowadzajace opis: " from ", " by ", " at ", " home of "
     (np. "Florida Mermaid Rum from NJoy Spirits Distillery" -> "florida-mermaid-
     rum", "Isla de Cañas by Don Pancho Rum" -> "isla-de-canas", "Desert Diamond
     Distillery home of Gold Miner Spirits" -> "desert-diamond-distillery").
     Lista jest celowo waska -- np. "distilled" pominieto, bo wycieloby prawdziwa
     marke "Chef Distilled".
   Uwaga: zwykly, niespacjowany myslnik w nazwie ZOSTAJE ("Saint-Aubin" ->
   "saint-aubin"), bo jest czescia nazwy, a nie separatorem opisu.
2. Ukosnik '/' tworzy DWA osobne keywordy -- to dwie rozne nazwy w jednym wierszu
   (roznica vs wodka): "Porchjam Distillery/Cheramie Rum" -> "porchjam-distillery"
   ORAZ "cheramie-rum".
3. Czesc w nawiasie jest usuwana: "Foo (bar)" -> "foo" (jak w wodce; w rumie brak
   takich przypadkow, regula zachowana dla spojnosci).
4. Apostrof (prosty i typograficzny) jest usuwany, a litery sklejane (tak apostrof
   zwykle znika w URL-ach): "John Watling's" -> "john-watlings", "O'Baptiste" ->
   "obaptiste".
5. Kropka (np. w skrocie) jest usuwana: "Illegal Tender Rum Co." -> "illegal-
   tender-rum-co".
6. Znak '&' tworzy DWA warianty tej samej nazwy: "Smith & Cross" -> "smith-cross"
   ORAZ "smith-and-cross".
7. Znaki diakrytyczne zamieniane na litery lacinskie: "Barceló" -> "barcelo",
   "Flor de Caña" -> "flor-de-cana", "ARÔME" -> "arome", "Božkov" -> "bozkov".
   Wszystkie diakrytyki w rum_brands.csv rozkladaja sie przez Unicode (NFKD);
   litery nierozkladalne (np. polskie 'ł') maja wlasne mapowanie w SPECJALNE.
8. Generyczne slowa "Rum"/"Rhum"/"Ron" sa ZACHOWANE w nazwie (jak "Vodka" w wodce):
   "Havana Club" -> "havana-club", "Ron Zacapa" -> "ron-zacapa".
9. Wszystko malymi literami; spacje i pozostale znaki niealfanumeryczne -> '-';
   wielokrotne '-' sklejane, '-' z brzegow obcinane.

Uruchomienie (z dowolnego cwd -- sciezki liczone wzgledem __file__):
    python3 scripts/data_manipulation/transform_rum_brands.py
"""

import csv
import re
import unicodedata
from pathlib import Path

# --- KONFIGURACJA ---
# Skrypt lezy w scripts/data_manipulation/, wiec do katalogu glownego repo trzeba
# wejsc trzy poziomy w gore (tak samo jak scrapery w scripts/scraping/).
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
PLIK_WEJSCIOWY = DATA_DIR / "rum_brands.csv"
KATALOG_WYJSCIOWY = DATA_DIR / "transformed"
PLIK_WYJSCIOWY = KATALOG_WYJSCIOWY / "rum_brands_transformed.csv"

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


def utnij_dopisek(nazwa: str) -> str:
    """Obcina koncowy dopisek opisowy/ABV; zwraca sam rdzen nazwy.

    Tnie na najwczesniejszym z markerow:
      - token ABV "<liczba>%"        (np. "55%"),
      - en-dash '\\u2013'             (zawsze separator opisu),
      - spacjowany myslnik " - " lub wiszacy " -" na koncu,
      - slowo-lacznik wprowadzajace opis (" from ", " by ", " at ", " home of ").
    Niespacjowany myslnik (np. "Saint-Aubin") NIE jest markerem -- zostaje.
    Lista slow-lacznikow jest waska i wymaga otoczenia bialymi znakami, zeby nie
    ucinac prawdziwych nazw (np. "Chef Distilled" zostaje nietkniete).
    """
    pozycje = []

    m = re.search(r"\d+\s*%", nazwa)            # ABV: liczba + '%'
    if m:
        pozycje.append(m.start())

    i = nazwa.find("–")                    # en-dash
    if i != -1:
        pozycje.append(i)

    m = re.search(r"\s-(?:\s|$)", nazwa)        # spacjowany / wiszacy myslnik
    if m:
        pozycje.append(m.start())

    # slowo-lacznik wprowadzajace opis (jako osobny token, otoczone bialymi znakami)
    m = re.search(r"(?i)\s+(?:from|by|at|home\s+of)\s+", nazwa)
    if m:
        pozycje.append(m.start())

    if pozycje:
        nazwa = nazwa[:min(pozycje)]
    return nazwa


def warianty_keywordow(nazwa: str) -> list:
    """Zwraca liste keywordow dla jednej nazwy marki (zwykle 1, dla '&'/'/' wiecej)."""
    # 1. Obetnij koncowy dopisek opisowy/ABV.
    nazwa = utnij_dopisek(nazwa)
    # 2. Usun czesc w nawiasie.
    nazwa = re.sub(r"\([^)]*\)", " ", nazwa)
    # 3. Usun apostrofy (prosty i typograficzny) -- litery zostaja sklejone.
    nazwa = nazwa.replace("'", "").replace("’", "")

    # 4. '/' -> osobne nazwy (dwie rozne marki w jednym wierszu).
    czesci = [c for c in nazwa.split("/") if c.strip()]

    # 5. Dla kazdej czesci: '&' -> dwa warianty zrodlowe; bez '&' -> jeden.
    zrodla = []
    for czesc in czesci:
        if "&" in czesc:
            zrodla.append(czesc.replace("&", " "))
            zrodla.append(czesc.replace("&", " and "))
        else:
            zrodla.append(czesc)

    # 6. Slugify kazdego wariantu, z deduplikacja i zachowaniem kolejnosci.
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
        # (brand, country) -- country przepuszczamy 1:1.
        marki = [
            (wiersz["brand"].strip(), (wiersz.get("country") or "").strip())
            for wiersz in czytnik
            if wiersz.get("brand", "").strip()
        ]

    wiersze_wyjsciowe = []
    widziane = set()  # deduplikacja par (brand, keyword); country zalezy od brand
    for marka, country in marki:
        for keyword in warianty_keywordow(marka):
            klucz = (marka, keyword)
            if klucz not in widziane:
                widziane.add(klucz)
                wiersze_wyjsciowe.append({"brand": marka, "country": country, "keyword": keyword})

    with PLIK_WYJSCIOWY.open("w", encoding="utf-8", newline="") as f:
        # lineterminator="\n" -> czyste koncowki LF (jak wejsciowy rum_brands.csv);
        # unika stray '\r' w keywordach trafiajacych pozniej do zapytan JSON.
        zapis = csv.DictWriter(f, fieldnames=["brand", "country", "keyword"], lineterminator="\n")
        zapis.writeheader()
        zapis.writerows(wiersze_wyjsciowe)

    print(f"Wczytano marek:        {len(marki)}")
    print(f"Zapisano keywordow:    {len(wiersze_wyjsciowe)}")
    print(f"Plik wyjsciowy:        {PLIK_WYJSCIOWY}")


if __name__ == "__main__":
    main()
