#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KROK 6: potwierdzenie finalnych wpisow na ZYWYM estymatorze.

Dotad walidacja byla lokalna (output.json ~ korpus). Tu odpytujemy realny estymator
dla KAZDEGO wpisu z mtrochimiuk.json (1:1, pelne required[+optional@threshold]):
  - quantity >= 1  -> zostaw (regula zadania: tylko pozycje lapiace URL),
  - quantity == 0  -> odrzuc,
  - zbieramy probke URL do recznej kontroli trafnosci.

BEZPIECZENSTWO:
  - wynik zapisywany do OSOBNEGO mtrochimiuk_confirmed.json -- NIGDY nie nadpisuje
    zrodlowego mtrochimiuk.json (chroni deliverable, gdyby estymator masowo padal),
  - przy serii kolejnych bledow (np. 503) -- WCZESNE PRZERWANIE bez zapisu wynikow
    (nie ma sensu mielic 267x przez minuty, gdy usluga jest down).

Uruchomienie (WYMAGA SIECI):  python3 scripts/data_manipulation/confirm_estimator.py
Po udanym pelnym przebiegu: promuj mtrochimiuk_confirmed.json -> mtrochimiuk.json.
"""

import csv
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from estymator_client import zapytaj_raw  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
DELIVERABLE = ROOT / "mtrochimiuk.json"                 # WEJSCIE (read-only)
OUT = ROOT / "mtrochimiuk_confirmed.json"               # WYJSCIE (osobne)
LOG = ROOT / "data" / "estimator" / "confirm_log.csv"
SLEEP = 0.25
MAX_CONSEC_FAIL = 8        # tyle kolejnych bledow -> usluga down -> przerwij


def main():
    results = json.load(DELIVERABLE.open(encoding="utf-8"))["results"]
    confirmed, empty, failed, log = [], [], [], []
    consec, aborted = 0, False

    for i, q in enumerate(results, 1):
        query = {k: q[k] for k in ("required", "optional", "optionalThreshold") if k in q}
        r = zapytaj_raw(query)
        kw = q["required"][0]["keyword"]
        if r is None:
            failed.append(kw)
            consec += 1
            log.append({"id": q["id"], "keyword": kw, "est_quantity": "", "decision": "blad"})
            if consec >= MAX_CONSEC_FAIL:
                aborted = True
                print(f"\n[ABORT] {consec} kolejnych bledow (estymator niedostepny / 503). "
                      f"Przerywam BEZ zapisu. mtrochimiuk.json nietkniety.", file=sys.stderr)
                break
            time.sleep(SLEEP)
            continue
        consec = 0
        if r["quantity"] >= 1:
            q["_urls"] = r["urls"][:3]
            confirmed.append(q)
            dec, qty = "keep", r["quantity"]
        else:
            empty.append(kw)
            dec, qty = "drop_empty", 0
        log.append({"id": q["id"], "keyword": kw, "est_quantity": qty, "decision": dec})
        if i % 50 == 0:
            print(f"  ... {i}/{len(results)}  (keep={len(confirmed)} empty={len(empty)})", file=sys.stderr)
        time.sleep(SLEEP)

    # log zawsze (diagnostyka)
    LOG.parent.mkdir(exist_ok=True)
    with LOG.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "keyword", "est_quantity", "decision"],
                           lineterminator="\n")
        w.writeheader()
        w.writerows(log)

    if aborted:
        print(f"PRZERWANO. Przetworzono {len(log)}/{len(results)}. Log: {LOG}")
        print("Estymator niedostepny -- sprobuj ponownie pozniej. Deliverable bez zmian.")
        return

    samples = [(q["id"], q.pop("_urls", [])) for q in confirmed]
    json.dump({"results": confirmed}, OUT.open("w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print(f"\nWpisow wejsciowych:   {len(results)}")
    print(f"POTWIERDZONE (q>=1):  {len(confirmed)}  -> {OUT.name}")
    print(f"Odrzucone (q==0):     {len(empty)}  {empty[:20]}")
    print(f"Bledy zapytania:      {len(failed)}")
    print(f"Log: {LOG}")
    print("Promuj:  cp mtrochimiuk_confirmed.json mtrochimiuk.json  (po weryfikacji)")
    print("\nProbka URL (kontrola trafnosci):")
    for idv, urls in samples[:14]:
        print(f"  [{idv}]")
        for u in urls[:2]:
            print(f"      {u[:84]}")


if __name__ == "__main__":
    main()
