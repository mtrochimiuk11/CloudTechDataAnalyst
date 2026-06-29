# Opis wykonania zadania

Zadanie rozpocząłem od przygotowania listy alkoholi. Za pomocą scraperów z folderu
`scripts/scraping/` pobrałem alkohole z następujących stron:

- <https://en.wikipedia.org/wiki/List_of_rum_brands>
- <https://en.wikipedia.org/wiki/List_of_tequilas>
- <https://en.wikipedia.org/wiki/Gin>
- <https://en.wikipedia.org/wiki/List_of_French_rums>
- <https://en.wikipedia.org/wiki/List_of_liqueur_brands>
- <https://en.wikipedia.org/wiki/List_of_Puerto_Rican_rums>
- <https://en.wikipedia.org/wiki/List_of_cider_brands>
- <https://en.wikipedia.org/wiki/List_of_vodka_brands>
- <https://www.whiskybase.com/whiskies/brands>

Pobrałem też dane ze stron:

- <https://www.thewhiskyexchange.com/brands/worldwhisky/32/irish-whiskey>
- <https://www.thewhiskyexchange.com/brands/worldwhisky/33/american-whiskey>
- <https://www.thewhiskyexchange.com/brands/worldwhisky/35/japanese-whisky>
- <https://www.thewhiskyexchange.com/brands/worldwhisky/34/canadian-whisky>
- <https://www.thewhiskyexchange.com/brands/worldwhisky/305/rest-of-the-world-whisky>
- <https://www.thewhiskyexchange.com/brands/scotchwhisky/40/single-malt-scotch-whisky>
- <https://www.thewhiskyexchange.com/brands/scotchwhisky/304/blended-scotch-whisky>
- <https://www.thewhiskyexchange.com/brands/scotchwhisky/309/blended-malt-scotch-whisky>
- <https://www.thewhiskyexchange.com/brands/scotchwhisky/310/grain-scotch-whisky>
- <https://www.thewhiskyexchange.com/brands/spirits/351/cognac>
- <https://www.thewhiskyexchange.com/brands/spirits/355/armagnac>
- <https://www.thewhiskyexchange.com/brands/spirits/338/gin>
- <https://www.thewhiskyexchange.com/brands/spirits/623/jenever>
- <https://www.thewhiskyexchange.com/brands/spirits/339/rum>
- <https://www.thewhiskyexchange.com/brands/spirits/335/vodka>
- <https://www.thewhiskyexchange.com/brands/spirits/359/tequila>
- <https://www.thewhiskyexchange.com/brands/spirits/343/liqueurs>
- <https://www.thewhiskyexchange.com/brands/spirits/345/bitters-and-sprays>
- <https://www.thewhiskyexchange.com/brands/spirits/365/vermouths-aperitifs-and-digestifs>
- <https://www.thewhiskyexchange.com/brands/spirits/366/other-spirits>

za pomocą skryptu `scripts/scraping/twe_brands.js`, uruchamianego z poziomu zakładki w
przeglądarce. Pobrałem dane z tych stron za pomocą skryptu JS, ponieważ przy skrypcie pythonowym
występowały problemy z CAPTCHĄ. Następnie dane połączyłem w jeden plik za pomocą
`scripts/scraping/merge_csv.py`.

Dodatkowo za pomocą narzędzia PetScan pobrałem dane stron z wikipedii z następujących kategorii
oraz kombinacji kategorii:

- Baijiu i Distilled drink brands
- Brands by country |2 i Baijiu
- Mezcal i Alcoholic beverage brands
- Honey liqueurs and spirits i Alcoholic beverage brands |2
- Wine brands
- Alcoholic beverage brands by company
- Distilled drink brands
- Alcoholic beverage brands
- Champagne producers

Dane stron z PetScan połączyłem w jeden plik po usunięciu duplikatów za pomocą
`scripts/scraping/petscan_merge.py`. PetScan zwraca tylko kod hasła w serwisie WikiData oraz nazwę
hasła, żeby uzupełnić te hasła o potencjalne słowa kluczowe za pomocą
`scripts/scraping/wikidata_keywords.py` pobrałem aliasy, typ, producenta i kraj pochodzenia każdego
hasła. Ze względu na zagnieżdżenia kategorii wikipedii wyniki WikiData zwróciły również strony nie
będące stricte marką alkoholu, za pomocą `scripts/data_manipulation/filtruj_alkohole_wikidata.py` odfiltrowałem
pozycje, których kategorie nie były związane z napojami alkoholowymi (m.in. non-alcoholic beverage,
soft drink) lub były stronami listującymi (m.in. wikimedia list article i list).

Listę marek uzupełniłem danymi ze zbioru danych zawierającego recenzje win pobranego z
<https://github.com/rogerioxavier/X-Wines> oraz zbioru danych zawierającego recenzje piw pobranego
z <https://www.kaggle.com/datasets/rdoume/beerreviews>. Oba zbiory odfiltrowałem, tak żeby zostały
unikalne nazwy kombinacji winiarnia-nazwa wina oraz browar-nazwa piwa, zdekodowałem w nich encje
typograficzne HTML oraz usunąłem zbędne kolumny.

Następnie za pomocą skryptów z folderu `scripts/data_manipulation/` ze wszystkich zebranych danych
przygotowałem główny keyword: w nazwie zamieniłem litery ze znakami diakrytycznymi na odpowiadające
im litery bez takich znaków, zamieniłem odstępy między słowami na znak `-`, dla nazw zawierających
znak `&` stworzyłem dwa warianty keywordu — jeden bez tego znaku, drugi ze słowem `and`.

W niektórych nazwach wódek występowały nazwy w alfabecie łacińskim oraz ich odpowiedniki w
cyrylicy, pobrałem dane z estymatora za pomocą zapytania:

```json
{
   "required": [{"keyword":"-","mode":"c"}]
}
```

następnie za pomocą skryptu `scripts/data_manipulation/analiza_alfabetow_output_json.sh` sprawdziłem czy w
danych występują URL-e w innym alfabecie niż łaciński. Sprawdzenie wykazało, że w URL-ach dominują
znaki łacińskie, skrypt `scripts/data_manipulation/transform_vodka_brands.py` dodatkowo odfiltrował
nazwy w cyrylicy.

Dane pobrane ze stron <https://www.thewhiskyexchange.com> zawierały szczegółowe kategorie (np.
„Blended Malt”, „Japanese Whisky”). Skrypt `scripts/data_manipulation/transform_twe_brands.py`
zmieniał te kategorie na bardziej ogólne „whisky”.

Dane pobrane z WikiData zawierały aliasy dla niektórych danych. Skrypt
`scripts/data_manipulation/transform_alkohole_wikidata.py` poza głównym keywordem tworzył również
warianty keywordu.

W przypadku win rozróżnialną marką jest winiarnia, więc
`scripts/data_manipulation/transform_xwines.py` na jej podstawie tworzy keyword oraz agreguje
optional na podstawie kraju, regionu oraz szczepu winogron z win danej winiarni.

W nazwach piw zastosowałem odwrotną metodę niż w przypadku win. Wyróżniającą nazwą była tutaj nazwa
piwa, a nazwa browaru była wykorzystana jako opcjonalne słowa kluczowe. Do opcjonalnych słów
kluczowych oprócz nazwy browaru zostały dodane słowa opisujące styl piwa oraz słowo „piwo” w różnych
językach.

Po utworzeniu słów kluczowych za pomocą `scripts/data_manipulation/merge_brands_cluster.py`
scaliłem listy alkoholi (z wyjątkiem nazw piw oraz win) do jednego pliku, usunąłem powtarzające się
słowa kluczowe, dodałem warianty słów kluczowych oraz dodałem opcjonalne słowa kluczowe.

Skrypt `scripts/data_manipulation/build_required_queries.py` buduje zapytania dla głównych słów
kluczowych z trybem `required` oraz tworzy plik z wykorzystanymi pozycjami ze zbiorów danych oraz
plik z unikalnymi słowami kluczowymi (uwzględniając również nazwy win oraz piw).

Z przetransformowanych danych utworzyłem ponad 82 tysiące słów kluczowych, żeby uniknąć wysyłania
tak dużej ilości requestów, sprawdziłem keywordy na podstawie lokalnie zapisanych URL-i, które
pobrałem przy sprawdzaniu alfabetów występujących w URL-ach za pomocą
`scripts/data_manipulation/prefilter_output_json.py`.

W lokalnej kopii nie zostały zapisane wszystkie URL-e (2,99 mln z ~3,22 mln URL-i licząc po polach
`sources.sourceN.sampleSize`) dlatego zweryfikowałem trafność sprawdzenia po lokalnej kopii w
`scripts/data_manipulation/kalibracja_local_vs_estymator.py` na próbkach zgrupowanych po ilości
zwróconych URL-i lokalnie. Weryfikacja wykazała, że lokalne wyniki nie różniły się znacząco od
wyników z estymatora.

Następnie w `scripts/data_manipulation/build_queries_with_optional.py` zbudowałem requesty na
podstawie keywordów zwracających URL-e. Odfiltrowując słowa kluczowe bazując na długości, ilości
zwróconych URL-i oraz gdy keyword składał się tylko z ogólnych słów związanych z alkoholami. Przez
zastosowane kryteria filtrowania zostało odrzucone dużo generycznych haseł, ale również kilkanaście
znanych marek, zostały one przywrócone w skrypcie `scripts/data_manipulation/recovery_famous.py`.

Na końcu `scripts/data_manipulation/build_final_json.py` scala zapytania utworzone w
`scripts/data_manipulation/build_queries_with_optional.py` oraz
`scripts/data_manipulation/recovery_famous.py`, zostawia zapytania z unikalnymi słowami kluczowymi w
required oraz nadaje każdemu zapytaniu unikalny id. Po utworzeniu finalnej listy zapytań
`scripts/data_manipulation/confirm_estimator.py` sprawdza utworzone zapytania względem estymatora.
