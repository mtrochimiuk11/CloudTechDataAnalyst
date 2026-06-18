#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KROK 1 potoku: builder zapytan REQUIRED-ONLY (bramka recall, bez `optional`).

Wejscie:  data/brands_merged.csv                     (klaster marek, krok 0)
          data/transformed/XWines_transformed.csv     (wino, poziom winiarni)
          data/transformed/beer_reviews_transformed.csv (piwo, poziom produktu)
Wyjscie:  data/estimator/positions.csv   -- rejestr pozycji (do zlaczenia wynikow)
          data/estimator/keywords.csv    -- DISTINCT keywordy do przetestowania
          data/estimator/requests.jsonl  -- gotowe cialo POST per distinct keyword

DLACZEGO REQUIRED-ONLY
----------------------
Estymator liczy match jako: (wszystkie required) AND (>=threshold optional). Czyli
  match(required + optional@1)  ⊆  match(required)
-- `optional` moze wynik tylko ZAWEZIC. Zatem `required`-only daje GORNA GRANICE
recall: pozycja pusta tutaj jest pusta definitywnie, a dorzucenie `optional` za
wczesnie grozi FALSZYWA PUSTKA (zabiciem realnej marki przez zle zgadniete slowo
kontekstowe). Empty-drop na `required`-only nie wymaga tez oceny trafnosci -- to
czyste `quantity > 0` -- wiec da sie zautomatyzowac na calym zbiorze. `optional`
wchodzi dopiero w kroku 3, na ocalalych, dobierany z PROBEK URL (kolumna
`optional` w plikach wejsciowych to pula kandydatow na ten krok).

KONTRAKT ESTYMATORA (z PDF zadania)
-----------------------------------
JEDNO zapytanie na POST:  curl --data '@q.json' https://urlkeywords.ctpl.dev/keywordURLs
Cialo:  {"required":[{"keyword":"<kw>","mode":"m"}]}
Odpowiedz: {"sources":{"sourceN":{"quantity":N,"sampleSize":N,"urls":[...]}}}
  -- `sourceN` to WEWNETRZNE zrodla danych firmy (nie batch zapytan); calkowity
  recall keyworda = suma `quantity` po zrodlach. Brak batchowania zapytan => jeden
  POST = jeden keyword. Dlatego TEST DEDUPLIKUJEMY DO DISTINCT KEYWORDOW (wiele
  pozycji dzieli ten sam wariant), a pozycja zyje, jesli >=1 jej wariant ma quantity>0.

mode = "m" (token samodzielny) -- tryb, ktorego uzyja finalne zapytania (precyzja);
pozycja niedopasowalna w "m" i tak nie trafilaby do deliverable.

Uruchomienie (z dowolnego cwd -- sciezki liczone wzgledem __file__):
    python3 scripts/data_manipulation/build_required_queries.py
"""

import collections
import csv
import json
from pathlib import Path

# --- KONFIGURACJA ---
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
KATALOG_WYJSCIOWY = DATA_DIR / "estimator"

MODE = "m"

# Zrodla: (tag, sciezka, kolumna nazwy, kolumna z wariantami lub None gdy tylko keyword).
SOURCES = [
    ("brands", DATA_DIR / "brands_merged.csv",
     "id", "keyword_variants"),
    ("xwines", DATA_DIR / "transformed" / "XWines_transformed.csv",
     "WineryName", "keyword_variants"),
    ("beer",   DATA_DIR / "transformed" / "beer_reviews_transformed.csv",
     "beer_name", None),
]


def warianty_wiersza(row, variants_col) -> list:
    """Lista wariantow keyworda dla wiersza: split kolumny wariantow albo [keyword].

    Zachowuje kolejnosc (primary pierwszy), deduplikuje, pomija puste.
    """
    if variants_col and (row.get(variants_col) or "").strip():
        surowe = row[variants_col].split("|")
    else:
        surowe = [row.get("keyword") or ""]

    out = []
    for v in surowe:
        v = v.strip()
        if v and v not in out:
            out.append(v)
    return out


def main() -> None:
    KATALOG_WYJSCIOWY.mkdir(exist_ok=True)

    positions = []                      # rejestr pozycji
    kw_pozycje = collections.Counter()  # distinct keyword -> ile pozycji go uzywa
    licznik = collections.Counter()     # numeracja position_id per zrodlo

    for tag, sciezka, name_col, variants_col in SOURCES:
        with sciezka.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                warianty = warianty_wiersza(row, variants_col)
                if not warianty:
                    continue
                licznik[tag] += 1
                pid = f"{tag}:{licznik[tag]:05d}"
                positions.append({
                    "position_id": pid,
                    "source": tag,
                    "name": (row.get(name_col) or "").strip(),
                    "keyword": warianty[0],
                    "variants": "|".join(warianty),
                })
                for kw in warianty:
                    kw_pozycje[kw] += 1

    # --- positions.csv: rejestr (do zlaczenia wynikow po przemiale) ---
    with (KATALOG_WYJSCIOWY / "positions.csv").open("w", encoding="utf-8", newline="") as f:
        zapis = csv.DictWriter(
            f, fieldnames=["position_id", "source", "name", "keyword", "variants"],
            lineterminator="\n")
        zapis.writeheader()
        zapis.writerows(positions)

    # --- keywords.csv: DISTINCT keywordy do przetestowania (jednostka = 1 POST) ---
    # sort: malejaco wg liczby pozycji (najpierw te wspoldzielone -> najwiekszy zwrot),
    # remisy alfabetycznie (deterministycznie).
    distinct = sorted(kw_pozycje.items(), key=lambda kv: (-kv[1], kv[0]))
    with (KATALOG_WYJSCIOWY / "keywords.csv").open("w", encoding="utf-8", newline="") as f:
        zapis = csv.writer(f, lineterminator="\n")
        zapis.writerow(["keyword", "mode", "n_positions"])
        for kw, n in distinct:
            zapis.writerow([kw, MODE, n])

    # --- requests.jsonl: gotowe cialo POST per distinct keyword ---
    with (KATALOG_WYJSCIOWY / "requests.jsonl").open("w", encoding="utf-8") as f:
        for kw, _ in distinct:
            body = {"required": [{"keyword": kw, "mode": MODE}]}
            f.write(json.dumps({"keyword": kw, "body": body}, ensure_ascii=False) + "\n")

    # --- Raport ---
    per_src = collections.Counter(p["source"] for p in positions)
    n_distinct = len(distinct)
    n_warianty = sum(kw_pozycje.values())
    wspoldzielone = sum(1 for _, n in distinct if n > 1)
    print("Pozycje wg zrodla:")
    for tag, _, _, _ in SOURCES:
        print(f"  {tag:8s}: {per_src.get(tag, 0):7d}")
    print(f"  RAZEM   : {len(positions):7d}")
    print()
    print(f"Wariantow (keyword-instancji) lacznie: {n_warianty}")
    print(f"DISTINCT keywordow do testu (POST-ow): {n_distinct}")
    print(f"  -> dedup oszczedza {n_warianty - n_distinct} wywolan "
          f"({100 * (n_warianty - n_distinct) // max(n_warianty, 1)}%)")
    print(f"  -> keywordow wspoldzielonych (>1 poz): {wspoldzielone}")
    print()
    print(f"Wyjscie: {KATALOG_WYJSCIOWY}/  (positions.csv, keywords.csv, requests.jsonl)")
    print("Cialo POST (przyklad):",
          json.dumps({"required": [{"keyword": distinct[0][0], "mode": MODE}]},
                     ensure_ascii=False))
    print("Test recznie:  curl --data '@q.json' 'https://urlkeywords.ctpl.dev/keywordURLs'")


if __name__ == "__main__":
    main()
