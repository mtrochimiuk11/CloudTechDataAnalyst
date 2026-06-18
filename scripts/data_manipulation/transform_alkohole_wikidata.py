#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Transformacja marek alkoholi z Wikidata do kandydatur keywordow dla estymatora.

Wejscie:  data/alkohole_wikidata_filtered.csv
          (kolumny: wikidata,name,aliases,types,makers,countries)
Wyjscie:  data/transformed/alkohole_wikidata_transformed.csv
          (kolumny: wikidata,name,keyword,keyword_variants,types,makers,countries)

Jeden wiersz wejsciowy = jedna marka = jeden wiersz wyjsciowy. W odroznieniu od
transform_rum_brands.py (1 wiersz = 1 keyword) kazda marka niesie tu kilka
kandydatur keywordow zlaczonych '|' w kolumnie `keyword_variants` -- tak jak w
liqueur/cider (patrz CLAUDE.md). `keyword` to glowny slug nazwy (rdzen pod
`required`), a `keyword_variants` to pelna lista wariantow do przetestowania.

Skad biora sie warianty:
  - slug pelnej `name`  (glowny, najprecyzyjniejszy keyword),
  - slug nazwy z odcietym KONCOWYM generykiem korporacyjnym/produkcyjnym
    (brewery, company, distillery, brewing, co, group... -- patrz STRIP_TRAILING),
  - slug nazwy z odcietym POCZATKOWYM generykiem (the, champagne, birra,
    brauerei... -- STRIP_LEADING),
  - to samo dla sensownych `aliases` (oddzielonych '|').
Slowa typu trunku na koncu (beer, vodka, rum, gin, lager...) SA CELOWO ZACHOWANE
-- daja precyzyjny standalone-match w mode:"m" ("red-horse-beer"), a samo
"brisbane" czy "murree" bylyby zbyt wieloznaczne (skan koncowych tokenow nazw to
potwierdzil: brewery/company/distillery to generyki, ale beer/vodka/rum to czesc
tozsamosci marki).

Kontekst do slow `optional` (`types`, `makers`, `countries`) jest przepuszczany
1:1 -- finalny dobor slow opcjonalnych nastepuje dopiero przy budowie zapytan,
na podstawie probek URL z estymatora.

Czyszczenie aliasow: pomijane sa aliasy puste, dluzsze niz MAX_ALIAS_WORDS slow
(opisowe pelne nazwy prawne, malo prawdopodobne w URL-ach), figurujace w
ALIAS_DENYLIST (ewidentny smiec, np. "qwerty" przy Martini) oraz takie, ktore po
slugify daja keyword juz obecny na liscie wariantow.

Uruchomienie (z dowolnego cwd -- sciezki liczone wzgledem __file__):
    python3 scripts/data_manipulation/transform_alkohole_wikidata.py
"""

import csv
import re
import unicodedata
from pathlib import Path

# --- KONFIGURACJA ---
# Skrypt lezy w scripts/data_manipulation/, wiec do katalogu glownego repo trzeba
# wejsc trzy poziomy w gore (tak samo jak pozostale transformy i scrapery).
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
PLIK_WEJSCIOWY = DATA_DIR / "alkohole_wikidata_filtered.csv"
KATALOG_WYJSCIOWY = DATA_DIR / "transformed"
PLIK_WYJSCIOWY = KATALOG_WYJSCIOWY / "alkohole_wikidata_transformed.csv"

MAX_ALIAS_WORDS = 4  # aliasy dluzsze pomijamy jako zrodlo keywordow (zbyt opisowe)

# Ewidentny smiec w kolumnie aliases (wykryty recznie -- patrz Martini).
ALIAS_DENYLIST = {"qwerty"}

# Generyki KORPORACYJNE/PRODUKCYJNE odcinane z KONCA nazwy (slug-tokeny).
# Daja dodatkowy, szerszy wariant: "Carling Brewery" -> tez "carling".
# UWAGA: brak tu slow typu trunku (beer/vodka/rum/...) -- te zostaja w slugu.
STRIP_TRAILING = {
    "brewery", "breweries", "brewing",
    "company", "co",
    "distillery", "distilleries", "distillers", "distilling",
    "winery", "wineries", "wines", "vineyard", "vineyards", "cellars", "cellar",
    "group", "brands", "beverages", "beverage", "drinks",
    "brauerei", "brau", "brasserie", "browar", "browary", "birra",
    "cerveceria", "cervejaria",
    "ltd", "limited", "inc", "incorporated", "plc", "corp", "corporation",
    "holdings", "ag", "sa", "spa", "gmbh", "llc", "ab", "kg", "nv", "bv",
    "srl", "sas",
}

# Generyki odcinane z POCZATKU nazwy (slug-tokeny). "Champagne Pol Roger" -> tez
# "pol-roger"; "Birra Moretti" -> tez "moretti"; "The Macallan" -> tez "macallan".
STRIP_LEADING = {
    "the", "champagne", "birra", "brauerei", "brau", "browar", "browary",
    "brasserie", "brouwerij", "cerveceria", "cervejaria", "domaine", "maison",
    "bodega", "bodegas", "weingut", "cantina",
}

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


def odetnij_tokeny(slug: str) -> list:
    """Z gotowego slug-a zwraca warianty z odcietymi generykami brzegowymi.

    Zamiast zachlannie ucinac od razu do rdzenia, generuje KAZDY posredni poziom
    obciecia -- tak by powstal tez najuzyteczniejszy wariant srodkowy. Np.
    "capital-brewing-company" -> "capital-brewing-company", "capital-brewing",
    "capital" (a nie tylko skrajne dwa). Pelny slug jest zawsze pierwszy.

    Obcinane sa wylacznie spojne tokeny brzegowe z list STRIP_*; nigdy nie obcina
    do pustego (zostaje >= 1 token).
    """
    if not slug:
        return []
    tokeny = slug.split("-")
    n = len(tokeny)

    # Ile spojnych tokenow z poczatku / konca nadaje sie do odciecia.
    li = 0
    while li < n - 1 and tokeny[li] in STRIP_LEADING:
        li += 1
    tj = 0
    while tj < n - 1 and tokeny[n - 1 - tj] in STRIP_TRAILING:
        tj += 1

    warianty = []
    for i in range(li + 1):           # i tokenow z poczatku
        for j in range(tj + 1):       # j tokenow z konca
            if i + j >= n:            # nie zostawiaj pustego
                continue
            s = "-".join(tokeny[i:n - j])
            if s and s not in warianty:
                warianty.append(s)
    return warianty


def warianty_nazwy(nazwa: str) -> list:
    """Wszystkie kandydatury keywordow z jednej nazwy (name lub alias)."""
    # Usun czesc w nawiasie: "Xingu (beer)" -> "Xingu".
    nazwa = re.sub(r"\([^)]*\)", " ", nazwa)
    # Usun apostrofy (prosty i typograficzny) -- litery zostaja sklejone.
    nazwa = nazwa.replace("'", "").replace("’", "")
    # '&' -> dwa zrodla: "Smith & Cross" -> "smith cross" oraz "smith and cross".
    if "&" in nazwa:
        zrodla = [nazwa.replace("&", " "), nazwa.replace("&", " and ")]
    else:
        zrodla = [nazwa]

    out = []
    for z in zrodla:
        for w in odetnij_tokeny(slugify(z)):
            if w not in out:
                out.append(w)
    return out


def main() -> None:
    KATALOG_WYJSCIOWY.mkdir(exist_ok=True)

    with PLIK_WEJSCIOWY.open(encoding="utf-8-sig", newline="") as f:
        wiersze = list(csv.DictReader(f))

    wynik = []
    for r in wiersze:
        name = (r.get("name") or "").strip()
        if not name:
            continue

        warianty = []
        # 1. Warianty z nazwy kanonicznej (glowny keyword bedzie pierwszy).
        for w in warianty_nazwy(name):
            if w not in warianty:
                warianty.append(w)
        # 2. Warianty z aliasow (krotkich, nie-smieciowych).
        for alias in (r.get("aliases") or "").split("|"):
            alias = alias.strip()
            if not alias or len(alias.split()) > MAX_ALIAS_WORDS:
                continue
            if alias.lower() in ALIAS_DENYLIST:
                continue
            for w in warianty_nazwy(alias):
                if w not in warianty:
                    warianty.append(w)

        if not warianty:
            continue

        wynik.append({
            "wikidata": r.get("wikidata", ""),
            "name": name,
            "keyword": warianty[0],
            "keyword_variants": "|".join(warianty),
            "types": (r.get("types") or "").strip(),
            "makers": (r.get("makers") or "").strip(),
            "countries": (r.get("countries") or "").strip(),
        })

    pola = ["wikidata", "name", "keyword", "keyword_variants",
            "types", "makers", "countries"]
    with PLIK_WYJSCIOWY.open("w", encoding="utf-8", newline="") as f:
        # lineterminator="\n" -> czyste LF, bez stray '\r' w keywordach do JSON.
        zapis = csv.DictWriter(f, fieldnames=pola, lineterminator="\n")
        zapis.writeheader()
        zapis.writerows(wynik)

    # --- Krotki raport ---
    liczby = [len(w["keyword_variants"].split("|")) for w in wynik]
    suma_kw = sum(liczby)
    multi = sum(1 for n in liczby if n > 1)
    print(f"Wczytano marek:            {len(wiersze)}")
    print(f"Zapisano marek:            {len(wynik)}")
    print(f"Lacznie kandydatur kw:     {suma_kw}")
    print(f"Marek z >1 wariantem:      {multi}")
    print(f"Plik wyjsciowy:            {PLIK_WYJSCIOWY}")
    print("\nPrzyklady (name -> keyword_variants):")
    for w in wynik[:12]:
        print(f"  {w['name'][:34]:34s} -> {w['keyword_variants']}")


if __name__ == "__main__":
    main()
