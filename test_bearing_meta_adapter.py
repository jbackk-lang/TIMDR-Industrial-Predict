"""test_bearing_meta_adapter.py -- kontrole syntetyczne + real-data end-to-end
dla bearing_meta_adapter.py (integracja TIMDR-Industrial-Predict <->
TIMDR-META-DYNAMICS <-> TIMDR-Earthquake-Core). Patrz docstring modulu dla
pelnej genezy (3 nieudane proby przed finalnym ksztaltem) i pre-rejestracji.
"""
import os

import numpy as np
import pytest

from bearing_meta_adapter import (
    RESONANCE_BAND_HZ,
    BearingGlobalThresholds,
    _resonance_band_fraction,
    build_meta_series_from_reference_and_test,
    compute_reference_thresholds,
    window_to_meta_state,
)
from timdr_core_earthquake import TIMDR_EarthquakeCore

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data", "cwru_bearing")
FS = 12000.0  # Hz - natywna czestotliwosc probkowania CWRU DE12


def _load_fixture(name):
    path = os.path.join(DATA_DIR, name)
    s = np.loadtxt(path, delimiter=",")
    t = np.arange(len(s), dtype=np.float64) / FS
    return t, s


def _synthetic_sine(freq_hz, n, fs, amplitude=1.0, phase=0.0):
    t = np.arange(n, dtype=np.float64) / fs
    s = amplitude * np.sin(2 * np.pi * freq_hz * t + phase)
    return t, s


# ---------------------------------------------------------------------------
# Kontrole syntetyczne
# ---------------------------------------------------------------------------

def test_resonance_band_fraction_is_self_normalized_and_bounded():
    fs = 12000.0
    n = 4096
    # cala energia W PASMIE rezonansu (3000 Hz jest w srodku RESONANCE_BAND_HZ)
    _, s_in_band = _synthetic_sine(3000.0, n, fs)
    frac_in = _resonance_band_fraction(s_in_band, fs)
    assert 0.0 <= frac_in <= 1.0
    assert frac_in > 0.9, f"sygnal calkowicie w pasmie powinien dac fraction bliski 1, dostano {frac_in}"

    # cala energia POZA pasmem (100 Hz, dużo ponizej RESONANCE_BAND_HZ)
    _, s_out_band = _synthetic_sine(100.0, n, fs)
    frac_out = _resonance_band_fraction(s_out_band, fs)
    assert 0.0 <= frac_out <= 1.0
    assert frac_out < 0.05, f"sygnal calkowicie poza pasmem powinien dac fraction bliski 0, dostano {frac_out}"

    assert frac_in > frac_out


def test_resonance_band_fraction_short_window_returns_zero():
    assert _resonance_band_fraction(np.array([1.0, 2.0]), fs=12000.0) == 0.0


def test_mapping_formulas_match_pre_registered_definitions():
    """Weryfikuje ksztalt (nie dokladne liczby) wzorow z docstringu modulu:
    Lambda w [0,1] samo-znormalizowane; tau/rho/J >= 0 i J/rho w [0,1]
    (to fractions probek)."""
    fs = 12000.0
    n = 4096
    core = TIMDR_EarthquakeCore()
    rng = np.random.default_rng(0)
    t_ref, s_ref = _synthetic_sine(50.0, n, fs, amplitude=0.1)
    s_ref = s_ref + rng.normal(scale=0.01, size=n)

    thresholds = compute_reference_thresholds(core, t_ref, s_ref)
    assert isinstance(thresholds, BearingGlobalThresholds)
    assert thresholds.flow_threshold >= 0
    assert thresholds.twist_threshold >= 0
    assert thresholds.anomaly_threshold >= 0

    state = window_to_meta_state(core, t_ref[:1024], s_ref[:1024], fs, thresholds)
    assert 0.0 <= state.Lambda <= 1.0
    assert state.tau >= 0.0
    assert 0.0 <= state.rho <= 1.0
    assert 0.0 <= state.J <= 1.0


def test_positive_control_synthetic_impulsive_fault_has_higher_state_than_clean_reference():
    """Kontrola pozytywna: referencja = czysta sinusoida (jak zdrowe
    lozysko, dominujaca skladowa nisko-czestotliwosciowa); test = ta sama
    sinusoida + okresowe impulsy o czestotliwosci w RESONANCE_BAND_HZ
    (symulacja uderzen wzbudzajacych rezonans strukturalny) - powinno dac
    WYZSZE Lambda/tau/rho/J niz sama referencja wzgledem samej siebie."""
    fs = 12000.0
    n = 8192
    rng = np.random.default_rng(1)

    t = np.arange(n, dtype=np.float64) / fs
    base = 0.1 * np.sin(2 * np.pi * 30.0 * t) + rng.normal(scale=0.01, size=n)

    # "uszkodzenie": impulsy wzbudzajace oscylacje w srodku pasma rezonansu (3250 Hz)
    impact_period_s = 1.0 / 120.0  # ~120 Hz, typowa skala BPFO/BPFI
    impact_signal = np.zeros(n)
    t_impact = 0.0
    while t_impact < t[-1]:
        idx = int(t_impact * fs)
        if idx < n:
            decay_n = min(200, n - idx)
            decay_t = np.arange(decay_n) / fs
            impact_signal[idx:idx + decay_n] += 0.5 * np.exp(-decay_t * 800) * np.sin(2 * np.pi * 3250.0 * decay_t)
        t_impact += impact_period_s
    faulty = base + impact_signal

    core = TIMDR_EarthquakeCore()
    thresholds = compute_reference_thresholds(core, t, base)

    window_samples = 2048
    n_windows = n // window_samples

    def mean_state(signal):
        states = [
            window_to_meta_state(core, t[i * window_samples:(i + 1) * window_samples],
                                  signal[i * window_samples:(i + 1) * window_samples], fs, thresholds)
            for i in range(n_windows)
        ]
        return (
            np.mean([s.Lambda for s in states]),
            np.mean([s.tau for s in states]),
            np.mean([s.rho for s in states]),
            np.mean([s.J for s in states]),
        )

    lam_ref, tau_ref, rho_ref, J_ref = mean_state(base)
    lam_test, tau_test, rho_test, J_test = mean_state(faulty)

    assert lam_test > lam_ref, f"Lambda powinno wzrosnac przy impulsach w pasmie rezonansu: {lam_test} vs {lam_ref}"
    assert rho_test >= rho_ref, f"rho nie powinno spasc: {rho_test} vs {rho_ref}"


def test_negative_control_test_equals_reference_gives_near_zero_rho():
    """Kontrola negatywna: gdy slad testowy TO TO SAMO nagranie co
    referencyjne, progi (policzone z referencji) powinny dac ~zero
    anomalii wzgledem samego siebie."""
    fs = 12000.0
    n = 4096
    rng = np.random.default_rng(2)
    t, s = _synthetic_sine(50.0, n, fs, amplitude=0.1)
    s = s + rng.normal(scale=0.01, size=n)

    core = TIMDR_EarthquakeCore()
    thresholds = compute_reference_thresholds(core, t, s)
    state = window_to_meta_state(core, t, s, fs, thresholds)
    assert state.rho < 0.1, f"slad porownany sam ze soba powinien dac niskie rho, dostano {state.rho}"


def test_requires_at_least_2_full_windows():
    fs = 12000.0
    t_ref, s_ref = _synthetic_sine(50.0, 4096, fs)
    t_test, s_test = _synthetic_sine(50.0, 500, fs)  # za krotki na 2 okna po 4096
    with pytest.raises(ValueError):
        build_meta_series_from_reference_and_test(t_ref, s_ref, t_test, s_test, fs=fs)


def test_mismatched_lengths_raise():
    fs = 12000.0
    t_ref, s_ref = _synthetic_sine(50.0, 4096, fs)
    t_test, s_test = _synthetic_sine(50.0, 4096, fs)
    with pytest.raises(ValueError):
        build_meta_series_from_reference_and_test(t_ref, s_ref[:-1], t_test, s_test, fs=fs)
    with pytest.raises(ValueError):
        build_meta_series_from_reference_and_test(t_ref, s_ref, t_test[:-1], s_test, fs=fs)


def test_window_samples_too_small_raises():
    fs = 12000.0
    t_ref, s_ref = _synthetic_sine(50.0, 4096, fs)
    t_test, s_test = _synthetic_sine(50.0, 4096, fs)
    with pytest.raises(ValueError):
        build_meta_series_from_reference_and_test(t_ref, s_ref, t_test, s_test, fs=fs, window_samples=2)


# ---------------------------------------------------------------------------
# Real-data end-to-end (CWRU Bearing Dataset, 1797 RPM, DE12 - pierwsze 1536
# probek/0.128s kazdego z 4 nagran - patrz README i docstring modulu dla
# pelnych liczb z sesji interaktywnej na calych nagraniach)
# ---------------------------------------------------------------------------

REAL_WINDOW_SAMPLES = 384  # 1536 / 384 = 4 pelne okna

FIXTURE_FILES = {
    "normal": "normal_1797_de_first1536.csv",
    "ir21": "ir_0021_1797_de_first1536.csv",
    "or6_21": "or6_0021_1797_de_first1536.csv",
    "b21": "b_0021_1797_de_first1536.csv",
}


def _fixtures_exist():
    return all(os.path.exists(os.path.join(DATA_DIR, f)) for f in FIXTURE_FILES.values())


@pytest.mark.skipif(not _fixtures_exist(), reason="brak fixture'ow CWRU w data/cwru_bearing/")
def test_real_data_negative_control_normal_vs_itself_gives_zero_rho():
    t_ref, s_ref = _load_fixture(FIXTURE_FILES["normal"])
    r = build_meta_series_from_reference_and_test(
        t_ref, s_ref, t_ref, s_ref, fs=FS, window_samples=REAL_WINDOW_SAMPLES
    )
    mean_rho = np.mean([s.rho for s in r.states])
    assert mean_rho == 0.0, f"zdrowe lozysko porownane samo ze soba powinno dac rho=0, dostano {mean_rho}"


@pytest.mark.skipif(not _fixtures_exist(), reason="brak fixture'ow CWRU w data/cwru_bearing/")
@pytest.mark.parametrize("fault_key", ["ir21", "or6_21", "b21"])
def test_real_data_positive_control_fault_has_higher_rho_and_lambda_than_healthy_reference(fault_key):
    """Na REALNYCH danych CWRU (fragment 0.128s, 4 okna): kazdy z trzech
    typow uszkodzenia (bieznia wewnetrzna, bieznia zewnetrzna, element
    toczny) daje wyraznie WYZSZE rho i Lambda niz zdrowe lozysko porownane
    samo ze soba - dokladnie ten sam kierunek wyniku, co w pelnej analizie
    z sesji interaktywnej (patrz README), tylko na krotszym wycinku."""
    t_ref, s_ref = _load_fixture(FIXTURE_FILES["normal"])
    t_test, s_test = _load_fixture(FIXTURE_FILES[fault_key])

    r_self = build_meta_series_from_reference_and_test(
        t_ref, s_ref, t_ref, s_ref, fs=FS, window_samples=REAL_WINDOW_SAMPLES
    )
    r_fault = build_meta_series_from_reference_and_test(
        t_ref, s_ref, t_test, s_test, fs=FS, window_samples=REAL_WINDOW_SAMPLES
    )

    rho_self = np.mean([s.rho for s in r_self.states])
    rho_fault = np.mean([s.rho for s in r_fault.states])
    lambda_self = np.mean([s.Lambda for s in r_self.states])
    lambda_fault = np.mean([s.Lambda for s in r_fault.states])

    for st in r_fault.states:
        assert np.isfinite(st.Lambda) and np.isfinite(st.tau) and np.isfinite(st.rho) and np.isfinite(st.J)

    assert rho_fault > rho_self, f"{fault_key}: rho={rho_fault} powinno przewyzszac zdrowe {rho_self}"
    assert lambda_fault > lambda_self, f"{fault_key}: Lambda={lambda_fault} powinno przewyzszac zdrowe {lambda_self}"


@pytest.mark.skipif(not _fixtures_exist(), reason="brak fixture'ow CWRU w data/cwru_bearing/")
def test_real_data_end_to_end_runs_without_crashing_and_returns_expected_shapes():
    t_ref, s_ref = _load_fixture(FIXTURE_FILES["normal"])
    t_test, s_test = _load_fixture(FIXTURE_FILES["ir21"])
    r = build_meta_series_from_reference_and_test(
        t_ref, s_ref, t_test, s_test, fs=FS, window_samples=REAL_WINDOW_SAMPLES
    )
    n_windows = len(t_test) // REAL_WINDOW_SAMPLES
    assert len(r.states) == n_windows
    assert len(r.window_starts) == n_windows
    assert len(r.M_series) == n_windows - 1
    assert len(r.phases) == n_windows - 1
    assert r.trigger is not None
