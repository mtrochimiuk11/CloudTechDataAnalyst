#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KROK 2b (kalibracja): czy lokalny pre-filtr (2a) jest wiarygodny jako empty-drop?

Przeslanka: suma `sampleSize` w odpowiedzi estymatora (~3,22 mln URL-i) ~ liczba
URL-i w output.json (2,99 mln), a bacardi: local_quantity=9 == estymator quantity=9.
To sugeruje, ze output.json ~ CALY korpus estymatora, wiec local_quantity==0
powinno oznaczac quantity==0 w estymatorze (mozna odrzucac local-zero bez utraty
marek i bez masowego sweepu ~82,5 tys. POST-ow).

Weryfikacja wprost: stratyfikowana probka keywordow rozpieta po local_quantity:
  - local==0 wg zrodla (brands/xwines/beer) -- KLUCZOWE: ile z nich est>0 (false-negative),
  - kubelki 1-10 / 11-100 / >100 -- czy est ~ local (potwierdzenie output.json ~ korpus).
Odpytuje estymator (mode "m") i porownuje.

Wejscie:  data/estimator/keywords_local.csv, data/estimator/positions.csv
Wyjscie:  data/estimator/calibration.csv  (keyword,source,bucket,local_q,est_q)

Uruchomienie (WYMAGA SIECI):
    python3 scripts/data_manipulation/kalibracja_local_vs_estymator.py
"""

import csv
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from estymator_client import zapytaj   # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
KAT = DATA_DIR / "estimator"
SEED = 42
SLEEP = 0.1                 # grzecznosc miedzy POST-ami
N_ZERO = 50                 # probka per zrodlo dla local==0
N_LOW, N_MID, N_HIGH = 30, 20, 10
PRIO = {"brands": 0, "xwines": 1, "beer": 2}


def main() -> None:
    # local_quantity per keyword
    local_q = {r["keyword"]: int(r["local_quantity"])
               for r in csv.DictReader(
                   (KAT / "keywords_local.csv").open(encoding="utf-8-sig"))}

    # keyword -> zrodlo wiodace (precedencja brands>xwines>beer)
    src = {}
    for p in csv.DictReader((KAT / "positions.csv").open(encoding="utf-8-sig")):
        s = p["source"]
        for v in p["variants"].split("|"):
            if v and (v not in src or PRIO[s] < PRIO[src[v]]):
                src[v] = s

    # strata
    zero = {"brands": [], "xwines": [], "beer": []}
    low, mid, high = [], [], []
    for kw, q in local_q.items():
        if q == 0:
            s = src.get(kw)
            if s:
                zero[s].append(kw)
        elif q <= 10:
            low.append(kw)
        elif q <= 100:
            mid.append(kw)
        else:
            high.append(kw)

    rng = random.Random(SEED)

    def probka(pool, n):
        return rng.sample(pool, min(n, len(pool)))

    plan = []
    for s in ("brands", "xwines", "beer"):
        plan += [(kw, s, f"zero-{s}") for kw in probka(zero[s], N_ZERO)]
    plan += [(kw, src.get(kw, "?"), "low") for kw in probka(low, N_LOW)]
    plan += [(kw, src.get(kw, "?"), "mid") for kw in probka(mid, N_MID)]
    plan += [(kw, src.get(kw, "?"), "high") for kw in probka(high, N_HIGH)]

    print(f"Odpytuje estymator dla {len(plan)} keywordow (mode m)...", file=sys.stderr)
    wyniki = []
    bledy = 0
    for i, (kw, s, bucket) in enumerate(plan, 1):
        r = zapytaj(kw, "m")
        est = r["quantity"] if r is not None else None
        if est is None:
            bledy += 1
        wyniki.append({"keyword": kw, "source": s, "bucket": bucket,
                       "local_q": local_q[kw], "est_q": est})
        if i % 50 == 0:
            print(f"  ... {i}/{len(plan)}", file=sys.stderr)
        time.sleep(SLEEP)

    # zapis
    with (KAT / "calibration.csv").open("w", encoding="utf-8", newline="") as f:
        zapis = csv.DictWriter(
            f, fieldnames=["keyword", "source", "bucket", "local_q", "est_q"],
            lineterminator="\n")
        zapis.writeheader()
        for w in wyniki:
            zapis.writerow({**w, "est_q": "" if w["est_q"] is None else w["est_q"]})

    # --- Raport ---
    print(f"\nBledne odpowiedzi (pominiete): {bledy}")
    print("\n=== local-zero: ile faktycznie ZYJE w estymatorze (false-negative)? ===")
    for s in ("brands", "xwines", "beer"):
        rows = [w for w in wyniki if w["bucket"] == f"zero-{s}" and w["est_q"] is not None]
        fn = [w for w in rows if w["est_q"] > 0]
        if rows:
            print(f"  zero-{s:6s}: {len(rows):3d} prob. | est>0: {len(fn):3d} "
                  f"({100*len(fn)//len(rows)}%)")
            for w in fn[:5]:
                print(f"      FN: {w['keyword']!r} est_q={w['est_q']} (local 0)")

    print("\n=== niezerowe: czy est ~ local (output.json ~ korpus)? ===")
    for bucket in ("low", "mid", "high"):
        rows = [w for w in wyniki if w["bucket"] == bucket and w["est_q"] is not None]
        if not rows:
            continue
        exact = sum(1 for w in rows if w["est_q"] == w["local_q"])
        ge = sum(1 for w in rows if w["est_q"] >= w["local_q"])
        zero_est = sum(1 for w in rows if w["est_q"] == 0)
        print(f"  {bucket:4s}: {len(rows):3d} prob. | est==local: {exact:3d} | "
              f"est>=local: {ge:3d} | est==0: {zero_est}")

    print(f"\nZapisano: {KAT/'calibration.csv'}")


if __name__ == "__main__":
    main()
