# timdr_industrial_trigger.py
# ============================================
# TIMDR Industrial Trigger Module
# ============================================
#
# ROLA: czujnik sygnałowy — NIE model predykcyjny (do tego służy
# TIMDRIndustrialPredict.predict_failure()/health_score()). Dispatcher
# nad już przetestowanym TIMDRIndustrialFusion (twist/anomalies) i
# TIMDRIndustrialPredict (predict_failure) — jedyna jego robota:
# powiedzieć, KTÓRY typ zdarzenia się odpalił i GDZIE.
#
# ZASTANY STAN (powód budowy tego pliku): api.py::api_analyze() już
# liczy twist_idx/anomaly_idx/ttf/health_score i wystawia je jako
# osobne, równoległe pola — ale (w odróżnieniu od siostrzanego repo
# TIMDR-EV-Predict, gdzie monitor_ev.py liczy `result["alert"]` z
# health_score/ttf) NIE ma tu żadnego dispatchera łączącego je w jedno,
# priorytetyzowane zdarzenie z lokalizacją. Ten plik wypełnia właśnie
# tę różnicę.
#
# Priorytet: FAILURE_IMMINENT (przewidywany czas do awarii — TTF —
# poniżej `alert_ttf_seconds`: najbardziej actionable, explicit
# prognoza przyszłości, nie tylko opis przeszłości) > STRUCTURE (twist —
# nagła zmiana energii stanu E(t)) > ANOMALY (pojedyncza statystyczna
# anomalia w E(t), najsłabszy/najbardziej szumiący sygnał z tego
# zestawu) > NONE.

from enum import Enum

import numpy as np

from timdr_industrial_fusion import TIMDRIndustrialFusion
from timdr_industrial_predict import TIMDRIndustrialPredict


class IndustrialTriggerType(Enum):
    FAILURE_IMMINENT = "failure_imminent"
    STRUCTURE = "structure_twist"
    ANOMALY = "anomaly"
    NONE = "none"


class IndustrialTriggerResult:
    def __init__(self, triggered=False, trigger_type=IndustrialTriggerType.NONE,
                 location=None, message=""):
        self.triggered = triggered
        self.trigger_type = trigger_type
        self.location = location
        self.message = message

    def as_dict(self):
        return {
            "triggered": self.triggered,
            "type": self.trigger_type.value,
            "location": self.location,
            "message": self.message,
        }


class IndustrialTrigger:
    """
    Dispatcher nad TIMDRIndustrialFusion.twist()/anomalies() i
    TIMDRIndustrialPredict.predict_failure(). `fusion`/`predictor` można
    wstrzyknąć (np. w testach) - domyślnie tworzą prawdziwe instancje.

    UWAGA: `twist()`/`anomalies()` w TIMDRIndustrialFusion mają WŁASNE,
    zakodowane na stałe progi (3.5 / 3.0) - nie przyjmują progu jako
    parametru, więc ten dispatcher świadomie NIE udaje, że może je
    przestawić (unika martwego parametru konstruktora - patrz
    TIMDR-Security-Module, gdzie taki dead parameter był realnym
    błędem). Jedyny prawdziwy próg dostrajalny tutaj to
    `alert_ttf_seconds` (dla predict_failure()) i `threshold`/`window`
    przekazywane do predict_failure() przy każdym `analyze()`.
    """

    def __init__(self, alert_ttf_seconds=3600.0, fusion=None, predictor=None):
        self.fusion = fusion if fusion is not None else TIMDRIndustrialFusion()
        self.predictor = predictor if predictor is not None else TIMDRIndustrialPredict()
        self.alert_ttf_seconds = alert_ttf_seconds
        self.last_result = IndustrialTriggerResult()

    def analyze(self, t, E, threshold=3.0, window=60):
        ttf, _ttf_lin, _ttf_exp = self.predictor.predict_failure(
            t, E, threshold=threshold, window=window,
        )
        if np.isfinite(ttf) and ttf <= self.alert_ttf_seconds:
            loc = int(len(t) - 1) if len(t) else None
            return self._set_result(
                True, IndustrialTriggerType.FAILURE_IMMINENT, loc,
                f"Przewidywany czas do przekroczenia progu: {ttf:.0f}s."
            )

        twist_idx, _tw_z = self.fusion.twist(t, E)
        if len(twist_idx):
            loc = int(min(twist_idx))
            return self._set_result(
                True, IndustrialTriggerType.STRUCTURE, loc,
                "Nagła zmiana energii stanu E(t) (twist)."
            )

        anomaly_idx, _an_z = self.fusion.anomalies(E)
        if len(anomaly_idx):
            loc = int(min(anomaly_idx))
            return self._set_result(
                True, IndustrialTriggerType.ANOMALY, loc,
                "Pojedyncza statystyczna anomalia w E(t)."
            )

        return self._set_result(
            False, IndustrialTriggerType.NONE, None,
            "Brak wykrytego zdarzenia sygnałowego."
        )

    def _set_result(self, triggered, trigger_type, location, message):
        self.last_result = IndustrialTriggerResult(triggered, trigger_type, location, message)
        return self.last_result

    def get_last(self):
        return self.last_result
