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
