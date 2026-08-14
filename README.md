# TIMDR-Industrial-Predict

Predictive maintenance metodą TIMDR: fuzja wielu czujników maszyny w
jeden sygnał "energii stanu" E(t) (`timdr_industrial_fusion.py`), plus
predykcja czasu do awarii i health-score (`timdr_industrial_predict.py`),
plus lokalny dashboard z REST API (`api.py` + `static/dashboard.html`),
uruchamiany jednym kliknięciem przez `run.bat`.

## 🖥️ Dashboard + API

![Dashboard - odpowiedź API z pełną analizą](screenshot_dashboard_api.png)

Uruchomienie: `run.bat` (Windows, instaluje zależności i otwiera
przeglądarkę) albo ręcznie `python api.py` + wejście na
`http://127.0.0.1:5000`. Wszystko działa lokalnie - żadne dane nie
opuszczają komputera.

- **Karty stanu**: health-score (z paskiem, kolor zależny od progu
  0.3/0.6), time-to-failure, fusion-score, liczba anomalii/twistów,
  wykryty rytm.
- **Wykres E(t)** z linią progu awarii i zaznaczonymi anomaliami/twistami.
- **Wykres trendu** (nachylenie E w oknie kroczącym).
- **Wykresy surowych czujników** (siatka, po jednym na czujnik).
- **Wybór scenariusza demo** (dropdown) - 5 gotowych, zweryfikowanych
  syntetycznych awarii (patrz niżej), próg `threshold` ustawia się
  automatycznie na wartość sugerowaną dla wybranego scenariusza.
- **📄 Wczytaj CSV** - podłączenie własnych danych (nie tylko demo):
  plik z nagłówkiem, kolumna czasu (domyślnie `t`, konfigurowalna w
  polu obok przycisku) + dowolna liczba kolumn numerycznych jako
  czujniki. Bez kolumny czasu o podanej nazwie używany jest indeks
  wiersza.
- Przyciski: wczytaj dane demo / wczytaj CSV / uruchom analizę, pola
  `threshold`/`window`/nazwa kolumny czasu.

### 🐛 Poprawka: wykresy (w tym czujniki) nie pokazywały się w ogóle

Pierwsza wersja dashboardu ładowała Chart.js z zewnętrznego CDN
(`cdnjs.cloudflare.com`). Jeśli przeglądarka nie ma dostępu do tego
akurat adresu (firewall firmowy, offline, DNS/proxy) - CDN nie ładuje
się CICHO, `Chart` zostaje niezdefiniowane, i **wszystkie** wykresy
(nie tylko czujniki - też E(t), trend, a nawet reszta inicjalizacji
strony) przestają działać bez żadnego widocznego komunikatu w UI
(błąd trafia tylko do konsoli deweloperskiej przeglądarki). Zweryfikowano
wprost w tym środowisku: próba pobrania tego samego pliku z CDN
zablokowana przez proxy sandboxa - dokładnie ten typ awarii sieciowej,
na który dashboard był podatny.

Naprawiono przez usunięcie zależności od CDN całkowicie: wykresy
rysowane są własnym, ok. 100-liniowym silnikiem opartym o `<canvas>` i
2D Context API (funkcja `drawChart()` w `dashboard.html`) - zero
zależności zewnętrznych, więc strona działa identycznie z internetem i
bez niego. Dodatkowo każdy krok inicjalizacji (`loadScenarios`,
`loadDemo`, `runAnalyze`) ma teraz `.catch()`, który wyświetla błąd w
widocznym polu `#err` zamiast cichego `Uncaught (in promise)` w
konsoli - jeśli coś pójdzie nie tak, będzie to widoczne na stronie, nie
tylko w devtools.

Zweryfikowano: (1) `node --check` - składnia, (2) uruchomienie
faktycznej logiki `drawChart()`/`parseCsv()` w Node z podstawionym
fałszywym `canvas`/`document` (7 przypadków: normalny sygnał, puste
dane, seria z markerami anomalii/twist + progiem, wartości
null/NaN/Infinity, pojedynczy punkt, wąski kontener, błędny CSV) - żaden
nie rzuca wyjątku, (3) porównanie wszystkich `getElementById()` w JS z
`id=` w HTML - brak rozbieżności, (4) `grep` po `http`/`https` w
`dashboard.html` - zero zewnętrznych adresów URL.

### 🎲 5 scenariuszy demo (`demo_scenarios.py`)

Zamiast jednego generycznego zestawu danych - 5 syntetycznych awarii
odpowiadających "Co wykrywa TIMDR-Industrial-Fusion w praktyce" z
oryginalnego zgłoszenia, każdy **zweryfikowany empirycznie**, że
faktycznie uruchamia deklarowany detektor (nie tylko założony -
sprawdzony pełnym pipeline'em Fusion+Predict, `test_demo_scenarios.py`):

| Scenariusz | Pokazuje | Czujniki |
|---|---|---|
| `bearing_wear` | trend + TTF w przód | temp, vib, pressure, current |
| `pump_seizure` | nagły twist/anomalia + trend po zdarzeniu | temp, vib, pressure, current |
| `uneven_motor_rotation` | rytm (okres 12) + odosobnione skoki | current, vibration |
| `resonance_loose_parts` | rytm (okres 20) + twist na każdym uderzeniu | temp, vib, pressure, current |
| `duty_cycle_problems` | rytm (okres 30) + anomalia + trend w drugiej połowie | current, pressure |

Po drodze znaleziono i skorygowano 3 nieoczywiste właściwości fuzji
wielu czujników (nie błędy w kodzie - właściwości samej metody
median/MAD, warte znajomości przy projektowaniu własnych scenariuszy):

1. **Rozcieńczanie rytmu przez niezwiązane czujniki**: `_mad_z()`
   normalizuje każdą cechę do porównywalnej skali - to dobra poprawka
   przeciw dominacji skali, ale oznacza, że czysto szumowy, niezwiązany
   z badanym zjawiskiem czujnik wnosi do E(t) TYLE SAMO znormalizowanej
   "energii" co prawdziwy sygnał okresowy. Zweryfikowano: dodanie 2
   niezwiązanych czujników (szum) do sygnału z czystą periodycznością
   zmniejszało `rhythm_score` z 0.73 do 0.24 (poniżej progu 0.4).
   Rozwiązanie: fuzuj czujniki fizycznie związane z badanym zjawiskiem.
2. **Ekstremalne odstające punkty niszczą wykrywalność rytmu**:
   znormalizowana autokorelacja nie jest odporna na pojedyncze,
   bardzo duże wartości odstające (dominują wariancję w mianowniku) -
   zbyt duży/szeroki skok "awarii" potrafił zrzucić `rhythm_score` z
   ~0.8 do 0.0, mimo niezmienionej periodyczności reszty sygnału.
3. **Powolny dryf bazowy ginie w lokalnej zmienności**: `_mad_z()`
   mierzy odległość od GLOBALNEJ (nie ruchomej) mediany - dryf słabszy
   niż lokalne wahania cyklu (np. duty-cycle) może zostać "wchłonięty"
   i nie być widoczny jako trend w ogóle, nawet gdy realnie rośnie.

### Endpointy API

| Endpoint | Metoda | Opis |
|---|---|---|
| `/` | GET | dashboard (HTML) |
| `/api/health` | GET | healthcheck samego API |
| `/api/scenarios` | GET | lista 5 scenariuszy demo (nazwa, opis, sugerowany próg) |
| `/api/demo` | GET | syntetyczny zestaw czujników (`?scenario=<nazwa>`, domyślnie `bearing_wear`) |
| `/api/analyze` | POST | pełna analiza: `{t, sensors, threshold, window}` → JSON z E(t), twist/trend/anomalie/rytm, TTF, health_score |

`/api/analyze` przyjmuje czujniki o **różnej długości** (korzysta z
`_align()` w Fusion) i zwraca czytelny błąd (HTTP 400 + opis) zamiast
500 przy brakujących/pustych danych - zweryfikowane bezpośrednio przez
prawdziwe zapytania HTTP (curl), nie tylko czytanie kodu:

```
POST /api/analyze {}                          -> 400 "wymagane pola: 't' i 'sensors'"
POST /api/analyze {"t":[],"sensors":{"x":[]}}  -> 400 "t i sensors nie moga byc puste"
POST /api/analyze <dane demo>                  -> 200, health_score=0.385, ttf=5.2s, fusion_score=40.93
```

**Uczciwe zastrzeżenie**: w tym środowisku (piaskownica bez
przeglądarki/wyświetlacza) nadal nie da się dosłownie zobaczyć
wyrenderowanych pikseli - ale zamiast tylko czytania kodu,
zweryfikowałem: (1) całe API prawdziwymi zapytaniami HTTP z serwerem
faktycznie uruchomionym, (2) składnię JS (`node --check`), (3)
FAKTYCZNE WYKONANIE logiki rysującej wykresy (`drawChart`, `parseCsv`)
w Node z podstawionym fałszywym `canvas`/DOM, na 7 przypadkach
brzegowych (patrz sekcja o poprawce CDN wyżej) - żaden nie rzucił
wyjątku, (4) zgodność wszystkich `getElementById()` z `id=` w HTML,
(5) brak jakichkolwiek zewnętrznych adresów URL na stronie. To
najsurowsza weryfikacja frontendu, jaką dało się zrobić bez realnej
przeglądarki. Jeśli mimo to coś w przeglądarce wygląda nie tak, daj
znać ze szczegółami/zrzutem ekranu - poprawię.

## Status

25/25 testów (`pytest -q`). Znalezione i naprawione: 3 błędy w
`timdr_industrial_fusion.py` (w tym jeden mylący trend z rytmem - a
trend to główny sygnał, który to narzędzie ma wykrywać) i 3 błędy w
`timdr_industrial_predict.py`, w tym jeden krytyczny (TTF zależne od
bezwzględnego znacznika czasu zamiast od faktycznej dynamiki).

## 🐛 Błędy w `timdr_industrial_fusion.py`

### 1. `rhythm()` myli trend z periodycznością

Oryginalny kod tylko odejmował średnią i zgłaszał **każdy** lag powyżej
progu, nie tylko lokalne maksima autokorelacji. Zweryfikowano: czysty
rosnący trend (zero periodyczności, z realistycznym szumem czujnika)
dawał `rhythm_score≈0.99` i **48 "wykrytych okresów"** - dokładnie to,
czego ten moduł ma NIE robić, bo trend to główny sygnał degradacji, nie
szum do zignorowania. Naprawiono: pełny detrend (nachylenie + wyraz
wolny) przed autokorelacją + zgłaszanie tylko lokalnych maksimów.
Zweryfikowano też, że prawdziwa okresowość (okres 15) nałożona na silny
trend nadal poprawnie wychodzi po poprawce.

### 2. Krótkie sygnały (n<2) crashowały `twist()`/`rhythm()`

`np.gradient` wywoływany bez ochrony na sygnałach 0-1-elementowych
dawał `IndexError`. Naprawiono zgodnie ze standardem reszty modułów
TIMDR w tym zestawie repozytoriów.

### 3. `fusion_score()` na pustych tablicach

`np.max([])` rzuca `ValueError` - może się zdarzyć dla bardzo krótkich
sygnałów po poprawce #2. Naprawiono (`safe_max`).

## 🐛 Błędy w `timdr_industrial_predict.py`

### 1. TTF zwracane jako współrzędna czasu, nie czas pozostały (najpoważniejszy błąd)

Oryginalny kod zwracał `(threshold - b) / a` wprost - czyli punkt na
osi `t`, w którym model przewiduje przekroczenie progu, **nie**
odejmując bieżącego czasu. Zweryfikowano wprost: przesunięcie całego
`t` o +1000s (fizycznie identyczna sytuacja maszyny) zmieniało zwrócone
"TTF" też dokładnie o +1000s. Z realnymi znacznikami epoch (~1.75
miliarda) dawało to **"czas do awarii: ~330 lat"** zamiast realnej
wartości. Naprawiono: TTF liczone jest jako różnica względem ostatniej
próbki (`t[-1]`), w tej samej, wycentrowanej skali co dopasowanie
regresji (patrz błąd #3 niżej).

### 2. TTF zależne 16-krotnie od długości historii danych, nie od stanu maszyny

Regresja (liniowa i wykładnicza) liczona była na CAŁEJ historii E(t) od
`t=0`. Zweryfikowano: dla FIZYCZNIE IDENTYCZNEJ ostatniej fazy
degradacji (te same 100 próbek), ale różnej długości wcześniejszej
zdrowej historii, przewidywany TTF wychodził:

| długość zdrowej historii | TTF |
|---|---|
| 50s | 135s |
| 150s | 273s |
| 400s | 818s |
| 800s | 2254s |

16-krotna różnica dla tej samej aktualnej sytuacji maszyny. Naprawiono:
regresja liczona tylko na ostatnich `window` próbkach (domyślnie 60).
Po poprawce te same 4 warianty dają wynik w zakresie 42.6-43.0s -
zbieżność, nie rozjazd rzędów wielkości.

### 3. Niestabilność numeryczna regresji przy realnych znacznikach czasu

Nawet po poprawce #2, `lstsq` na surowych wartościach `t` (kolumna `[t,
1]`) jest źle uwarunkowane dla dużych, przesuniętych wartości czasu
(epoch, rząd 1e9) - kolumny różnią się o ~9 rzędów wielkości. Naprawiono:
`t` jest centrowane (`t - t[0]` okna) przed dopasowaniem.

### 4. `health_score()` permanentnie zatruty starym zdarzeniem

Oryginalny kod liczył z-score E względem WŁASNEJ CAŁEJ historii i brał
`max()` po wszystkim - jeden stary, jednorazowy skok (np. chwilowe
zakłócenie czujnika) blokował wynik na zawsze. Zweryfikowano: 500 próbek,
jednorazowy skok w próbce 50, reszta (450 próbek = 90% danych) w normie
→ `health_score=0.000` (permanentnie "krytyczny"), mimo że maszyna od
dawna pracuje normalnie. Dodatkowy problem: skala health_score (z-score
własnej historii /5) nie miała żadnego związku z `threshold` używanym w
`predict_failure()` - "krytyczny" w obu miejscach mogło oznaczać zupełnie
różne wartości E. Naprawiono: health_score liczy medianę z ostatnich
`window` próbek (domyślnie 20) względem TEGO SAMEGO `threshold`, co
`predict_failure()`.

## ✅ Co było już poprawnie zaprojektowane (bez zmian)

- `fuse()`: normalizacja każdej cechy (median/MAD) przed połączeniem w
  normę - unika błędu "dominacji skali" znalezionego wcześniej w innych
  modułach tej rodziny (`timdr_security.py`, `timdr_rhythm.py`).
- `twist()`: `np.gradient(E, t)` z realnym `t`, nie po indeksie.
- `_mad_z()`: median/MAD zamiast mean/std - odporne na to, że pojedyncza
  anomalia zawyży własny próg detekcji (sprawdzone empirycznie).
- Podstawowy szkielet autokorelacji w `rhythm()` (korekta malejącego
  okna nakładania przez dzielenie przez `n-lag`) - ta sama poprawna
  technika, którą wprowadziliśmy wcześniej w `TIMDR-Security-Module/timdr_rhythm.py`.

## 📦 Nowe repo?

Tak - to osobna domena (predictive maintenance dla maszyn przemysłowych:
łożyska, pompy, silniki, wibracje/temperatura/ciśnienie/prąd), odrębna
od istniejących repozytoriów (Radar, Flight-Tracking, Security,
Echosonda, Earthquake). Oba moduły (`Fusion` + `Predict`) trzymane
razem w jednym repo, bo `Predict` bezpośrednio zależy od wyjścia
`Fusion` (energii stanu E(t)) i zawsze są używane razem, jak pokazuje
przykład użycia poniżej.

## Przykład użycia

```python
from timdr_industrial_fusion import TIMDRIndustrialFusion
from timdr_industrial_predict import TIMDRIndustrialPredict

fusion = TIMDRIndustrialFusion()
predict = TIMDRIndustrialPredict()

E, Z = fusion.fuse(t, [temperature_signal, vibration_signal, pressure_signal, current_signal])

tw_idx, tw_z = fusion.twist(t, E)
tr_sl, tr_z = fusion.trend(t, E)
an_idx, an_z = fusion.anomalies(E)
periods, r_score = fusion.rhythm(E)
score = fusion.fusion_score(tw_z, tr_z, an_z, r_score)

ttf, ttf_lin, ttf_exp = predict.predict_failure(t, E, threshold=60.0)
health = predict.health_score(E, threshold=60.0)
```

![Fuzja czujników + predykcja TTF](screenshot_industrial_predict.png)

## 🎯 Zastosowania i warunki

- **Zużycie łożysk / zatarcie pompy / nierówne obroty**: działa jak
  opisano w oryginalnym zgłoszeniu - `trend` na powolną degradację,
  `twist` na pierwsze "uderzenia", `anomalies` na skoki, `rhythm` (po
  poprawce) na prawdziwe cykliczne wzorce, nie na sam trend.
- **`threshold` musi być spójny między `predict_failure()` i
  `health_score()`** - oba teraz go współdzielą, ale to WY wybieracie
  wartość odpowiednią dla Waszej maszyny (E to znormalizowana,
  bezwymiarowa "odległość od normy", nie fizyczna jednostka).
- **`window` w `predict_failure()`/`degradation_model()` (domyślnie 60)
  musi pasować do dynamiki Waszej maszyny i częstotliwości próbkowania**
  - za krótkie okno = wrażliwość na szum, za długie = powrót do
    oryginalnego błędu (TTF rozwodnione przez starą historię).
- **Model wykładniczy jest bardziej pesymistyczny niż liniowy** przy
  typowych profilach degradacji (zweryfikowane na przykładach w tym
  README) - `predict_failure()` domyślnie bierze bardziej pesymistyczny
  z obu (`min()`), nie "bardziej stabilny" (żadna z metod nie mierzy
  stabilności) - ostrzega wcześniej kosztem większej liczby fałszywych
  alarmów. Jeśli wolisz mniej czułe ostrzeżenia, użyj `ttf_linear`
  bezpośrednio zamiast `ttf`.
- Metoda nie jest przyczynowa (`np.gradient` w punktach wewnętrznych) -
  do strumienia na żywo nadaje się z jednopróbkowym opóźnieniem.

Uruchomienie: `python demo.py` / testy: `pytest -q`.
