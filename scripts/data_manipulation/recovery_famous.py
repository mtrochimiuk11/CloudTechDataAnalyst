#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KROK 3b: odzysk znanych marek odrzuconych przez ostre reguly kroku 3.

Skalibrowana regula kroku 3 (opt_recall>=2, DF<=200) jest celowo ostra -- odsiewa
dlugi ogon FP, ale ucina tez kilka OCZYWISTYCH marek: o wysokim DF z innym
znaczeniem (corona DF 452 -> cap) albo bez >=2 korroboracji kontekstu (jagermeister
opt 0). Tu odzyskujemy je z kuratorskiej listy FAMOUS, lagodzac regule (bo wiemy,
ze to realne marki):
  - jesli marka ma opt_recall>=1 -> required+optional@1 (corona+beer => czyste),
  - wpp. jesli DF>=1 (jest w korpusie) -> required-only (ufamy; jagermeister),
  - jesli DF==0 (brak w korpusie) -> pomijamy (i tak nie do znalezienia).

Reuzywa funkcji/metadanych z build_queries_with_optional (bez duplikacji logiki).
Wejscie:  data/estimator/query_decisions.csv (+ keywords_local.csv posrednio)
Wyjscie:  data/estimator/recovered_famous.jsonl
Uruchomienie:  python3 scripts/data_manipulation/recovery_famous.py
"""

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_queries_with_optional import load_meta, build_optional, KAT, MODE  # noqa: E402

DICT_PATH = Path("/usr/share/dict/words")
RECOVER_TRUST = 40      # famous bez kontekstu: required-only tylko gdy coined i DF<=
                        # (wpp. wysokie DF -> inne znaczenie dominuje: chivas/tiger/kraken)

# Kuratorska lista znanych marek (slugi jak w naszych keywordach). Tylko marki
# powszechnie rozpoznawalne -- by NIE wprowadzac z powrotem FP.
FAMOUS = {
    # wodka
    "smirnoff", "absolut", "grey-goose", "belvedere", "ketel-one", "ciroc",
    "stolichnaya", "skyy", "eristoff", "zubrowka", "finlandia", "russian-standard",
    # whisky / bourbon
    "jack-daniels", "johnnie-walker", "jameson", "jim-beam", "glenfiddich",
    "glenlivet", "macallan", "chivas-regal", "chivas", "ballantines", "dewars",
    "famous-grouse", "crown-royal", "wild-turkey", "makers-mark", "bushmills",
    "monkey-shoulder", "jameson", "canadian-club",
    # rum
    "bacardi", "captain-morgan", "havana-club", "malibu", "kraken", "mount-gay",
    "appleton", "diplomatico", "zacapa", "brugal", "ron-zacapa",
    # gin
    "gordons", "tanqueray", "bombay-sapphire", "beefeater", "hendricks", "bombay",
    # tequila
    "jose-cuervo", "cuervo", "patron", "don-julio", "casamigos", "sauza",
    "herradura", "espolon",
    # piwo
    "heineken", "budweiser", "corona", "stella-artois", "guinness", "carlsberg",
    "becks", "amstel", "fosters", "miller", "coors", "modelo", "peroni", "grolsch",
    "tiger", "asahi", "sapporo", "tsingtao", "paulaner", "erdinger", "leffe",
    "hoegaarden", "pilsner-urquell", "kronenbourg", "san-miguel", "estrella",
    # likiery
    "baileys", "jagermeister", "kahlua", "cointreau", "grand-marnier", "aperol",
    "campari", "disaronno", "chartreuse", "drambuie", "frangelico", "sambuca",
    "limoncello", "midori", "chambord",
    # koniak / brandy
    "hennessy", "remy-martin", "courvoisier", "martell",
    # wino musujace / wermut
    "moet", "dom-perignon", "veuve-clicquot", "mumm", "bollinger", "martini",
    "cinzano", "noilly-prat", "grey-goose",
}


def main():
    by_kw = {}
    for r in csv.DictReader((KAT / "query_decisions.csv").open(encoding="utf-8-sig")):
        by_kw.setdefault(r["keyword"], []).append(r)
    META = load_meta()
    words = {w.strip().lower() for w in DICT_PATH.open(encoding="utf-8", errors="ignore")}

    recovered, already, not_found, skipped = [], [], [], []
    for slug in sorted(FAMOUS):
        recs = by_kw.get(slug)
        if not recs:
            not_found.append(slug)
            continue
        if any(r["decision"] == "keep" for r in recs):
            already.append(slug)
            continue
        # najlepsza pozycja: max opt_recall, preferuj zrodlo brands
        r = max(recs, key=lambda r: (int(r["opt_recall"]), r["source"] == "brands"))
        df, optr = int(r["df"]), int(r["opt_recall"])
        if df < 1:
            not_found.append(slug)
            continue
        meta = META[r["source"]].get(r["name"], {})
        opt = build_optional(meta, set(slug.split("-"))) if meta else []
        toks = slug.split("-")
        # FP-prone tylko gdy POJEDYNCZE slowo slownikowe (tiger, bombay); fraza
        # wielotokenowa jest dystynktywna mimo zwyklego tokenu (captain-morgan).
        single_common = len(toks) == 1 and toks[0] in words
        q = {"id": r["name"], "required": [{"keyword": slug, "mode": MODE}]}
        if optr >= 1 and opt:
            q["optional"] = [{"keyword": o, "mode": MODE} for o in opt]
            q["optionalThreshold"] = 1
            how = f"req+opt@1 (opt={optr})"
        elif (not single_common) and df <= RECOVER_TRUST:
            how = f"req-only (DF={df})"
        else:
            skipped.append((slug, df, optr))   # pojedyncze slowo slownikowe / wysokie DF
            continue
        recovered.append((slug, r["name"], r["source"], how, q))

    with (KAT / "recovered_famous.jsonl").open("w", encoding="utf-8") as f:
        for _, _, _, _, q in recovered:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")

    print(f"Lista FAMOUS:                {len(FAMOUS)}")
    print(f"Juz w kroku 3 (keep):        {len(already)}  {sorted(already)}")
    print(f"ODZYSKANE:                   {len(recovered)}")
    print(f"Pominiete (FP-prone, wys.DF): {len(skipped)}  {sorted(s for s,_,_ in skipped)}")
    print(f"Brak w korpusie/danych:      {len(not_found)}  {sorted(not_found)}")
    print(f"\nWyjscie: {KAT}/recovered_famous.jsonl")
    print("\nOdzyskane (slug -> jak):")
    for slug, name, src, how, _ in recovered:
        print(f"    {slug[:20]:20} [{src:6}] {how}")


if __name__ == "__main__":
    main()
