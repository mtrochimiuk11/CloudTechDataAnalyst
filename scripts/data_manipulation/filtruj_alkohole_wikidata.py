#!/usr/bin/env python3
"""Filtrowanie danych z Wikidata do użytecznych marek alkoholi.

Wejście:  data/alkohole_wikidata.csv (kolumny: wikidata,name,aliases,types,makers,countries)
Wyjście:  data/alkohole_wikidata_filtered.csv  — rzędy, które zostają (te same kolumny)
          data/alkohole_wikidata_rejected.csv  — rzędy odrzucone + kolumna reject_reason

Strategia: BLACKLIST nie-alkoholi (najszerszy wynik). Rząd zostaje domyślnie;
odrzucamy go TYLKO, gdy kolumna `types` jawnie wskazuje, że to nie jest alkohol,
i jednocześnie nie ma w niej żadnego pozytywnego typu alkoholowego.

Powody odrzucenia (każdy działa tylko przy BRAKU pozytywnego typu alko):
  - non_alcohol_drink : dairy product, soft drink, non-alcoholic beverage, ...
  - meta_page         : strona-lista Wikimedia ("list of vodkas" itd.)

Rzędy z PUSTYM `types` lub tylko z surowym kodem Q (brak dyskwalifikatora) celowo
ZOSTAJĄ — to realne marki, których Wikidata po prostu nie otagowała etykietą
(Midori, Lillet, Plymouth Gin, Allen's Coffee Brandy, ...).

Uwaga zakresowa: skrypt NIE czyści zawartości kolumny `types` — przepisuje rzędy
w całości, w oryginalnym kształcie. Jedyne zadanie to odsianie nie-alkoholi.
"""

import csv
from pathlib import Path

# --- KONFIGURACJA ---
# claude_scripts/ leży tuż pod katalogiem głównym repo, a `data/` jest jego sąsiadem.
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
INPUT = DATA_DIR / "alkohole_wikidata.csv"
OUT_KEPT = DATA_DIR / "alkohole_wikidata_filtered.csv"
OUT_REJECTED = DATA_DIR / "alkohole_wikidata_rejected.csv"

# Typy jednoznacznie nie-alkoholowe (napoje, które dyskwalifikują rząd).
NON_ALCOHOL_TYPES = {
    "dairy product",
    "dairy drink",
    "non-alcoholic beverage",
    "soft drink",
    "sugary drink",
}

# Typy oznaczające stronę-listę / artefakt Wikimedia (to nie jest pojedyncza marka).
META_PAGE_TYPES = {
    "wikimedia list article",
    "wikimedia internal item",
    "wikimedia article page",
    "list",
}

# Pozytywne typy alkoholowe — GUARD. Jeśli rząd ma choć jeden z nich, ZOSTAJE
# niezależnie od dyskwalifikatorów (chroni m.in. likiery kremowe = dairy + liqueur
# oraz pozycje typu "Free Beer" = realna marka + szum "social movement/list").
# Lista wyciągnięta z faktycznych wartości kolumny `types` w tym zbiorze.
ALCOHOL_POSITIVE_TYPES = {
    # ogólne kategorie napojów alkoholowych
    "alcoholic beverage", "fermented alcoholic beverage", "alcoholic fruit beverage",
    "alcohol brand", "drink brand", "spirit drink", "liquor", "liqueur", "apéritif",
    "aperitif", "brew", "malt beverage", "wine spirit", "eau-de-vie",
    # piwo
    "beer", "beer brand", "beer style", "lager", "pale lager", "pilsner", "ale",
    "pale ale", "brown ale", "cream ale", "india pale ale", "stout", "bock",
    "märzen", "witbier", "wheat beer", "light beer", "abbey beer", "trappist beer",
    "barley wine", "malt liquor", "low fermentation beer", "high fermentation beer",
    "american wild ale", "seasonal beer", "blond", "oud bruin",
    "beer in the czech republic", "beer in the netherlands",
    "microbrewery", "brewery", "brewpub", "brewpub chain", "lambic brewery",
    "brewery building", "brewer", "beer professional",
    # whisky / whiskey
    "whisky", "whiskey", "american whiskey", "bourbon whiskey", "scotch whisky",
    "blended whiskey", "blended scotch whisky", "blended malt whisky",
    "single malt whisky", "malt whisky", "grain whisky", "grain spirit",
    "wheat whiskey", "irish whiskey", "whisky distillery",
    # destylarnie / spirytusy
    "distillery", "microdistillery", "distiller", "gin distiller",
    "distilling industry", "spirits industry",
    # gin / wódka / rum / brandy itd.
    "gin", "jenever", "vodka", "rum", "white rum", "cachaça", "brandy", "cognac",
    "coca wine", "baijiu", "shaojiu", "kaoliang wine", "chūhai", "hard seltzer",
    # wino / cydr
    "wine", "french wine", "sparkling wine", "champagne", "champagne house",
    "wine company", "wine brand", "winery", "viticulture plant", "vineyard",
    "cider", "cider brand", "cider mill", "perry",
}


def split_types(raw):
    """Rozbija kolumnę `types` na znormalizowane (lower, trim) tokeny."""
    return [t.strip() for t in (raw or "").split("|") if t.strip()]


def reject_reason(types_raw):
    """Zwraca powód odrzucenia rzędu albo None, jeśli rząd zostaje.

    Rząd odrzucamy tylko, gdy NIE ma żadnego pozytywnego typu alkoholowego
    i jednocześnie zawiera jawny dyskwalifikator.
    """
    tokens = split_types(types_raw)
    lower = {t.lower() for t in tokens}

    # Guard: jakikolwiek pozytywny typ alkoholowy => zostaje.
    if lower & ALCOHOL_POSITIVE_TYPES:
        return None

    if lower & NON_ALCOHOL_TYPES:
        return "non_alcohol_drink"
    if lower & META_PAGE_TYPES:
        return "meta_page"

    # Brak dyskwalifikatora (również pusty `types` lub sam kod Q) => zostaje.
    return None


def main():
    with INPUT.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    kept, rejected = [], []
    for row in rows:
        reason = reject_reason(row.get("types"))
        if reason is None:
            kept.append(row)
        else:
            rejected.append({**row, "reject_reason": reason})

    DATA_DIR.mkdir(exist_ok=True)

    with OUT_KEPT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(kept)

    with OUT_REJECTED.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames + ["reject_reason"])
        writer.writeheader()
        writer.writerows(rejected)

    # Krótkie podsumowanie na ekranie.
    from collections import Counter
    by_reason = Counter(r["reject_reason"] for r in rejected)
    print(f"Wejście:    {len(rows)} rzędów")
    print(f"Zostaje:    {len(kept)} -> {OUT_KEPT.name}")
    print(f"Odrzucono:  {len(rejected)} -> {OUT_REJECTED.name}")
    for reason, n in by_reason.most_common():
        print(f"  - {reason}: {n}")
    if rejected:
        print("\nOdrzucone pozycje:")
        for r in rejected:
            print(f"  [{r['reject_reason']}] {r['name']} :: {r['types']}")


if __name__ == "__main__":
    main()
