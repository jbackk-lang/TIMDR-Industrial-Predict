"""Testy sita rezonansowego (bearing_resonance_sieve.py)."""
import numpy as np
import pytest

import bearing_resonance_sieve as S

CWRU = "data/cwru_bearing/b4_raw/source_mirror/Data/1797 RPM/"


def _impacts(fault_mult, seed=7, carrier=5000.0, fs=32000, rpm=1500):
    rng = np.random.default_rng(seed); x = rng.standard_normal(int(2 * fs)); imp = np.zeros_like(x)
    imp[(np.arange(0, 2, 1 / (fault_mult * rpm / 60)) * fs).astype(int)] = 6
    ring = np.exp(-np.arange(200) / 30) * np.sin(2 * np.pi * carrier * np.arange(200) / fs)
    return x + np.convolve(imp, ring, "same")


def test_fault_multipliers_known_values():
    m = S.fault_multipliers(*S.BEARINGS["6205"])
    assert m["BPFO"] == pytest.approx(3.5848, abs=1e-3) and m["BPFI"] == pytest.approx(5.4152, abs=1e-3)
    m = S.fault_multipliers(*S.BEARINGS["6203"])
    assert m["BPFO"] == pytest.approx(3.054, abs=1e-3) and m["BPFI"] == pytest.approx(4.946, abs=1e-3)


def test_outer_race_impacts_select_bpfo_and_ringing_band():
    r = S.analyze(_impacts(3.0543, carrier=5500.0), 32000, 1500, "6203")  # dzwonienie w srodku pasma 5-6 kHz
    assert r.strongest == "BPFO" and r.features["Q_BPFO"] > r.features["Q_BPFI"] + 1
    assert r.hypotheses[0].top_bands_hz[0] == [5000.0, 6000.0]


def test_inner_race_impacts_select_bpfi():
    r = S.analyze(_impacts(4.9457), 32000, 1500, "6203")
    assert r.strongest == "BPFI" and r.features["Q_BPFI"] > r.features["Q_BPFO"] + 1


def test_golden_values_match_validated_implementation():
    # wartosci z GIA-TIMDR core/real_paderborn_resonance_sieve.rs_feats na tym samym sygnale (2026-09-26)
    r = S.analyze(_impacts(76.35 / 25.0), 32000, 1500, "6203")
    assert r.features["Q_BPFO"] == pytest.approx(4.3252546860581536, abs=1e-9)
    assert r.features["Q_BPFI"] == pytest.approx(1.550869487984554, abs=1e-9)


def test_decimation_path_64k_equals_manual():
    x = _impacts(3.0543, fs=64000)
    r = S.analyze(x, 64000, 1500, "6203")
    assert r.fs_used == 32000.0 and r.strongest == "BPFO"


def test_too_short_signal_rejected():
    with pytest.raises(ValueError):
        S.analyze(np.zeros(1000), 32000, 1500)


@pytest.mark.parametrize("name,expected", [("1797_IR_21_DE12", "BPFI"), ("1797_OR@6_21_DE12", "BPFO")])
def test_real_cwru_fault_type(name, expected):
    d = np.load(CWRU + name + ".npz")
    assert S.analyze(d["DE"], 12000, 1797, "6205").strongest == expected


def test_real_cwru_normal_scores_lower_than_faults():
    q = lambda n: max(S.analyze(np.load(CWRU + n + ".npz")["DE"], 12000, 1797, "6205").features[k] for k in ("Q_BPFO", "Q_BPFI"))
    assert q("1797_Normal") < min(q("1797_IR_21_DE12"), q("1797_OR@6_21_DE12")) - 1


# ---------------- zmienna predkosc: sito w osi katowej ----------------
def _variable_speed(order=4.593, fs=18500.0, T=120, seed=3):
    n = int(T * fs); t = np.arange(n) / fs; fr = 0.3 + 0.5 * t / T
    th = np.concatenate([[0.0], np.cumsum((fr[1:] + fr[:-1]) / 2) / fs])
    x = np.random.default_rng(seed).standard_normal(n); imp = np.zeros(n)
    k = np.searchsorted(th, np.arange(0, th[-1], 1 / order)); imp[k[k < n]] = 8
    ring = np.exp(-np.arange(300) / 40) * np.sin(2 * np.pi * 4500 * np.arange(300) / fs)
    return x + np.convolve(imp, ring, "same"), th, fs


def test_orders_golden_values_match_validated_implementation():
    # wartosci z GIA-TIMDR core/modal_speed_tracking.order_resonance_map + order_sieve (konfiguracja turbiny LBF), 2026-09-27
    x, th, fs = _variable_speed()
    r = S.analyze_orders(x, fs, th, "6007-LBF")
    assert r["strongest"] == "BPFO" and r["segments"] == 2
    assert r["features"]["QO_BPFO"] == pytest.approx(2.0980221945222293, abs=1e-9)
    assert r["features"]["QO_BPFI"] == pytest.approx(1.600305466996475, abs=1e-9)
    assert r["features"]["QO_BSF2"] == pytest.approx(1.807323026409767, abs=1e-9)


def test_tach_angle_recovers_revolutions():
    fs, tfs, ppr = 18500.0, 2960.0, 108
    t = np.arange(int(60 * tfs)) / tfs; ang = 0.5 * t + 0.002 * t ** 2          # obroty
    tach = (np.mod(ang * ppr, 1.0) < 0.5).astype(float) * 5
    th, _, _ = S.shaft_angle_from_tach(tach, tfs, ppr, int(60 * fs), fs)
    assert th[-1] == pytest.approx(0.5 * 60 + 0.002 * 3600, rel=0.02)


def test_feasibility_flags_short_window():
    assert not S.feasibility(0.1, 50.0)["sito_ma_szanse"]       # 5 cykli w oknie: grzebien rozmyty
    assert S.feasibility(2.0, 76.0)["sito_ma_szanse"]
