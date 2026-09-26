# bearing_resonance_sieve.py -- sito rezonansowe: diagnostyka lozyska wg drogowskazow TIMDR
# (membrana = pole, rezonans ustala oczka sita, samokorekta per hipoteza uszkodzenia).
#
# Pochodzenie i walidacja: metoda przeniesiona 1:1 (bez importu, repo pozostaje niezalezne) z GIA-TIMDR
# core/real_paderborn_resonance_sieve.py -- cechy Q. Wynik pre-rejestrowany na lozyskach Paderborn z uszkodzeniami
# naturalnymi, lozyska testowe spoza uczenia:
#   v0.1 (pomiary 6-10): 0,68 vs klasyczne 0,56 i obwiednia 0,61 -- SUPPORTED;
#   v0.2 (pomiary 11-15): 0,65 vs klasyczne 0,56 (SUPPORTED), kurtogram 0,55 (SUPPORTED), obwiednia 0,61 (MIESZANY).
# Zgodnosc liczbowa z implementacja walidowana sprawdza test_bearing_resonance_sieve.py (wartosci wzorcowe).
#
# Uzycie:
#   python bearing_resonance_sieve.py analyze plik.npz --fs 64000 --rpm 1500 --bearing 6203 [--channel DE]
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
}
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


def analyze(x: np.ndarray, fs: float, rpm: float, bearing: str = "6203") -> SieveReport:
    xs, fs2 = prepare(x, fs)
    Rz, al, bl = resonance_map(xs, fs2)
    mult = fault_multipliers(*BEARINGS[bearing]); fr = rpm / 60.0
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
    return SieveReport(fs2, float(rpm), bearing, hyps, feats, strongest)


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
    a.add_argument("--rpm", type=float, required=True); a.add_argument("--bearing", default="6203", choices=sorted(BEARINGS))
    a.add_argument("--channel", default=None)
    args = ap.parse_args(argv)
    rep = analyze(_load(args.file, args.channel), args.fs, args.rpm, args.bearing)
    print(json.dumps(asdict(rep), indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
