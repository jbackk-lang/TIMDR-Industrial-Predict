# TIMDR-Industrial-Predict

Predictive maintenance metodą TIMDR: fuzja wielu czujników maszyny w
jeden sygnał "energii stanu" E(t) (`timdr_industrial_fusion.py`), plus
predykcja czasu do awarii i health-score (`timdr_industrial_predict.py`),
plus dispatcher priorytetyzujący te wyniki w jedno zdarzenie
(`timdr_industrial_trigger.py`), plus lokalny dashboard z REST API
(`api.py` + `static/dashboard.html`), uruchamiany jednym kliknięciem
przez `run.bat`.

## 🚨 `timdr_industrial_trigger.py` — jedno priorytetyzowane zdarzenie

Dispatcher NIE liczy własnej statystyki - tylko woła już przetestowane
`TIMDRIndustrialFusion.twist()`/`anomalies()` i
`TIMDRIndustrialPredict.predict_failure()` i mapuje ich łączny wynik na
jedno zdarzenie (typ + lokalizacja + komunikat), według priorytetu:

**FAILURE_IMMINENT** (przewidywany TTF ≤ `alert_ttf_seconds`, domyślnie
3600s — najbardziej actionable, explicit prognoza przyszłości) >
**STRUCTURE** (`twist` — nagła zmiana energii stanu E(t)) > **ANOMALY**
(pojedyncza statystyczna anomalia w E(t)) > **NONE**.

```python
from timdr_industrial_trigger import IndustrialTrigger

trigger = IndustrialTrigger(alert_ttf_seconds=3600.0)
result = trigger.analyze(t, E, threshold=60.0, window=60)
print(result.as_dict())
# {'triggered': True, 'type': 'anomaly', 'location': 5, 'message': '...'}
```

`twist()`/`anomalies()` mają własne, zakodowane na stałe progi (3.5 /
3.0 odchylenia MAD) — dispatcher świadomie NIE udaje, że może je
przestawić parametrem konstruktora, bo takiego parametru nie da się
faktycznie wpiąć w te metody (martwy parametr — błąd znaleziony
wcześniej w `TIMDR-Security-Module`). Wpięty w `/api/analyze` (pole
`"trigger"` w odpowiedzi JSON) i w dashboardzie (karta "Trigger").

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
| `/api/analyze` | POST | pełna analiza: `{t, sensors, threshold, window}` → JSON z E(t), twist/trend/anomalie/rytm, TTF, health_score, trigger |

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

81/81 testów (`pytest -q`, w tym 13 dla nowego `bearing_meta_adapter.py` -
patrz sekcja "Integracja z TIMDR-META-DYNAMICS" niżej).
Znalezione i naprawione: 3 błędy w
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

from timdr_industrial_trigger import IndustrialTrigger
trigger_result = IndustrialTrigger().analyze(t, E, threshold=60.0)
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

## Integracja z TIMDR-META-DYNAMICS (eksperymentalna) — wibracja łożysk

`bearing_meta_adapter.py` mapuje sygnał wibracji łożyska (akcelerometr) na
`MetaState(Λ,τ,ρ,J)` z repozytorium-siostry `TIMDR-META-DYNAMICS` —
czwarta realna integracja tego formalizmu w ekosystemie (pierwsza:
finansowa w `analizator-gieldowy-v3`, druga: pogodowa w `Synoptyk-v3`,
trzecia: sejsmiczna w `TIMDR-Earthquake-Core`, którego `flow()`/`trm()`
ten adapter **importuje jako sibling** zamiast duplikować — te funkcje są
domenowo-niezależne, zweryfikowane raz przeciw ObsPy w kontekście
sejsmicznym).

**Dane**: [CWRU Bearing Dataset](https://engineering.case.edu/bearingdatacenter)
(Case Western Reserve University), mirror w formacie `.npz`
[`srigas/CWRU_Bearing_NumPy`](https://github.com/srigas/CWRU_Bearing_NumPy)
— 1797 RPM, kanał DE, 12 kHz, jedno zdrowe łożysko + trzy typy uszkodzeń
0.021" (bieżnia wewnętrzna IR, bieżnia zewnętrzna OR@6, element toczny B).
Pobrane w sesji interaktywnej przez przeglądarkę (`fetch`+`JSZip`,
konwersja `.npz→tablice` w JS) — **bash tego środowiska ma zablokowany
dostęp do `raw.githubusercontent.com`** (`403 blocked-by-allowlist`,
zweryfikowane), więc pełne nagrania (10-20s każde) nie mogły zostać
automatycznie ściągnięte do repo. `data/cwru_bearing/*.csv` zawiera tylko
pierwsze 1536 próbek (0.128s) z każdego nagrania — wystarczające do testu
end-to-end/kształtu, **nie** do odtworzenia pełnej analizy statystycznej
poniżej (która użyła całych nagrań); pełne pliki można pobrać samodzielnie
pod wskazanym adresem.

**Cztery próby, trzy nieudane — pełna historia w docstringu modułu**:

1. Dane zdecymowane do 500 Hz (żeby dało się przesłać przez wąski kanał
   przeglądarka→sandbox), Λ = pół widma na pół (jak w
   `TIMDR-Earthquake-Core`): **zero sensownej dyskryminacji** — łożysko z
   uszkodzeniem elementu tocznego wyszło SPOKOJNIEJSZE niż zdrowe (ρ=0,
   J=0), odwrotnie niż oczekiwane. Przyczyna: decymacja boxcar /24 to
   prymitywny filtr antyaliasingowy z zerami dokładnie na wielokrotnościach
   500 Hz, który różnie tłumi różne typy usterek.
2. Pełna rozdzielczość natywna 12 kHz (bez decymacji), wciąż Λ = pół na
   pół: naprawiło problem z elementem tocznym (ρ/τ/J teraz sensownie
   podwyższone u wszystkich trzech typów uszkodzeń), ale operator M
   (pochodna stanu) rzadko dawał fazę „krytyczna” — bo M mierzy ZMIANĘ
   między oknami, a uszkodzenie łożyska to stan STAŁY przez cały zapis
   (w przeciwieństwie do mainshocku trzęsienia ziemi, który jest
   prawdziwym przejściem w środku ciągłego zapisu).
3. Kurtoza widmowa (jeden poziom rozdzielczości, 4096 próbek): **szum, nie
   sygnał** — za mało niezależnych ramek (29-59) na tak wąskie pasmo (2.93
   Hz/bin). Piki niespójne między typami usterek (jeden na granicy
   Nyquista, jeden blisko DC — artefakty numeryczne).
4. Wielopoziomowy "kurtogram" (STFT, 7 długości okna 64-4096 próbek,
   różnica SK(uszkodzenie)−SK(zdrowe)): dalej niespójne (piki: 5625 Hz,
   6000 Hz — znów granica Nyquista, 12 Hz — znów blisko DC). Prawdziwy
   Fast Kurtogram (Antoniego) wymaga starannego banku filtrów
   rekurencyjnych — to przybliżenie przez STFT nie wystarczyło.

**Znalezisko końcowe (użyte w kodzie)**: prosta moc pasmowa względem
REALNEJ zdrowej referencji — uśrednione widmo mocy (FFT na oknach 4096
próbek, natywne 12 kHz) podzielone na 12 pasm co ~500 Hz, porównane
uszkodzenie/zdrowe pasmo-po-paśmie. W paśmie **~2.5-4 kHz** stosunek
wynosi: IR21 ≈ 32 600× i 34 400×, OR@6_21 ≈ 28 150×, 33 700× i 90 000×,
B21 ≈ 620× i 3 640× (słabiej, ale ten sam wzorzec pasmowy) — klasyczny
sygnał rezonansu strukturalnego obudowy łożyska wzbudzanego uderzeniami
(to, co w prawdziwej diagnostyce łożysk wyciąga się metodą
obwiedni/spectral kurtosis — tu znalezione prostszym narzędziem, bo
akurat była dostępna prawdziwa zdrowa referencja, silniejszy punkt
odniesienia niż ślepa kurtoza). `RESONANCE_BAND_HZ=(2500,4000)` w kodzie
jest tym stałym, **empirycznym** pasmem — nie wykrywanym automatycznie
per-maszynę (próbowano, patrz próby 3/4 wyżej, nie udało się w tej sesji).

**Dwie ścieżki zamiast jednej**: w przeciwieństwie do adaptera
sejsmicznego (jeden ciągły ślad, próg liczony z wcześniejszej/całej jego
części), łożysko nie ma „spokojnego okresu przed zdarzeniem” wewnątrz
jednego zapisu — to reżim stały. `build_meta_series_from_reference_and_test()`
liczy progi τ/ρ/J z osobnego REFERENCYJNEGO (zdrowego) nagrania, a Λ
(pasmo rezonansu) osobno, samo-znormalizowane — dopiero
`MetaOperatorM.magnitude()` z `TIMDR-META-DYNAMICS` (niezmieniony) sumuje
obie ścieżki w jeden stan. Koncepcyjnie odpowiada to temu, jak GIA-TIMDR
formalnie rozdziela gałęzie tego samego formalizmu na odrębne obiekty
(patrz skill `timdr-signal-framework`, Axioms_S vs Axioms_G vs Axioms_K) —
tu „stan względem referencji” i „energia w paśmie rezonansu” jako trzecia,
niezależnie liczona wielkość. To pozostaje **otwartym wątkiem
koncepcyjnym** (jak niedomknięte G4/G7 w `Axioms_G_TIMDR_Geometry.md`) —
żaden nowy aksjomat nie został tu dopisany, to tylko użycie istniejącego
trójkąta Λ-τ-ρ-J, nie jego formalne rozszerzenie.

**Doprecyzowanie „stan vs przejście”** (kluczowa różnica między tym
adapterem a adapterem sejsmicznym, warta nazwania wprost, nie tylko
wywnioskowania z kodu): **w domenie przemysłowej TIMDR nie wykrywa
przejścia reżimu w czasie, lecz klasyfikuje stan względem referencyjnego
zdrowego profilu.** W sejsmice mainshock jest przejściem W ŚRODKU jednego
ciągłego zapisu (spokój → zdarzenie → powrót), więc kalibracja progu z
wcześniejszej części TEGO SAMEGO śladu ma sens. Uszkodzenie łożyska jest
stanem stałym od pierwszej do ostatniej próbki nagrania testowego — nie
ma tam „spokojnego okresu przed zdarzeniem” do wykorzystania, dlatego
architektura jest inna: dwa OSOBNE nagrania (referencyjne zdrowe + testowe),
nie jedno kalibrowane wewnętrznie.

Dwie dalsze konsekwencje tego rozróżnienia, na razie świadomie nie
rozwiązane (nie blokują obecnego, zwalidowanego rozwiązania — patrz
wynik niżej):

- **Progi referencyjne są per-konfiguracja, nie globalne.** Obecne progi
  τ/ρ/J i pasmo rezonansu `RESONANCE_BAND_HZ=(2500, 4000)` są
  wyliczone/dobrane dla 1797 RPM, kanału DE (Drive End), tego jednego typu
  łożyska. Inna prędkość obrotowa, inny kanał (FE/BA) albo inny typ
  łożyska prawdopodobnie przesunie zarówno progi, jak i pasmo rezonansu —
  potrzebne byłoby coś w rodzaju `reference_profile[rpm][channel]` zamiast
  jednego zestawu stałych globalnych. Nie zaimplementowane teraz — tylko
  odnotowane jako miejsce do rozbudowy, gdy pojawią się dane z innej
  konfiguracji.
- **`k_neighbors=8` (domyślne `TIMDR_EarthquakeCore`) jest dobrane pod
  sejsmikę, nie pod sygnał maszynowy.** Działa tu bez zmian, bo obecne
  rozwiązanie używa Λ wyłącznie z pasma rezonansu (uśrednione widmo mocy
  całego okna), nie z `flow()`/`trm()` per-próbka. Gdyby w przyszłości
  wrócić do lokalnych anomalii/impulsów IR/OR/B na poziomie próbek (patrz
  próby 1-2 wyżej), `k_neighbors=8` przy natywnych 12 kHz obejmuje ~0.58ms
  — krócej niż okres uderzenia (~7-9ms), więc technicznie poprawne, ale
  warto pamiętać, że przy innej częstotliwości próbkowania to samo `k=8`
  może znów objąć wielokrotność okresu uderzenia (patrz analogiczny
  problem z decymacją 500Hz w próbie 1) — wartość 2-4 byłaby bezpieczniejszym
  punktem wyjścia do takiego rozszerzenia, nie 8.

**Wynik na realnych danych (fixture 0.128s, 4 okna po 384 próbki)**:
zdrowe łożysko porównane samo ze sobą daje ρ=0; wszystkie trzy typy
uszkodzeń dają WYŻSZE ρ i Λ niż zdrowa referencja (IR21: ρ=0.668,
Λ=0.907; OR@6_21: ρ=0.438, Λ=0.867; B21: ρ=0.220, Λ=0.824 — dla
porównania zdrowe: ρ=0.000, Λ=0.002) — a kontrast Λ jest na tyle
ekstremalny, że nawet operator M (pochodna, zaprojektowany do wykrywania
przejść, nie reżimów stałych — patrz próba 2) wychodzi „krytyczna” na
każdym oknie testowym z usterką. To własność SKALI tego konkretnego
kontrastu, nie gwarancja — przy słabszym/wczesnym uszkodzeniu sam stan
(`states`) może dyskryminować, zanim zrobi to jego pochodna (`phases`).

Test: `test_bearing_meta_adapter.py` (13 testów: kontrole syntetyczne
pozytywna/negatywna, walidacja wejścia, kształt wzorów, oraz 5 testów na
realnych danych CWRU — negatywna kontrola zdrowe-vs-samo-siebie,
pozytywna kontrola dla każdego z 3 typów usterek, end-to-end).

## Uwaga o stanie tego lokalnego repo (2026-09-08)

Ten folder lokalny nie miał `.git` (był zwykłym, niewersjonowanym
katalogiem) i był STARSZĄ migawką niż `origin/main` na GitHubie — brakowało
`HISTORIA_BLEDOW.md`, `LICENSE`, `monitor.py`, `obd_source.py`,
`real_engines/` oraz nowszych wersji `timdr_industrial_fusion.py`/
`timdr_industrial_predict.py`/testów (m.in. `calibrate()`/
`predict_failure_smoothed()` - patrz `HISTORIA_BLEDOW.md`). Naprawiono
przez `git init` + `git remote add origin` + zsynchronizowanie working
tree z `origin/main` (`git checkout origin/main -- .`) PRZED dopisaniem
tego adaptera, żeby nie nadpisać nowszej pracy starszą kopią.

Przy okazji znaleziono i naprawiono jeden dodatkowy błąd: `real_engines/`
było scommitowane na złym poziomie katalogów (root repo), podczas gdy
`demo_scenarios.py` (`DATA_DIR`) i `real_engines/README.md` (własny tekst:
"patrz data/real_engines/README.md") jednoznacznie zakładają
`data/real_engines/` — dwa testy (`real_engine_1_full`,
`real_engine_2_live`) faktycznie failowały z `FileNotFoundError` przed tą
poprawką. Przeniesiono folder na właściwe miejsce.
