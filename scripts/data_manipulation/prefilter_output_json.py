#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KROK 2a potoku: lokalny empty-drop keywordow wzgledem output.json (tryb "m").

Wejscie:  data/estimator/keywords.csv    (distinct keywordy z kroku 1)
          data/estimator/positions.csv   (rejestr pozycji z kroku 1)
          output.json                    (~2,3 mln URL-i; zapisana odpowiedz estymatora)
Wyjscie:  data/estimator/keywords_local.csv   (keyword,n_positions,local_quantity)
          data/estimator/positions_alive.csv  (pozycje z >=1 trafionym wariantem)

PO CO LOKALNIE
--------------
Estymator bierze 1 zapytanie na POST, wiec brute-force empty-dropu = ~82,5 tys.
POST-ow na publiczny estymator. output.json to zapisana odpowiedz estymatora z
~2,3 mln zroznicowanych URL-i -- reprezentatywna probka korpusu. Dopasowujac
keywordy LOKALNIE do tej probki robimy empty-drop bez ani jednego wywolania API;
estymator zostaje na krok 2b (precyzyjne quantity + probka URL do oceny trafnosci)
juz tylko dla OCALALYCH. To realizuje "sprytne rozwiazanie" z PDF i uzywa
output.json zgodnie z przeznaczeniem ("do lokalnej analizy").

ODTWORZENIE SEMANTYKI mode:"m"
-----------------------------
W trybie "m" keyword liczy sie, gdy wystepuje SAMODZIELNIE -- otoczony znakami
niealfanumerycznymi ("...-audi-a3-..." tak, "audition" nie). Znak "-" w keywordzie
matchuje dowolny znak niealfanumeryczny ("honda-civic" = honda%civic, honda/civic).
Mapujemy to wiernie tak:
  - URL tnie sie na maksymalne tokeny alfanumeryczne (lower): kazdy token jest z
    natury otoczony nie-alnum -> dopasowanie CALYCH tokenow = regula samodzielnosci
    (token "audi" != token "audition").
  - keyword tnie sie na tokeny po "-".
  - keyword PASUJE do URL-a <=> jego krotka tokenow jest CIAGLA PODSEKWENCJA krotki
    tokenow URL-a ("honda","civic" obok siebie; "honda","old","civic" -- nie).
Dopasowania szukamy przez TRIE keywordow (zejscie tylko tam, gdzie prefiks jest
keywordem -> szybkie). local_quantity = liczba URL-i, ktore keyword trafil
(per URL liczony raz).

UWAGA: output.json to PROBKA pelnego korpusu, wiec local_quantity==0 != "na pewno
zero w estymatorze". To filtr o wysokiej precyzji (marka z realna obecnoscia w
sieci pojawi sie w 2,3 mln URL-i); niepewnosc kalibrujemy w kroku 2b, puszczajac
probke "lokalnie zerowych" na zywy estymator.

Uruchomienie (z dowolnego cwd -- sciezki liczone wzgledem __file__):
    python3 scripts/data_manipulation/prefilter_output_json.py
"""

import collections
import csv
import re
import sys
from pathlib import Path

# --- KONFIGURACJA ---
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
KATALOG = DATA_DIR / "estimator"
PLIK_KEYWORDS = KATALOG / "keywords.csv"
PLIK_POSITIONS = KATALOG / "positions.csv"
PLIK_OUTPUT_JSON = DATA_DIR.parent / "output.json"   # lezy w katalogu glownym repo

PLIK_KEYWORDS_LOCAL = KATALOG / "keywords_local.csv"
PLIK_POSITIONS_ALIVE = KATALOG / "positions_alive.csv"

# Klucze strukturalne JSON-a (nie URL-e) -- pomijane przy ekstrakcji.
META_KEYS = {"sources", "quantity", "sampleSize", "urls"}
SOURCE_RE = re.compile(r"^source\d+$")
QUOTED = re.compile(r'"([^"]*)"')          # zawartosc stringow JSON (URL-e nie maja ")
NIEALNUM = re.compile(r"[^a-z0-9]+")        # rozdzielacz tokenow (po lower())

TERMINAL = "$"                              # marker konca keyworda w trie


def iter_urls(path):
    """Strumieniowo wyciaga URL-e z output.json (bezpieczne pamieciowo).

    Czyta plik w kawalkach, wybiera zawartosc stringow JSON, odrzuca klucze
    strukturalne; URL-em jest string zawierajacy '.' (domena). Bufor trzyma
    ogon po ostatnim domknietym stringu, by nie ciac stringa na granicy kawalka.
    """
    buf = ""
    with path.open(encoding="utf-8") as f:
        while True:
            chunk = f.read(1 << 20)             # 1 MB
            if not chunk:
                for m in QUOTED.finditer(buf):
                    s = m.group(1)
                    if "." in s and s not in META_KEYS and not SOURCE_RE.match(s):
                        yield s
                break
            buf += chunk
            ostatni = 0
            for m in QUOTED.finditer(buf):
                ostatni = m.end()
                s = m.group(1)
                if "." in s and s not in META_KEYS and not SOURCE_RE.match(s):
                    yield s
            buf = buf[ostatni:]                 # zachowaj ewentualny niedomkniety string


def zbuduj_trie(keywords):
    """Trie krotek tokenow keywordow; wezel terminalny niesie kanoniczny keyword."""
    trie = {}
    for kw in keywords:
        node = trie
        for tok in kw.split("-"):
            node = node.setdefault(tok, {})
        node[TERMINAL] = kw
    return trie


def dopasuj_url(tokeny, trie):
    """Zwraca zbior keywordow (krotek tokenow) trafionych w jednym URL-u."""
    hits = set()
    n = len(tokeny)
    for i in range(n):
        node = trie
        j = i
        while j < n:
            node = node.get(tokeny[j])
            if node is None:
                break
            j += 1
            term = node.get(TERMINAL)
            if term is not None:
                hits.add(term)               # krotszy keyword; petla idzie dalej po dluzszy
    return hits


def main() -> None:
    # --- wczytanie keywordow + budowa trie ---
    with PLIK_KEYWORDS.open(encoding="utf-8-sig", newline="") as f:
        kw_rows = list(csv.DictReader(f))
    keywords = [r["keyword"] for r in kw_rows]
    trie = zbuduj_trie(keywords)
    print(f"Keywordow w tescie: {len(keywords)}", file=sys.stderr)

    # --- przelot po URL-ach: zliczanie local_quantity ---
    local_q = collections.Counter()
    n_url = 0
    for url in iter_urls(PLIK_OUTPUT_JSON):
        tokeny = [t for t in NIEALNUM.split(url.lower()) if t]
        if not tokeny:
            continue
        for kw in dopasuj_url(tokeny, trie):
            local_q[kw] += 1
        n_url += 1
        if n_url % 500000 == 0:
            print(f"  ... {n_url} URL-i", file=sys.stderr)
    print(f"Przetworzono URL-i: {n_url}", file=sys.stderr)

    # --- keywords_local.csv: wszystkie keywordy + local_quantity ---
    with PLIK_KEYWORDS_LOCAL.open("w", encoding="utf-8", newline="") as f:
        zapis = csv.writer(f, lineterminator="\n")
        zapis.writerow(["keyword", "n_positions", "local_quantity"])
        for r in kw_rows:
            zapis.writerow([r["keyword"], r["n_positions"], local_q.get(r["keyword"], 0)])

    # --- positions_alive.csv: pozycje z >=1 trafionym wariantem ---
    with PLIK_POSITIONS.open(encoding="utf-8-sig", newline="") as f:
        positions = list(csv.DictReader(f))

    zywe = []
    per_src_total = collections.Counter()
    per_src_alive = collections.Counter()
    for p in positions:
        per_src_total[p["source"]] += 1
        warianty = p["variants"].split("|")
        trafione = [(v, local_q.get(v, 0)) for v in warianty if local_q.get(v, 0) > 0]
        if not trafione:
            continue
        per_src_alive[p["source"]] += 1
        maxq = max(q for _, q in trafione)
        zywe.append({
            "position_id": p["position_id"],
            "source": p["source"],
            "name": p["name"],
            "keyword": p["keyword"],
            "variants": p["variants"],
            "alive_variants": "|".join(f"{v}:{q}" for v, q in trafione),
            "max_local_quantity": maxq,
        })

    with PLIK_POSITIONS_ALIVE.open("w", encoding="utf-8", newline="") as f:
        zapis = csv.DictWriter(
            f, fieldnames=["position_id", "source", "name", "keyword", "variants",
                           "alive_variants", "max_local_quantity"],
            lineterminator="\n")
        zapis.writeheader()
        zapis.writerows(zywe)

    # --- Raport ---
    kw_zywe = sum(1 for r in kw_rows if local_q.get(r["keyword"], 0) > 0)
    print(f"\nKeywordy zywe (local_quantity>0): {kw_zywe} / {len(keywords)} "
          f"({100 * kw_zywe // max(len(keywords), 1)}%)")
    print("Pozycje zywe wg zrodla (zywe / wszystkie):")
    for src in ("brands", "xwines", "beer"):
        print(f"  {src:8s}: {per_src_alive[src]:6d} / {per_src_total[src]:6d}")
    print(f"  RAZEM   : {len(zywe):6d} / {len(positions):6d} "
          f"({100 * len(zywe) // max(len(positions), 1)}%)")
    print(f"\nWyjscie: {PLIK_KEYWORDS_LOCAL.name}, {PLIK_POSITIONS_ALIVE.name}")
    print("\nTOP pozycje wg local_quantity (zwykle generyczne nazwy -> precyzja w kroku 3):")
    for w in sorted(zywe, key=lambda w: -w["max_local_quantity"])[:12]:
        print(f"  {w['name'][:26]:26s} [{w['source']:6s}] kw={w['keyword'][:22]:22s} "
              f"q={w['max_local_quantity']}")


if __name__ == "__main__":
    main()
