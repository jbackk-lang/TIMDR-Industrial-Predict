"""Testy trendu stanu lozyska (bearing_health_trend.py)."""
import numpy as np
import pytest

import bearing_health_trend as H


def test_golden_values_match_validated_implementation():
    # wartosci z GIA-TIMDR core/pronostia_features.snap_features na tym samym sygnale (2026-09-27)
    y = np.random.default_rng(5).standard_normal(2560); y[::256] += 12
    f = H.snapshot_features(y, 25600.0)
    assert f["P"] == pytest.approx(0.4315728953970736, abs=1e-12)
    assert f["D"] == pytest.approx(1.6114664063884179, abs=1e-12)
    assert f["kurt"] == pytest.approx(32.10018960564946, abs=1e-9)


def _life(n=300, end_return=True, seed=0):
    """Syntetyczne zycie: szum (pole) -> coraz silniejsze blyski (czasteczka) -> gesty sygnal na koncu (fala)."""
    rng = np.random.default_rng(seed); out = []
    for i in range(n):
        x = rng.standard_normal(2560); a = i / n
        if a > 0.2:
            ring = np.exp(-np.arange(60) / 8) * np.sin(2 * np.pi * 5000 * np.arange(60) / 25600)
            imp = np.zeros(2560); imp[::400] = 40 * (a - 0.2)
            x = x + np.convolve(imp, ring, "same")
        if end_return and a > 0.95:
            x = x + 20 * np.sin(2 * np.pi * 4000 * np.arange(2560) / 25600) * (1 + 0.1 * rng.standard_normal(2560))
        out.append(H.snapshot_features(x, 25600.0))
    return out


def test_phases_field_particle_wave():
    s = _life()
    assert H.trend(s[:40])["faza"] == "pole"
    assert H.trend(s[:280])["faza"] == "czasteczka"
    r = H.trend(s); assert r["faza"] == "powrot ku fali" and r["trend_rho_D"] < 0
