import pandas as pd, requests
from pathlib import Path

# folder 'data' w katalogu głównym repo (skrypt leży w scripts/scraping/)
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)   # utwórz, jeśli nie istnieje

URL = "https://en.wikipedia.org/wiki/List_of_vodka_brands"
html = requests.get(URL, headers={"User-Agent": "Mozilla/5.0"}).text
df = pd.read_html(html, attrs={"class": "wikitable"})[0]
brands = df.iloc[:, 0].dropna().astype(str).str.strip()
print(type(brands))
print(brands.tolist())
brands.to_csv(DATA_DIR / "vodka_brands.csv", index=False, header=["brand"])