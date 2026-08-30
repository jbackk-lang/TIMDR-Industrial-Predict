"""
demo_scenarios.py — syntetyczne zestawy danych demo dla TIMDR-Industrial-Predict
====================================================================================
5 scenariuszy odpowiadających "Co wykrywa TIMDR-Industrial-Fusion w
praktyce" z opisu oryginalnego zgłoszenia - każdy zaprojektowany tak, by
faktycznie uruchamiał deklarowany detektor (zweryfikowane w
test_demo_scenarios.py, nie tylko założone).
"""

import os

import numpy as np

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "real_engines")

SCENARIOS = {
    "bearing_wear": "Zużycie łożysk — narastająca wibracja i temperatura (trend), TTF liczy się w przód",
    "pump_seizure": "Zatarcie pompy — nagły skok ciśnienia i prądu (anomalia/twist), potem narastająca temperatura (trend)",
    "uneven_motor_rotation": "Nierówne obroty silnika — cykliczne wahania prądu/wibracji (rytm) z okazjonalnymi skokami (anomalia)",
    "resonance_loose_parts": "Rezonans / luźne elementy — regularne uderzenia wibracji, narastające w czasie (rytm + twist)",
    "duty_cycle_problems": "Problemy z cyklem pracy — powtarzalny cykl włącz/wyłącz (rytm) z jednym zepsutym cyklem (anomalia) i dryfem bazowym (trend)",
    "real_engine_1_full": "🛩️ REALNE dane (NASA C-MAPSS FD001, silnik nr 1) — pełny przebieg run-to-failure, 192 cykle",
    "real_engine_2_live": "🛩️ REALNE dane (NASA C-MAPSS FD001, silnik nr 2) — tylko pierwsze 85 cykli, silnik wciąż zdrowy (symulacja monitoringu na żywo)",
}

DEFAULT_THRESHOLDS = {
    "bearing_wear": 60.0,
    "pump_seizure": 25.0,
    "uneven_motor_rotation": 3.5,
    "resonance_loose_parts": 20.0,
    "duty_cycle_problems": 4.0,
    # POPRAWKA/UWAGA: te dwa scenariusze uzywaja REALNYCH danych 10-czujnikowych
    # analizowanych przez fuse() (nie fuse_calibrated()) - tak jak wszystkie demo
    # ponizej, to zwykly "replay" calej nagranej historii, nie live-symulacja
    # krok-po-kroku (patrz monitor.py + auto_calibrate() dla tamtej wersji).
    # Prog 6.0 dobrano EMPIRYCZNIE z realnych danych: healthy E(t) dla obu
    # silnikow miesci sie w 1.3-4.7, a silnik 1 tuz przed awaria dochodzi do E~9.6
    # - 6.0 poprawnie odroznia oba przypadki (zweryfikowano bezposrednio, nie
    # zgadywane).
    "real_engine_1_full": 6.0,
    "real_engine_2_live": 6.0,
}


def bearing_wear(seed=0):
    """Zużycie łożysk: 300s zdrowej pracy, potem 100s narastającej
    wibracji i temperatury (typowy powolny trend degradacji)."""
    rng = np.random.default_rng(seed)
    n_healthy, n_degrade = 300, 100
    n = n_healthy + n_degrade
    t = np.arange(n, dtype=float)
    temp = np.concatenate([
        rng.normal(60, 1, n_healthy),
        60 + np.linspace(0, 20, n_degrade) + rng.normal(0, 1, n_degrade),
    ])
    vib = np.concatenate([
        rng.normal(0.2, 0.02, n_healthy),
        0.2 + np.linspace(0, 1.5, n_degrade) + rng.normal(0, 0.02, n_degrade),
    ])
    pres = rng.normal(5.0, 0.1, n)
    curr = rng.normal(10.0, 0.3, n)
    return t, {"temperature": temp, "vibration": vib, "pressure": pres, "current": curr}


def pump_seizure(seed=0):
    """Zatarcie pompy: 250s normalnej pracy, nagły skok ciśnienia i
    prądu w momencie zatarcia (t=250), potem 100s narastającej
    temperatury (nagrzewanie zablokowanego silnika)."""
    rng = np.random.default_rng(seed)
    n_healthy, n_after = 250, 100
    n = n_healthy + n_after
    t = np.arange(n, dtype=float)
    event = n_healthy

    pres = np.concatenate([
        rng.normal(5.0, 0.1, n_healthy),
        rng.normal(5.0, 0.1, n_after),
    ])
    pres[event:event + 3] += [12.0, 18.0, 9.0]  # gwaltowny skok cisnienia w momencie zatarcia

    curr = np.concatenate([
        rng.normal(10.0, 0.3, n_healthy),
        rng.normal(10.0, 0.3, n_after),
    ])
    curr[event:event + 3] += [15.0, 25.0, 10.0]  # prad rozruchowy/blokady silnika

    temp = np.concatenate([
        rng.normal(60, 1, n_healthy),
        60 + np.linspace(0, 30, n_after) + rng.normal(0, 1, n_after),
    ])
    vib = np.concatenate([
        rng.normal(0.2, 0.02, n_healthy),
        rng.normal(0.3, 0.05, n_after),
    ])
    return t, {"temperature": temp, "vibration": vib, "pressure": pres, "current": curr}


def uneven_motor_rotation(seed=0, n=300, period=12):
    """Nierówne obroty silnika: cykliczne wahania prądu i wibracji (W
    FAZIE, ta sama częstotliwość obrotów wału), plus kilka odosobnionych
    skoków energii (np. przeskoki zębów przekładni).

    UWAGA (świadomy wybór, zweryfikowany empirycznie): scenariusz
    zawiera TYLKO 2 czujniki (current, vibration), nie 4. Powód:
    `_mad_z()` normalizuje KAŻDĄ cechę do porównywalnej skali - to
    dobra poprawka przeciw dominacji skali (patrz README), ale ma
    konsekwencję, że czysto szumowa, niezwiązana z rotacją cecha (np.
    temperatura otoczenia) wnosi do E(t) TYLE SAMO znormalizowanej
    "energii" co prawdziwy sygnał okresowy - zweryfikowano wprost:
    dodanie 2 niezwiązanych czujników (temp, pressure, czysty szum)
    zmniejszało wykrywalność rytmu z score=0.73 do score=0.24 (poniżej
    domyślnego progu 0.4), niezależnie od tego, jak silny był sam sygnał
    okresowy. To nie jest błąd do naprawienia w Fusion - to naturalna
    konsekwencja normalizacji per-cecha; wniosek praktyczny: do wykrywania
    rytmu fuzuj czujniki FIZYCZNIE ZWIĄZANE z badanym zjawiskiem (tu:
    rotacja), nie wszystkie dostępne czujniki naraz.
    """
    rng = np.random.default_rng(seed)
    t = np.arange(n, dtype=float)
    phase = 2 * np.pi * t / period
    curr = 10.0 + 1.2 * np.sin(phase) + rng.normal(0, 0.1, n)
    vib = 0.2 + 0.08 * np.sin(phase) + rng.normal(0, 0.005, n)  # w fazie z curr
    for idx in (80, 160, 240):
        curr[idx] += 4.0  # odosobniony skok energii (np. przeskok zeba przekladni)
        vib[idx] += 0.15
    return t, {"current": curr, "vibration": vib}


def resonance_loose_parts(seed=0, n=300, period=20):
    """Rezonans / luźne elementy: regularne, ostre uderzenia wibracji co
    `period` próbek, o amplitudzie rosnącej w czasie (elementy coraz
    bardziej się obluzowują)."""
    rng = np.random.default_rng(seed)
    t = np.arange(n, dtype=float)
    base = rng.normal(0.15, 0.01, n)
    knock_mask = (np.arange(n) % period) == 0
    growth = np.linspace(0.3, 2.5, n)  # amplituda uderzen rosnie w czasie
    vib = base.copy()
    vib[knock_mask] += growth[knock_mask]
    curr = 10.0 + 0.1 * np.sin(2 * np.pi * t / period) + rng.normal(0, 0.1, n)
    temp = rng.normal(58, 0.5, n)
    pres = rng.normal(4.5, 0.05, n)
    return t, {"temperature": temp, "vibration": vib, "pressure": pres, "current": curr}


def duty_cycle_problems(seed=0, n=360, period=30):
    """Problemy z cyklem pracy: powtarzalny cykl obciążenia (połowa
    okresu wysoko, połowa nisko) w current+pressure, jeden wyraźny,
    odosobniony skok w pierwszej połowie (np. przeciążenie przy
    zablokowanym zaworze), plus narastający dryf bazowy w drugiej
    połowie nagrania (postępująca degradacja).

    UWAGA (świadomy wybór, zweryfikowany empirycznie - kilka iteracji):
    (1) tylko 2 czujniki (current, pressure) - z tego samego powodu co
    w `uneven_motor_rotation` (patrz tam). (2) "zepsuty cykl" to
    KRÓTKI, OSTRY skok (1 próbka), nie przedłużone "utkniecie" na
    normalnym poziomie wysokim - zweryfikowano, że wersja z dłuższym
    "utknięciem" była nierozróżnialna od zwykłej fazy wysokiej cyklu
    (mediana/MAD liczone globalnie na sygnale dwumodalnym trudno
    odróżniają "nienormalnie długo wysoko" od "normalnie wysoko").
    Zbyt duży/szeroki skok (np. +12, 5 próbek) niszczył za to
    wykrywalność rytmu (score spadał do 0.0) - statystyki oparte na
    wariancji nie są odporne na pojedyncze ekstremalne wartości
    odstające bez wcześniejszego odszumienia (ten sam wniosek co przy
    Hampel-despike w TIMDR-Earthquake-Core/seismic_loader.py).
    (3) dryf bazowy MUSI zaczynać się dopiero w drugiej połowie
    nagrania i być odpowiednio DUŻY względem amplitudy cyklu (~6) -
    zweryfikowano, że dryf obecny od próbki 0 (symetryczny względem
    globalnej mediany) albo zbyt mały względem wahań cyklu dawał
    nachylenie w trendzie bliskie zeru albo nawet UJEMNE, mimo realnie
    rosnącej wartości bazowej - `_mad_z()` mierzy odległość od
    GLOBALNEJ (nie lokalnej/ruchomej) mediany, więc powolny dryf
    słabszy niż lokalna zmienność cyklu potrafi zostać "wchłonięty"
    przez nią i w ogóle nie być widoczny jako trend.
    """
    rng = np.random.default_rng(seed)
    t = np.arange(n, dtype=float)
    phase = np.arange(n) % period
    high = phase < (period // 2)

    drift_start = n // 2
    baseline_drift = np.concatenate([np.zeros(drift_start), np.linspace(0, 15.0, n - drift_start)])

    curr = 8.0 + baseline_drift + np.where(high, 6.0, 0.0) + rng.normal(0, 0.2, n)
    pres = 5.0 + np.where(high, 0.6, 0.0) + rng.normal(0, 0.05, n)

    fault_idx = 100
    curr[fault_idx] += 3.0
    pres[fault_idx] += 0.75

    return t, {"current": curr, "pressure": pres}


_REAL_ENGINE_SENSOR_IDX = [2, 3, 4, 7, 11, 12, 15, 17, 20, 21]


def _load_real_engine(filename):
    """Wczytuje surowy plik C-MAPSS (26 kolumn: unit, cycle, 3 ustawienia
    operacyjne, 21 czujnikow) i zwraca (t, {sensor_N: wartosci}) dla
    podzbioru 10 czujnikow uznanych w literaturze za informacyjne dla
    FD001 - dokladnie ten sam podzbior, ktorego uzywano przy weryfikacji
    calibrate()/auto_calibrate() na tych danych (patrz README, sekcje
    "Blad 1"-"Blad 5")."""
    path = os.path.join(DATA_DIR, filename)
    with open(path) as f:
        rows = [line.split() for line in f if line.strip()]
    cols = [4 + i for i in _REAL_ENGINE_SENSOR_IDX]
    t = np.array([float(r[1]) for r in rows])
    sensors = {
        f"sensor_{i}": np.array([float(r[c]) for r in rows])
        for i, c in zip(_REAL_ENGINE_SENSOR_IDX, cols)
    }
    return t, sensors


def real_engine_1_full(seed=0):
    """Silnik nr 1, NASA C-MAPSS FD001 - REALNE dane, PELNY przebieg
    run-to-failure (192 cykle). `seed` ignorowany (dane nie sa syntetyczne)."""
    return _load_real_engine("cmapss_fd001_unit1_full_192cycles.txt")


def real_engine_2_live(seed=0):
    """Silnik nr 2, NASA C-MAPSS FD001 - REALNE dane, TYLKO pierwsze 85
    cykli (nie caly przebieg do awarii - patrz data/real_engines/README.md
    po wyjasnienie tego ograniczenia). Silnik jest w tym oknie zdrowy.
    `seed` ignorowany (dane nie sa syntetyczne)."""
    return _load_real_engine("cmapss_fd001_unit2_partial_85cycles.txt")


GENERATORS = {
    "bearing_wear": bearing_wear,
    "pump_seizure": pump_seizure,
    "uneven_motor_rotation": uneven_motor_rotation,
    "resonance_loose_parts": resonance_loose_parts,
    "duty_cycle_problems": duty_cycle_problems,
    "real_engine_1_full": real_engine_1_full,
    "real_engine_2_live": real_engine_2_live,
}


def make_demo_data(scenario="bearing_wear", seed=0):
    if scenario not in GENERATORS:
        raise ValueError(f"Nieznany scenariusz '{scenario}'. Dostepne: {list(GENERATORS)}")
    return GENERATORS[scenario](seed=seed)
