"""
Wzbogaca listę kodów Q (z PetScan) o dane z Wikidaty: nazwę, aliasy,
typ (P31), producenta (P176) i kraj pochodzenia (P495).

Wejście:  CSV z kolumną 'wikidata' (np. alkohole_merged.csv z poprzedniego kroku).
Wyjście:  CSV z kolumnami wikidata, name, aliases, types, makers, countries.

Zależności:
    pip install requests

WAŻNE: Wikidata wymaga sensownego nagłówka User-Agent z kontaktem,
inaczej blokuje zapytania (403/429). Uzupełnij swój e-mail poniżej.
"""

import csv
import sys
import time
import requests
from pathlib import Path

# ------------------- KONFIGURACJA -------------------
INPUT = Path(__file__).resolve().parent.parent.parent / "alkohole_petscan_merged.csv"
OUTPUT = Path(__file__).resolve().parent.parent.parent / "data/alkohole_wikidata.csv"
ENDPOINT = "https://query.wikidata.org/sparql"
BATCH = 200                          # ile Q na jedno zapytanie (zmniejsz, jeśli timeout)
REQUEST_DELAY = 1.0
HEADERS = {
    "User-Agent": "alcohol-taxonomy/1.0 (mtrochimiuk11@gmail.com)",   # <-- WPISZ KONTAKT
    "Accept": "application/sparql-results+json",
}
# ----------------------------------------------------

QUERY_TMPL = """
SELECT ?item ?itemLabel
       (GROUP_CONCAT(DISTINCT ?alias;       separator=" | ") AS ?aliases)
       (GROUP_CONCAT(DISTINCT ?typeLabel;   separator=" | ") AS ?types)
       (GROUP_CONCAT(DISTINCT ?makerLabel;  separator=" | ") AS ?makers)
       (GROUP_CONCAT(DISTINCT ?countryLabel; separator=" | ") AS ?countries)
WHERE {
  VALUES ?item { %s }
  # typ + do 2 poziomów nadklas; każde dodatkowe /wdt:P279? = jeden poziom głębiej
  OPTIONAL { ?item wdt:P31/wdt:P279? ?type. }
  OPTIONAL { ?item wdt:P176 ?maker.   }
  OPTIONAL { ?item wdt:P495 ?country. }
  OPTIONAL { ?item skos:altLabel ?alias. FILTER(LANG(?alias) IN ("en")) }
  SERVICE wikibase:label {
    bd:serviceParam wikibase:language "en".
    ?item    rdfs:label ?itemLabel.
    ?type    rdfs:label ?typeLabel.
    ?maker   rdfs:label ?makerLabel.
    ?country rdfs:label ?countryLabel.
  }
}
GROUP BY ?item ?itemLabel
"""

FIELDS = ["wikidata", "name", "aliases", "types", "makers", "countries"]


def read_qids(path: str):
    qids = []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            q = (row.get("wikidata") or "").strip()
            if q.startswith("Q") and q[1:].isdigit():
                qids.append(q)
    # zachowaj unikalność, kolejność bez znaczenia
    return list(dict.fromkeys(qids))


def fetch_batch(qids):
    values = " ".join(f"wd:{q}" for q in qids)
    query = QUERY_TMPL % values
    r = requests.get(ENDPOINT, params={"query": query}, headers=HEADERS, timeout=180)
    r.raise_for_status()
    return r.json()["results"]["bindings"]


def binding_to_row(b: dict) -> dict:
    qid = b["item"]["value"].rsplit("/", 1)[-1]
    g = lambda k: b.get(k, {}).get("value", "")
    return {
        "wikidata": qid,
        "name": g("itemLabel"),
        "aliases": g("aliases"),
        "types": g("types"),
        "makers": g("makers"),
        "countries": g("countries"),
    }


def main():
    qids = read_qids(INPUT)
    print(f"Wczytano {len(qids)} kodów Q z {INPUT}")
    if not qids:
        sys.exit("Brak kodów Q — sprawdź, czy plik wejściowy ma kolumnę 'wikidata'.")

    rows = []
    for i in range(0, len(qids), BATCH):
        batch = qids[i:i + BATCH]
        try:
            data = fetch_batch(batch)
        except Exception as e:
            print(f"[!] Partia {i // BATCH + 1} nie powiodła się: {e}", file=sys.stderr)
            continue
        rows.extend(binding_to_row(b) for b in data)
        print(f"  partia {i // BATCH + 1}: {len(data)} wyników")
        time.sleep(REQUEST_DELAY)

    with open(OUTPUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"\nZapisano {len(rows)} pozycji do {OUTPUT}")


if __name__ == "__main__":
    main()