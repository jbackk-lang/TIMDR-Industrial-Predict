"""test_bearing_envelope_diagnostics.py -- kontrole syntetyczne + real-data
end-to-end dla bearing_envelope_diagnostics.py (diagnostyka TYPU usterki
lozyska, komplementarna do bearing_meta_adapter.py). Patrz docstring modulu
dla pelnego kontekstu (metoda przeniesiona i juz zwalidowana w GIA-TIMDR)."""
import os

import numpy as np
import pytest

from bearing_envelope_diagnostics import (
    characteristic_frequencies,
    envelope_spectrum_peak,
    diagnose_fault_type,
)

HERE = os.path.dirname(os.path.abspath(__file__))
NPZ_DIR = os.path.join(HERE, "data", "cwru_bearing", "b4_raw", "source_mirror", "Data", "1797 RPM")
FS = 12000.0
RPM = 1797.0


# ---------------------------------------------------------------------------
# Geometria / czestotliwosci charakterystyczne
# ---------------------------------------------------------------------------


def test_characteristic_frequencies_match_documented_cwru_values():
    """Wartosci zweryfikowane przez WebSearch dla SKF 6205-2RS JEM @ 1797 RPM
    (patrz GIA-TIMDR chrono_modal_geometry_bridge.py, ta sama weryfikacja) -
    BPFO=107.364, BPFI=162.186, BSF(2x)=141.169, FTF=11.929 Hz."""
    freqs = characteristic_frequencies(RPM)
    assert freqs["BPFO"] == pytest.approx(107.364, abs=0.01)
    assert freqs["BPFI"] == pytest.approx(162.186, abs=0.01)
    assert freqs["BSF"] == pytest.approx(141.169, abs=0.01)
    assert freqs["FTF"] == pytest.approx(11.929, abs=0.01)


# ---------------------------------------------------------------------------
# Kontrole syntetyczne (pozytywna + negatywna) dla envelope_spectrum_peak
# ---------------------------------------------------------------------------


def test_envelope_spectrum_peak_positive_control_detects_periodic_impulses():
    fs = 5000.0
    n = 10000
    rng = np.random.default_rng(1)
    t = np.arange(n) / fs
    f_target = 80.0
    f_res = 1800.0
    period = fs / f_target
    signal = rng.normal(0, 1, n)
    k = 0
    while k * period < n:
        idx = int(k * period)
        local_t = (np.arange(n) - idx) / fs
        mask = (local_t >= 0) & (local_t < 0.01)
        signal[mask] += 5.0 * np.exp(-local_t[mask] / 0.001) * np.sin(2 * np.pi * f_res * local_t[mask])
        k += 1

    resonance_band = (1500.0, 2000.0)
    peaks_signal = envelope_spectrum_peak(signal, fs, resonance_band, {"target": f_target})
    peaks_noise = envelope_spectrum_peak(rng.normal(0, 1, n), fs, resonance_band, {"target": f_target})
    assert peaks_signal["target"] > peaks_noise["target"]


def test_diagnose_fault_type_synthetic_specificity():
    """Kontrola syntetyczna dla calego pipeline'u diagnose_fault_type:
    wstrzyknij periodyczne uderzenia dokladnie na czestotliwosci BPFI (162Hz
    @ 1797 RPM) modulujace rezonans, zdrowa referencja = czysty szum -
    best_match powinien wyjsc BPFI, i to wyraznie (is_specific=True), bo
    inne czestotliwosci charakterystyczne nie sa wstrzykniete."""
    fs = 12000.0
    n = 48000  # 4s, rozdzielczosc widma obwiedni 0.25 Hz - wystarczajaca dla separacji BPFO/BPFI/BSF
    rng = np.random.default_rng(7)
    targets = characteristic_frequencies(RPM)
    f_inject = targets["BPFI"]
    f_res = 3000.0
    period = fs / f_inject

    s_ref = rng.normal(0, 1, n)

    s_test = rng.normal(0, 1, n)
    k = 0
    while k * period < n:
        idx = int(k * period)
        local_t = (np.arange(n) - idx) / fs
        mask = (local_t >= 0) & (local_t < 0.005)
        s_test[mask] += 8.0 * np.exp(-local_t[mask] / 0.0008) * np.sin(2 * np.pi * f_res * local_t[mask])
        k += 1

    diag = diagnose_fault_type(s_ref, s_test, fs, RPM, resonance_band=(2500.0, 3500.0))
    assert diag.best_match == "BPFI", f"oczekiwano BPFI, dostano {diag.best_match} (ratios={diag.ratios})"
    assert diag.is_specific, f"oczekiwano wyraznej specyficznosci, ratios={diag.ratios}"


# ---------------------------------------------------------------------------
# Real-data end-to-end (CWRU, pelne nagrania .npz juz obecne w tym repo) -
# odtworzenie jakosciowego wzorca znalezionego w GIA-TIMDR
# (RESULT_MODAL_BAND_ENERGY_BRIDGE_v0.2.md): IR/OR specyficzne, B slabsze.
# ---------------------------------------------------------------------------


def _npz_files_exist():
    names = ["1797_Normal.npz", "1797_IR_21_DE12.npz", "1797_OR@6_21_DE12.npz", "1797_B_21_DE12.npz"]
    return all(os.path.exists(os.path.join(NPZ_DIR, n)) for n in names)


def _load_de(name):
    d = np.load(os.path.join(NPZ_DIR, f"{name}.npz"))
    return d["DE"].astype(np.float64).ravel()


@pytest.mark.skipif(not _npz_files_exist(), reason="brak pelnych nagran CWRU .npz")
def test_real_data_inner_race_fault_best_match_is_bpfi_and_specific():
    s_ref = _load_de("1797_Normal")
    s_test = _load_de("1797_IR_21_DE12")
    diag = diagnose_fault_type(s_ref, s_test, FS, RPM)
    assert diag.best_match == "BPFI", f"IR: oczekiwano BPFI, dostano {diag.best_match} (ratios={diag.ratios})"
    assert diag.is_specific


@pytest.mark.skipif(not _npz_files_exist(), reason="brak pelnych nagran CWRU .npz")
def test_real_data_outer_race_fault_best_match_is_bpfo_and_specific():
    s_ref = _load_de("1797_Normal")
    s_test = _load_de("1797_OR@6_21_DE12")
    diag = diagnose_fault_type(s_ref, s_test, FS, RPM)
    assert diag.best_match == "BPFO", f"OR: oczekiwano BPFO, dostano {diag.best_match} (ratios={diag.ratios})"
    assert diag.is_specific


@pytest.mark.skipif(not _npz_files_exist(), reason="brak pelnych nagran CWRU .npz")
def test_real_data_ball_fault_runs_and_elevates_bsf_ratio_but_specificity_not_guaranteed():
    """UCZCIWE ZASTRZEZENIE (zgodne z GIA-TIMDR RESULT_MODAL_BAND_ENERGY_BRIDGE_v0.2.md):
    usterki elementu tocznego (B) sa znanym, udokumentowanym w literaturze
    trudnym przypadkiem diagnostycznym - NIE wymagamy tu ani poprawnej
    klasyfikacji best_match, ani is_specific=True. Test sprawdza tylko, ze
    pipeline dziala bez bledow i ze BSF-ratio jest wyraznie > 1 (podwyzszone
    wzgledem zdrowego), tak jak w oryginalnym wyniku."""
    s_ref = _load_de("1797_Normal")
    s_test = _load_de("1797_B_21_DE12")
    diag = diagnose_fault_type(s_ref, s_test, FS, RPM)
    assert np.isfinite(diag.ratios["BSF"])
    assert diag.ratios["BSF"] > 5.0, f"B: oczekiwano wyraznie podwyzszonego BSF-ratio, dostano {diag.ratios}"


@pytest.mark.skipif(not _npz_files_exist(), reason="brak pelnych nagran CWRU .npz")
def test_real_data_resonance_band_matches_earlier_kurtosis_selection():
    """Sanity-check spojnosci z wynikiem juz zweryfikowanym w tej sesji
    (bearing_meta_adapter.select_resonance_band_from_reference na tych samych
    danych wybralo (4500,5000)Hz, kurtoza=0.372) - ten modul uzywa tej samej
    funkcji, wiec powinien wybrac identyczne pasmo."""
    s_ref = _load_de("1797_Normal")
    s_test = _load_de("1797_IR_21_DE12")
    diag = diagnose_fault_type(s_ref, s_test, FS, RPM)
    assert diag.resonance_band_used == (4500.0, 5000.0)
    assert diag.resonance_band_kurtosis == pytest.approx(0.372, abs=0.01)
