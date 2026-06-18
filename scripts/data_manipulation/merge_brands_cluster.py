#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KROK 0 potoku: scalenie i deduplikacja klastra list marek (cross-file).

Wejscie:  data/transformed/{rum_brands,french_rums,puerto_rican_rums,gin_brands,
          vodka_brands,tequila_brands,liqueur_brands,cider_brands,twe_brands,
          alkohole_wikidata}_transformed.csv
Wyjscie:  data/brands_merged.csv
          (kolumny: id,keyword,keyword_variants,optional,category,country,maker,
                    extra,sources,aka)

DLACZEGO TYLKO TEN KLASTER (a nie XWines/beer)
----------------------------------------------
Pomiar nakladania (przeciecia keywordow) pokazal, ze cala cross-file duplikacja
siedzi w tych 10 plikach: spirytusy ∩ (twe+wikidata) = 24%, twe ∩ wikidata = 7%.
Dwa giganty -- XWines (wino) i beer_reviews (piwo) -- to WYSPY: nakladaja sie na
reszte w <1%, a wspolne slugi wino<->piwo to KOLIZJE NAZW ("Aurora" winiarnia !=
"Aurora" piwo), nie duplikaty. Dlatego gigantow NIE scalamy tu stringiem (zostana
zdeduplikowane po estymatorze, behawioralnie -- po nakladaniu zbiorow URL).

CO ROBI TEN SKRYPT
------------------
Laczy wpisy z 10 plikow po kluczu = znormalizowana nazwa (lower, bez diakrytykow,
tylko alfanumeryczne). Dla kazdej grupy:
  - id               -> nazwa kanoniczna: pierwsza wg priorytetu zrodel (pliki
                        kategorii > twe > wikidata; pliki przetwarzane w tej
                        kolejnosci), oryginalna pisownia. Reszta nazw -> `aka`.
  - keyword          -> glowny slug = pierwszy kandydat wg priorytetu (pliki
                        kategorii daja precyzyjny rdzen z koncowka typu, np.
                        "safari-rum"; to swiadomy default precision-first).
  - keyword_variants -> UNIA wszystkich slugow ze wszystkich zrodel ('|') --
                        material na wezsze/szersze zapytania (m.in. aliasy z
                        wikidata, np. "cc" dla Canadian Club).
  - optional         -> pula KANDYDATOW na slowa opcjonalne (slugi, '|'), wg
                        malejacej uzytecznosci dyskryminujacej: typ trunku ->
                        kraj -> producent -> kontekst (miasto/region). To te slowa
                        odcinaja falszywe trafienia dla wieloznacznych nazw.
                        Finalny dobor i prog nastepuja przy budowie zapytan.
  - category/country/maker/extra/sources -> zagregowany, czytelny kontekst i
                        proweniencja (audyt scalenia, mozliwosc rozdzielenia).

Scalamy PONAD kategoriami (ta sama nazwa w obrebie klastra spirytusowego to
zwykle ta sama marka -- linia produktowa destylarni). Ryzykowne scalenia
miedzydomenowe (np. spirytus zlany z winem/piwem z agregatora o tej samej nazwie)
sa RAPORTOWANE (flaga multi-domena), bo proweniencja pozwala je pozniej rozdzielic;
ostatecznie wylapie je bramka precyzji po estymatorze.

Uruchomienie (z dowolnego cwd -- sciezki liczone wzgledem __file__):
    python3 scripts/data_manipulation/merge_brands_cluster.py
"""

import collections
import csv
import re
import unicodedata
from pathlib import Path

# --- KONFIGURACJA ---
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
KATALOG_TRANSFORMED = DATA_DIR / "transformed"
PLIK_WYJSCIOWY = DATA_DIR / "brands_merged.csv"

# Pliki klastra w KOLEJNOSCI PRIORYTETU (pierwszy, ktory wprowadzi klucz, ustala
# nazwe kanoniczna i glowny keyword): pliki kategorii > twe > wikidata.
# Krotka konfiguracja per plik:
#   nazwa pliku (bez sufiksu), kolumna nazwy, kategoria (literal albo
#   ("col", kolumna) / ("wikidata", kolumna)), kolumna kraju, kolumna producenta,
#   kolumny kontekstu dodatkowego.
FILES = [
    ("rum_brands",        "brand", "rum",      "country", None,     []),
    ("french_rums",       "name",  "rum",      None,      None,     ["location"]),
    ("puerto_rican_rums", "brand", "rum",      None,      None,     []),
    ("gin_brands",        "brand", "gin",      None,      None,     ["extraInfo"]),
    ("vodka_brands",      "brand", "vodka",    None,      None,     []),
    ("tequila_brands",    "brand", "tequila",  None,      None,     ["extraInfo"]),
    ("liqueur_brands",    "brand", "liqueur",  None,      None,     ["category"]),
    ("cider_brands",      "brand", "cider",    "country", None,     ["town", "type"]),
    ("twe_brands",        "brand", ("col", "category"),     None, None, []),
    ("alkohole_wikidata", "name",  ("wikidata", "types"),   "countries", "makers", []),
]

# Slownik typow trunku -- do wyciagniecia czystej kategorii z zaszumionych pol
# (twe.category, wikidata.types: "trademark | alcoholic beverage | drink brand").
DRINK_TYPE_VOCAB = {
    "rum", "gin", "vodka", "tequila", "mezcal", "whisky", "whiskey", "scotch",
    "bourbon", "rye", "liqueur", "cider", "beer", "ale", "lager", "stout",
    "wine", "brandy", "cognac", "armagnac", "vermouth", "aperitif", "sake",
    "mead", "schnapps", "absinthe", "port", "sherry", "champagne", "prosecco",
    "cachaca", "pisco", "grappa", "calvados", "sambuca", "amaro",
}

# Normalizacja kategorii twe do slownika typow.
TWE_CAT_MAP = {
    "liqueurs": "liqueur", "other-spirits": "spirits",
    "vermouth-and-aperitif": "vermouth", "wine": "wine", "whisky": "whisky",
    "rum": "rum", "gin": "gin", "vodka": "vodka", "cognac": "cognac",
    "tequila": "tequila",
}

# Mapa kategoria -> domena (do flagi ryzykownych scalen miedzydomenowych).
DOMENA = {
    "rum": "spirits", "gin": "spirits", "vodka": "spirits", "tequila": "spirits",
    "mezcal": "spirits", "whisky": "spirits", "whiskey": "spirits",
    "scotch": "spirits", "bourbon": "spirits", "rye": "spirits",
    "brandy": "spirits", "cognac": "spirits", "armagnac": "spirits",
    "liqueur": "spirits", "vermouth": "spirits", "aperitif": "spirits",
    "schnapps": "spirits", "absinthe": "spirits", "spirits": "spirits",
    "cachaca": "spirits", "pisco": "spirits", "grappa": "spirits",
    "wine": "wine", "port": "wine", "sherry": "wine", "champagne": "wine",
    "prosecco": "wine",
    "beer": "beer", "ale": "beer", "lager": "beer", "stout": "beer",
    "cider": "cider",
}

# Slowa kontekstu (extra) zbyt generyczne, by byly wartosciowym keywordem.
EXTRA_STOP = {
    "distillery", "microdistillery", "distilling", "distillers", "brewery",
    "brewing", "company", "co", "style", "brand", "based", "founded",
    "the", "of", "and", "a", "an", "de", "la", "el",
    # slowa funkcyjne/wypelniacze z opisow (extraInfo/location) -- nigdy nie sa
    # dobrym standalone keywordem: "...one of the first gin distilled in Oregon".
    "in", "on", "at", "for", "one", "its", "was", "were", "is", "are", "has",
    "have", "with", "from", "near", "also", "known", "made", "produced", "first",
}
STOPWORDS = {"the", "of", "and", "a", "an", "de", "la", "el", "le", "di", "do"}

MAX_OPTIONAL = 12

# Litery, ktorych NFKD nie rozklada -- mapujemy recznie (jak w transformach).
SPECJALNE = {
    "ł": "l", "Ł": "l", "ø": "o", "Ø": "o", "đ": "d", "Đ": "d", "ð": "d",
    "Ð": "d", "þ": "th", "Þ": "th", "ß": "ss", "æ": "ae", "Æ": "ae",
    "œ": "oe", "Œ": "oe", "ı": "i", "İ": "i",
}


def transliteruj(tekst: str) -> str:
    """Zamienia znaki diakrytyczne na odpowiedniki lacinskie (ASCII)."""
    for zrodlo, cel in SPECJALNE.items():
        tekst = tekst.replace(zrodlo, cel)
    nfkd = unicodedata.normalize("NFKD", tekst)
    return "".join(z for z in nfkd if not unicodedata.combining(z))


def slugify(tekst: str) -> str:
    """Sprowadza tekst do keywordu: ASCII, male litery, slowa laczone '-'."""
    tekst = transliteruj(tekst).lower()
    tekst = re.sub(r"[^a-z0-9]+", "-", tekst)
    return tekst.strip("-")


def klucz_dopasowania(nazwa: str) -> str:
    """Klucz tozsamosci marki: lower, bez diakrytykow, tylko alfanumeryczne."""
    return re.sub(r"[^a-z0-9]+", "", transliteruj(nazwa).lower())


def tokeny_typu(raw: str) -> list:
    """Wyciaga z zaszumionego pola tokeny bedace typem trunku (DRINK_TYPE_VOCAB)."""
    out = []
    for czesc in re.split(r"[|/,]", raw or ""):
        for tok in slugify(czesc).split("-"):
            if tok in DRINK_TYPE_VOCAB and tok not in out:
                out.append(tok)
    return out


def rozwiaz_kategorie(spec, row) -> list:
    """Zwraca liste tokenow-kategorii (typ trunku) dla wiersza wg konfiguracji."""
    if isinstance(spec, str):
        return [spec]
    rodzaj, kol = spec
    surowe = (row.get(kol) or "").strip()
    if rodzaj == "wikidata":
        return tokeny_typu(surowe)
    # rodzaj == "col" (twe.category)
    s = slugify(surowe)
    return [TWE_CAT_MAP.get(s, s)] if s else []


def warianty_keyworda(row) -> list:
    """Lista slugow-kandydatow z wiersza: keyword + keyword_variants (jesli jest)."""
    out = []
    for pole in (row.get("keyword"), row.get("keyword_variants")):
        for czesc in (pole or "").split("|"):
            s = czesc.strip()
            if s and s not in out:
                out.append(s)
    return out


def podziel_wartosci(raw: str) -> list:
    """Rozbija pole na wartosci (separatory: '|', ',') -- np. kraje/producenci."""
    return [c.strip() for c in re.split(r"[|,]", raw or "") if c.strip()]


def zbuduj_optional(categories, countries, makers, extras, keyword_tokeny) -> list:
    """Pula `optional` wg malejacej uzytecznosci: typ -> kraj -> producent -> extra."""
    seen, optional = set(), []

    def add(token):
        if (token and token not in keyword_tokeny and token not in STOPWORDS
                and token not in seen and not token.isdigit()):
            seen.add(token)
            optional.append(token)

    for c in categories:                       # typ trunku -- najlepszy dyskryminator
        add(c)
    for kraj in countries[:2]:                 # kraj pochodzenia
        add(slugify(kraj))
    for maker in makers[:2]:                    # producent
        add(slugify(maker))
    for ex in extras:                          # miasto/region/opis -- tokeny
        for tok in slugify(ex).split("-"):
            if tok not in EXTRA_STOP:
                add(tok)

    return optional[:MAX_OPTIONAL]


def main() -> None:
    # grupy: klucz -> agregat (OrderedDict -> stabilna kolejnosc pierwszego wystapienia)
    grupy = collections.OrderedDict()
    wczytane = 0

    for stem, name_col, cat_spec, country_col, maker_col, extra_cols in FILES:
        sciezka = KATALOG_TRANSFORMED / f"{stem}_transformed.csv"
        with sciezka.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                nazwa = (row.get(name_col) or "").strip()
                if not nazwa:
                    continue
                wczytane += 1
                klucz = klucz_dopasowania(nazwa)
                if not klucz:
                    continue

                g = grupy.get(klucz)
                if g is None:
                    g = grupy[klucz] = {
                        "id": nazwa,                       # pierwszy wg priorytetu
                        "aka": [],
                        "keywords": [],                    # slugi wg priorytetu
                        "categories": [],
                        "countries": [],
                        "makers": [],
                        "extras": [],
                        "sources": [],
                    }
                elif nazwa != g["id"] and nazwa not in g["aka"]:
                    g["aka"].append(nazwa)

                for kw in warianty_keyworda(row):
                    if kw not in g["keywords"]:
                        g["keywords"].append(kw)
                for c in rozwiaz_kategorie(cat_spec, row):
                    if c and c not in g["categories"]:
                        g["categories"].append(c)
                if country_col:
                    for kraj in podziel_wartosci(row.get(country_col)):
                        if kraj not in g["countries"]:
                            g["countries"].append(kraj)
                if maker_col:
                    for mk in podziel_wartosci(row.get(maker_col)):
                        if mk not in g["makers"]:
                            g["makers"].append(mk)
                for col in extra_cols:
                    val = (row.get(col) or "").strip()
                    if val and val not in g["extras"]:
                        g["extras"].append(val)
                if stem not in g["sources"]:
                    g["sources"].append(stem)

    # --- Budowa wierszy wyjsciowych ---
    wynik = []
    for g in grupy.values():
        if not g["keywords"]:
            continue
        keyword = g["keywords"][0]
        keyword_tokeny = set(keyword.split("-"))
        optional = zbuduj_optional(
            g["categories"], g["countries"], g["makers"], g["extras"], keyword_tokeny
        )
        wynik.append({
            "id": g["id"],
            "keyword": keyword,
            "keyword_variants": "|".join(g["keywords"]),
            "optional": "|".join(optional),
            "category": "|".join(g["categories"]),
            "country": "|".join(g["countries"]),
            "maker": "|".join(g["makers"]),
            "extra": "|".join(g["extras"]),
            "sources": "|".join(sorted(g["sources"])),
            "aka": "|".join(g["aka"]),
        })

    pola = ["id", "keyword", "keyword_variants", "optional", "category",
            "country", "maker", "extra", "sources", "aka"]
    with PLIK_WYJSCIOWY.open("w", encoding="utf-8", newline="") as f:
        zapis = csv.DictWriter(f, fieldnames=pola, lineterminator="\n")
        zapis.writeheader()
        zapis.writerows(wynik)

    # --- Raport ---
    multi_src = [w for w in wynik if "|" in w["sources"]]
    # flaga: scalenie miedzydomenowe (kategorie z >1 domeny: spirits/wine/beer/cider)
    def domeny(w):
        return {DOMENA.get(c) for c in w["category"].split("|") if DOMENA.get(c)}
    multi_dom = [w for w in wynik if len(domeny(w)) > 1]

    print(f"Wczytano wierszy (10 plikow): {wczytane}")
    print(f"Unikalnych marek po scaleniu: {len(wynik)}")
    print(f"Scalonych duplikatow:         {wczytane - len(wynik)}")
    print(f"Marek z >1 zrodla:            {len(multi_src)}")
    print(f"Flaga multi-domena (przejrzec): {len(multi_dom)}")
    print(f"Plik wyjsciowy:               {PLIK_WYJSCIOWY}")

    print("\nPrzyklady scalen z wielu zrodel (id <- sources | keyword | optional):")
    for w in multi_src[:12]:
        print(f"  {w['id'][:24]:24s} <- {w['sources']:34s} | {w['keyword']:18s} | {w['optional']}")

    if multi_dom:
        print("\nFlaga multi-domena (do przegladu -- mozliwa kolizja nazw):")
        for w in multi_dom[:10]:
            print(f"  {w['id'][:24]:24s} | category={w['category']:22s} | sources={w['sources']}")


if __name__ == "__main__":
    main()
