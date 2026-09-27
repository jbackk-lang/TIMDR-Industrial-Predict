# bearing_resonance_sieve.py -- sito rezonansowe: diagnostyka lozyska wg drogowskazow TIMDR
# (membrana = pole, rezonans ustala oczka sita, samokorekta per hipoteza uszkodzenia).
#
# Pochodzenie i walidacja: metoda przeniesiona 1:1 (bez importu, repo pozostaje niezalezne) z GIA-TIMDR
# core/real_paderborn_resonance_sieve.py -- cechy Q. Wynik pre-rejestrowany na lozyskach Paderborn z uszkodzeniami
# naturalnymi, lozyska testowe spoza uczenia:
#   v0.1 (pomiary 6-10): 0,68 vs klasyczne 0,56 i obwiednia 0,61 -- SUPPORTED;
#   v0.2 (pomiary 11-15): 0,65 vs klasyczne 0,56 (SUPPORTED), kurtogram 0,55 (SUPPORTED), obwiednia 0,61 (MIESZANY);
#   v0.3 (pomiary 16-20): 0,65; lacznie 15 foldow: vs klasyczne +0,08 (12/15, SUPPORTED), vs obwiednia +0,04 (MIESZANY).
# Wersja w osi katowej (analyze-orders, zegar z tachometru) -- GIA-TIMDR core/modal_speed_tracking.py (order_sieve),
# turbina wiatrowa Fraunhofer LBF, zmienna predkosc 0,2-0,9 obr/s: biezna zewnetrzna AUC 1,00, swoistosc 1,00
# (wobec 0,85 bez osi katowej) -- SUPPORTED; biezna wewnetrzna i element toczny niewykryte.
# Zgodnosc liczbowa z implementacja walidowana sprawdza test_bearing_resonance_sieve.py (wartosci wzorcowe).
#
# Uzycie:
#   python bearing_resonance_sieve.py analyze plik.npz --fs 64000 --rpm 1500 --bearing 6203 [--channel DE]
#   python bearing_resonance_sieve.py analyze-orders plik.npz --fs 18500 --channel vib --tach-channel tach
#          --tach-fs 2960 --ppr 108 --bearing 6007-LBF     (zmienna predkosc: sito w osi katowej wirnika)
#   (plik: .npz / .npy / .csv z jedna kolumna sygnalu drgan)
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from scipy.signal import decimate

# geometria lozysk: liczba kulek, srednica kulki d [mm], srednica podzialowa D [mm], kat dzialania [deg]
BEARINGS = {
    "6203": (8, 6.75, 28.55, 0.0),   # Paderborn
    "6205": (9, 7.94, 39.04, 0.0),   # CWRU, strona napedowa
    "PRONOSTIA": (13, 3.5, 25.6, 0.0),   # FEMTO-ST PRONOSTIA (IEEE PHM 2012)
}
# lozyska podane mnoznikami z publikacji zbioru (geometria niepodana)
MULT_TABLE = {"6007-LBF": {"BPFO": 4.593, "BPFI": 6.407, "BSF": 5.995}}   # turbina Fraunhofer LBF
REF_FS = 32000.0          # czestotliwosc, na ktorej metode walidowano
SEGMENT_S = 2.0           # dlugosc analizowanego odcinka [s]
BAND_W = 1000.0           # szerokosc pasma nosnego [Hz]
BAND_LO, BAND_HI = 1000.0, 16000.0
AMIN, AMAX = 5.0, 500.0   # zakres czestotliwosci modulacji [Hz]
TOL = 0.03                # tolerancja wokol czestotliwosci uszkodzenia


def fault_multipliers(n: int, d: float, D: float, angle_deg: float = 0.0) -> Dict[str, float]:
    """Mnozniki czestotliwosci obrotowej: BPFO, BPFI, BSF."""
    r = d / D * np.cos(np.radians(angle_deg))
    return {"BPFO": n / 2 * (1 - r), "BPFI": n / 2 * (1 + r), "BSF": D / (2 * d) * (1 - r ** 2)}


def multipliers(bearing: str) -> Dict[str, float]:
    return dict(MULT_TABLE[bearing]) if bearing in MULT_TABLE else fault_multipliers(*BEARINGS[bearing])


def feasibility(window_s: float, fault_hz: float) -> Dict[str, object]:
    """Regula wykonalnosci TIMDR (GIA-TIMDR core/transition_params.py): N_cyk = cykle rytmu uszkodzenia w oknie.
    N_cyk < 10 -> grzebien rozmyty, sito nie ma szans (trafnie przewidziane na PRONOSTIA, okno 0,1 s)."""
    n = float(window_s * fault_hz)
    return {"N_cyk": n, "sito_ma_szanse": bool(n >= 10.0)}


def prepare(x: np.ndarray, fs: float) -> tuple[np.ndarray, float]:
    """Sprowadza sygnal do 32 kHz, jesli fs jest wielokrotnoscia 32 kHz (jak w walidacji), i wycina 2 s."""
    x = np.asarray(x, float).ravel()
    q = int(round(fs / REF_FS))
    if q > 1 and abs(fs - q * REF_FS) < 1e-6:
        x = decimate(x, q, ftype="fir", zero_phase=True); fs = REF_FS
    n = int(SEGMENT_S * fs)
    if len(x) < n:
        raise ValueError(f"za krotki sygnal: {len(x)} probek, potrzeba {n} ({SEGMENT_S} s)")
    x = x[:n]
    return x - x.mean(), fs


def bands(fs: float) -> List[tuple]:
    hi = min(BAND_HI, fs / 2)
    out, lo = [], BAND_LO
    while lo + BAND_W <= hi + 1e-9:
        out.append((lo, lo + BAND_W)); lo += BAND_W
    return out


def resonance_map(x: np.ndarray, fs: float):
    """Pole -> mapa rezonansu Rz[pasmo, alfa]: widmo obwiedni kazdego pasma nosnego, tlo (mediana) = 1."""
    N = len(x); X = np.fft.fft(x); f = np.fft.fftfreq(N, 1 / fs)
    alpha = np.fft.rfftfreq(N, 1 / fs); am = (alpha >= AMIN) & (alpha <= AMAX); w = np.hanning(N); rows = []
    bl = bands(fs)
    for lo, hi in bl:
        Z = np.zeros_like(X); m = (f >= lo) & (f < hi); Z[m] = 2 * X[m]
        e = np.abs(np.fft.ifft(Z)); e = e - e.mean()
        E = np.abs(np.fft.rfft(e * w))[am]; rows.append(E / (np.median(E) + 1e-12))
    return np.array(rows), alpha[am], bl


@dataclass
class HypothesisSieve:
    fault: str
    fault_freq_hz: float
    score: float                 # cecha Q_k = log(max S_k przy 1x + max przy 2x)
    mesh_entropy: float          # entropia oczek (niska = sito skupione na kilku pasmach)
    top_bands_hz: List[List[float]]   # pasma o najwiekszych oczkach
    top_band_weights: List[float]


@dataclass
class SieveReport:
    fs_used: float
    rpm: float
    bearing: str
    hypotheses: List[HypothesisSieve]
    features: Dict[str, float]
    strongest: str
    wykonalnosc: Dict[str, object] = None


def analyze(x: np.ndarray, fs: float, rpm: float, bearing: str = "6203") -> SieveReport:
    xs, fs2 = prepare(x, fs)
    Rz, al, bl = resonance_map(xs, fs2)
    mult = multipliers(bearing); fr = rpm / 60.0
    hyps, feats = [], {}
    for k in ("BPFO", "BPFI"):
        fc = mult[k] * fr
        b1 = np.where((al >= (1 - TOL) * fc) & (al <= (1 + TOL) * fc))[0]
        j = b1[np.argmax(Rz[:, b1].max(0))]
        v = np.clip(Rz[:, j] - 1, 0, None)
        wk = v / v.sum() if v.sum() > 0 else np.full(len(v), 1 / len(v))
        Sk = wk @ Rz; a = 0.0
        for h in (1, 2):
            band = (al >= (1 - TOL) * h * fc) & (al <= (1 + TOL) * h * fc); a += float(Sk[band].max())
        q = wk[wk > 0]; ent = float(-(q * np.log(q)).sum() / np.log(len(wk)))
        top = np.argsort(wk)[::-1][:3]
        hyps.append(HypothesisSieve(k, float(fc), float(np.log(a)), ent, [list(bl[i]) for i in top], [float(wk[i]) for i in top]))
        feats[f"Q_{k}"] = float(np.log(a)); feats[f"Q_went_{k}"] = ent
    strongest = max(hyps, key=lambda h: h.score).fault
    return SieveReport(fs2, float(rpm), bearing, hyps, feats, strongest, feasibility(SEGMENT_S, min(mult["BPFO"], mult["BPFI"]) * fr))


# ---------------- zmienna predkosc: sito w osi katowej (zegar z tachometru) ----------------
ORD_BAND_HI = 9000.0          # pasma nosne 1-9 kHz (jak w walidacji, fs ~ 18,5 kHz)
ORD_SEG_S, ORD_MIN_REV = 60.0, 10.0
ORD_SPR, ORD_OMIN, ORD_OMAX = 64, 0.5, 30.0


def shaft_angle_from_tach(tach: np.ndarray, tach_fs: float, ppr: int, n: int, fs: float, thr: float = 2.0):
    """Kat walu [obroty] dla n probek drgan (fs) z impulsow tachometru (ppr impulsow na obrot, prog thr)."""
    up = np.where((tach[1:] >= thr) & (tach[:-1] < thr))[0]
    if len(up) < 3:
        raise ValueError("za malo impulsow tachometru")
    tt = up[1:] / tach_fs; fr = 1.0 / (ppr * np.diff(up) / tach_fs)
    t = np.arange(n) / fs; frt = np.interp(t, tt, fr)
    return np.concatenate([[0.0], np.cumsum((frt[1:] + frt[:-1]) / 2) / fs]), tt, fr


def order_resonance_map(x, fs, theta, band_list, spr=ORD_SPR, omin=ORD_OMIN, omax=ORD_OMAX):
    """Mapa rezonansu w rzedach: obwiednia pasma przeliczona na rowne kroki kata (rura wyprostowana wzdluz)."""
    x = np.asarray(x, float) - np.mean(x); N = len(x); X = np.fft.fft(x); f = np.fft.fftfreq(N, 1 / fs)
    th_u = np.arange(theta[0], theta[-1], 1.0 / spr); rows = []
    orders = np.fft.rfftfreq(len(th_u), 1.0 / spr); m = (orders >= omin) & (orders <= omax); w = np.hanning(len(th_u))
    for lo, hi in band_list:
        Zb = np.zeros_like(X); sel = (f >= lo) & (f < hi); Zb[sel] = 2 * X[sel]
        e = np.abs(np.fft.ifft(Zb)); eu = np.interp(th_u, theta, e); eu = eu - eu.mean()
        E = np.abs(np.fft.rfft(eu * w))[m]; rows.append(E / (np.median(E) + 1e-12))
    return np.array(rows), orders[m]


def order_sieve(Rz, orders, fault_orders, tol=TOL):
    out = {}
    for k, o in fault_orders.items():
        b1 = np.where((orders >= (1 - tol) * o) & (orders <= (1 + tol) * o))[0]
        j = b1[np.argmax(Rz[:, b1].max(0))]; v = np.clip(Rz[:, j] - 1, 0, None)
        w = v / v.sum() if v.sum() > 0 else np.full(len(v), 1 / len(v)); S = w @ Rz; a = 0.0
        for h in (1, 2):
            band = (orders >= (1 - tol) * h * o) & (orders <= (1 + tol) * h * o); a += float(S[band].max())
        out[f"QO_{k}"] = float(np.log(a))
    return out


def analyze_orders(x: np.ndarray, fs: float, theta: np.ndarray, bearing: str) -> Dict[str, object]:
    """Sito w osi katowej na odcinkach 60 s (min. 10 obrotow); wynik = mediana z odcinkow."""
    mult = multipliers(bearing); hyp = {"BPFO": mult["BPFO"], "BPFI": mult["BPFI"], "BSF2": 2 * mult["BSF"]}
    bl = [(lo, lo + 1000.0) for lo in np.arange(1000.0, min(ORD_BAND_HI, fs / 2), 1000.0) if lo + 1000.0 <= min(ORD_BAND_HI, fs / 2) + 1e-9]
    n = int(ORD_SEG_S * fs); rows = []
    for s0 in (list(range(0, len(x) - n + 1, n)) or [0]):
        seg = x[s0:s0 + n]; th = theta[s0:s0 + len(seg)] - theta[s0]
        if th[-1] < ORD_MIN_REV:
            continue
        Ro, o = order_resonance_map(seg, fs, th, bl); rows.append(order_sieve(Ro, o, hyp))
    if not rows:
        raise ValueError("zaden odcinek nie ma >= 10 obrotow")
    feats = {k: float(np.median([r[k] for r in rows])) for k in rows[0]}
    return {"bearing": bearing, "segments": len(rows), "features": feats,
            "strongest": max(feats, key=feats.get).replace("QO_", ""),
            "wykonalnosc": feasibility(ORD_SEG_S * float(np.median(np.diff(theta)) * fs), min(hyp.values()))}


def _load(path: str, channel: Optional[str]) -> np.ndarray:
    p = Path(path)
    if p.suffix == ".npz":
        d = np.load(p); key = channel or d.files[0]; return np.asarray(d[key]).ravel()
    if p.suffix == ".npy":
        return np.load(p).ravel()
    return np.loadtxt(p, delimiter=",").ravel()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Sito rezonansowe TIMDR: diagnostyka lozyska z drgan")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze"); a.add_argument("file"); a.add_argument("--fs", type=float, required=True)
    a.add_argument("--rpm", type=float, required=True); a.add_argument("--bearing", default="6203", choices=sorted(set(BEARINGS) | set(MULT_TABLE)))
    a.add_argument("--channel", default=None)
    o = sub.add_parser("analyze-orders"); o.add_argument("file"); o.add_argument("--fs", type=float, required=True)
    o.add_argument("--channel", required=True); o.add_argument("--tach-channel", required=True)
    o.add_argument("--tach-fs", type=float, required=True); o.add_argument("--ppr", type=int, required=True)
    o.add_argument("--thr", type=float, default=2.0)
    o.add_argument("--bearing", required=True, choices=sorted(set(BEARINGS) | set(MULT_TABLE)))
    args = ap.parse_args(argv)
    if args.cmd == "analyze":
        rep = analyze(_load(args.file, args.channel), args.fs, args.rpm, args.bearing)
        print(json.dumps(asdict(rep), indent=1, ensure_ascii=False))
    else:
        x = _load(args.file, args.channel); tach = _load(args.file, args.tach_channel)
        theta, _, _ = shaft_angle_from_tach(tach, args.tach_fs, args.ppr, len(x), args.fs, args.thr)
        print(json.dumps(analyze_orders(x, args.fs, theta, args.bearing), indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
