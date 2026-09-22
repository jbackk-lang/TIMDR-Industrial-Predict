# bearing_envelope_diagnostics.py -- diagnostyka TYPU usterki lozyska
# (BPFO/BPFI/BSF-specyficzna), komplementarna do bearing_meta_adapter.py.
#
# KONTEKST: bearing_meta_adapter.py odpowiada na pytanie "czy TO okno jest
# anomalne" (Lambda/tau/rho/J wzgledem zdrowej referencji, stale
# RESONANCE_BAND_HZ dobrane pod OGOLNA amplitude, nie pod typ usterki). Ten
# modul odpowiada na INNE pytanie: "JAKI typ usterki (biezna zewnetrzna
# BPFO / biezna wewnetrzna BPFI / element toczny BSF)" -- metoda standardowej
# "envelope spectrum analysis" z diagnostyki lozysk: filtr wokol pasma
# rezonansu strukturalnego -> obwiednia Hilberta -> widmo (FFT) obwiedni ->
# wysokosc piku PRZY czestotliwosci charakterystycznej danego typu usterki.
#
# Metodologia (Hilbert-obwiednia + widmo obwiedni + kurtoza-dobor-pasma)
# jest PRZENIESIONA 1:1 z GIA-TIMDR (docs/geometry/
# PREREG_MODAL_BAND_ENERGY_BRIDGE_v0.2.md /
# RESULT_MODAL_BAND_ENERGY_BRIDGE_v0.2.md, core/modal_band_energy_bridge.py,
# TIMDR-Math-Formalism/timdr_formalism/envelope_demodulation.py) - tam
# metoda przeszla pelny protokol prereg->implementacja->kontrole
# syntetyczne->dane realne i zostala POTWIERDZONA (wszystkie 3 pary
# dopasowane p=6.0e-6, r=1.000, stabilna miedzy polowami okna; IR/OR ze
# specyficznoscia widoczna w surowych liczbach, B bez niej - zgodnie z
# literatura diagnostyki lozysk, gdzie usterki elementu tocznego sa trudniej
# wykrywalne przez slabsze/bardziej rozmyte modulowanie obwiedni). TEN plik
# NIE powtarza tamtego pelnego prereg-protokolu od zera (metoda jest juz
# zwalidowana) - implementuje ja lokalnie (bez importu z GIA-TIMDR/
# TIMDR-Math-Formalism, zgodnie z decyzja "repozytoria kodu maja byc
# niezalezne od siebie" udokumentowana w naglowku bearing_meta_adapter.py) i
# weryfikuje na TYCH SAMYCH realnych danych CWRU juz obecnych w tym repo
# (patrz test_bearing_envelope_diagnostics.py) - odtwarza jakosciowo ten sam
# wzorzec (IR/OR specyficzne, B slabsze) jako sprawdzenie portu, nie jako
# nowe odkrycie.
#
# Czestotliwosci charakterystyczne lozyska (BPFO/BPFI/BSF/FTF) zweryfikowane
# przez WebSearch (nie z pamieci modelu) dla SKF 6205-2RS JEM (lozysko CWRU
# DE) w tej samej sesji, w ktorej powstal chrono_modal_geometry_bridge w
# GIA-TIMDR - patrz `characteristic_frequencies()` nizej dla wzorow.
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from bearing_meta_adapter import (
    _bandpass_fft,
    _kurtosis_excess,
    _default_candidate_bands,
    select_resonance_band_from_reference,
)

# ---------------------------------------------------------------------
# Geometria lozyska i czestotliwosci charakterystyczne
# ---------------------------------------------------------------------

# SKF 6205-2RS JEM (lozysko strony napedowej, DE, w zestawie CWRU) -
# zweryfikowane przez WebSearch, nie z pamieci (patrz GIA-TIMDR
# chrono_modal_geometry_bridge.py dla tej samej weryfikacji).
BEARING_N_BALLS = 9
BEARING_BALL_DIAM_MM = 7.94
BEARING_PITCH_DIAM_MM = 39.04
BEARING_CONTACT_ANGLE_DEG = 0.0


def characteristic_frequencies(
    rpm: float,
    n_balls: int = BEARING_N_BALLS,
    ball_diam_mm: float = BEARING_BALL_DIAM_MM,
    pitch_diam_mm: float = BEARING_PITCH_DIAM_MM,
    contact_angle_deg: float = BEARING_CONTACT_ANGLE_DEG,
) -> Dict[str, float]:
    """BPFO/BPFI/BSF(2x)/FTF [Hz] ze standardowych wzorow diagnostyki
    lozysk tocznych. `rpm` - obroty walu na minute. BSF zwracane jako
    2xBSF (czestotliwosc uderzen elementu tocznego o obie biezne na jeden
    obrot elementu) - konwencja zgodna z GIA-TIMDR
    chrono_modal_geometry_bridge.py, zweryfikowana tam do 4 cyfr znaczacych
    przeciw dokumentacji CWRU."""
    fr = rpm / 60.0
    d_over_D = ball_diam_mm / pitch_diam_mm
    cos_theta = np.cos(np.radians(contact_angle_deg))
    bpfo = (n_balls / 2.0) * fr * (1 - d_over_D * cos_theta)
    bpfi = (n_balls / 2.0) * fr * (1 + d_over_D * cos_theta)
    bsf_2x = (pitch_diam_mm / ball_diam_mm) * fr * (1 - (d_over_D * cos_theta) ** 2)
    ftf = (fr / 2.0) * (1 - d_over_D * cos_theta)
    return {"BPFO": float(bpfo), "BPFI": float(bpfi), "BSF": float(bsf_2x), "FTF": float(ftf)}


# ---------------------------------------------------------------------
# Obwiednia Hilberta + widmo obwiedni (reimplementacja lokalna, jw. -
# identyczna logika co timdr_formalism.envelope_demodulation, zweryfikowana
# tam przeciw analitycznemu sygnalowi AM - patrz TIMDR-Math-Formalism
# tests/test_envelope_demodulation.py)
# ---------------------------------------------------------------------


def _hilbert_envelope(signal: np.ndarray) -> np.ndarray:
    """|sygnal analityczny| przez FFT."""
    n = len(signal)
    spectrum = np.fft.fft(signal)
    h = np.zeros(n)
    if n % 2 == 0:
        h[0] = h[n // 2] = 1
        h[1 : n // 2] = 2
    else:
        h[0] = 1
        h[1 : (n + 1) // 2] = 2
    analytic = np.fft.ifft(spectrum * h)
    return np.abs(analytic)


def envelope_spectrum(signal: np.ndarray, fs: float, resonance_band: Tuple[float, float]) -> Tuple[np.ndarray, np.ndarray]:
    """Filtr wokol pasma rezonansu -> obwiednia -> widmo amplitudowe
    obwiedni (po odjeciu DC). Zwraca (freqs, spectrum)."""
    f_lo, f_hi = resonance_band
    x_res = _bandpass_fft(signal, fs, f_lo, f_hi)
    envelope = _hilbert_envelope(x_res)
    envelope_centered = envelope - np.mean(envelope)
    n = len(envelope_centered)
    spectrum = np.abs(np.fft.rfft(envelope_centered)) / n
    freqs = np.fft.rfftfreq(n, d=1.0 / fs)
    return freqs, spectrum


def envelope_spectrum_peak(
    signal: np.ndarray,
    fs: float,
    resonance_band: Tuple[float, float],
    target_freqs: Dict[str, float],
    window_hz: float = 2.0,
) -> Dict[str, float]:
    """Wysokosc piku widma obwiedni w oknie +-window_hz wokol kazdej
    czestotliwosci w `target_freqs`."""
    freqs, spectrum = envelope_spectrum(signal, fs, resonance_band)
    out = {}
    for name, target in target_freqs.items():
        mask = (freqs >= target - window_hz) & (freqs <= target + window_hz)
        out[name] = float(np.max(spectrum[mask])) if np.any(mask) else float("nan")
    return out


# ---------------------------------------------------------------------
# Diagnostyka typu usterki: peak-height w widmie obwiedni test/ref przy
# BPFO/BPFI/BSF, znormalizowane wzgledem referencji -> klasyfikacja
# ---------------------------------------------------------------------


@dataclass
class FaultTypeDiagnosis:
    resonance_band_used: Tuple[float, float]
    resonance_band_kurtosis: float
    ratios: Dict[str, float]           # peak_test / peak_ref per BPFO/BPFI/BSF/FTF (>=0, nan jesli ref-peak~0)
    best_match: Optional[str]          # nazwa czestotliwosci o najwyzszym ratio, lub None gdy niejednoznaczne
    best_match_ratio: Optional[float]
    is_specific: bool                  # czy best_match ratio wyraznie odstaje od pozostalych (patrz SPECIFICITY_MARGIN)


SPECIFICITY_MARGIN = 1.5  # best_match musi miec ratio >= 1.5x drugiego najlepszego, zeby uznac za "specyficzny" (nie tylko ogolnie glosniej)


def diagnose_fault_type(
    s_ref: np.ndarray,
    s_test: np.ndarray,
    fs: float,
    rpm: float,
    resonance_band: Optional[Tuple[float, float]] = None,
    window_hz: float = 2.0,
) -> FaultTypeDiagnosis:
    """Diagnoza typu usterki lozyska metoda widma obwiedni (patrz naglowek
    modulu). `s_ref` - zdrowe nagranie referencyjne (uzywane WYLACZNIE do
    (a) doboru pasma rezonansu przez kurtoze, (b) jako mianownik ratio -
    peaki testowe znormalizowane wzgledem peakow referencyjnych PRZY TYCH
    SAMYCH czestotliwosciach, wiec ratio~1 = "jak zdrowe", ratio>>1 =
    "podwyzszony pik przy tej czestotliwosci wzgledem zdrowego").
    `resonance_band=None` (domyslnie) wybiera pasmo automatycznie z `s_ref`
    przez kurtoze nadmiarowa - podaj wlasne `(f_lo,f_hi)`, zeby pominac
    auto-dobor.

    `best_match`/`is_specific` implementuja zamrozona regule klasyfikacji z
    GIA-TIMDR PREREG_MODAL_BAND_ENERGY_BRIDGE_v0.2.md, prog SPECIFICITY_MARGIN
    - PATRZ UCZCIWE ZASTRZEZENIE tamtejszego RESULT v0.2: usterki elementu
    tocznego (B/BSF) maja tam SLABSZA specyficznosc niz IR/OR (znany,
    udokumentowany w literaturze problem diagnostyczny) - `is_specific=False`
    dla B jest OCZEKIWANYM, nie bledym wynikiem."""
    s_ref = np.asarray(s_ref, dtype=np.float64)
    s_test = np.asarray(s_test, dtype=np.float64)

    if resonance_band is None:
        resonance_band, kurt = select_resonance_band_from_reference(s_ref, fs)
    else:
        kurt = _kurtosis_excess(_bandpass_fft(s_ref, fs, *resonance_band))

    targets = characteristic_frequencies(rpm)

    peaks_ref = envelope_spectrum_peak(s_ref, fs, resonance_band, targets, window_hz=window_hz)
    peaks_test = envelope_spectrum_peak(s_test, fs, resonance_band, targets, window_hz=window_hz)

    ratios: Dict[str, float] = {}
    for name in targets:
        p_ref = peaks_ref[name]
        p_test = peaks_test[name]
        if not np.isfinite(p_ref) or p_ref < 1e-12:
            ratios[name] = float("nan")
        else:
            ratios[name] = float(p_test / p_ref)

    finite_ratios = {k: v for k, v in ratios.items() if np.isfinite(v)}
    if not finite_ratios:
        best_match, best_ratio, is_specific = None, None, False
    else:
        sorted_names = sorted(finite_ratios, key=lambda k: finite_ratios[k], reverse=True)
        best_match = sorted_names[0]
        best_ratio = finite_ratios[best_match]
        if len(sorted_names) >= 2:
            second_ratio = finite_ratios[sorted_names[1]]
            is_specific = second_ratio <= 1e-12 or (best_ratio / second_ratio) >= SPECIFICITY_MARGIN
        else:
            is_specific = True

    return FaultTypeDiagnosis(
        resonance_band_used=resonance_band,
        resonance_band_kurtosis=kurt,
        ratios=ratios,
        best_match=best_match,
        best_match_ratio=best_ratio,
        is_specific=is_specific,
    )


__all__ = [
    "BEARING_N_BALLS",
    "BEARING_BALL_DIAM_MM",
    "BEARING_PITCH_DIAM_MM",
    "BEARING_CONTACT_ANGLE_DEG",
    "characteristic_frequencies",
    "envelope_spectrum",
    "envelope_spectrum_peak",
    "FaultTypeDiagnosis",
    "SPECIFICITY_MARGIN",
    "diagnose_fault_type",
]
