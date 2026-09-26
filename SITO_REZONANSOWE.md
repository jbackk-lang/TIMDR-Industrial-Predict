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
- **Zgodność z wersją walidowaną** — test wzorcowy w `test_bearing_resonance_sieve.py` (identyczne liczby).
- **CWRU (1797 RPM, dane w repo)** — nagranie z uszkodzeniem wewnętrznym → BPFI, zewnętrznym → BPFO, zdrowe ma wyraźnie
  niższe wyniki (test).

## Granice

- Wynik `score` jest wskaźnikiem, nie werdyktem: próg „uszkodzone / zdrowe” trzeba ustalić na zdrowych nagraniach
  danej maszyny. Uszkodzenia kulek (BSF) nie są modelowane — na CWRU podnoszą wynik BPFI.
- Walidacja dotyczy jednego stanowiska (Paderborn). To nie jest certyfikowane narzędzie diagnostyczne.
