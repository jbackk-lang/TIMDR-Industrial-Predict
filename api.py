"""
api.py — TIMDR Industrial Predict, lokalne REST API + dashboard
====================================================================
Serwer Flask udostepniajacy:
  GET  /                  -> dashboard (static/dashboard.html)
  GET  /api/scenarios     -> lista dostepnych scenariuszy demo (nazwa, opis, sugerowany prog)
  GET  /api/demo          -> syntetyczny zestaw czujnikow (?scenario=<nazwa>, domyslnie bearing_wear)
  POST /api/analyze       -> pelna analiza TIMDR (fuse + twist/trend/anomalies/rhythm + TTF + health)
  GET  /api/health        -> healthcheck samego API (nie mylic z health_score maszyny)
  GET  /api/bearing/scenarios -> lista realnych nagran CWRU (referencja + 3 typy usterek)
  GET  /api/bearing/demo      -> meta-dynamika (Lambda/tau/rho/J, bearing_meta_adapter.py) na
                                  realnych danych CWRU (?fault=normal|ir21|or6_21|b21)

Uruchomienie: `python api.py` (albo `run.bat` na Windows), potem
http://127.0.0.1:5000 w przegladarce.
"""

import os

import numpy as np
from flask import Flask, jsonify, request, send_from_directory

from demo_scenarios import DEFAULT_THRESHOLDS, SCENARIOS, make_demo_data
from timdr_industrial_fusion import TIMDRIndustrialFusion
from timdr_industrial_predict import TIMDRIndustrialPredict
from timdr_industrial_trigger import IndustrialTrigger
from bearing_meta_adapter import (
    MetaOperatorM,
    build_meta_series_from_reference_and_test,
)

app = Flask(__name__, static_folder="static", static_url_path="")

# ---------------------------------------------------------------------------
# Wibracja lozyska (CWRU, dane realne) - patrz bearing_meta_adapter.py i
# test_bearing_meta_adapter.py. UWAGA: fixture'y w data/cwru_bearing/ to
# TYLKO pierwsze 1536 probek (0.128s) kazdego nagrania (zastrzezenie #5 w
# naglowku bearing_meta_adapter.py - pelne nagrania nie mieszcza sie w repo,
# patrz README po URL do samodzielnego pobrania). Dlatego demo uzywa
# window_samples=384 (4 pelne okna na fixture), NIE domyslnego
# WINDOW_SAMPLES_DEFAULT=4096 z modulu (ktory zaklada pelne, kilkunasto-
# sekundowe nagrania) - identyczna wartosc, co juz zweryfikowany
# test_real_data_end_to_end_runs_without_crashing_and_returns_expected_shapes
# w test_bearing_meta_adapter.py, NIE nowo dobrana tutaj.
_HERE = os.path.dirname(os.path.abspath(__file__))
_BEARING_DATA_DIR = os.path.join(_HERE, "data", "cwru_bearing")
_BEARING_FS = 12000.0
_BEARING_WINDOW_SAMPLES = 384
_BEARING_FIXTURES = {
    "normal": ("normal_1797_de_first1536.csv", "Zdrowe łożysko (referencja, porównana sama ze sobą)"),
    "ir21": ("ir_0021_1797_de_first1536.csv", "Usterka bieżni wewnętrznej (IR, 0.021\")"),
    "or6_21": ("or6_0021_1797_de_first1536.csv", "Usterka bieżni zewnętrznej (OR@6, 0.021\")"),
    "b21": ("b_0021_1797_de_first1536.csv", "Usterka elementu tocznego (B, 0.021\")"),
}
_meta_operator_bearing = MetaOperatorM()


def _load_bearing_fixture(filename: str):
    path = os.path.join(_BEARING_DATA_DIR, filename)
    s = np.loadtxt(path, delimiter=",")
    t = np.arange(len(s), dtype=np.float64) / _BEARING_FS
    return t, s


def _bearing_result_to_dict(r) -> dict:
    """Serializuje BearingMetaResult. Dolacza SUROWE stany (Lambda/tau/rho/J
    per okno), nie tylko fazy - patrz zastrzezenie #4 w bearing_meta_adapter.py:
    dla lozysk to STAN (nie jego pochodna M) niesie glowny sygnal, wiec
    dashboard MUSI pokazac oba, zeby nie sugerowac, ze same fazy wystarcza."""
    return {
        "window_starts": [float(w) for w in r.window_starts],
        "states": [
            {"Lambda": s.Lambda, "tau": s.tau, "rho": s.rho, "J": s.J}
            for s in r.states
        ],
        "phases": list(r.phases),
        "magnitude": [_meta_operator_bearing.magnitude(m) for m in r.M_series],
        "trigger": r.trigger.as_dict(),
    }

fusion = TIMDRIndustrialFusion()
predict = TIMDRIndustrialPredict()
# Ta sama instancja fusion/predict co wyzej - IndustrialTrigger nie duplikuje
# stanu, tylko odpytuje juz istniejacy fusion/predict jeszcze raz z tym samym
# threshold/window co reszta api_analyze() (deterministyczne funkcje, wiec
# wynik jest identyczny z tw_idx/an_idx/ttf ponizej - trigger tylko je
# priorytetyzuje i mapuje na jedno zdarzenie).
trigger = IndustrialTrigger(fusion=fusion, predictor=predict)


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "dashboard.html")


@app.route("/api/health")
def api_health():
    return jsonify({"status": "ok"})


@app.route("/api/scenarios")
def api_scenarios():
    return jsonify([
        {"id": name, "description": desc, "default_threshold": DEFAULT_THRESHOLDS[name]}
        for name, desc in SCENARIOS.items()
    ])


@app.route("/api/demo")
def api_demo():
    scenario = request.args.get("scenario", "bearing_wear")
    try:
        t, sensors = make_demo_data(scenario)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({
        "scenario": scenario,
        "default_threshold": DEFAULT_THRESHOLDS.get(scenario, 3.0),
        "t": t.tolist(),
        "sensors": {k: v.tolist() for k, v in sensors.items()},
    })


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    """
    Body (JSON):
      t: [..]                 - znaczniki czasu
      sensors: {nazwa: [..]}  - dowolna liczba czujnikow (min. 1), kazdy
                                 moze miec inna dlugosc (patrz _align w Fusion)
      threshold: float=3.0    - prog "awarii" dla E(t)
      window: int=60          - okno regresji/health_score (patrz Predict README)

    Zwraca pelny wynik analizy jako JSON - wszystko, co dashboard
    potrzebuje do narysowania wykresow i wskaznikow.
    """
    body = request.get_json(force=True, silent=True) or {}

    if "t" not in body or "sensors" not in body:
        return jsonify({"error": "wymagane pola: 't' (lista) i 'sensors' (obiekt nazwa->lista)"}), 400

    try:
        t = np.asarray(body["t"], dtype=float)
        sensor_names = list(body["sensors"].keys())
        sensor_arrays = [np.asarray(body["sensors"][name], dtype=float) for name in sensor_names]
    except (TypeError, ValueError) as exc:
        return jsonify({"error": f"niepoprawne dane wejsciowe: {exc}"}), 400

    if len(t) == 0 or not sensor_arrays:
        return jsonify({"error": "t i sensors nie moga byc puste"}), 400

    threshold = float(body.get("threshold", 3.0))
    window = int(body.get("window", 60))

    try:
        E, Z = fusion.fuse(t, sensor_arrays)
        tw_idx, tw_z = fusion.twist(t, E)
        tr_sl, tr_z = fusion.trend(t, E, window=window)
        an_idx, an_z = fusion.anomalies(E)
        periods, r_score = fusion.rhythm(E)
        score = fusion.fusion_score(tw_z, tr_z, an_z, r_score)

        ttf, ttf_lin, ttf_exp = predict.predict_failure(t, E, threshold=threshold, window=window)
        health = predict.health_score(E, threshold=threshold, window=window)

        try:
            trigger_result = trigger.analyze(t, E, threshold=threshold, window=window).as_dict()
        except Exception:  # noqa: BLE001 - trigger jest dodatkiem, nie moze wywalic calej analizy
            trigger_result = None
    except Exception as exc:  # noqa: BLE001 - chcemy zwrocic czytelny blad do dashboardu, nie 500 bez opisu
        return jsonify({"error": f"blad analizy: {exc}"}), 400

    def clean(x):
        # JSON nie ma inf/nan - zamieniamy na null, dashboard obsluzy to jako "brak predykcji"
        x = float(x)
        return None if not np.isfinite(x) else x

    return jsonify({
        "t": t.tolist(),
        "E": E.tolist(),
        "sensor_names": sensor_names,
        "twist_idx": tw_idx.tolist(),
        "trend_slopes": tr_sl.tolist(),
        "anomaly_idx": an_idx.tolist(),
        "rhythm_periods": periods,
        "rhythm_score": float(r_score),
        "fusion_score": float(score),
        "ttf": clean(ttf),
        "ttf_linear": clean(ttf_lin),
        "ttf_exp": clean(ttf_exp),
        "health_score": float(health),
        "threshold": threshold,
        "window": window,
        "trigger": trigger_result,
    })


@app.route("/api/bearing/scenarios")
def api_bearing_scenarios():
    return jsonify([
        {"id": key, "label": label}
        for key, (_, label) in _BEARING_FIXTURES.items()
    ])


@app.route("/api/bearing/demo")
def api_bearing_demo():
    fault = request.args.get("fault", "ir21")
    if fault not in _BEARING_FIXTURES:
        return jsonify({"error": f"Nieznany fault '{fault}'. Dostępne: {sorted(_BEARING_FIXTURES)}"}), 400

    ref_filename, _ = _BEARING_FIXTURES["normal"]
    test_filename, _ = _BEARING_FIXTURES[fault]
    try:
        t_ref, s_ref = _load_bearing_fixture(ref_filename)
        t_test, s_test = _load_bearing_fixture(test_filename)
    except OSError as exc:
        return jsonify({"error": f"Brak pliku fixture CWRU: {exc}"}), 500

    try:
        result = build_meta_series_from_reference_and_test(
            t_ref, s_ref, t_test, s_test,
            fs=_BEARING_FS, window_samples=_BEARING_WINDOW_SAMPLES,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({
        "fault": fault,
        "label": _BEARING_FIXTURES[fault][1],
        "fs": _BEARING_FS,
        "window_samples": _BEARING_WINDOW_SAMPLES,
        "note": (
            "Fragment 0.128s (1536 próbek, pierwsze z każdego nagrania CWRU) - "
            "nie pełne nagranie (patrz README/zastrzeżenie #5 w bearing_meta_adapter.py). "
            "Ufaj przede wszystkim kolumnie 'states' (Λ/τ/ρ/J), nie samym fazom "
            "M-operatora - patrz zastrzeżenie #4: uszkodzenie łożyska to stan stały, "
            "nie przejście, więc pochodna M rzadko wychodzi 'krytyczna'."
        ),
        "result": _bearing_result_to_dict(result),
    })


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
