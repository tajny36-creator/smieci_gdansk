# Gdansk Waste Collection for Home Assistant

Integracja Home Assistant pokazujaca najblizsze odbiory smieci dla konkretnego adresu w Gdansku. Dane sa pobierane z miejskiego harmonogramu odpadow.

## Co dostajesz

- konfiguracje z poziomu UI Home Assistanta
- wyszukiwanie po ulicy i numerze domu
- obsluge niejednoznacznych adresow, np. roznych grup zabudowy
- sensor z najblizszym odbiorem
- dodatkowe sensory dla kazdej frakcji odpadow

## Instalacja przez HACS

1. Utworz na GitHubie nowe repozytorium, najlepiej `ha-gdansk-waste`.
2. Wrzuc do niego cala zawartosc tego folderu.
3. Utworz GitHub Release o nazwie i tagu `v1.0.3`.
4. W HACS dodaj repo jako `Custom repository` typu `Integration`.
5. Zainstaluj release `v1.0.3`, a nie sam commit z galezi.

## Instalacja reczna

1. Skopiuj katalog `custom_components/gdansk_waste` do `config/custom_components` w Home Assistant.
2. Zrestartuj Home Assistanta.
3. Wejdz w `Ustawienia -> Urzadzenia i uslugi -> Dodaj integracje`.
4. Wyszukaj `Gdansk Waste Collection`.

## Sensory

Integracja tworzy:

- sensor `Najblizszy odbior`
- osobne sensory dat dla frakcji takich jak `BIO`, `PAPIER`, `SZKLO`, `RESZTKOWE`, `METALE I TWORZYWA SZTUCZNE`, `WIELKOGABARYTY`

Termin `TERMINY PLATNOSCI` jest pomijany, bo nie dotyczy odbioru odpadow.

## Po wrzuceniu na GitHub

Jesli Twoj login GitHub albo nazwa repo beda inne niz `WERTJ/ha-gdansk-waste`, zaktualizuj pola `documentation`, `issue_tracker` i `codeowners` w pliku `custom_components/gdansk_waste/manifest.json`.
