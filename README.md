# Gdansk Waste Collection for Home Assistant

Custom integration do Home Assistanta, ktora pobiera z miejskiego harmonogramu Gdanska najblizsze terminy odbioru odpadow dla konkretnej ulicy i numeru domu.

## Co robi

- dodaje config flow w UI Home Assistanta
- wyszukuje adres po ulicy i numerze domu
- obsluguje wieloznaczne adresy, np. rozne grupy zabudowy
- tworzy sensor z najblizszym odbiorem
- tworzy dodatkowe sensory dla poszczegolnych frakcji odpadow

## Instalacja

1. Skopiuj katalog `custom_components/gdansk_waste` do katalogu `config/custom_components` w Home Assistant.
2. Zrestartuj Home Assistanta.
3. Wejdz w `Ustawienia -> Urzadzenia i uslugi -> Dodaj integracje`.
4. Wyszukaj `Gdansk Waste Collection`.
5. Podaj ulice i numer domu w Gdansku.

## Instalacja przez HACS

Repozytorium zawiera plik `hacs.json`, wiec moze byc dodane jako `Custom repository` typu `Integration`.

Jesli publikujesz to na GitHubie, najlepiej utworz tez normalny release, np. `v0.1.1`. Bez release HACS moze uzyc skrotu ostatniego commita jako wersji, a to bywa problematyczne.

## Sensory

Integracja tworzy:

- sensor `Najblizszy odbior`
- osobne sensory dat dla frakcji takich jak `BIO`, `PAPIER`, `SZKLO`, `RESZTKOWE`, `METALE I TWORZYWA SZTUCZNE`, `WIELKOGABARYTY`

Termin platnosci jest celowo pomijany, bo nie jest odbiorem odpadow.
