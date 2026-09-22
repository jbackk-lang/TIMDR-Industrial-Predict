"""bearing_meta_adapter.py -- adapter bearing_vibration_state -> MetaState
(integracja z TIMDR-META-DYNAMICS), czwarta realna integracja formalizmu
Lambda-tau-rho-J w tym ekosystemie (pierwsza: finansowa w
analizator-gieldowy-v3, druga: pogodowa w Synoptyk-v3, trzecia: sejsmiczna
w TIMDR-Earthquake-Core). Ten sam wzorzec sys.path (folder-siostra), inny
sygnal wejsciowy: wibracja lozyska (akcelerometr), CZESTOTLIWOSC PROBKOWANIA
o 2-4 rzedy wielkosci wyzsza niz w sejsmice (12 kHz vs pojedyncze-do-100 Hz).

KONTEKST: to repo (TIMDR-Industrial-Predict) nie ma wlasnego rdzenia
flow/twist/trm - ZAMIAST duplikowac te funkcje, ten adapter importuje
TIMDR_EarthquakeCore z siostrzanego repo TIMDR-Earthquake-Core (drugi
sibling-import obok TIMDR-META-DYNAMICS). Uzasadnienie: flow()/twist()/trm()
sa DOMENOWO NIEZALEZNE - to ogolne narzedzia do lokalnego gradientu/
wygladzania/rezyduow na dowolnym jednokanalowym s(t), zweryfikowane juz raz
(przeciw ObsPy) w kontekscie sejsmicznym. Duplikowanie ich tutaj byloby
dokladnie tym zapachem kodu, ktoremu ten ekosystem juz raz zapobiegl (patrz
analizator-gieldowy-v3/meta_dynamics_module.py - pierwszy sibling-import
tego wzorca).

===========================================================================
GENEZA (2026-09-08, sesja interaktywna) - trzy nieudane proby PRZED tym,
co ponizej, wszystkie uczciwie udokumentowane zamiast ukryte:

PROBA 1 (dane zdecymowane do 500 Hz, Lambda = pol-widma-na-pol jak w
TIMDR-Earthquake-Core): zero dyskryminacji sensownej - plik z uszkodzeniem
elementu tocznego (B, 0.021") wyszedl SPOKOJNIEJSZY niz zdrowe lozysko
(rho=0, J=0), odwrotnie niz oczekiwane. Przyczyna: decymacja boxcar /24 to
prymitywny filtr antyaliasingowy, ktory rozny sposob tlumi rozne typy
usterek w zaleznosci od tego, gdzie leza ich czestotliwosci wzgledem zer
filtra (zera dokladnie na wielokrotnosciach 500 Hz).

PROBA 2 (pelna rozdzielczosc natywna 12 kHz, bez decymacji, ale wciaz
Lambda = pol-widma-na-pol): naprawilo B-fault (rho/tau/J teraz sensownie
podwyzszone u WSZYSTKICH trzech typow uszkodzen wzgledem zdrowego), ALE
operator M (pochodna stanu w czasie) nadal prawie nigdy nie daje fazy
"krytyczna" - bo M mierzy ZMIANE miedzy kolejnymi oknami, a uszkodzenie
lozyska to STAN STALY przez caly zapis (w przeciwienstwie do trzesienia
ziemi, gdzie mainshock to prawdziwe PRZEJSCIE w srodku ciaglego zapisu).
Wniosek: dla lozysk to SAM STAN (Lambda/tau/rho/J), nie jego pochodna,
niesie sygnal - stad ponizszy dwu-sciezkowy (referencja+test) ksztalt tego
adaptera, inny niz jednosladowy ksztalt adaptera sejsmicznego.

PROBA 3 (kurtoza widmowa, jeden poziom rozdzielczosci 4096 probek): SZUM,
nie sygnal - za malo niezaleznych ramek (29-59) na tak waskie pasmo (2.93
Hz/bin). Piki wyszly niespojne miedzy trzema typami usterek, dwa z trzech
(6000 Hz - dokladnie granica Nyquista; 12 Hz - blisko DC) wygladaly na
artefakty numeryczne, nie fizyke.

PROBA 4 (wielopoziomowy "kurtogram" - STFT z oknem Hanna, 7 dlugosci okna
64-4096 probek, roznica SK(uszkodzenie)-SK(zdrowe) na kazdym poziomie):
dalej niespojne miedzy trzema typami usterek (IR: pik 5625 Hz; OR: pik
dokladnie na 6000 Hz - znow granica Nyquista, podejrzany artefakt; B: pik
12 Hz - znow blisko DC). Prawdziwy Fast Kurtogram (Antoniego) wymaga
starannego banku filtrow rekurencyjnych z odpowiednia normalizacja - to,
co tu policzono, to za plytkie przyblizenie przez STFT, i NIE zastapilo
prostszego, uczciwie zweryfikowanego wyniku ponizej.

ZNALEZISKO KONCOWE (uzyte w tym pliku) - prosta moc pasmowa wzgledem
REALNEJ zdrowej referencji: podzielono usrednione widmo mocy (FFT na
oknach 4096 probek, natywne 12 kHz) na 12 pasm co ~500 Hz i porownano
stosunek uszkodzenie/zdrowe pasmo-po-pasmie. W pasmie ~2.5-4 kHz stosunek
wynosi: IR21 ~32 600x i ~34 400x, OR@6_21 ~28 150x, ~33 700x i ~90 000x,
B21 ~620x i ~3 640x (slabiej, ale TEN SAM wzorzec pasmowy) - klasyczny
sygnal rezonansu strukturalnego obudowy lozyska wzbudzanego uderzeniami
(dokladnie to, co w prawdziwej diagnostyce lozysk wyciaga sie metoda
obwiedni/spectral kurtosis, tu znalezione prostszym narzedziem: PRAWDZIWA
zdrowa referencja jest silniejszym punktem odniesienia niz slepa kurtoza,
gdy akurat sie ja ma). RESONANCE_BAND_HZ ponizej jest tym stalym,
EMPIRYCZNYM pasmem - NIE wykrywanym automatycznie per-plik (probowano,
patrz PROBA 3/4 wyzej, i sie nie udalo w tej sesji).

DWIE SCIEZKI ZAMIAST JEDNEJ (koncepcyjnie: trzecia, "rezonansowa" wielkosc
obok istniejacej pary sciezek referencja/test) - odzwierciedla to, jak
GIA-TIMDR formalnie rozdziela gal-zie tego samego formalizmu na odrebne,
NIE utozsamiane obiekty (patrz skill timdr-signal-framework, Axioms_S vs
Axioms_G vs Axioms_K) - tu, analogicznie, "stan wzgledem referencji"
(rho/tau/J) i "energia w pasmie rezonansowym" (Lambda) sa policzone
niezaleznie i dopiero SUMOWANE przez istniejacy, niezmieniony
MetaOperatorM.magnitude() z TIMDR-META-DYNAMICS - zaden nowy operator nie
zostal tu dopisany, to jest UZYCIE istniejacego trojkata Lambda-tau-rho-J,
nie jego rozszerzenie. Formalne domkniecie tej analogii (np. jako nowy
aksjomat) NIE zostalo zrobione w tym pliku - to jest tylko zaznaczony,
otwarty watek koncepcyjny, w tym samym duchu co niedomkniete G4/G7 w
Axioms_G_TIMDR_Geometry.md, do ewentualnego sformalizowania pozniej.
===========================================================================
PRE-REJESTRACJA MAPOWANIA (ustalone PRZED zbudowaniem finalnego adaptera,
choc PO trzech nieudanych probach udokumentowanych wyzej - protokol
numerologii/formalizmu, skill timdr-signal-framework):

    Lambda (struktura)   = fraction mocy widmowej W TYM OKNIE lezacej w
                            RESONANCE_BAND_HZ=(2500,4000) wzgledem calkowitej
                            mocy widma tego okna - samo-znormalizowane [0,1],
                            NIE zalezy od progow referencyjnych.

    tau (transformacja)  = sredni |flow_grad| W TYM OKNIE / GLOBALNY
                            flow_threshold POLICZONY Z REFERENCYJNEGO
                            (zdrowego) NAGRANIA - identyczny wzor co
                            TIMDR-Earthquake-Core, ale prog pochodzi z
                            INNEGO NAGRANIA (zdrowa jednostka), nie z
                            wczesniejszej czesci TEGO SAMEGO sladu (bo
                            lozysko nie ma "spokojnego okresu przed
                            zdarzeniem" wewnatrz jednego zapisu - to REZIM
                            STALY, patrz PROBA 2 wyzej).

    rho (anomalia)       = fraction probek W TYM OKNIE, gdzie
                            |s - core.trm(s)| > GLOBALNY anomaly_threshold
                            z REFERENCYJNEGO nagrania.

    J (operator punktowy)= fraction probek W TYM OKNIE, gdzie
                            |d(flow_grad)/dt| > GLOBALNY twist_threshold
                            z REFERENCYJNEGO nagrania.

UCZCIWE ZASTRZEZENIA:
  1. RESONANCE_BAND_HZ=(2500,4000) jest STALE i EMPIRYCZNE (znalezione na
     JEDNYM zestawie: CWRU 1797 RPM, DE12, 4 nagrania - 1 zdrowe + 3 typy
     usterek 0.021"), NIE wykrywane automatycznie per-maszyna. Inna
     predkosc obrotowa/inny typ lozyska/inna maszyna moze miec rezonans
     strukturalny w zupelnie innym pasmie - to NIE jest uniwersalna stala
     fizyczna, tylko punkt startowy do przeliczenia na wlasnych danych.
  2. Progi classify_phase() (0.1/1.0, w MetaOperatorM z TIMDR-META-DYNAMICS)
     sa PRZENIESIONE bez zmian, NIE skalibrowane na tym sygnale - i jak
     pokazuje PROBA 2, dla lozysk M-operator (pochodna) rzadko w ogole
     dochodzi do "krytyczna", bo mierzy zmiane, nie poziom - patrz #4.
  3. k=3.5 (prog robust dla tau/J) i factor=3.5 (prog anomalii dla rho) sa
     tymi samymi stalymi co Synoptyk-v3/TIMDR-Earthquake-Core, dla spojnosci
     ekosystemu, NIE niezalezna kalibracja na wibracji lozysk.
  4. Operator M (pochodna stanu) jest ZAPROJEKTOWANY do wykrywania PRZEJSC
     w obrebie jednego ciaglego sladu (jak mainshock trzesienia ziemi), nie
     REZIMU STALEGO (usterka lozyska trwa przez caly zapis, nie jest
     przejsciem) - koncepcyjnie SAM STAN (Lambda/tau/rho/J), nie jego
     pochodna M, powinien niesc glowny sygnal dyskryminujacy tutaj (patrz
     PROBA 2). W PRAKTYCE, na tym konkretnym zestawie danych, kontrast
     Lambda miedzy zdrowym (~0.002-0.005) a uszkodzonym (~0.82-0.91) lozyskiem
     jest tak ekstremalny, ze M-operator TEZ wychodzi zdecydowanie
     "krytyczna" na kazdym oknie testowym z usterka (patrz test end-to-end)
     - ale to jest WLASCIWOSC TEJ konkretnej skali kontrastu, nie
     gwarancja: przy slabszym uszkodzeniu (mniejsza srednica defektu,
     wczesne stadium) kontrast Lambda moglby byc za maly, zeby M-pochodna
     to zlapala, mimo ze `states` (surowy stan) juz by pokazywal
     podwyzszenie. Dlatego ten plik zawsze zwraca OBA (`states` i
     `M_series`/`phases`) - w razie watpliwosci ufaj `states`, nie samym
     fazom.
  5. Cztery realne nagrania (CWRU, 1797 RPM, DE12, 0.021" dla wszystkich
     trzech typow usterek) to JEDEN zestaw warunkow pracy - nie test na
     wielu predkosciach/obciazeniach/glebokosciach usterki. Fixture w
     data/cwru_bearing/*.csv to TYLKO pierwsze 1536 probek (0.128s) z
     kazdego pliku - wystarczajace do testu end-to-end/ksztaltu, NIE do
     odtworzenia pelnej analizy statystycznej z sesji interaktywnej
     (ktora uzyla calych nagran, 10-20s kazde) - pelne liczby sa
     udokumentowane w README, zrodlo (URL, dokladne nazwy plikow) podane
     do samodzielnego pobrania, bo srodowisko tej sesji ma zablokowany
     dostep sieciowy z poziomu bash do raw.githubusercontent.com (przez co
     pelne pliki .npz nie mogly zostac automatycznie sciagniete do repo -
     pobrano je przez przegladarke, konwertujac .npz->tablice w JS).
  6. (2026-09-08, uwaga uzytkownika, NIE zaimplementowane teraz - tylko
     odnotowane, patrz README sekcja "Doprecyzowanie stan vs przejscie")
     Progi referencyjne (RESONANCE_BAND_HZ + progi tau/rho/J z #1-#3) sa
     obecnie GLOBALNE dla calego modulu, dobrane dla JEDNEJ konfiguracji
     (1797 RPM, kanal DE). Inna predkosc obrotowa, inny typ lozyska albo
     inny kanal (FE/BA) prawdopodobnie wymaga WLASNYCH progow - docelowy
     ksztalt to `reference_profile[rpm][channel]` zamiast stalych
     modulowych, gdy pojawia sie dane z wiecej niz jednej konfiguracji.
     Podobnie `k_neighbors=8` (domyslne TIMDR_EarthquakeCore, dziedziczone
     przez sibling-import) jest dobrane pod sejsmike; tu nie ma na to
     wplywu, bo Lambda liczone jest z usrednionego widma calego okna, nie
     z per-probkowego flow()/trm() (patrz PRE-REJESTRACJA wyzej) - ale
     gdyby w przyszlosci wrocic do lokalnych anomalii per-probka (PROBA
     1-2), k=8 przy natywnych 12 kHz obejmuje ~0.58ms (krocej niz okres
     uderzenia ~7-9ms, wiec formalnie OK), lecz przy innej czestotliwosci
     probkowania to samo k=8 moglby znow objac wielokrotnosc okresu
     uderzenia (ten sam blad co decymacja 500Hz w PROBIE 1) - k=2-4
     bylby bezpieczniejszym punktem wyjscia do takiego rozszerzenia.
===========================================================================
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple, Union

import numpy as np

MAD_TO_STD = 1.4826    # ta sama stala co Synoptyk-v3/TIMDR-Earthquake-Core
ROBUST_K = 3.5          # ta sama wartosc co Synoptyk-v3 DEFECT_K, patrz zastrzezenie #3
ANOMALY_FACTOR = 3.5    # jw.

# Pasmo rezonansu strukturalnego znalezione empirycznie na realnych danych
# CWRU (patrz GENEZA wyzej) - NIE uniwersalna stala, patrz zastrzezenie #1.
RESONANCE_BAND_HZ = (2500.0, 4000.0)

# Okno produkcyjne zweryfikowane w sesji interaktywnej (4096 probek przy
# 12 kHz = ~0.3413s) - testy na malych fixture'ach uzywaja mniejszego okna
# (patrz test_bearing_meta_adapter.py), bo fixture'y maja tylko 1536 probek.
WINDOW_SAMPLES_DEFAULT = 4096

# ZWENDOROWANE 2026-09-10 (patrz naglowki `_vendor_*.py` w tym repo dla
# pelnego uzasadnienia): wczesniej ten modul ladowal TIMDR-META-DYNAMICS
# i TIMDR-Earthquake-Core przez sys.path sibling-import z folderow-siostr
# na dysku. Zamienione na lokalne, zwendorowane kopie, zeby to repo
# dzialalo samodzielnie po sklonowaniu WYLACZNIE siebie (decyzja na
# wyrazna prosbe: "repozytoria kodu maja byc niezalezne od siebie").
# Zachowanie/matematyka bez zmian.
from _vendor_timdr_meta_dynamics_core import MetaState, MetaOperatorM, MetaMap, MetaTrigger, MetaTriggerResult
from _vendor_timdr_core_earthquake import TIMDR_EarthquakeCore


@dataclass
class BearingMetaResult:
    window_starts: List[float]     # czas poczatku kazdego okna [s] W SLADZIE TESTOWYM, dlugosc n
    states: List[MetaState]        # S_meta(t) per okno TESTOWEGO sladu, dlugosc n - TU jest realna dyskryminacja (patrz zastrzezenie #4)
    M_series: List[MetaState]      # M(t) = dS/dt, dlugosc n-1 - rzadko "krytyczna" dla lozysk, patrz #4
    phases: List[str]              # faza per krok M, dlugosc n-1
    trigger: MetaTriggerResult
    resonance_band_used: Tuple[float, float] = RESONANCE_BAND_HZ  # pasmo faktycznie uzyte do Lambda (stale lub auto-wybrane)
    resonance_band_kurtosis: Optional[float] = None  # kurtoza nadmiarowa wybranego pasma na s_ref, tylko gdy resonance_band="auto"


def _robust_threshold(values: np.ndarray, k: float = ROBUST_K) -> float:
    """Mediana + k*MAD - identyczna logika co Synoptyk-v3/TIMDR-Earthquake-Core,
    reimplementowana tu lokalnie (repo-do-repo, nie import) dla samowystarczalnosci."""
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return 0.0
    med = float(np.median(finite))
    mad = float(np.median(np.abs(finite - med))) * MAD_TO_STD
    return med + k * mad


def _default_candidate_bands(fs: float, band_width_hz: float = 500.0, nyquist_margin: float = 0.85) -> List[Tuple[float, float]]:
    """Siatka kandydackich pasm co `band_width_hz` Hz, zaczynajac od
    `band_width_hz` (pomija DC), ograniczona do <= `nyquist_margin`*Nyquista.

    UZASADNIENIE MARGINESU (2026-09-22, "podmien i sprawdz"): PROBA 3 w
    GENEZIE modulu (wyzej) trafila na spurious kurtoze na pasmach dotykajacych
    Nyquista (6000 Hz przy fs=12kHz) - artefakt maskowania FFT, nie fizyczny
    rezonans, niezaleznie odtworzony i zdiagnozowany w GIA-TIMDR
    (modal_band_energy_bridge v0.2 / envelope_demodulation): kandydat
    (5500,6000) daje kurtoze ~130-160 (numeryczny artefakt), podczas gdy
    siatka bezpieczna do 5000 Hz (margines 0.85 przy fs=12kHz) poprawnie
    wybiera (3500,4000) Hz - blisko udokumentowanej stalej empirycznej
    RESONANCE_BAND_HZ=(2500,4000) znalezionej rowniez tu (patrz GENEZA).
    Domyslny margines 0.85 odtwarza dokladnie ten bezpieczny zakres przy
    12 kHz (cap=5100 -> pasma 500..5000) i skaluje sie proporcjonalnie dla
    innych czestotliwosci probkowania (np. inne repo/inna maszyna)."""
    nyquist = fs / 2.0
    cap = nyquist * nyquist_margin
    bands = []
    f_lo = band_width_hz
    while f_lo + band_width_hz <= cap:
        bands.append((f_lo, f_lo + band_width_hz))
        f_lo += band_width_hz
    return bands


def _kurtosis_excess(signal: np.ndarray) -> float:
    """Kurtoza nadmiarowa (Fisher, 0=Gauss). Reimplementowana lokalnie
    (repo-do-repo, nie import - patrz naglowek modulu / decyzja o
    samowystarczalnosci przez wendorowanie) - identyczna logika co
    `timdr_formalism.envelope_demodulation.kurtosis_excess` w
    TIMDR-Math-Formalism/GIA-TIMDR, gdzie zostala pierwotnie zweryfikowana
    (PREREG_MODAL_BAND_ENERGY_BRIDGE_v0.2.md)."""
    x = signal - np.mean(signal)
    m2 = np.mean(x ** 2)
    if m2 < 1e-18:
        return 0.0
    m4 = np.mean(x ** 4)
    return float(m4 / (m2 ** 2) - 3.0)


def _bandpass_fft(signal: np.ndarray, fs: float, f_lo: float, f_hi: float) -> np.ndarray:
    """Maskowanie w dziedzinie czestotliwosci + odwrotna FFT. Reimplementacja
    lokalna, jw."""
    n = len(signal)
    spectrum = np.fft.rfft(signal)
    freqs = np.fft.rfftfreq(n, d=1.0 / fs)
    mask = (freqs >= f_lo) & (freqs <= f_hi)
    return np.fft.irfft(spectrum * mask, n=n)


def select_resonance_band_from_reference(
    s_ref: np.ndarray,
    fs: float,
    candidate_bands: Optional[List[Tuple[float, float]]] = None,
) -> Tuple[Tuple[float, float], float]:
    """Automatyczny wybor pasma rezonansu: pasmo z maksymalna kurtoza
    nadmiarowa sposrod `candidate_bands`, wybrane z REFERENCYJNEGO (zdrowego)
    nagrania PRZED jakimkolwiek porownaniem miedzy grupami - rezonans
    strukturalny jest wlasciwoscia czujnika/obudowy, nie samego uszkodzenia
    (ten sam argument metodologiczny co w GIA-TIMDR
    PREREG_MODAL_BAND_ENERGY_BRIDGE_v0.2.md, patrz tez timdr-signal-framework
    skill).

    Zastepuje PROBE 3 z GENEZY modulu (ktora zawiodla przez brak marginesu
    od Nyquista, patrz `_default_candidate_bands`) - ten sam pomysl, teraz
    poprawnie ograniczony. Domyslna siatka kandydacka to
    `_default_candidate_bands(fs)`. Zwraca (pasmo, kurtoza_najlepszego)."""
    if candidate_bands is None:
        candidate_bands = _default_candidate_bands(fs)
    if not candidate_bands:
        raise ValueError(f"Pusta siatka kandydacka pasm dla fs={fs} - Nyquist za niski")
    best_band = None
    best_kurt = -np.inf
    for f_lo, f_hi in candidate_bands:
        filtered = _bandpass_fft(s_ref, fs, f_lo, f_hi)
        k = _kurtosis_excess(filtered)
        if k > best_kurt:
            best_kurt = k
            best_band = (f_lo, f_hi)
    return best_band, best_kurt


def _resonance_band_fraction(s_window: np.ndarray, fs: float, band=RESONANCE_BAND_HZ) -> float:
    """Ulamek mocy widmowej W TYM OKNIE lezacej w `band` (Hz) wzgledem
    calkowitej mocy widma tego okna - samo-znormalizowane [0,1], jak
    high_freq_fraction() w TIMDR-Earthquake-Core, ale pasmo jest WASKIE i
    UMIEJSCOWIONE na empirycznie znalezionym rezonansie (patrz GENEZA),
    zamiast pol-na-pol podzialu calego widma."""
    n = len(s_window)
    if n < 4:
        return 0.0
    centered = s_window - np.mean(s_window)
    spectrum = np.fft.rfft(centered)
    power = np.abs(spectrum) ** 2
    freqs = np.fft.rfftfreq(n, d=1.0 / fs)
    total = float(power.sum())
    if total <= 0:
        return 0.0
    band_mask = (freqs >= band[0]) & (freqs < band[1])
    return float(power[band_mask].sum() / total)


def compute_reference_thresholds(
    core: TIMDR_EarthquakeCore, t_ref: np.ndarray, s_ref: np.ndarray
) -> "BearingGlobalThresholds":
    """Liczy progi robust na REFERENCYJNYM (zdrowym) nagraniu - PRZED
    policzeniem jakiegokolwiek stanu/M-serii na sladzie TESTOWYM (byc moze
    tym samym zdrowym nagraniu jako sanity-check, byc moze innym,
    uszkodzonym) - pre-rejestracja w doslownym sensie, analogicznie do
    `compute_global_thresholds(calibration_end=...)` w
    TIMDR-Earthquake-Core, ale tu "przed" znaczy "z INNEGO nagrania", nie
    "z wczesniejszej czesci TEGO SAMEGO sladu" (patrz PROBA 2 w docstringu
    modulu dla uzasadnienia, dlaczego lozyska tego wymagaja)."""
    flow_grad_ref = core.flow(t_ref, s_ref)
    flow_threshold = _robust_threshold(np.abs(flow_grad_ref))

    twist_strength_ref = np.abs(np.gradient(flow_grad_ref, t_ref))
    twist_threshold = _robust_threshold(twist_strength_ref)

    smooth_ref = core.trm(t_ref, s_ref)
    residuals_ref = s_ref - smooth_ref
    mad = float(np.median(np.abs(residuals_ref))) * MAD_TO_STD
    if mad <= 1e-12:
        std = float(np.std(residuals_ref))
        mad = std if std > 1e-12 else 1e-9
    anomaly_threshold = ANOMALY_FACTOR * mad

    return BearingGlobalThresholds(
        flow_threshold=flow_threshold,
        twist_threshold=twist_threshold,
        anomaly_threshold=anomaly_threshold,
    )


@dataclass
class BearingGlobalThresholds:
    """Progi policzone RAZ na REFERENCYJNYM (zdrowym) nagraniu - patrz
    compute_reference_thresholds i zastrzezenie #4/PROBA 2 w docstringu
    modulu dla wyjasnienia, dlaczego zrodlem jest osobne nagranie, nie
    wczesniejsza czesc tego samego sladu jak w adapterze sejsmicznym."""
    flow_threshold: float
    twist_threshold: float
    anomaly_threshold: float


def window_to_meta_state(
    core: TIMDR_EarthquakeCore,
    t_window: np.ndarray,
    s_window: np.ndarray,
    fs: float,
    thresholds: BearingGlobalThresholds,
    resonance_band: Tuple[float, float] = RESONANCE_BAND_HZ,
) -> MetaState:
    """Mapowanie jednego okna (t,s) -> jeden MetaState. Lambda liczona z
    `resonance_band` (samo-znormalizowana, nie potrzebuje progu; domyslnie
    stala empiryczna RESONANCE_BAND_HZ, patrz `select_resonance_band_from_reference`
    dla alternatywy z automatycznym wyborem), tau/rho/J wzgledem progow z
    REFERENCYJNEGO nagrania. Wzory zamrozone w PRE-REJESTRACJI na gorze pliku."""
    n = len(s_window)

    Lambda = _resonance_band_fraction(s_window, fs, band=resonance_band)

    flow_grad = core.flow(t_window, s_window)
    abs_flow = np.abs(flow_grad)
    tau = float(abs_flow.mean()) / thresholds.flow_threshold if thresholds.flow_threshold > 0 else 0.0

    if n >= 3:
        twist_strength = np.abs(np.gradient(flow_grad, t_window))
        n_twist = int(np.sum(twist_strength > thresholds.twist_threshold))
    else:
        n_twist = 0
    J = n_twist / n if n > 0 else 0.0

    smooth = core.trm(t_window, s_window)
    residuals = s_window - smooth
    n_anomaly = int(np.sum(np.abs(residuals) > thresholds.anomaly_threshold))
    rho = n_anomaly / n if n > 0 else 0.0

    return MetaState(Lambda=Lambda, tau=tau, rho=rho, J=J)


def build_meta_series_from_reference_and_test(
    t_ref: np.ndarray,
    s_ref: np.ndarray,
    t_test: np.ndarray,
    s_test: np.ndarray,
    fs: float,
    window_samples: int = WINDOW_SAMPLES_DEFAULT,
    core: Optional[TIMDR_EarthquakeCore] = None,
    dt: Optional[float] = None,
    resonance_band: Union[Tuple[float, float], str] = RESONANCE_BAND_HZ,
) -> BearingMetaResult:
    """DWIE SCIEZKI zamiast jednego ciaglego sladu (patrz docstring modulu,
    'GENEZA'/PROBA 2): `(t_ref, s_ref)` to zdrowe nagranie referencyjne
    (uzywane WYLACZNIE do policzenia progow), `(t_test, s_test)` to slad,
    ktory faktycznie chcemy sklasyfikowac - moze to byc TO SAMO zdrowe
    nagranie (sanity/negative control - powinno wyjsc w duzej wiekszosci
    "stabilna" w `phases`, ale patrz zastrzezenie #4: to `states`, nie
    `phases`, niesie glowny sygnal) albo nagranie z uszkodzeniem.

    `window_samples` - LICZBA PROBEK na okno (nie sekund, w przeciwienstwie
    do adapterow pogodowego/sejsmicznego) - bo przy 12 kHz sekundy okna
    zalezaloby od fs, a Lambda (FFT) i tak dziala na probkach. Okna sa
    NIENAKLADAJACE SIE (partycjonowanie), tak jak w pozostalych trzech
    adapterach. `dt` (czas miedzy KOLEJNYMI OKNAMI, dla M-operatora)
    domyslnie = window_samples/fs.

    `resonance_band` - domyslnie stala empiryczna RESONANCE_BAND_HZ
    (zachowanie bez zmian wzgledem oryginalnego adaptera - patrz GENEZA).
    Przekaz jawnie `"auto"`, zeby wybrac pasmo automatycznie z `s_ref` przez
    kurtoze nadmiarowa (`select_resonance_band_from_reference`, siatka
    kandydacka bezpieczna od Nyquista - patrz `_default_candidate_bands` i
    zastrzezenie ponizej #1 o tym, ze RESONANCE_BAND_HZ nie jest uniwersalne).
    Mozna tez podac wlasne pasmo `(f_lo, f_hi)` bezposrednio.

    Ostatnie, niepelne okno jest ODRZUCANE, nie dopelniane (jak w
    TIMDR-Earthquake-Core)."""
    t_ref = np.asarray(t_ref, dtype=np.float64)
    s_ref = np.asarray(s_ref, dtype=np.float64)
    t_test = np.asarray(t_test, dtype=np.float64)
    s_test = np.asarray(s_test, dtype=np.float64)

    if len(t_ref) != len(s_ref):
        raise ValueError(f"t_ref i s_ref musza miec ta sama dlugosc, dostano {len(t_ref)} i {len(s_ref)}")
    if len(t_test) != len(s_test):
        raise ValueError(f"t_test i s_test musza miec ta sama dlugosc, dostano {len(t_test)} i {len(s_test)}")
    if len(t_ref) < 4:
        raise ValueError(f"Referencyjne nagranie za krotkie ({len(t_ref)} probek < 4)")
    if window_samples < 4:
        raise ValueError(f"window_samples={window_samples} musi byc >= 4")

    if core is None:
        core = TIMDR_EarthquakeCore()
    if dt is None:
        dt = window_samples / fs

    thresholds = compute_reference_thresholds(core, t_ref, s_ref)

    resolved_band: Tuple[float, float]
    selected_kurtosis: Optional[float] = None
    if resonance_band == "auto":
        resolved_band, selected_kurtosis = select_resonance_band_from_reference(s_ref, fs)
    else:
        resolved_band = resonance_band  # type: ignore[assignment]

    n_windows = len(t_test) // window_samples
    if n_windows < 2:
        raise ValueError(
            f"Za krotki slad testowy ({len(t_test)} probek) na >= 2 pelne okna "
            f"po {window_samples} probek - dostano {n_windows}."
        )

    window_starts: List[float] = []
    states: List[MetaState] = []
    for i in range(n_windows):
        start = i * window_samples
        end = start + window_samples
        t_win = t_test[start:end]
        s_win = s_test[start:end]
        window_starts.append(float(t_test[start]))
        states.append(window_to_meta_state(core, t_win, s_win, fs, thresholds, resonance_band=resolved_band))

    meta_operator = MetaOperatorM()
    M_series: List[MetaState] = []
    for i in range(len(states) - 1):
        M_series.append(meta_operator.compute(states[i], states[i + 1], dt))

    meta_map = MetaMap(meta_operator)
    phases = meta_map.detect_transitions(M_series)
    trigger = MetaTrigger().analyze(phases)

    return BearingMetaResult(
        window_starts=window_starts, states=states,
        M_series=M_series, phases=phases, trigger=trigger,
        resonance_band_used=resolved_band, resonance_band_kurtosis=selected_kurtosis,
    )
