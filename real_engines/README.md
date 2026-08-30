# Realne dane silników (NASA C-MAPSS FD001) użyte do testów TIMDR-Industrial-Predict

## Źródło

Oryginalny zbiór: **NASA C-MAPSS Turbofan Engine Degradation Simulation
Data Set** (FD001), publicznie udostępniony przez NASA Prognostics Center
of Excellence - dane rządowe, bez restrykcji licencyjnych na same dane.

Plik `train_FD001.txt`, z którego wycięto poniższe silniki, pobrano z
publicznego mirrora na GitHubie:
`https://github.com/LahiruJayasinghe/RUL-Net` (licencja MIT dla kodu
repozytorium - same dane C-MAPSS pochodzą od NASA).

## Pliki

- `cmapss_fd001_unit1_full_192cycles.txt` / `cmapss_unit1_live_192cycles.csv`
  Silnik nr 1, **KOMPLETNY przebieg run-to-failure** (192 cykle, od
  zdrowego stanu do awarii). Plik `.txt` to surowy format C-MAPSS
  (26 kolumn: unit, cycle, 3 ustawienia operacyjne, 21 czujników).
  Plik `.csv` to wersja gotowa do `monitor.py --csv` (kolumna `t` +
  10 czujników uznanych w literaturze za informacyjne dla FD001:
  sensor_2, 3, 4, 7, 11, 12, 15, 17, 20, 21).

- `cmapss_fd001_unit2_partial_85cycles.txt` / `cmapss_unit2_live_85cycles.csv`
  Silnik nr 2, **TYLKO pierwsze 85 cykli** - NIE jest to pełny przebieg
  do awarii (silniki FD001 zwykle żyją 130-360+ cykli). Ograniczenie
  wynika z limitu rozmiaru pojedynczego pobrania strony przez narzędzie
  do pobierania danych, nie z samego zbioru - potraktowany celowo jako
  symulacja "monitoringu na żywo": dokładnie tyle danych, ile miałby
  operator, gdyby ten silnik był aktualnie w eksploatacji i jeszcze nie
  wiadomo, czy/kiedy dojdzie do awarii.

## Do czego posłużyły

Weryfikacja `calibrate()`, `auto_calibrate()`, `calibration_convergence()`
i `validate_window()` (Mann-Kendall) na PRAWDZIWYCH danych silnikowych,
nie tylko syntetycznych - patrz sekcje "Błąd 1"-"Błąd 5" w głównym
`README.md` repozytorium po szczegóły i zmierzone wyniki na obu silnikach.

## Użycie

```
python monitor.py --csv data/real_engines/cmapss_unit1_live_192cycles.csv --auto-calibrate --once
python monitor.py --csv data/real_engines/cmapss_unit2_live_85cycles.csv --auto-calibrate --once
```
