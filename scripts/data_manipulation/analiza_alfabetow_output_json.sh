#!/usr/bin/env bash
#
# Analiza alfabetow/skryptow w URL-ach z output.json
# ===================================================
#
# Cel: sprawdzic, czy URL-e zwrocone przez estymator (zrzut korpusu w output.json)
# zawieraja wylacznie znaki alfabetu lacinskiego, czy rowniez znaki innych alfabetow
# (cyrylica, arabski, CJK, koreanski, grecki, hebrajski, indyjskie, diakrytyka lacinska...).
#
# Kluczowa obserwacja: plik jest w 100% ASCII, bo znaki spoza ASCII sa w URL-ach
# zakodowane PROCENTOWO (%XX, UTF-8) albo jako PUNYCODE (xn--) w domenach.
# Dlatego "obecnosc innych alfabetow" wykrywamy po sekwencjach %XX i po xn--,
# a nie po surowych bajtach.
#
# Metoda klasyfikacji skryptu: w UTF-8 wieloznakowy znak zaczyna sie bajtem wiodacym
# z zakresu C2-F4, a kolejne bajty (kontynuacja) sa w zakresie 80-BF. Te zakresy sa
# rozlaczne, wiec liczac TYLKO bajty wiodace (%C2-%F4) dostajemy liczbe znakow
# spoza ASCII, a pierwszy bajt wskazuje blok Unicode (czyli w przyblizeniu skrypt).
#
# Plik strumieniowany przez grep (output.json ~253 MB) -- nie wczytujemy go w calosci.
#
# Uzycie:
#   ./claude_scripts/analiza_alfabetow_output_json.sh [sciezka_do_output.json]
# Domyslnie szuka output.json w katalogu glownym repo.

set -euo pipefail

# --- KONFIGURACJA ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
INPUT="${1:-$REPO_ROOT/output.json}"

# Wymuszamy bajtowe (a nie wielobajtowe) traktowanie danych przez grep/sort.
export LC_ALL=C

if [[ ! -f "$INPUT" ]]; then
  echo "BLAD: nie znaleziono pliku wejsciowego: $INPUT" >&2
  exit 1
fi

echo "Plik wejsciowy: $INPUT"
echo "Rozmiar:        $(wc -c < "$INPUT") bajtow"
echo

# --- KROK 1: czy plik to jedna linia i czy sa SUROWE bajty spoza ASCII? ---
echo "== KROK 1: uklad pliku + surowe bajty spoza ASCII =="
echo "Liczba znakow nowej linii (0 = caly JSON w jednej linii): $(wc -l < "$INPUT")"
# grep zwroci 1 (brak dopasowan), gdy nie ma zadnego bajtu >0x7F -- stad '|| true'.
raw_non_ascii="$(grep -c $'[\x80-\xFF]' "$INPUT" || true)"
echo "Linie z surowymi bajtami >0x7F: $raw_non_ascii (0 => plik jest w pelni ASCII)"
echo

# --- KROK 2: ile znakow spoza ASCII jest zakodowanych (punycode + procentowo)? ---
echo "== KROK 2: zliczenie kodowan znakow spoza ASCII =="
echo "Domeny IDN (punycode 'xn--'):                $(grep -o 'xn--' "$INPUT" | wc -l)"
echo "Procentowo kodowane bajty spoza ASCII (%80-%FF): $(grep -oE '%[89aAbBcCdDeEfF][0-9a-fA-F]' "$INPUT" | wc -l)"
echo "Wszystkie sekwencje %XX (dla kontekstu):     $(grep -oE '%[0-9a-fA-F]{2}' "$INPUT" | wc -l)"
echo

# --- KROK 3: przyklady URL-i z punycode i z kodowaniem procentowym ---
echo "== KROK 3: przykladowe URL-e (po 12) =="
echo "-- domeny punycode (xn--):"
grep -oE '"[^"]*xn--[^"]*"' "$INPUT" | head -12 || true
echo
echo "-- URL-e z procentowo kodowanymi znakami spoza ASCII:"
grep -oE '"[^"]*%[cdCD][0-9a-fA-F]%[0-9a-fA-F]{2}[^"]*"' "$INPUT" | head -12 || true
echo

# --- KROK 4: rozklad wg skryptu (pierwszy bajt wiodacej sekwencji UTF-8) ---
echo "== KROK 4: rozklad wiodacych bajtow UTF-8 wg skryptu =="
tmp="$(mktemp)"
# Tylko bajty wiodace (C2-F4); pomijamy bajty kontynuacji (80-BF), aby liczyc znaki, nie bajty.
grep -oE '%[cCdDeEfF][0-9a-fA-F]' "$INPUT" > "$tmp"
echo "Lacznie znakow spoza ASCII (wiodacych bajtow UTF-8): $(wc -l < "$tmp")"
echo
echo "Rozklad wg pierwszego bajtu (TOP 25):"
echo "  bajt   szacowany skrypt"
echo "  ----   ----------------"
{ tr '[:lower:]' '[:upper:]' < "$tmp" | sort | uniq -c | sort -rn | head -25 || true; } \
  | while read -r count byte; do
      case "$byte" in
        %C3|%C2)        s="lacinski z diakrytyka (Latin-1 Supplement)";;
        %C4|%C5)        s="lacinski rozszerzony (Latin Extended-A, np. l/s/z)";;
        %CE|%CF)        s="grecki";;
        %D0|%D1)        s="cyrylica";;
        %D6|%D7)        s="hebrajski";;
        %D8|%D9|%DA|%DB) s="arabski";;
        %E0)            s="indyjskie / tajski (Devanagari, Thai, ...)";;
        %E2)            s="symbole / interpunkcja (myslnik, wielokropek, ...)";;
        %E3)            s="japonski (kana) + interpunkcja CJK";;
        %E4|%E5|%E6|%E7|%E8|%E9) s="CJK (hanzi/kanji)";;
        %EA|%EB|%EC|%ED) s="koreanski (Hangul)";;
        %EF)            s="formy fullwidth / specjalne (CJK Compatibility)";;
        %F0)            s="plany dodatkowe / emoji (4-bajtowe UTF-8)";;
        *)              s="?";;
      esac
      printf "  %-6s %-8s %s\n" "$byte" "$count" "$s"
    done
rm -f "$tmp"
echo
echo "Wniosek: URL-e zawieraja znaki z wielu alfabetow (nie tylko lacinskiego)."
