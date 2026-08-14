import numpy as np
import pytest
from demo_scenarios import DEFAULT_THRESHOLDS, SCENARIOS, make_demo_data
from timdr_industrial_fusion import TIMDRIndustrialFusion

fusion = TIMDRIndustrialFusion()


def test_wszystkie_scenariusze_maja_prog_i_opis():
    for name in SCENARIOS:
        assert name in DEFAULT_THRESHOLDS


def test_nieznany_scenariusz_rzuca_czytelny_blad():
    with pytest.raises(ValueError):
        make_demo_data("nie_istnieje")


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_scenariusz_generuje_poprawne_dane(name):
    t, sensors = make_demo_data(name)
    assert len(t) > 0
    assert len(sensors) >= 1
    for arr in sensors.values():
        assert np.all(np.isfinite(arr))


def test_bearing_wear_wykrywa_trend_i_daje_skonczone_ttf():
    """Zużycie łożysk - to scenariusz TTF/health, nie rytm."""
    t, sensors = make_demo_data("bearing_wear")
    E, _ = fusion.fuse(t, list(sensors.values()))
    tr_sl, _ = fusion.trend(t, E)
    assert tr_sl[-1] > 0  # narastajacy trend degradacji na koncu


def test_pump_seizure_wykrywa_twist_i_anomalie():
    t, sensors = make_demo_data("pump_seizure")
    E, _ = fusion.fuse(t, list(sensors.values()))
    tw_idx, _ = fusion.twist(t, E)
    an_idx, _ = fusion.anomalies(E)
    assert len(tw_idx) > 0
    assert len(an_idx) > 0


def test_uneven_motor_rotation_wykrywa_rytm():
    """Regresja: pierwsza wersja tego scenariusza (4 czujniki, w tym 2
    niezwiazane z rotacja) dawala rhythm_score~0.24 - ponizej progu.
    Po ograniczeniu do 2 fizycznie zwiazanych czujnikow (current,
    vibration) powinno wyraznie wykrywac okres=12."""
    t, sensors = make_demo_data("uneven_motor_rotation")
    E, _ = fusion.fuse(t, list(sensors.values()))
    periods, score = fusion.rhythm(E, max_lag=60, power_thresh=0.4)
    assert 12 in periods
    assert score > 0.4


def test_resonance_loose_parts_wykrywa_rytm_i_twist():
    t, sensors = make_demo_data("resonance_loose_parts")
    E, _ = fusion.fuse(t, list(sensors.values()))
    periods, score = fusion.rhythm(E, max_lag=60, power_thresh=0.4)
    tw_idx, _ = fusion.twist(t, E)
    assert 20 in periods
    assert len(tw_idx) > 0


def test_duty_cycle_problems_wykrywa_rytm_i_anomalie_i_trend():
    """Regresja: pierwsza wersja "zepsutego cyklu" (dluzsze utkniecie na
    normalnym poziomie wysokim) byla nieodrozniala od zwyklej fazy
    wysokiej (0 anomalii); wersja z za duzym/szerokim skokiem (+12,
    5 probek) niszczyla wykrywalnosc rytmu (score spadal do 0). Finalna
    wersja (umiarkowany, 1-probkowy skok) wykrywa oba jednoczesnie.

    UWAGA: trend() liczy LOKALNE nachylenie w oknie kroczacym - na
    sygnale z nalozonym cyklem duty-cycle znak nachylenia w OSTATNIM
    oknie zalezy od fazy cyklu w tym momencie (rosnaca/malejaca krawedz),
    nie tylko od dlugoterminowego dryfu bazowego. Sprawdzamy wiec
    srednie nachylenie w drugiej polowie (faza dryfu), nie pojedyncza
    probke slopes[-1] ani regresje na calym E (ktora psuje sam
    odosobniony punkt anomalii - patrz komentarz w demo_scenarios.py)."""
    t, sensors = make_demo_data("duty_cycle_problems")
    E, _ = fusion.fuse(t, list(sensors.values()))
    periods, score = fusion.rhythm(E, max_lag=60, power_thresh=0.4)
    an_idx, _ = fusion.anomalies(E)
    tr_sl, _ = fusion.trend(t, E, window=60)
    assert 30 in periods
    assert len(an_idx) > 0
    assert tr_sl[len(t) // 2:].mean() > 0
