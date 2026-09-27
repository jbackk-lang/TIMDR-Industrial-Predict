# Sito rezonansowe — diagnostyka łożyska według drogowskazów TIMDR

`bearing_resonance_sieve.py` rozpoznaje uszkodzenie bieżni zewnętrznej (BPFO) i wewnętrznej (BPFI) z drgań i mówi,
**dlaczego**: które pasma nośne przepuściło sito i przy jakiej częstotliwości modulacji.

```
python bearing_resonance_sieve.py analyze nagranie.npz --fs 64000 --rpm 1500 --bearing 6203 --channel DE
```

Wejście: `.npz` (kanał `--channel`), `.npy` albo `.csv` z jedną kolumną; co najmniej 2 s sygnału.
Wyjście (JSON): dla każdej hipotezy uszkodzenia wynik `score`, entropia oczek sita, 3 najsilniej przepuszczone pasma
i ich wagi, oraz `strongest` — hipoteza z najwyższym wynikiem.

## Jak działa (idea: membrana = pole, rezonans ustala oczka sita)

1. **Pole** — sygnał rozłożony na pasma nośne po 1 kHz (1–16 kHz; przy niższym próbkowaniu do połowy fs),
   w każdym paśmie obwiednia analityczna.
2. **Mapa rezonansu** — widmo obwiedni każdego pasma (modulacje 5–500 Hz), znormalizowane tak, że tło = 1.
3. **Sito samokorygujące** — dla każdej hipotezy (BPFO, BPFI) oczka sita ustawia sam rezonans: pasmo dostaje wagę
   proporcjonalną do tego, jak mocno rezonuje przy częstotliwości tego uszkodzenia. Przesiane widmo daje wynik
   `score = log(szczyt przy 1× + szczyt przy 2×)`.

## Co jest sprawdzone

- **Walidacja pre-rejestrowana** (GIA-TIMDR, `docs/geometry/RESULT_PADERBORN_RESONANCE_SIEVE_*.md`): łożyska Paderborn
  z uszkodzeniami naturalnymi, 15 łożysk, test zawsze na łożyskach spoza uczenia. Cechy sita z prostym klasyfikatorem:
  0,68 i 0,65 (macro-F1, 3 klasy) wobec 0,56 klasycznych cech, 0,61 widma obwiedni i 0,55 kurtogramu. Przewaga nad
  klasycznymi i kurtogramem potwierdzona; nad samą obwiednią dodatnia, ale w replikacji poniżej progu.
- **Trzecia próba (pomiary 16–20):** 0,65; łącznie 15 foldów: vs klasyczne +0,08 w 12/15 (SUPPORTED), vs obwiednia
  +0,04 w 10/15 (poniżej progu 0,05 — nie ogłaszamy).
- **Zgodność z wersją walidowaną** — test wzorcowy w `test_bearing_resonance_sieve.py` (identyczne liczby).
- **CWRU (1797 RPM, dane w repo)** — nagranie z uszkodzeniem wewnętrznym → BPFI, zewnętrznym → BPFO, zdrowe ma wyraźnie
  niższe wyniki (test).

## Zmienna prędkość: `analyze-orders`

```
python bearing_resonance_sieve.py analyze-orders nagranie.npz --fs 18500 --channel vib --tach-channel tach --tach-fs 2960 --ppr 108 --bearing 6007-LBF
```

Zegar z tachometru → kąt wału → obwiednie pasm 1–9 kHz przeliczone na równe kroki kąta („wyprostowana rura”) → mapa
rezonansu w rzędach → to samo sito. Odcinki 60 s, co najmniej 10 obrotów, wynik = mediana. Walidacja: turbina
Fraunhofer LBF (0,2–0,9 obr/s) — bieżnia zewnętrzna AUC 1,00, swoistość 1,00 wobec 0,85 przy założeniu stałej
prędkości. Bieżnia wewnętrzna i element toczny niewykryte. Śledzenie prędkości z samych drgań na tej turbinie odpadło —
potrzebny tachometr.

## Trend życia łożyska: `bearing_health_trend.py`

```
python bearing_health_trend.py trend KATALOG_MIGAWEK --fs 25600 --pattern "acc_*.csv" --col 4
```

Dla każdej migawki: RMS, kurtoza, P (błyski obwiedni), D (gęstość zdarzeń). Faza: **pole** (D przy tle początku życia),
**cząsteczka** (D spadło < 0,9 × tło), **powrót ku fali** (D z końca ≥ 1,2 × minimum — w walidacji w 7/11 łożysk przed
końcem życia). Walidacja PRONOSTIA: D spada w 9/11 łożysk. D zachowuje się jak kurtoza; przewaga nad RMS dotyczy
spójności kierunku trendu, nie jego siły.

## Wykonalność

`wykonalnosc.N_cyk` = liczba cykli rytmu uszkodzenia w analizowanym oknie. Poniżej 10 grzebień jest rozmyty i sito nie
ma szans (reguła trafnie przewidziała słabe sito na PRONOSTIA, okno 0,1 s).

## Granice

- Wynik `score` jest wskaźnikiem, nie werdyktem: próg „uszkodzone / zdrowe” trzeba ustalić na zdrowych nagraniach
  danej maszyny. Uszkodzenia kulek (BSF) nie są modelowane — na CWRU podnoszą wynik BPFI.
- Walidacja dotyczy jednego stanowiska (Paderborn). To nie jest certyfikowane narzędzie diagnostyczne.
