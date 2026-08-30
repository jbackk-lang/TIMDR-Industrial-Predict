"""
api.py — TIMDR Industrial Predict, lokalne REST API + dashboard
====================================================================
Serwer Flask udostepniajacy:
  GET  /                  -> dashboard (static/dashboard.html)
  GET  /api/scenarios     -> lista dostepnych scenariuszy demo (nazwa, opis, sugerowany prog)
  GET  /api/demo          -> syntetyczny zestaw czujnikow (?scenario=<nazwa>, domyslnie bearing_wear)
  POST /api/analyze       -> pelna analiza TIMDR (fuse + twist/trend/anomalies/rhythm + TTF + health)
  GET  /api/monitor/status -> ostatni stan zapisany przez monitor.py (timdr_status.json), do panelu live
  GET  /api/monitor/calibration -> raport z MOMENTU kalibracji (Mann-Kendall + ile probek do
                                    stabilizacji) - pisany RAZ przez monitor.py, nie w petli live
  GET  /api/health        -> healthcheck samego API (nie mylic z health_score maszyny)

Uruchomienie: `python api.py` (albo `run.bat` na Windows), potem
http://127.0.0.1:5000 w przegladarce.
"""

import json
import os

import numpy as np
from flask import Flask, jsonify, request, send_from_directory

from demo_scenarios import DEFAULT_THRESHOLDS, SCENARIOS, make_demo_data
from timdr_industrial_fusion import TIMDRIndustrialFusion
from timdr_industrial_predict import TIMDRIndustrialPredict

app = Flask(__name__, static_folder="static", static_url_path="")

# Plik zapisywany przez monitor.py (--state-file) - domyslnie w tym samym
# katalogu co api.py. Jesli monitor.py dziala z innego katalogu roboczego
# z innym --state-file, ustaw zmienna srodowiskowa TIMDR_STATUS_FILE.
STATUS_FILE = os.environ.get("TIMDR_STATUS_FILE", "timdr_status.json")

# Plik raportu kalibracji zapisywany przez monitor.py (--calib-report) -
# RAZ, przy faktycznej (nowej) kalibracji, nie przy kazdym sprawdzeniu.
CALIB_REPORT_FILE = os.environ.get("TIMDR_CALIB_REPORT_FILE", "timdr_calibration_report.json")

fusion = TIMDRIndustrialFusion()
predict = TIMDRIndustrialPredict()


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
    })


@app.route("/api/monitor/status")
def api_monitor_status():
    """
    Zwraca ostatni stan zapisany przez `monitor.py` (ciagly albo
    okresowy - patrz README) do `STATUS_FILE`. Jesli monitor.py nigdy
    nie byl uruchomiony (plik nie istnieje), zwraca `running: false`
    zamiast bledu - dashboard traktuje to jako "brak aktywnego
    monitoringu", nie awarie API.
    """
    if not os.path.exists(STATUS_FILE):
        return jsonify({"running": False})
    try:
        with open(STATUS_FILE) as f:
            status = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        # POPRAWKA: monitor.py moze akurat zapisywac plik w momencie
        # odczytu (nie jest to atomowy zapis) - traktujemy to jako
        # przejsciowy brak danych, nie blad 500, zeby panel live nie
        # migotal czerwonym bledem przy kazdym odswiezeniu w zlym momencie.
        return jsonify({"running": True, "error": f"chwilowy blad odczytu: {exc}"}), 200
    status["running"] = True
    return jsonify(status)


@app.route("/api/monitor/calibration")
def api_monitor_calibration():
    """
    Zwraca raport zapisany RAZ przez monitor.py w momencie faktycznej
    kalibracji (--healthy-ref lub --auto-calibrate) - metoda, ile probek
    uzyto, wynik walidacji Mann-Kendalla (czy okno kalibracyjne ma
    statystycznie istotny trend) i ile probek teoretycznie trzeba do
    stabilizacji (calibration_convergence). NIE odswieza sie przy kazdym
    sprawdzeniu jak /api/monitor/status - to diagnostyka jednorazowa,
    dashboard pobiera ja raz przy zaladowaniu strony, nie w petli.
    """
    if not os.path.exists(CALIB_REPORT_FILE):
        return jsonify({"available": False})
    try:
        with open(CALIB_REPORT_FILE) as f:
            report = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return jsonify({"available": True, "error": f"chwilowy blad odczytu: {exc}"}), 200
    report["available"] = True
    return jsonify(report)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
