"""
monitor.py — TIMDR Industrial Predict, monitoring ciagly / okresowy
====================================================================
Uruchamia pipeline TIMDR (fuse_calibrated + health_score + TTF
unormowany) na REALNYM, rosnacym pliku CSV z czujnikami maszyny -
zamiast jednorazowego uruchomienia z dashboardu, dziala jako proces w
petli (monitoring ciagly) albo jako pojedyncze sprawdzenie do
wywolania z zewnetrznego harmonogramu (monitoring okresowy: cron,
Harmonogram zadan Windows, systemd timer).

KALIBRACJA: wymaga OSOBNEGO pliku ze zdrowym okresem odniesienia (patrz
ostrzezenie w `TIMDRIndustrialFusion.calibrate()` - to musi byc znany
zdrowy stan, nie zgadywane z pierwszych probek na zywo). Kalibracja
jest liczona RAZ przy starcie i zapisywana do JSON (`--calib-cache`),
zeby kolejne uruchomienia w trybie okresowym (osobny proces za kazdym
razem) nie musialy miec dostepu do pliku referencyjnego ani przeliczac
go od nowa.

Format plikow CSV: naglowek + kolumna czasu (domyslnie `t`, lub uzyj
--t-col; bez niej uzywany jest indeks wiersza) + dowolna liczba kolumn
numerycznych jako czujniki (--sensor-cols, domyslnie wszystkie kolumny
numeryczne oprocz kolumny czasu).

PRZYKLADY UZYCIA:

  Monitoring CIAGLY (proces dziala caly czas, sprawdza co --interval
  sekund, Ctrl+C konczy):
    python monitor.py --csv maszyna_live.csv --healthy-ref rozruch_zdrowy.csv --interval 5

  Monitoring OKRESOWY (jedno sprawdzenie, wywolywane z zewnatrz np.
  przez cron/Harmonogram zadan co godzine):
    python monitor.py --csv maszyna_live.csv --healthy-ref rozruch_zdrowy.csv --once

  Drugie i kolejne uruchomienie --once (kalibracja juz zapisana):
    python monitor.py --csv maszyna_live.csv --once

Wyjscie kazdego sprawdzenia: jedna linia na stdout + zapis pelnego
stanu do pliku JSON (--state-file, domyslnie timdr_status.json) -
mozna to podpiac pod dashboard/alerting bez zmiany tego skryptu.
"""
import argparse
import csv as csvmod
import json
import os
import sys
import time
from datetime import datetime, timezone

import numpy as np

from timdr_industrial_fusion import TIMDRIndustrialFusion
from timdr_industrial_predict import TIMDRIndustrialPredict


def load_csv(path, t_col=None, sensor_cols=None):
    with open(path, "r", newline="") as f:
        reader = csvmod.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    if not rows:
        return np.array([]), [], []

    if sensor_cols is None:
        candidate = [c for c in fieldnames if c != t_col]
        sensor_cols = []
        for c in candidate:
            try:
                float(rows[0][c])
                sensor_cols.append(c)
            except (TypeError, ValueError):
                continue

    if t_col and t_col in fieldnames:
        t = np.array([float(r[t_col]) for r in rows])
    else:
        t = np.arange(len(rows), dtype=float)

    sensors = []
    for c in sensor_cols:
        sensors.append(np.array([float(r[c]) for r in rows]))

    return t, sensors, sensor_cols


def save_calibration(fusion, path):
    with open(path, "w") as f:
        json.dump({
            "baseline_med": fusion.baseline_med.tolist(),
            "baseline_mad": fusion.baseline_mad.tolist(),
        }, f)


def save_calibration_report(path, report):
    """Zapisuje diagnostyke kalibracji (Mann-Kendall + ile probek do
    stabilizacji) RAZ, w momencie faktycznej kalibracji - nie przy kazdym
    --once/sprawdzeniu jak timdr_status.json. Osobny plik, zeby nie
    zaszumiac panelu live odswiezanego co kilka sekund; dashboard pobiera
    to jednorazowo, nie w petli pollingu."""
    with open(path, "w") as f:
        json.dump(report, f, indent=2)


def load_calibration(fusion, path):
    with open(path) as f:
        d = json.load(f)
    fusion.baseline_med = np.array(d["baseline_med"])
    fusion.baseline_mad = np.array(d["baseline_mad"])


def run_check(args, fusion, predict):
    t, sensors, sensor_cols = load_csv(args.csv, t_col=args.t_col, sensor_cols=args.sensor_cols)
    if len(t) == 0:
        print("BRAK DANYCH w pliku live - pomijam to sprawdzenie.")
        return None

    E, _ = fusion.fuse_calibrated(t, sensors)
    hs = predict.health_score(E, threshold=args.threshold, window=args.hs_window)
    ttf, confirmed, raw = predict.predict_failure_smoothed(
        t, E, threshold=args.threshold, window=args.ttf_window,
        smooth_window=args.smooth_window,
    )

    now_iso = datetime.now(timezone.utc).isoformat()
    n_samples = int(len(t))

    # ROZROZNIENIE "checker zyje" vs "zrodlo danych faktycznie zyje" - dla
    # zrodel typu OBD-II/czujnik na zywo, monitor.py moze dalej grzecznie
    # odpytywac CSV co --interval sekund (wiec 'timestamp' ponizej zawsze
    # bedzie swiezy) NAWET jesli obd_source.py/adapter sie rozlaczyl i CSV
    # przestal rosnac - sam swiezy 'timestamp' tego NIE wykryje. Dlatego
    # osobno sledzimy `last_data_change`: moment, w ktorym n_samples
    # OSTATNI RAZ faktycznie wzrosl (odczytane z poprzedniego stanu przed
    # nadpisaniem) - to jest prawdziwy sygnal "czy dane na zywo naplywaja",
    # nie tylko "czy petla monitor.py dziala".
    last_data_change = now_iso
    try:
        with open(args.state_file) as f:
            prev = json.load(f)
        if prev.get("n_samples") == n_samples and prev.get("last_data_change"):
            last_data_change = prev["last_data_change"]
    except (OSError, json.JSONDecodeError, KeyError):
        pass

    status = {
        "timestamp": now_iso,
        "last_data_change": last_data_change,
        "interval": (None if args.once else args.interval),
        "n_samples": n_samples,
        "sensor_cols": sensor_cols,
        "E_last": float(E[-1]),
        "health_score": float(hs),
        "ttf": (None if not np.isfinite(ttf) else float(ttf)),
        "ttf_confirmed": bool(confirmed),
        "alert": bool(hs < args.alert_health or (confirmed and ttf < args.alert_ttf)),
    }

    with open(args.state_file, "w") as f:
        json.dump(status, f, indent=2)

    alert_txt = " !!! ALARM !!!" if status["alert"] else ""
    ttf_txt = f"{status['ttf']:.1f}" if status["ttf"] is not None else "inf"
    print(
        f"[{status['timestamp']}] n={status['n_samples']:5d}  "
        f"E={status['E_last']:.2f}  health={status['health_score']:.3f}  "
        f"TTF={ttf_txt} (confirmed={status['ttf_confirmed']}){alert_txt}"
    )
    return status


def main():
    ap = argparse.ArgumentParser(description="TIMDR Industrial Predict - monitoring ciagly/okresowy")
    ap.add_argument("--csv", required=True, help="Plik CSV z live danymi maszyny (rosnie w czasie)")
    ap.add_argument("--healthy-ref", default=None,
                     help="Plik CSV ze znanym zdrowym okresem odniesienia (albo uzyj --auto-calibrate)")
    ap.add_argument("--auto-calibrate", action="store_true",
                     help="Zamiast --healthy-ref: automatycznie znajdz najbardziej stabilne podokno "
                          "w --csv (wymaga co najmniej --calib-probe probek juz zebranych) i kalibruj z niego. "
                          "Patrz TIMDRIndustrialFusion.auto_calibrate() - nadal wymaga, zeby GDZIES w probce "
                          "istnial prawdziwie stabilny odcinek, nie wymysla go z niczego.")
    ap.add_argument("--calib-probe", type=int, default=None,
                     help="Ile poczatkowych probek przeszukac przy --auto-calibrate (domyslnie: wszystkie dostepne)")
    ap.add_argument("--calib-window", type=int, default=None,
                     help="Rozmiar okna kalibracyjnego przy --auto-calibrate (domyslnie: probe_window/4)")
    ap.add_argument("--calib-cache", default="timdr_calibration.json",
                     help="Gdzie zapisac/wczytac kalibracje (domyslnie timdr_calibration.json)")
    ap.add_argument("--calib-report", default="timdr_calibration_report.json",
                     help="Gdzie zapisac diagnostyke kalibracji (Mann-Kendall + ile probek do "
                          "stabilizacji) - pisane RAZ, tylko przy faktycznej (nowej) kalibracji, "
                          "nie przy kazdym sprawdzeniu (domyslnie timdr_calibration_report.json)")
    ap.add_argument("--convergence-rel-tol", type=float, default=0.05,
                     help="Prog wzglednej zmiany mediany dla calibration_convergence() w raporcie")
    ap.add_argument("--state-file", default="timdr_status.json",
                     help="Gdzie zapisywac biezacy stan (JSON) po kazdym sprawdzeniu")
    ap.add_argument("--t-col", default="t", help="Nazwa kolumny czasu (domyslnie 't')")
    ap.add_argument("--sensor-cols", nargs="*", default=None,
                     help="Jawna lista kolumn-czujnikow (domyslnie: wszystkie numeryczne oprocz t-col)")
    ap.add_argument("--threshold", type=float, default=3.0)
    ap.add_argument("--hs-window", type=int, default=20)
    ap.add_argument("--ttf-window", type=int, default=60)
    ap.add_argument("--smooth-window", type=int, default=10)
    ap.add_argument("--alert-health", type=float, default=0.2,
                     help="Alarm, gdy health_score spadnie ponizej tej wartosci")
    ap.add_argument("--alert-ttf", type=float, default=24.0,
                     help="Alarm, gdy potwierdzony TTF spadnie ponizej tej liczby jednostek czasu")
    ap.add_argument("--interval", type=float, default=60.0,
                     help="Monitoring CIAGLY: sekund miedzy sprawdzeniami (ignorowane z --once)")
    ap.add_argument("--once", action="store_true",
                     help="Monitoring OKRESOWY: jedno sprawdzenie i wyjscie (do wywolania z cron/Harmonogramu)")
    args = ap.parse_args()

    fusion = TIMDRIndustrialFusion()
    predict = TIMDRIndustrialPredict()

    if os.path.exists(args.calib_cache):
        load_calibration(fusion, args.calib_cache)
        print(f"Wczytano kalibracje z {args.calib_cache}.")
    elif args.healthy_ref:
        t_ref, sensors_ref, _ = load_csv(args.healthy_ref, t_col=args.t_col, sensor_cols=args.sensor_cols)
        fusion.calibrate(sensors_ref)
        save_calibration(fusion, args.calib_cache)
        print(f"Skalibrowano z {args.healthy_ref} ({len(t_ref)} probek) i zapisano do {args.calib_cache}.")

        validation = fusion.validate_window(sensors_ref)
        convergence = fusion.calibration_convergence(sensors_ref, rel_tol=args.convergence_rel_tol)
        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "method": "healthy-ref",
            "source_file": args.healthy_ref,
            "n_samples_used": int(len(t_ref)),
            "validated": validation["valid"],
            "validation_detail": validation["per_sensor"],
            "convergence_n_required": convergence["n_required"],
            "convergence_rel_tol": args.convergence_rel_tol,
        }
        save_calibration_report(args.calib_report, report)
        if not validation["valid"]:
            print(
                f"UWAGA: walidacja Mann-Kendalla wykryla statystycznie istotny trend w "
                f"referencji '{args.healthy_ref}' - okno moze nie byc tak stabilne, jak zakladano "
                f"(szczegoly w {args.calib_report})."
            )
    elif args.auto_calibrate:
        t_probe, sensors_probe, _ = load_csv(args.csv, t_col=args.t_col, sensor_cols=args.sensor_cols)
        if len(t_probe) == 0:
            print("BLAD: --auto-calibrate wymaga, zeby --csv mial juz jakies dane.", file=sys.stderr)
            sys.exit(1)
        info = fusion.auto_calibrate(sensors_probe, probe_window=args.calib_probe, candidate_size=args.calib_window)
        save_calibration(fusion, args.calib_cache)
        print(
            f"Autokalibracja z {args.csv}: wybrano okno [{info['chosen_start']}:"
            f"{info['chosen_start']+info['window_size']}] (zmiennosc {info['variability_chosen']:.3f} "
            f"vs {info['variability_naive_first']:.3f} dla naiwnego pierwszego okna). "
            f"Zapisano do {args.calib_cache}."
        )

        convergence = fusion.calibration_convergence(sensors_probe, rel_tol=args.convergence_rel_tol)
        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "method": "auto-calibrate",
            "source_file": args.csv,
            "n_samples_used": int(info["window_size"]),
            "chosen_start": info["chosen_start"],
            "variability_chosen": info["variability_chosen"],
            "variability_naive_first": info["variability_naive_first"],
            "validated": info["validated"],
            "validation_detail": info["validation_detail"],
            "convergence_n_required": convergence["n_required"],
            "convergence_rel_tol": args.convergence_rel_tol,
        }
        save_calibration_report(args.calib_report, report)
        if not info["validated"]:
            print(
                f"UWAGA: walidacja Mann-Kendalla wykryla statystycznie istotny trend w "
                f"wybranym oknie kalibracyjnym - moze nie byc tak stabilne, jak sugerowal sam "
                f"wskaznik zmiennosci (szczegoly w {args.calib_report})."
            )
    else:
        print(
            "BLAD: brak zapisanej kalibracji i nie podano --healthy-ref ani --auto-calibrate. "
            "Pierwsze uruchomienie wymaga jednego z nich.",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.once:
        run_check(args, fusion, predict)
        return

    print(f"Monitoring CIAGLY: sprawdzanie co {args.interval}s. Ctrl+C konczy.")
    try:
        while True:
            run_check(args, fusion, predict)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nZatrzymano monitoring.")


if __name__ == "__main__":
    main()
