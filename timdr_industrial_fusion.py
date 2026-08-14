"""
timdr_industrial_fusion.py — TIMDR Industrial Fusion
=======================================================
Fuzja wielu czujników maszyny (temperatura, wibracje, ciśnienie, prąd,
...) w jeden sygnał "energii stanu" E(t), plus standardowy zestaw
detektorów TIMDR (twist, trend, anomalie, rytm) na tym sygnale.
"""

import numpy as np


class TIMDRIndustrialFusion:
    def __init__(self, mad_scale=1.4826):
        self.mad_scale = mad_scale

    # ---------- MAD fallback ----------
    def _mad_z(self, x):
        x = np.asarray(x, float)
        if x.size == 0:
            return np.zeros_like(x)

        med = np.median(x)
        mad = np.median(np.abs(x - med)) * self.mad_scale

        if mad == 0:
            span = np.max(x) - np.min(x)
            if span == 0:
                return np.zeros_like(x)
            return (x - med) / (span / 4.0)

        return (x - med) / mad

    # ---------- interpolacja ----------
    def _align(self, t, sensors):
        """
        UWAGA (założenie, nie błąd): dla czujnika o innej liczbie próbek
        niż `t` zakładamy, że był on próbkowany RÓWNOMIERNIE w tym samym
        przedziale czasu [t.min(), t.max()] - typowe dla wielu czujników
        o różnych częstotliwościach próbkowania na tej samej maszynie w
        tym samym oknie czasowym. Jeśli Twój czujnik ma inny start/koniec
        albo nierówne próbkowanie, podaj go z własnym `t` i wyrównaj
        ręcznie przed wywołaniem `fuse()`.
        """
        t = np.asarray(t, float)
        out = []
        for s in sensors:
            s = np.asarray(s, float)
            if len(s) != len(t):
                ti = np.linspace(t.min(), t.max(), len(s))
                si = np.interp(t, ti, s)
                out.append(si)
            else:
                out.append(s)
        return np.column_stack(out)

    # ---------- fuzja cech ----------
    def fuse(self, t, sensors):
        X = self._align(t, sensors)
        Z = np.column_stack([self._mad_z(X[:, i]) for i in range(X.shape[1])])
        E = np.sqrt(np.sum(Z**2, axis=1))
        return E, Z

    # ---------- twist ----------
    def twist(self, t, E):
        """
        POPRAWKA (odporność na krótkie sygnały): oryginalny kod wywoływał
        `np.gradient` dwukrotnie bez żadnej ochrony na sygnały krótsze niż
        2 próbki. Zweryfikowano: n=0 i n=1 dawały `IndexError` (crash),
        zamiast zwrócić puste/zerowe wyniki - niespójne z resztą rodziny
        modułów TIMDR w tym repo (np. TIMDR-Earthquake-Core), gdzie
        krótkie sygnały są jawnie obsłużone. Naprawiono: n<2 zwraca puste
        idx i zera.
        """
        t = np.asarray(t, float)
        E = np.asarray(E, float)
        n = len(E)
        if n < 2:
            return np.array([], dtype=int), np.zeros(n)

        dE = np.gradient(E, t)
        ddE = np.gradient(dE, t)
        z = np.abs(self._mad_z(ddE))
        idx = np.where(z > 3.5)[0]
        return idx, z

    # ---------- trend ----------
    def trend(self, t, E, window=20):
        n = len(t)
        if n == 0:
            return np.array([]), np.array([])

        slopes = np.zeros_like(E, dtype=float)
        for i in range(n):
            j0 = max(0, i - window + 1)
            tt = t[j0:i + 1]
            ee = E[j0:i + 1]
            if len(tt) < 2:
                slopes[i] = 0.0
                continue
            A = np.column_stack([tt, np.ones_like(tt)])
            a, b = np.linalg.lstsq(A, ee, rcond=None)[0]
            slopes[i] = a
        z = self._mad_z(slopes)
        return slopes, z

    # ---------- anomaly ----------
    def anomalies(self, E):
        z = np.abs(self._mad_z(E))
        idx = np.where(z > 3.0)[0]
        return idx, z

    # ---------- rhythm ----------
    def rhythm(self, E, max_lag=60, power_thresh=0.4):
        """
        POPRAWKA (bug krytyczny): oryginalny kod tylko odejmował średnią
        (`E - mean(E)`) i zgłaszał KAŻDY lag powyżej `power_thresh`, nie
        tylko lokalne maksima. Dla sygnału z TRENDEM (a nie okresowością)
        - czyli dokładnie tym, co ten moduł ma wykrywać jako degradację! -
        kolejne próbki są do siebie podobne z powodu gładkiego trendu, nie
        żadnej cykliczności, co dawało bardzo wysoką "autokorelację" na
        niemal wszystkich krótkich lagach.

        Zweryfikowano: czysty rosnący trend (bez śladu okresowości, z
        realistycznym szumem czujnika) dawał `rhythm_score≈0.99` i **48
        "wykrytych okresów"** - narzędzie zgłaszało silny "rytm" dla
        sygnału, który nie ma żadnej cykliczności. To bezpośrednio myli
        się z głównym zastosowaniem modułu (degradacja = trend), a
        `fusion_score` dodatkowo podwójnie liczy tę samą informację
        (trend już wnosi 0.3 wagi przez `trend_z`, plus fałszywie wysoki
        `rhythm_score` dokłada kolejne 0.1).

        Naprawiono dwutorowo: (1) pełny detrend (nachylenie + wyraz
        wolny, nie tylko średnia) przed liczeniem autokorelacji, (2)
        zgłaszane są tylko LOKALNE MAKSIMA autokorelacji powyżej progu,
        nie każdy lag który go przekracza - inaczej nawet po detrendzie
        płaskie "plateau" wokół prawdziwego piku generowałoby wiele
        sztucznych "okresów" zamiast jednego. Zweryfikowano: ten sam
        czysty trend po poprawce daje `[]`, `0.0` (poprawnie: brak
        rytmu); sygnał z prawdziwą okresowością (okres 15) NAŁOŻONĄ na
        silny trend nadal poprawnie wykrywa okres 15 (i jego
        harmoniczne).
        """
        E = np.asarray(E, float)
        n = len(E)
        if n < 2:
            return [], 0.0

        t_idx = np.arange(n, dtype=float)
        if n > 2:
            slope, intercept = np.polyfit(t_idx, E, 1)
            E = E - (slope * t_idx + intercept)
        else:
            E = E - np.mean(E)

        max_lag = min(max_lag, n - 1)
        ac = np.zeros(max_lag + 1)
        for lag in range(max_lag + 1):
            if lag == 0:
                ac[lag] = np.dot(E, E) / n
            else:
                overlap = n - lag
                if overlap <= 0:
                    break
                ac[lag] = np.dot(E[:-lag], E[lag:]) / overlap

        if ac[0] == 0:
            return [], 0.0

        ac /= ac[0]

        peaks = []
        for i in range(1, len(ac) - 1):
            if ac[i] > ac[i - 1] and ac[i] > ac[i + 1] and ac[i] >= power_thresh:
                peaks.append((i, float(ac[i])))

        if not peaks:
            return [], 0.0

        score = max(p for _, p in peaks)
        return [p for p, _ in peaks], score

    # ---------- fusion-score ----------
    def fusion_score(self, twist_z, trend_z, anomaly_z, rhythm_score):
        """
        UWAGA: `np.max` na pustej tablicy rzuca ValueError - może się
        zdarzyć dla bardzo krótkich sygnałów (patrz poprawka w twist()).
        Traktujemy pustą tablicę jako "brak sygnału" (0.0), nie błąd.
        """
        def safe_max(x):
            x = np.asarray(x, float)
            return float(np.max(x)) if x.size else 0.0

        return float(
            0.4 * safe_max(twist_z) +
            0.3 * safe_max(trend_z) +
            0.2 * safe_max(anomaly_z) +
            0.1 * rhythm_score
        )
