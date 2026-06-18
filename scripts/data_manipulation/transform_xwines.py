#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Transformacja win X-Wines do kandydatur keywordow dla estymatora -- POZIOM WINIARNI.

Wejscie:  data/XWines_unique.csv
          (kolumny: WineID,WineName,Type,Grapes,Country,RegionName,WineryID,WineryName)
Wyjscie:  data/transformed/XWines_transformed.csv
          (kolumny: WineryID,WineryName,keyword,keyword_variants,optional,
                    Type,Grapes,Country,RegionName)

DLACZEGO POZIOM WINIARNI, A NIE WINA
------------------------------------
W winie rozroznialna marka to WINIARNIA (Casillero del Diablo, Esporao, Miolo,
Salton), a nie nazwa wina -- ta jest zwykle deskryptorem szczepu/stylu ("Cabernet
Sauvignon", "Reserva Tinto", "Espumante Moscatel"). Poprzednia wersja brala
keyword z nazwy wina, przez co 2180 roznych win od roznych producentow laczylo sie
w jeden keyword "cabernet-sauvignon" (generyk -> masowa bledna klasyfikacja;
podobnie "champagne" 511x, "bordeaux"/"rioja" ~351x). Tu zwijamy 100646 win do
~30,5 tys. winiarni (group by WineryID; WineryName jest spojna w obrebie WineryID)
i budujemy keyword z nazwy winiarni.

To jest ODWROTNIE niz w beer_reviews (transform_beer_name.py), gdzie rozroznialnosc
siedzi w nazwie PIWA -- bo piwowarzy nadaja piwom wlasne nazwy ("Cauldron DIPA"),
a winiarnie nazywaja wina szczepem. Stad piwo zostaje na poziomie produktu, a wino
przechodzi na poziom producenta.

CO TRAFIA DO KOLUMN
-------------------
  - keyword          -> glowny (pelny) slug nazwy winiarni -> pod `required`.
  - keyword_variants -> slugi wariantow nazwy winiarni '|'-zlaczone: pelny oraz
                        z odcietymi generykami brzegowymi (bodega/winery/vina/...),
                        do budowy wezszych/szerszych zapytan. Maszyneria slugify
                        i odcinania generykow JEST TA SAMA co w
                        transform_alkohole_wikidata.py.
  - optional         -> pula KANDYDATOW na slowa opcjonalne (slugi, '|'-zlaczone),
                        zagregowana ze WSZYSTKICH win danej winiarni: kraj, region,
                        szczepy (wg czestosci), typ oraz wielojezyczne slowa-kontekst
                        wina (wine/vino/vinho/wein/vin -- jak DRINK_CONTEXT_WORDS w
                        transform_beer_name.py). To te slowa odcinaja falszywe
                        trafienia dla generycznych nazw winiarni ("Aurora", "Casa").
                        UWAGA: finalny dobor `optional` i progu nastepuje dopiero
                        przy budowie zapytan, na podstawie probek URL z estymatora
                        -- tu zbieramy material, kolejnosc = malejaca uzytecznosc.
  - Type/Grapes/Country/RegionName -> zagregowany kontekst czytelny ('|'-zlaczony,
                        wg czestosci), zrodlo dla `optional`; jak passthrough
                        types/makers/countries w transform_alkohole_wikidata.py.

Uruchomienie (z dowolnego cwd -- sciezki liczone wzgledem __file__):
    python3 scripts/data_manipulation/transform_xwines.py
"""

import ast
import collections
import csv
import re
import unicodedata
from pathlib import Path

# --- KONFIGURACJA ---
# Skrypt lezy w scripts/data_manipulation/, wiec do katalogu glownego repo trzeba
# wejsc trzy poziomy w gore (tak samo jak pozostale transformy i scrapery).
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
PLIK_WEJSCIOWY = DATA_DIR / "XWines_unique.csv"
KATALOG_WYJSCIOWY = DATA_DIR / "transformed"
PLIK_WYJSCIOWY = KATALOG_WYJSCIOWY / "XWines_transformed.csv"

KOLUMNY_WYJSCIOWE = [
    "WineryID", "WineryName", "keyword", "keyword_variants", "optional",
    "Type", "Grapes", "Country", "RegionName",
]

# Wielojezyczne slowa "kontekstu wina" zawsze dorzucane do puli `optional`
# (korpus jest mocno PT/ES/FR/IT -- Brazylia, Chile, Francja, Wlochy).
# UWAGA: bez "vin" -- DF w korpusie ~772, zdominowane przez numery VIN aut, nie
# francuskie wino (pomiar z kroku doboru optional); jako korroborator dawalby FP.
DRINK_CONTEXT_WORDS = ["wine", "vino", "vinho", "wein"]

# Slowa zbyt generyczne, by byly wartosciowym keywordem opcjonalnym.
STOPWORDS = {
    "the", "of", "and", "a", "an",
    "de", "la", "el", "le", "du", "des", "der", "di", "do", "da", "y", "e", "i",
}

MAX_GRAPES = 6      # ile najczestszych szczepow winiarni wpuscic do `optional`
MAX_OPTIONAL = 14   # gorny limit slow opcjonalnych (higiena zapytania)

# Generyki KORPORACYJNE/PRODUKCYJNE odcinane z KONCA nazwy (slug-tokeny) -- daja
# dodatkowy, szerszy wariant. Lista jak w transform_alkohole_wikidata.py
# (zawiera juz winery/wineries/wines/vineyard/cellars -- generyki winiarskie).
STRIP_TRAILING = {
    "brewery", "breweries", "brewing",
    "company", "co",
    "distillery", "distilleries", "distillers", "distilling",
    "winery", "wineries", "wines", "vineyard", "vineyards", "cellars", "cellar",
    "group", "brands", "beverages", "beverage", "drinks",
    "brauerei", "brau", "brasserie", "browar", "browary", "birra",
    "cerveceria", "cervejaria",
    "ltd", "limited", "inc", "incorporated", "plc", "corp", "corporation",
    "holdings", "ag", "sa", "spa", "gmbh", "llc", "ab", "kg", "nv", "bv",
    "srl", "sas",
    # winiarskie dopiski koncowe:
    "estate", "estates", "family", "bodega", "bodegas", "vinedos",
}

# Generyki odcinane z POCZATKU nazwy (slug-tokeny). "Bodega Norton" -> tez
# "norton"; "Vina Concha y Toro" -> tez "concha-y-toro"; "Domaine Leflaive" ->
# "leflaive". CELOWO bez "chateau"/"clos" -- te sa zwykle integralna czescia
# marki winiarskiej ("Chateau Margaux" to marka, nie "margaux" = apelacja).
STRIP_LEADING = {
    "the", "champagne", "birra", "brauerei", "brau", "browar", "browary",
    "brasserie", "brouwerij", "cerveceria", "cervejaria", "domaine", "maison",
    "bodega", "bodegas", "weingut", "cantina",
    # winiarskie dopiski poczatkowe:
    "vina", "vinas", "vinedos", "vinedo", "tenuta", "weinkellerei", "weinhaus",
}

# Litery, ktorych NFKD nie rozklada na "litera + znak laczacy" -- mapujemy recznie.
SPECJALNE = {
    "ł": "l", "Ł": "l",
    "ø": "o", "Ø": "o",
    "đ": "d", "Đ": "d",
    "ð": "d", "Ð": "d",
    "þ": "th", "Þ": "th",
    "ß": "ss",
    "æ": "ae", "Æ": "ae",
    "œ": "oe", "Œ": "oe",
    "ı": "i", "İ": "i",
}


def transliteruj(tekst: str) -> str:
    """Zamienia znaki diakrytyczne na odpowiedniki lacinskie (ASCII)."""
    for zrodlo, cel in SPECJALNE.items():
        tekst = tekst.replace(zrodlo, cel)
    nfkd = unicodedata.normalize("NFKD", tekst)
    return "".join(znak for znak in nfkd if not unicodedata.combining(znak))


def slugify(tekst: str) -> str:
    """Sprowadza tekst do keywordu: ASCII, male litery, slowa laczone '-'."""
    tekst = transliteruj(tekst).lower()
    tekst = re.sub(r"[^a-z0-9]+", "-", tekst)
    return tekst.strip("-")


def odetnij_tokeny(slug: str) -> list:
    """Z gotowego slug-a zwraca warianty z odcietymi generykami brzegowymi.

    Generuje KAZDY posredni poziom obciecia (pelny slug zawsze pierwszy), tnac
    wylacznie spojne tokeny brzegowe z list STRIP_*; nigdy nie obcina do pustego.
    Identyczna logika jak w transform_alkohole_wikidata.py.
    """
    if not slug:
        return []
    tokeny = slug.split("-")
    n = len(tokeny)

    li = 0
    while li < n - 1 and tokeny[li] in STRIP_LEADING:
        li += 1
    tj = 0
    while tj < n - 1 and tokeny[n - 1 - tj] in STRIP_TRAILING:
        tj += 1

    warianty = []
    for i in range(li + 1):
        for j in range(tj + 1):
            if i + j >= n:
                continue
            s = "-".join(tokeny[i:n - j])
            if s and s not in warianty:
                warianty.append(s)
    return warianty


def warianty_nazwy(nazwa: str) -> list:
    """Wszystkie kandydatury keywordow z jednej nazwy winiarni.

    Domyslnie tresc w nawiasach jest odcinana. FALLBACK (jak w
    transform_beer_name.py): gdy POZA nawiasami nie ma tresci lacinskiej -- nazwa
    w pismie nielacinskim, a wersja ASCII siedzi w nawiasie ("Бельбек (Belbek)",
    "Шато Пино (Château Pinot)") -- uzyj zawartosci nawiasow zamiast pustki.
    """
    bez_nawiasow = re.sub(r"\([^)]*\)", " ", nazwa)        # usun nawiasy
    if re.search(r"[A-Za-z0-9]", transliteruj(bez_nawiasow)):
        nazwa = bez_nawiasow
    else:
        wewnatrz = " ".join(re.findall(r"\(([^)]*)\)", nazwa))
        nazwa = wewnatrz if wewnatrz.strip() else bez_nawiasow
    nazwa = nazwa.replace("'", "").replace("’", "")        # apostrofy -> sklej
    if "&" in nazwa:
        zrodla = [nazwa.replace("&", " "), nazwa.replace("&", " and ")]
    else:
        zrodla = [nazwa]

    out = []
    for z in zrodla:
        for w in odetnij_tokeny(slugify(z)):
            if w not in out:
                out.append(w)
    return out


def parse_grapes(raw: str) -> list:
    """Parsuje kolumne Grapes (literal listy Pythona) -> lista nazw szczepow."""
    raw = (raw or "").strip()
    if not raw:
        return []
    try:
        val = ast.literal_eval(raw)
        if isinstance(val, (list, tuple)):
            return [str(x).strip() for x in val if str(x).strip()]
    except (ValueError, SyntaxError):
        pass
    return [raw]


def slug_tokeny_metadanej(wartosc: str) -> list:
    """Slugify wartosci kontekstowej, z rozbiciem synonimow po '/'.

    "Muscat/Moscato" -> ["muscat", "moscato"], "Syrah/Shiraz" -> ["syrah",
    "shiraz"], "Dessert/Port" -> ["dessert", "port"], a "Cabernet Sauvignon"
    (jeden szczep, dwa slowa) -> ["cabernet-sauvignon"].
    """
    out = []
    for czesc in str(wartosc).split("/"):
        s = slugify(czesc)
        if s and s not in out:
            out.append(s)
    return out


def posortowane_wg_czestosci(licznik: collections.Counter) -> list:
    """Klucze licznika malejaco wg liczby, remisy alfabetycznie (deterministycznie)."""
    return [k for k, _ in sorted(licznik.items(), key=lambda kv: (-kv[1], kv[0]))]


def zbuduj_optional(types_c, grapes_c, countries_c, regions_c, keyword_tokeny):
    """Buduje uporzadkowana, zdeduplikowana, przycieta pule slow `optional`.

    Kolejnosc = malejaca uzytecznosc dyskryminujaca: kraj -> region -> szczepy
    (wg czestosci) -> wielojezyczny kontekst wina -> typ. Przy przycinaniu do
    MAX_OPTIONAL jako pierwsze wypadaja najslabsze (generyczny typ red/white).
    Pomija tokeny bedace czescia keywordu winiarni, stopwordy i czyste liczby.
    """
    seen, optional = set(), []

    def add(token):
        if (token and token not in keyword_tokeny and token not in STOPWORDS
                and token not in seen and not token.isdigit()):
            seen.add(token)
            optional.append(token)

    for kraj in posortowane_wg_czestosci(countries_c)[:2]:
        for t in slug_tokeny_metadanej(kraj):
            add(t)
    for region in posortowane_wg_czestosci(regions_c)[:3]:
        for t in slug_tokeny_metadanej(region):
            add(t)
    for szczep in posortowane_wg_czestosci(grapes_c)[:MAX_GRAPES]:
        for t in slug_tokeny_metadanej(szczep):
            add(t)
    for slowo in DRINK_CONTEXT_WORDS:
        add(slowo)
    for typ in posortowane_wg_czestosci(types_c):
        for t in slug_tokeny_metadanej(typ):
            add(t)

    return optional[:MAX_OPTIONAL]


def main() -> None:
    KATALOG_WYJSCIOWY.mkdir(exist_ok=True)

    with PLIK_WEJSCIOWY.open(encoding="utf-8-sig", newline="") as f:
        wiersze = list(csv.DictReader(f))

    # --- Grupowanie win po winiarni (WineryID) + agregacja metadanych ---
    grupy = collections.OrderedDict()  # WineryID -> agregat (zachowuje kolejnosc)
    for r in wiersze:
        wid = (r.get("WineryID") or "").strip()
        wname = (r.get("WineryName") or "").strip()
        if not wid or not wname:
            continue
        g = grupy.get(wid)
        if g is None:
            g = grupy[wid] = {
                "WineryName": wname,
                "types": collections.Counter(),
                "grapes": collections.Counter(),
                "countries": collections.Counter(),
                "regions": collections.Counter(),
            }
        typ = (r.get("Type") or "").strip()
        if typ:
            g["types"][typ] += 1
        kraj = (r.get("Country") or "").strip()
        if kraj:
            g["countries"][kraj] += 1
        region = (r.get("RegionName") or "").strip()
        if region:
            g["regions"][region] += 1
        for szczep in parse_grapes(r.get("Grapes")):
            g["grapes"][szczep] += 1

    # --- Budowa wierszy wyjsciowych (jeden = jedna winiarnia) ---
    wynik = []
    for wid, g in grupy.items():
        warianty = warianty_nazwy(g["WineryName"])
        if not warianty:
            continue
        keyword = warianty[0]
        keyword_tokeny = set(keyword.split("-"))

        optional = zbuduj_optional(
            g["types"], g["grapes"], g["countries"], g["regions"], keyword_tokeny
        )

        wynik.append({
            "WineryID": wid,
            "WineryName": g["WineryName"],
            "keyword": keyword,
            "keyword_variants": "|".join(warianty),
            "optional": "|".join(optional),
            # czytelny kontekst (wg czestosci) -- zrodlo dla `optional`
            "Type": "|".join(posortowane_wg_czestosci(g["types"])),
            "Grapes": "|".join(posortowane_wg_czestosci(g["grapes"])),
            "Country": "|".join(posortowane_wg_czestosci(g["countries"])),
            "RegionName": "|".join(posortowane_wg_czestosci(g["regions"])),
        })

    with PLIK_WYJSCIOWY.open("w", encoding="utf-8", newline="") as f:
        # lineterminator="\n" -> czyste LF, bez stray '\r' w keywordach do JSON.
        zapis = csv.DictWriter(f, fieldnames=KOLUMNY_WYJSCIOWE, lineterminator="\n")
        zapis.writeheader()
        zapis.writerows(wynik)

    # --- Krotki raport ---
    puste_opt = sum(1 for w in wynik if not w["optional"])
    sr_opt = (sum(len(w["optional"].split("|")) for w in wynik if w["optional"])
              / max(len(wynik) - puste_opt, 1))
    print(f"Wczytano win:              {len(wiersze)}")
    print(f"Zapisano winiarni:         {len(wynik)}")
    print(f"Unikalnych keyword:        {len({w['keyword'] for w in wynik})}")
    print(f"Winiarnie bez optional:    {puste_opt}")
    print(f"Srednio slow optional:     {sr_opt:.1f}")
    print(f"Plik wyjsciowy:            {PLIK_WYJSCIOWY}")
    print("\nPrzyklady (WineryName -> keyword | optional):")
    for w in wynik[:12]:
        print(f"  {w['WineryName'][:28]:28s} -> {w['keyword']:22s} | {w['optional']}")


if __name__ == "__main__":
    main()
