import numpy as np
import pytest
from timdr_industrial_predict import TIMDRIndustrialPredict


def _degrading_signal(n_healthy=50, n_degrade=100, top=15.0, seed=0):
    rng = np.random.default_rng(seed)
    E_healthy = np.abs(rng.normal(0, 0.05, n_healthy))
    E_degrade = np.linspace(E_healthy[-1], top, n_degrade)
    return np.concatenate([E_healthy, E_degrade])


# -----------------------------------------------------------
# POPRAWKA 1: TTF niezalezne od bezwzglednego polozenia zegara
# -----------------------------------------------------------

def test_ttf_niezalezne_od_przesuniecia_czasu():
    """Regresja dla błędu: oryginalny kod zwracał bezwzględną
    współrzędną czasu (z regresji), nie czas pozostały - przesunięcie
    całego `t` o +1000s zmieniało zwrócony TTF też o +1000s.
    Zweryfikowano też z realnym epoch (~1.75e9): oryginalny kod dawał
    TTF rzędu 10 miliardów sekund (~330 lat) zamiast tej samej wartości
    co dla t zaczynającego się od 0."""
    predict = TIMDRIndustrialPredict()
    E = _degrading_signal()
    n = len(E)

    t_zero = np.arange(n, dtype=float)
    t_shifted = t_zero + 1000.0
    t_epoch = t_zero + 1_755_000_000.0

    ttf_zero, _, _ = predict.predict_failure(t_zero, E, threshold=30.0)
    ttf_shifted, _, _ = predict.predict_failure(t_shifted, E, threshold=30.0)
    ttf_epoch, _, _ = predict.predict_failure(t_epoch, E, threshold=30.0)

    assert ttf_zero == pytest.approx(ttf_shifted, abs=1e-3)
    assert ttf_zero == pytest.approx(ttf_epoch, abs=1e-3)


# -----------------------------------------------------------
# POPRAWKA 2: TTF stabilne wzgledem dlugosci zdrowej historii
# -----------------------------------------------------------

def test_ttf_stabilne_niezaleznie_od_dlugosci_zdrowej_historii():
    """Regresja dla błędu: oryginalny kod dopasowywał regresję do CAŁEJ
    historii E(t). Dla identycznej ostatniej fazy degradacji, ale różnej
    długości wcześniejszej zdrowej historii, dawało to 16-krotne różnice
    w przewidywanym TTF (135s vs 2254s dla 50s vs 800s historii).
    Po poprawce (regresja tylko na ostatnim `window`) wynik powinien
    być względnie stabilny (w granicach szumu, nie rzędów wielkości)."""
    predict = TIMDRIndustrialPredict()
    results = []
    for healthy_len in (50, 150, 400, 800):
        rng = np.random.default_rng(0)
        E_healthy = np.abs(rng.normal(0, 0.05, healthy_len))
        E_degrade = np.linspace(E_healthy[-1], 15.0, 100)
        E = np.concatenate([E_healthy, E_degrade])
        t = np.arange(len(E), dtype=float)
        ttf, _, _ = predict.predict_failure(t, E, threshold=30.0)
        results.append(ttf)

    spread = max(results) - min(results)
    assert spread < 5.0  # przed poprawka roznica siegala >2000s


def test_degradation_model_ignoruje_stara_historie_poza_oknem():
    predict = TIMDRIndustrialPredict()
    E = _degrading_signal(n_healthy=500, n_degrade=100)
    t = np.arange(len(E), dtype=float)
    (a, b), (ae, be), t0 = predict.degradation_model(t, E, window=60)
    # nachylenie powinno odzwierciedlac TYLKO faze degradacji (ostatnie 60 probek),
    # nie byc rozwodnione przez 500 probek plaskiej historii
    assert a > 0.05  # w oknie tylko degradacja, wiec nachylenie wyraznie dodatnie


# -----------------------------------------------------------
# predict_failure - podstawy
# -----------------------------------------------------------

def test_predict_failure_juz_przekroczony_prog_zwraca_zero():
    predict = TIMDRIndustrialPredict()
    E = np.array([1.0, 2.0, 5.0])
    t = np.array([0.0, 1.0, 2.0])
    ttf, _, _ = predict.predict_failure(t, E, threshold=3.0)
    assert ttf == 0.0


def test_predict_failure_brak_trendu_daje_nieskonczonosc():
    predict = TIMDRIndustrialPredict()
    rng = np.random.default_rng(0)
    E = np.abs(rng.normal(0.1, 0.01, 100))  # stabilne, bez trendu
    t = np.arange(100, dtype=float)
    ttf, ttf_lin, ttf_exp = predict.predict_failure(t, E, threshold=30.0)
    assert ttf == float("inf") or ttf > 1e5


def test_predict_failure_pusty_sygnal_nie_crashuje():
    predict = TIMDRIndustrialPredict()
    ttf, lin, exp_ = predict.predict_failure(np.array([]), np.array([]), threshold=3.0)
    assert ttf == float("inf")


def test_ttf_ujemny_nie_wystepuje():
    """TTF liczone jest jako czas OD teraz - jeśli model ekstrapoluje
    wstecz poniżej progu, wynik powinien być przycięty do >=0, nie
    ujemny (co sugerowałoby "awaria była w przeszłości")."""
    predict = TIMDRIndustrialPredict()
    E = _degrading_signal(top=2.9)  # tuz PONIZEJ progu na koniec danych
    t = np.arange(len(E), dtype=float)
    ttf, ttf_lin, ttf_exp = predict.predict_failure(t, E, threshold=3.0)
    assert ttf >= 0.0


# -----------------------------------------------------------
# POPRAWKA 3: health_score nie jest permanentnie zatruty starym zdarzeniem
# -----------------------------------------------------------

def test_health_score_nie_jest_permanentnie_zatruty_starym_skokiem():
    predict = TIMDRIndustrialPredict()
    n = 500
    E = np.abs(np.random.default_rng(1).normal(0, 0.1, n))
    E[50] = 8.0  # jednorazowy stary skok
    score = predict.health_score(E, threshold=3.0)
    assert score > 0.8  # maszyna od dawna w normie -> wysoki wynik


def test_health_score_odzwierciedla_aktualny_stan_krytyczny():
    predict = TIMDRIndustrialPredict()
    n = 100
    E = np.abs(np.random.default_rng(1).normal(0, 0.05, n))
    E[-10:] = 10.0  # AKTUALNY (niedawny) stan krytyczny
    score = predict.health_score(E, threshold=3.0)
    assert score < 0.2


def test_health_score_pusty_sygnal_daje_wynik_1():
    predict = TIMDRIndustrialPredict()
    assert predict.health_score(np.array([])) == 1.0


def test_health_score_spojny_z_threshold_w_predict_failure():
    """health_score i predict_failure powinny uzywac tej samej definicji
    'krytyczny' (ten sam threshold), w przeciwienstwie do oryginalnego
    kodu, gdzie health_score mial wlasna, niezalezna skale (/5)."""
    predict = TIMDRIndustrialPredict()
    n = 50
    E = np.full(n, 3.0)  # dokladnie na progu
    t = np.arange(n, dtype=float)
    score = predict.health_score(E, threshold=3.0)
    ttf, _, _ = predict.predict_failure(t, E, threshold=3.0)
    assert score == pytest.approx(0.0, abs=1e-9)
    assert ttf == 0.0  # oba zgodnie zglaszaja "juz krytyczny"
