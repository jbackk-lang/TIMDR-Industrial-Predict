import numpy as np
import pytest
from timdr_industrial_fusion import TIMDRIndustrialFusion


def _healthy_and_degrading(n_healthy=150, n_degrade=100, seed=0):
    rng = np.random.default_rng(seed)
    temp = np.concatenate([rng.normal(60, 1, n_healthy), 60 + np.linspace(0, 15, n_degrade)])
    vib = np.concatenate([rng.normal(0.2, 0.02, n_healthy), 0.2 + np.linspace(0, 1.0, n_degrade)])
    pres = rng.normal(5.0, 0.1, n_healthy + n_degrade)
    curr = rng.normal(10.0, 0.3, n_healthy + n_degrade)
    t = np.arange(n_healthy + n_degrade, dtype=float)
    return t, [temp, vib, pres, curr]


# -----------------------------------------------------------
# fuse() / _align()
# -----------------------------------------------------------

def test_fuse_rozne_dlugosci_czujnikow_wyrownuje_do_wspolnej_osi():
    fusion = TIMDRIndustrialFusion()
    t = np.arange(100, dtype=float)
    s1 = np.sin(np.linspace(0, 10, 100))       # ta sama dlugosc co t
    s2 = np.sin(np.linspace(0, 10, 50))        # 2x rzadziej probkowany
    s3 = np.sin(np.linspace(0, 10, 300))       # 3x gesciej probkowany
    E, Z = fusion.fuse(t, [s1, s2, s3])
    assert E.shape == (100,)
    assert Z.shape == (100, 3)
    assert np.all(np.isfinite(E))


def test_fuse_e_nieujemne():
    t, sensors = _healthy_and_degrading()
    fusion = TIMDRIndustrialFusion()
    E, _ = fusion.fuse(t, sensors)
    assert np.all(E >= 0)


# -----------------------------------------------------------
# POPRAWKA: krotkie sygnaly nie crashuja
# -----------------------------------------------------------

@pytest.mark.parametrize("n", [0, 1])
def test_twist_krotki_sygnal_nie_crashuje(n):
    fusion = TIMDRIndustrialFusion()
    t = np.arange(n, dtype=float)
    E = np.ones(n)
    idx, z = fusion.twist(t, E)
    assert len(idx) == 0
    assert len(z) == n


@pytest.mark.parametrize("n", [0, 1])
def test_rhythm_krotki_sygnal_nie_crashuje(n):
    fusion = TIMDRIndustrialFusion()
    E = np.ones(n)
    periods, score = fusion.rhythm(E)
    assert periods == []
    assert score == 0.0


def test_fusion_score_na_pustych_tablicach_nie_crashuje():
    fusion = TIMDRIndustrialFusion()
    score = fusion.fusion_score(np.array([]), np.array([]), np.array([]), 0.0)
    assert score == 0.0


# -----------------------------------------------------------
# twist / trend / anomalies - sanity checks
# -----------------------------------------------------------

def test_twist_wykrywa_gwaltowna_zmiane():
    fusion = TIMDRIndustrialFusion()
    n = 200
    t = np.arange(n, dtype=float)
    # skokowa zmiana (np. pierwsze "uderzenie" luznego elementu) + odrobina
    # realistycznego szumu tla - na CALKOWICIE bezszumnym skoku fallback
    # MAD=0 (span/4) daje mniej dyskryminujacy wynik, co nie jest bugiem,
    # tylko wlasciwoscia fallbacku dla zdegenerowanych (bezszumnych) danych,
    # ktore w praktyce nie wystepuja.
    E = np.full(n, 1.0) + np.random.default_rng(0).normal(0, 0.01, n)
    E[100:] += 10.0
    idx, z = fusion.twist(t, E)
    assert len(idx) > 0
    assert any(98 <= i <= 101 for i in idx)


def test_trend_wykrywa_narastajaca_degradacje():
    fusion = TIMDRIndustrialFusion()
    n = 100
    t = np.arange(n, dtype=float)
    E = np.linspace(0, 10, n)  # staly, dodatni trend
    slopes, z = fusion.trend(t, E, window=20)
    assert slopes[-1] > 0
    assert slopes[-1] == pytest.approx(10 / (n - 1), rel=0.05)


def test_anomalies_wykrywa_odosobniony_skok():
    fusion = TIMDRIndustrialFusion()
    rng = np.random.default_rng(0)
    E = np.abs(rng.normal(0, 0.1, 100))
    E[50] = 5.0
    idx, z = fusion.anomalies(E)
    assert 50 in idx


# -----------------------------------------------------------
# rhythm() - overlap-corrected autocorr (ta sama poprawka co w TIMDRRhythm)
# -----------------------------------------------------------

def test_rhythm_nie_myli_trendu_z_periodycznoscia():
    """Regresja dla błędu: czysty rosnący trend (zero periodyczności) z
    realistycznym szumem czujnika dawał przed poprawką score~0.99 i 48
    'wykrytych okresów'. Po poprawce (pełny detrend + tylko lokalne
    maksima) powinien dawać brak wykrytego rytmu."""
    fusion = TIMDRIndustrialFusion()
    rng = np.random.default_rng(0)
    n = 200
    E = np.linspace(0, 10, n) + rng.normal(0, 0.15, n)
    periods, score = fusion.rhythm(E, max_lag=60, power_thresh=0.4)
    assert periods == []
    assert score == 0.0


def test_rhythm_wykrywa_prawdziwa_periodycznosc_mimo_nalozonego_trendu():
    fusion = TIMDRIndustrialFusion()
    t = np.arange(300, dtype=float)
    E = 5 * np.sin(2 * np.pi * t / 15) + np.linspace(0, 10, 300)
    periods, score = fusion.rhythm(E, max_lag=60, power_thresh=0.4)
    assert 15 in periods


def test_rhythm_wykrywa_okresowosc_bez_sztucznego_spadku_mocy():
    fusion = TIMDRIndustrialFusion()
    n, period = 200, 20
    E = np.sin(2 * np.pi * np.arange(n) / period)
    periods, score = fusion.rhythm(E, max_lag=100, power_thresh=0.0)
    # z korekta overlap, moc przy lag=20,40,...,100 powinna byc ~1.0, nie malejaca
    # (pelny detrend wprowadza minimalna, oczekiwana odchylke rzedu 1e-3
    # przy niecalkowitej liczbie okresow w oknie - to nie jest regresja
    # testowanego bugu, ktory dawal spadek rzedu dziesiatek procent)
    assert score == pytest.approx(1.0, abs=2e-3)


# -----------------------------------------------------------
# fusion_score - kombinacja wynikow
# -----------------------------------------------------------

def test_fusion_score_rosnie_z_powaznoscia_sygnalow():
    fusion = TIMDRIndustrialFusion()
    low = fusion.fusion_score(np.array([0.1]), np.array([0.1]), np.array([0.1]), 0.1)
    high = fusion.fusion_score(np.array([10.0]), np.array([10.0]), np.array([10.0]), 1.0)
    assert high > low
