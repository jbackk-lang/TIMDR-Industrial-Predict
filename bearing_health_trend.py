# bearing_health_trend.py -- trend stanu lozyska wzdluz zycia: droga rezimu TIMDR (pole -> czasteczka -> fala).
#
# Pochodzenie i walidacja: metoda przeniesiona 1:1 (bez importu) z GIA-TIMDR core/pronostia_features.py (P, D) oraz
# core/transition_params.py (event_density). Wynik pre-rejestrowany na 11 nieogladanych lozyskach PRONOSTIA do zniszczenia
# (GIA-TIMDR docs/geometry/RESULT_PRONOSTIA_REGIME_PATH_v0_1.md):
#   D (gestosc zdarzen obwiedni) spada wzdluz zycia w 9/11 lozysk (pole -> czasteczka), na koncu wraca >= 1,2 x minimum
#   w 7/11 (fala). D zachowuje sie jak kurtoza (remis); przewaga nad RMS tylko w spojnosci kierunku trendu.
#
# Uzycie (katalog migawek, np. PRONOSTIA acc_*.csv):
#   python bearing_health_trend.py trend KATALOG --fs 25600 --pattern "acc_*.csv" --col 4
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

import numpy as np
from scipy.ndimage import median_filter
from scipy.stats import kurtosis, spearmanr

BAND = (1000.0, 12000.0)     # pasmo obwiedni (walidacja: 25,6 kHz)
SMOOTH = 15                  # mediana ruchoma migawek
BASE_FRAC, END_FRAC = 0.10, 0.03
DROP, RETURN = 0.9, 1.2      # progi faz wzgledem tla (poczatek zycia) i minimum


def band_envelope(x, fs, lo, hi):
    x = np.asarray(x, float) - np.mean(x); X = np.fft.fft(x); f = np.fft.fftfreq(len(x), 1 / fs)
    Z = np.zeros_like(X); m = (f >= lo) & (f < hi); Z[m] = 2 * X[m]
    return np.abs(np.fft.ifft(Z))


def snapshot_features(x: np.ndarray, fs: float) -> Dict[str, float]:
    """RMS, kurtoza, P (udzial 5% najsilniejszych probek energii obwiedni), D = eta/(1-eta), eta = (E e)^2 / E e^2."""
    x = np.asarray(x, float); x = x - x.mean()
    env = band_envelope(x, fs, BAND[0], min(BAND[1], fs / 2))
    e2 = env ** 2; k = max(1, int(0.05 * len(e2)))
    eta = float(env.mean() ** 2 / (np.mean(e2) + 1e-30))
    return {"rms": float(np.sqrt(np.mean(x ** 2))), "kurt": float(kurtosis(x)),
            "P": float(np.sort(e2)[-k:].sum() / e2.sum()), "D": eta / max(1 - eta, 1e-9)}


def trend(snaps: List[Dict[str, float]]) -> Dict[str, object]:
    """Faza rezimu dla serii migawek (kolejnosc czasowa): 'pole' (D przy tle poczatku zycia), 'czasteczka' (D spadlo),
    'powrot ku fali' (D z konca >= 1,2 x minimum -- w walidacji zwiastun konca zycia w 7/11)."""
    D = median_filter(np.array([s["D"] for s in snaps], float), SMOOTH); n = len(D)
    base = float(np.median(D[: max(3, int(BASE_FRAC * n))])); e = max(3, int(END_FRAC * n))
    now = float(D[-e:].mean()); dmin = float(D.min())
    if now >= RETURN * dmin and dmin < DROP * base and int(np.argmin(D)) < n - e:
        phase = "powrot ku fali"
    elif now < DROP * base:
        phase = "czasteczka"
    else:
        phase = "pole"
    rho = float(spearmanr(np.arange(n), D).correlation) if n > 3 else float("nan")
    return {"n": n, "D_tlo": base, "D_teraz": now, "D_min": dmin, "faza": phase, "trend_rho_D": rho,
            "kurt_teraz": float(np.median([s["kurt"] for s in snaps[-e:]])), "rms_teraz": float(np.median([s["rms"] for s in snaps[-e:]]))}


def _read(p: Path, col: int) -> np.ndarray:
    txt = p.read_text(); sep = ";" if ";" in txt.splitlines()[0] else ","
    return np.array([float(l.split(sep)[col]) for l in txt.splitlines() if l.strip()])


def main(argv=None):
    ap = argparse.ArgumentParser(description="Trend stanu lozyska: droga rezimu TIMDR")
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("trend"); t.add_argument("folder"); t.add_argument("--fs", type=float, required=True)
    t.add_argument("--pattern", default="acc_*.csv"); t.add_argument("--col", type=int, default=4)
    a = ap.parse_args(argv)
    files = sorted(Path(a.folder).glob(a.pattern))
    snaps = [snapshot_features(_read(f, a.col), a.fs) for f in files]
    print(json.dumps(trend(snaps), indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
