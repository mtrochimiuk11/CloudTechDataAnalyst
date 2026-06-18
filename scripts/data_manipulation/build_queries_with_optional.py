#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KROK 3: konstrukcja finalnych zapytan (required[+optional@1]) + lokalna walidacja.

Wejscie:  data/estimator/positions_alive.csv   (zywe pozycje z kroku 2a)
          data/estimator/keywords_local.csv     (DF = local_quantity per keyword)
          data/brands_merged.csv, data/transformed/XWines_transformed.csv,
          data/transformed/beer_reviews_transformed.csv   (metadane -> optional)
          output.json                            (lokalna walidacja recall)
Wyjscie:  data/estimator/query_decisions.csv     (decyzja per pozycja)
          data/estimator/validated_queries.jsonl (zapytania KEPT w formacie deliverable)

REGULA DECYZYJNA (DF + zmierzony opt_recall dla WSZYSTKICH pozycji)
------------------------------------------------------------------
Analiza pokazala, ze `required`-only ma masowe FP: czesc "dystynktywnych" to wcale
nie marki (new-york DF 3118, the-walking-dead 857 -- frazy, ktore omijaly kontrole
DF bo byly wielotokenowe), a nawet realne marki tona w innym znaczeniu (guinness ->
Guinness World Records, heineken -> firma/rodzina). Dlatego KAZDA pozycja dostaje
`optional` (kontekst trunku), a o losie decyduja DF (= local_quantity) oraz opt_recall
zmierzony lokalnie na output.json (liczba URL-i, gdzie keyword stoi obok slowa
kontekstowego):

  max dlugosc tokenu keyworda <= 2        -> SMIEC (drop; v-s, 1-2, e-o)
  wszystkie tokeny w STYLE_GENERIC        -> SMIEC (drop; styl/typ, nie marka:
                                            ipa, belgian, imperial-stout)
  opt_recall >= OPT_MIN i DF <= DF_CAP    -> KEEP (required + optional@1)
  wpp.                                    -> drop
        (DF > DF_CAP: zbyt pospolite, new-york/corona; albo opt_recall < OPT_MIN:
         brak >=OPT_MIN korroboracji kontekstu -- homonim-smiec albo realna marka
         o zbyt rzadkiej probce, np. suntory/beefeater -> odzysk w recovered_famous)

Dobor `optional`: synset trunku MULTILINGWISTYCZNY + szczep/styl + producent/linia,
budowany z bezpiecznych pol (BEZ kraju/regionu/miasta -> geo nie przecieka; bez
'ron'/'vin' -- dwuznaczne obce). Prog 1 (kontekst rzadki; prog>1 zbija recall do 0).

Walidacja MECHANICZNA (nie "czytanie"): opt_recall liczony lokalnie na output.json
(~korpus). Finalne potwierdzenie zywym estymatorem to osobny krok (3b). Progi
OPT_MIN/DF_CAP sa do kalibracji.

Uruchomienie:  python3 scripts/data_manipulation/build_queries_with_optional.py
"""

import collections
import csv
import json
import re
import sys
import unicodedata
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
KAT = DATA_DIR / "estimator"
OUTPUT_JSON = DATA_DIR.parent / "output.json"

# KALIBRACJA EMPIRYCZNA (kalibracja_progi.py): required-only okazalo sie pelne FP na
# kazdym poziomie DF (elementum=lac., vitus=zespol, xxxx=gazety), a opt_recall>=1
# przepuszcza przypadkowe trafienia (carrot-cake+beer). Realne marki maja >=2
# niezalezne korroboracje kontekstu (guinness 2, heineken 3, bacardi 2). Stad:
OPT_MIN = 2             # wymagana liczba URL-i z kontekstem trunku (>=2 odsiewa przypadkowe)
DF_CAP = 200            # powyzej -> zbyt pospolite na czysty keyword marki -> drop
MAX_OPTIONAL = 10
MODE = "m"

DRINK_SYN = {
    "beer": ["beer", "cerveza", "cerveja", "bier", "birra", "biere", "piwo", "pivo"],
    "ale": ["ale", "beer"], "lager": ["lager", "beer"], "stout": ["stout", "beer"],
    "wine": ["wine", "vino", "vinho", "wein", "vinos"],
    "sparkling": ["sparkling", "spumante", "espumante", "cava", "prosecco"],
    "champagne": ["champagne"],
    "rum": ["rum", "rhum"], "gin": ["gin", "ginebra"], "vodka": ["vodka", "wodka"],
    "whisky": ["whisky", "whiskey", "scotch", "bourbon"],
    "whiskey": ["whiskey", "whisky", "bourbon"],
    "tequila": ["tequila", "mezcal"], "mezcal": ["mezcal", "tequila"],
    "liqueur": ["liqueur", "licor", "likor", "liquore"],
    "cider": ["cider", "cidre", "sidra", "cidra", "apfelwein"],
    "brandy": ["brandy", "cognac", "weinbrand"], "cognac": ["cognac", "brandy"],
    "vermouth": ["vermouth", "vermut"], "spirits": ["spirits", "spirit"],
}
AMBIG_FOREIGN = {"ron", "vin"}
GENERIC_BREWERY = {"brewing", "brewery", "breweries", "company", "co", "brouwerij",
                   "brauerei", "cerveceria", "cervejaria", "brasserie", "the", "of"}

# Slowa-style/typy/generyki: keyword zlozony WYLACZNIE z nich to nie marka, lecz
# styl/kategoria (IPA, Belgian, Oktoberfest, Keller, Imperial Stout) -> drop.
# (kalibracja: opt_recall>=2 przepuszczalo je, bo "ipa beer"/"belgian beer"
# wspolwystepuja naturalnie >=2x).
STYLE_GENERIC = {
    # typy trunku
    "beer", "ale", "lager", "stout", "porter", "ipa", "pale", "pils", "pilsner",
    "pilsener", "wine", "vino", "rum", "gin", "vodka", "whisky", "whiskey",
    "tequila", "cider", "liqueur", "brandy", "cognac", "mead", "sake", "vermouth",
    "champagne", "prosecco", "cava", "spirits", "spirit", "bourbon", "mezcal",
    # obcojezyczne slowa trunku (keyword = samo slowo trunku -> nie marka)
    "cerveza", "cerveja", "bier", "birra", "biere", "piwo", "pivo", "vinho", "wein",
    "vinos", "vin", "rhum", "ron", "ginebra", "wodka", "licor", "likor", "liquore",
    "sidra", "cidre", "abbey", "trappist",
    # style piwne
    "hefeweizen", "weizen", "weisse", "weiss", "witbier", "wit", "dubbel", "tripel",
    "quadrupel", "saison", "belgian", "oktoberfest", "marzen", "bock", "doppelbock",
    "maibock", "kolsch", "amber", "brown", "blonde", "golden", "dunkel", "gose",
    "lambic", "altbier", "alt", "schwarzbier", "rauchbier", "barleywine", "esb",
    "bitter", "mild", "helles", "kellerbier", "keller", "vienna", "wiener", "india",
    "imperial", "session", "wheat", "rye", "milk", "oatmeal", "cream", "scotch",
    "irish", "english", "american", "german", "czech", "bohemian", "dry", "sweet",
    "sour", "fruit", "spiced", "herbed", "smoked", "strong", "double", "triple",
    # typy/deskryptory wina
    "red", "white", "rose", "sparkling", "dessert", "port", "sherry", "tinto",
    "blanco", "branco", "brut", "sec", "reserva", "riserva", "crianza",
    # generyki
    "premium", "reserve", "special", "export", "original", "classic", "select",
    "estate", "vintage", "old", "new", "grand", "gran", "gold", "silver", "black",
    "dark", "light", "extra", "fine", "craft",
}
SPECJALNE = {"ł": "l", "Ł": "l", "ø": "o", "Ø": "o", "đ": "d", "ð": "d", "þ": "th",
             "ß": "ss", "æ": "ae", "œ": "oe", "ı": "i"}


def slugify(t):
    for a, b in SPECJALNE.items():
        t = t.replace(a, b)
    t = "".join(c for c in unicodedata.normalize("NFKD", t.lower())
                if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def syn_for(cats):
    out = []
    for c in cats:
        for w in DRINK_SYN.get(c, [c] if c else []):
            if w not in out:
                out.append(w)
    return out


def build_optional(meta, keyword_tokens):
    """Trunek (multilingw.) + szczep/styl + producent. Tylko bezpieczne pola (bez geo)."""
    cands = syn_for(meta.get("cat", [])) + meta.get("sub", []) + meta.get("mak", [])
    seen, out = set(), []
    for t in cands:
        if (not t or t in seen or len(t) <= 2 or t in keyword_tokens
                or t in AMBIG_FOREIGN):
            continue
        seen.add(t)
        out.append(t)
    return out[:MAX_OPTIONAL]


def iter_urls(path):
    buf = ""
    MET = {"sources", "quantity", "sampleSize", "urls"}
    SRC = re.compile(r"^source\d+$")
    Q = re.compile(r'"([^"]*)"')
    with open(path, encoding="utf-8") as f:
        while True:
            chunk = f.read(1 << 20)
            if not chunk:
                for m in Q.finditer(buf):
                    s = m.group(1)
                    if "." in s and s not in MET and not SRC.match(s):
                        yield s
                break
            buf += chunk
            last = 0
            for m in Q.finditer(buf):
                last = m.end()
                s = m.group(1)
                if "." in s and s not in MET and not SRC.match(s):
                    yield s
            buf = buf[last:]


def subtuple(tokens, phrase):
    m = len(phrase)
    for i in range(len(tokens) - m + 1):
        if tokens[i:i + m] == phrase:
            return True
    return False


def load_meta():
    brands, xw, beer = {}, {}, {}
    for r in csv.DictReader((DATA_DIR / "brands_merged.csv").open(encoding="utf-8-sig")):
        brands.setdefault(r["id"], {
            "cat": [c for c in r["category"].split("|") if c], "sub": [],
            "mak": [t for t in slugify(r["maker"]).split("-") if t and t not in GENERIC_BREWERY]})
    for r in csv.DictReader((DATA_DIR / "transformed" / "XWines_transformed.csv").open(encoding="utf-8-sig")):
        grapes = []
        for g in r["Grapes"].split("|")[:5]:
            s = slugify(g)
            if s and s not in grapes:
                grapes.append(s)
        xw.setdefault(r["WineryName"], {
            "cat": ["wine"] + (["sparkling"] if "Sparkling" in r["Type"] else []),
            "sub": grapes, "mak": []})
    for r in csv.DictReader((DATA_DIR / "transformed" / "beer_reviews_transformed.csv").open(encoding="utf-8-sig")):
        beer.setdefault(r["beer_name"], {
            "cat": ["beer"],
            "sub": [t for t in slugify(r["beer_style"]).split("-") if t and t not in GENERIC_BREWERY],
            "mak": [t for t in slugify(r["brewery_name"]).split("-") if t and t not in GENERIC_BREWERY]})
    return {"brands": brands, "xwines": xw, "beer": beer}


def main():
    df = {r["keyword"]: int(r["local_quantity"])
          for r in csv.DictReader((KAT / "keywords_local.csv").open(encoding="utf-8-sig"))}
    META = load_meta()
    alive = list(csv.DictReader((KAT / "positions_alive.csv").open(encoding="utf-8-sig")))

    recs = []
    eval_map = {}   # chosen keyword -> [rec, ...] do wyliczenia opt_recall w jednym przejsciu
    for p in alive:
        chosen = p["alive_variants"].split("|")[0].rsplit(":", 1)[0]
        toks = chosen.split("-")
        rec = {"position_id": p["position_id"], "source": p["source"], "name": p["name"],
               "keyword": chosen, "df": df.get(chosen, 0), "optional": "", "tier": "",
               "decision": "", "reason": "", "opt_recall": 0}
        if max(len(t) for t in toks) <= 2:
            rec.update(tier="smiec", decision="drop", reason="token<=2")
            recs.append(rec)
            continue
        if all(t in STYLE_GENERIC for t in toks):
            rec.update(tier="smiec", decision="drop", reason="styl/generyk")
            recs.append(rec)
            continue
        meta = META[p["source"]].get(p["name"], {})
        opt = build_optional(meta, set(toks)) if meta else []
        rec["_opt"] = opt
        rec["_opttok"] = [o.split("-") for o in opt]
        rec["_opthit"] = 0
        recs.append(rec)
        if opt:
            eval_map.setdefault(chosen, []).append(rec)

    # --- jedno przejscie po output.json: opt_recall dla pozycji z optional ---
    if eval_map:
        TERM = "$"
        trie = {}
        for kw in eval_map:
            node = trie
            for t in kw.split("-"):
                node = node.setdefault(t, {})
            node[TERM] = kw
        n_url = 0
        for url in iter_urls(OUTPUT_JSON):
            tk = [t for t in re.split(r"[^a-z0-9]+", url.lower()) if t]
            if not tk:
                continue
            n = len(tk)
            hit = set()
            for s in range(n):
                node, j = trie, s
                while j < n:
                    node = node.get(tk[j])
                    if node is None:
                        break
                    j += 1
                    if TERM in node:
                        hit.add(node[TERM])
            for kw in hit:
                for rec in eval_map[kw]:
                    if any(subtuple(tk, ot) for ot in rec["_opttok"]):
                        rec["_opthit"] += 1
            n_url += 1
            if n_url % 1000000 == 0:
                print(f"  ... {n_url} URL-i", file=sys.stderr)

    # --- decyzja ---
    for rec in recs:
        if rec["decision"]:
            continue
        opt_recall = rec.pop("_opthit", 0)
        opt = rec.pop("_opt", [])
        rec.pop("_opttok", None)
        rec["opt_recall"] = opt_recall
        d = rec["df"]

        if opt_recall >= OPT_MIN and d <= DF_CAP:
            rec["optional"] = "|".join(opt)
            rec.update(tier="keep", decision="keep", reason="required+optional@1")
        else:
            if d > DF_CAP:
                reason = "DF>cap_pospolite"
            elif opt_recall < OPT_MIN:
                reason = f"opt_recall<{OPT_MIN}"
            else:
                reason = "inne"
            rec.update(tier="drop", decision="drop", reason=reason)

    # --- zapis ---
    pola = ["position_id", "source", "name", "keyword", "tier", "optional",
            "decision", "reason", "df", "opt_recall"]
    with (KAT / "query_decisions.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=pola, lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        w.writerows(recs)

    kept = [r for r in recs if r["decision"] == "keep"]
    with (KAT / "validated_queries.jsonl").open("w", encoding="utf-8") as f:
        for r in kept:
            q = {"id": r["name"], "required": [{"keyword": r["keyword"], "mode": MODE}]}
            if r["optional"]:
                q["optional"] = [{"keyword": o, "mode": MODE} for o in r["optional"].split("|")]
                q["optionalThreshold"] = 1
            f.write(json.dumps(q, ensure_ascii=False) + "\n")

    # --- raport ---
    by_reason = collections.Counter(r["reason"] for r in recs if r["decision"] == "drop")
    by_src = collections.Counter(r["source"] for r in kept)
    print(f"Wejscie zywych pozycji:        {len(alive)}")
    print(f"KEPT (required+optional, opt_recall>={OPT_MIN}, DF<={DF_CAP}): {len(kept)}")
    for src in ("brands", "xwines", "beer"):
        print(f"    {src:8s}: {by_src.get(src,0)}")
    print("Drop wg powodu:")
    for reason, n in by_reason.most_common():
        print(f"    {reason:24s}: {n}")
    print(f"\nWyjscie: {KAT}/query_decisions.csv, validated_queries.jsonl")
    print("\nPrzyklady required+optional (wieloznaczne uratowane):")
    shown = 0
    for r in kept:
        if r["optional"]:
            print(f"    {r['name'][:24]:24s} req={r['keyword']:16s} DF={r['df']:>4} opt[{r['opt_recall']}]={r['optional'][:40]}")
            shown += 1
            if shown >= 10:
                break


if __name__ == "__main__":
    main()
