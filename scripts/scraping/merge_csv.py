"""
Scalanie wielu plików CSV (o tych samych kolumnach) w jeden.

Domyślnie zbiera pliki 'twe_brands*.csv' z folderu pobierania (przeglądarka
dokleja '(1)', '(2)' do powtórzonych nazw) i zapisuje scalony plik do data/.

Zależności:
    pip install pandas
"""

from pathlib import Path
import pandas as pd

# ------------------- KONFIGURACJA -------------------
INPUT_DIR = Path.home() / "Downloads"   # gdzie leżą pobrane pliki
PATTERN = "twe_brands*.csv"             # które pliki scalić ("*.csv" = wszystkie)

OUTPUT = Path(__file__).resolve().parent.parent.parent / "data" / "twe_brands_merged.csv"
DEDUP = True
# ----------------------------------------------------


def main():
    files = sorted(INPUT_DIR.glob(PATTERN))
    if not files:
        raise SystemExit(f"Brak plików '{PATTERN}' w {INPUT_DIR}")

    frames = []
    for f in files:
        # utf-8-sig zdejmuje BOM dodany przez skrypt w przeglądarce
        df = pd.read_csv(f, encoding="utf-8-sig", dtype=str).fillna("")
        print(f"{f.name}: {len(df)} wierszy, kolumny {list(df.columns)}")
        frames.append(df)

    merged = pd.concat(frames, ignore_index=True)
    before = len(merged)
    if DEDUP:
        merged = merged.drop_duplicates().reset_index(drop=True)

    print(f"\nScalono {len(files)} plików: {before} wierszy"
          + (f" -> {len(merged)} po dedupie" if DEDUP else ""))

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(OUTPUT, index=False)
    print(f"Zapisano do {OUTPUT}")


if __name__ == "__main__":
    main()