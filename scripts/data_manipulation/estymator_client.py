#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Klient estymatora keywordow (wspoldzielony przez kroki 2b/kalibracje).

Estymator (z PDF): JEDNO zapytanie na POST:
    curl --data '@q.json' 'https://urlkeywords.ctpl.dev/keywordURLs'
Cialo:     {"required":[{"keyword":"<kw>","mode":"m"}], ...opcjonalnie optional...}
Odpowiedz: {"sources":{"sourceN":{"quantity":N,"sampleSize":N,"urls":[...]}}}
  -- `sourceN` to wewnetrzne zrodla danych firmy; calkowity recall = SUMA `quantity`
  po zrodlach, a probka URL do oceny trafnosci = polaczone `urls` ze zrodel.

Replikujemy DZIALAJACE wywolanie curl --data: Content-Type
application/x-www-form-urlencoded, cialo = surowy JSON (serwer parsuje body jako
JSON niezaleznie od naglowka). Grzecznosc: timeout, retry z backoffem.

Uzycie jako modul:
    from estymator_client import zapytaj
    r = zapytaj("bacardi")              # {"keyword","quantity","per_source","urls"} albo None
Uzycie z CLI (recznie):
    python3 scripts/data_manipulation/estymator_client.py bacardi
    python3 scripts/data_manipulation/estymator_client.py "casillero-del-diablo" m
"""

import json
import sys
import time
import urllib.error
import urllib.request

URL = "https://urlkeywords.ctpl.dev/keywordURLs"
TIMEOUT = 30
RETRIES = 3
BACKOFF = 1.5            # sekundy: BACKOFF**proba


def zapytaj(keyword, mode="m", optional=None, optional_threshold=None,
            timeout=TIMEOUT, retries=RETRIES):
    """Odpytuje estymator o jedno zapytanie. Zwraca dict albo None (po retry).

    dict: {"keyword", "quantity" (suma po zrodlach), "per_source" {srcN: q},
           "sample_size" (suma sampleSize), "urls" (polaczona probka)}.
    """
    query = {"required": [{"keyword": keyword, "mode": mode}]}
    if optional:
        query["optional"] = [{"keyword": k, "mode": mode} for k in optional]
        query["optionalThreshold"] = (optional_threshold
                                      if optional_threshold is not None else 1)
    body = json.dumps(query).encode("utf-8")
    req = urllib.request.Request(
        URL, data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"})

    for proba in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                d = json.loads(resp.read().decode("utf-8"))
            sources = d.get("sources", {}) or {}
            return {
                "keyword": keyword,
                "quantity": sum(v.get("quantity", 0) for v in sources.values()),
                "per_source": {k: v.get("quantity", 0) for k, v in sources.items()},
                "sample_size": sum(v.get("sampleSize", 0) for v in sources.values()),
                "urls": [u for v in sources.values() for u in (v.get("urls") or [])],
            }
        except (urllib.error.URLError, urllib.error.HTTPError,
                json.JSONDecodeError, TimeoutError) as e:
            if proba == retries - 1:
                print(f"  [BLAD] {keyword!r}: {e}", file=sys.stderr)
                return None
            time.sleep(BACKOFF ** proba)
    return None


def zapytaj_raw(query, timeout=TIMEOUT, retries=RETRIES):
    """Wysyla GOTOWY obiekt zapytania (required[+optional+optionalThreshold]).

    Zwraca {"quantity" (suma po zrodlach), "urls" (polaczona probka)} albo None.
    Uzywane do potwierdzania finalnych wpisow deliverable 1:1.
    """
    body = json.dumps(query).encode("utf-8")
    req = urllib.request.Request(
        URL, data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    for proba in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                d = json.loads(resp.read().decode("utf-8"))
            sources = d.get("sources", {}) or {}
            return {
                "quantity": sum(v.get("quantity", 0) for v in sources.values()),
                "urls": [u for v in sources.values() for u in (v.get("urls") or [])],
            }
        except (urllib.error.URLError, urllib.error.HTTPError,
                json.JSONDecodeError, TimeoutError) as e:
            if proba == retries - 1:
                print(f"  [BLAD] {query}: {e}", file=sys.stderr)
                return None
            time.sleep(BACKOFF ** proba)
    return None


if __name__ == "__main__":
    kw = sys.argv[1] if len(sys.argv) > 1 else "bacardi"
    mode = sys.argv[2] if len(sys.argv) > 2 else "m"
    r = zapytaj(kw, mode)
    if r is None:
        print("Brak odpowiedzi.")
    else:
        print(f"keyword={r['keyword']!r} mode={mode} quantity={r['quantity']} "
              f"sample_size={r['sample_size']}")
        print("per_source:", r["per_source"])
        print("przyklad urls:", r["urls"][:5])
