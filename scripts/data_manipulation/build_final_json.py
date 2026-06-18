#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KROK 4+5: dedup po keywordzie + zlozenie finalnego deliverable mtrochimiuk.json.

Wejscie:  data/estimator/validated_queries.jsonl (krok 3, opt_recall>=2)
          data/estimator/recovered_famous.jsonl  (krok 3b, odzysk famous)
Wyjscie:  mtrochimiuk.json  (katalog glowny repo) -- {"results":[...]}

DEDUP: kluczem jest pojedynczy keyword `required` (definiuje dopasowanie). Wiele
pozycji z tym samym keywordem (np. 3 piwa Redhook -> "redhook") to ta sama marka =>
jeden wpis. `id` wybierany jest tak, by byl czysta nazwa marki: jesli ktoras z
nazw po slugify == keyword, bierzemy ja (zachowuje akcenty: "Patron"->"Patrón");
wpp. titlecase keyworda ("redhook" -> "Redhook"). `optional` = unia po grupie.

Format wpisu zgodny z PDF:
  {"id": "...", "required":[{"keyword":"...","mode":"m"}],
   "optional":[{"keyword":"...","mode":"m"}, ...], "optionalThreshold":1}
(`optional`/`optionalThreshold` tylko gdy sa slowa opcjonalne).

Uruchomienie:  python3 scripts/data_manipulation/build_final_json.py
"""

import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_queries_with_optional import slugify, KAT  # noqa: E402

ROOT = KAT.parent.parent          # data/estimator -> data -> repo root
OUT = ROOT / "mtrochimiuk.json"
MAX_OPTIONAL = 10


def load(path):
    out = []
    if path.exists():
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
    return out


def main():
    entries = load(KAT / "validated_queries.jsonl") + load(KAT / "recovered_famous.jsonl")

    groups = collections.OrderedDict()   # keyword -> {ids:[], optional:[]}
    for e in entries:
        kw = e["required"][0]["keyword"]
        g = groups.setdefault(kw, {"ids": [], "optional": []})
        g["ids"].append(e["id"])
        have = {o["keyword"] for o in g["optional"]}
        for o in e.get("optional", []):
            if o["keyword"] not in have:
                g["optional"].append(o)
                have.add(o["keyword"])

    results, id_seen = [], collections.Counter()
    for kw, g in groups.items():
        # id: preferuj nazwe, ktorej slug == keyword (czysta nazwa marki, z akcentami)
        id_ = next((nm for nm in g["ids"] if slugify(nm) == kw), None)
        if id_ is None:
            id_ = kw.replace("-", " ").title()
        # unikalnosc id (gdyby dwa keywordy d, byly tej samej nazwy)
        id_seen[id_] += 1
        if id_seen[id_] > 1:
            id_ = f"{id_} ({kw})"

        entry = {"id": id_, "required": [{"keyword": kw, "mode": "m"}]}
        if g["optional"]:
            entry["optional"] = g["optional"][:MAX_OPTIONAL]
            entry["optionalThreshold"] = 1
        results.append(entry)

    with OUT.open("w", encoding="utf-8") as f:
        json.dump({"results": results}, f, ensure_ascii=False, indent=1)

    # --- raport ---
    n_opt = sum(1 for r in results if "optional" in r)
    print(f"Wejscie wpisow (validated + recovered): {len(entries)}")
    print(f"Po dedupie po keywordzie:           {len(results)}")
    print(f"  z optional:    {n_opt}")
    print(f"  required-only: {len(results) - n_opt}")
    print(f"  zwiniete duplikaty: {len(entries) - len(results)}")
    print(f"Plik: {OUT}")
    print("\nPrzyklady wpisow:")
    for r in results[:6] + results[-4:]:
        print("  " + json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    main()
