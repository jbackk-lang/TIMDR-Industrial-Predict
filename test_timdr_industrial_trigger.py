"""
test_timdr_industrial_trigger.py — testy timdr_industrial_trigger.py.

Ten plik NIE re-weryfikuje matematyki TIMDRIndustrialFusion.twist()/
anomalies() ani TIMDRIndustrialPredict.predict_failure() (już
przetestowane w test_timdr_industrial_fusion.py/test_timdr_industrial_predict.py)
- to nie jest robota dispatchera. Dwa rodzaje testów:

1. test_anomaly_na_realnym_pojedynczym_skoku - JEDEN test integracyjny na
   prawdziwym TIMDRIndustrialFusion (bez mockowania), z ręcznie
   wyprowadzonym z-score (pojedynczy skok 10->20 wśród 10 próbek E(t) -
   ten sam wzorzec MAD=0 -> fallback rozstęp/4 jak w bio_core.py z
   TIMDR-Bio-Signals, ten sam _mad_z()).
2. Reszta testów wstrzykuje fałszywe `fusion`/`predictor` (stuby
   zwracające ustalone wyniki) - testujemy WYŁĄCZNIE logikę
   priorytetów/mapowania dispatchera.
"""
from timdr_industrial_fusion import TIMDRIndustrialFusion
from timdr_industrial_trigger import IndustrialTrigger, IndustrialTriggerType


# ----------------------------------------------------------------------
# 1) Test integracyjny na realnym TIMDRIndustrialFusion
# ----------------------------------------------------------------------

def test_anomaly_na_realnym_pojedynczym_skoku():
    """
    E(t) = [10]*10 z pojedynczym skokiem do 20 w idx=5.
    _mad_z: mediana=10, mad_raw=median(|E-10|)=0 (9 z 10 wartosci to 0)
    -> fallback span/4 = (20-10)/4 = 2.5. z[5]=(20-10)/2.5=4.0 > 3.0
    (prog wewnetrzny anomalies()) -> anomalies() zwraca [5].

    twist(): dds (druga pochodna) = [0,0,0,2.5,0,-5,0,2.5,0,0] (dwa
    przeciwstawne piki wokol skoku), fallback span/4 = (2.5-(-5))/4=1.875,
    z_max=5/1.875=2.667 < prog wewnetrzny 3.5 -> twist() PUSTE.

    Zaslepiony `predictor` (predict_failure zwraca inf) wylacza
    FAILURE_IMMINENT, wiec dociera do ANOMALY.
    """
    t = list(range(10))
    E = [10.0] * 10
    E[5] = 20.0

    fusion = TIMDRIndustrialFusion()
    anomaly_idx, _ = fusion.anomalies(E)
    assert list(anomaly_idx) == [5]  # sanity
    twist_idx, _ = fusion.twist(t, E)
    assert len(twist_idx) == 0  # sanity - dowod ze to naprawde ANOMALY, nie STRUCTURE

    trigger = IndustrialTrigger(predictor=_InfPredictor())
    result = trigger.analyze(t, E)

    assert result.triggered is True
    assert result.trigger_type == IndustrialTriggerType.ANOMALY
    assert result.location == 5


class _InfPredictor:
    """Stub predict_failure() zawsze zwracajacy 'brak przewidywanej awarii'
    (inf) - uzywany, gdy test chce dojsc do STRUCTURE/ANOMALY/NONE bez
    ingerencji warstwy FAILURE_IMMINENT."""

    def predict_failure(self, t, E, threshold=3.0, window=60):
        return float("inf"), float("inf"), float("inf")


# ----------------------------------------------------------------------
# 2) Testy priorytetów/mapowania z wstrzykniętymi stubami
# ----------------------------------------------------------------------

class _FakeFusion:
    def __init__(self, twist_idx=None, anomaly_idx=None):
        self._twist_idx = twist_idx or []
        self._anomaly_idx = anomaly_idx or []

    def twist(self, t, E):
        return self._twist_idx, []

    def anomalies(self, E):
        return self._anomaly_idx, []


class _FakePredictor:
    def __init__(self, ttf=float("inf")):
        self._ttf = ttf

    def predict_failure(self, t, E, threshold=3.0, window=60):
        return self._ttf, self._ttf, self._ttf


def _dummy_args():
    return list(range(5)), [0.0] * 5


def test_priorytet_failure_imminent_nad_wszystkim():
    fusion = _FakeFusion(twist_idx=[1], anomaly_idx=[0])
    predictor = _FakePredictor(ttf=120.0)
    trigger = IndustrialTrigger(alert_ttf_seconds=3600.0, fusion=fusion, predictor=predictor)
    t, E = _dummy_args()
    result = trigger.analyze(t, E)
    assert result.trigger_type == IndustrialTriggerType.FAILURE_IMMINENT
    assert result.location == len(t) - 1
    assert "120" in result.message


def test_ttf_powyzej_progu_nie_odpala_failure_imminent():
    fusion = _FakeFusion(twist_idx=[2])
    predictor = _FakePredictor(ttf=99999.0)
    trigger = IndustrialTrigger(alert_ttf_seconds=3600.0, fusion=fusion, predictor=predictor)
    t, E = _dummy_args()
    result = trigger.analyze(t, E)
    assert result.trigger_type == IndustrialTriggerType.STRUCTURE
    assert result.location == 2


def test_priorytet_structure_nad_anomaly():
    fusion = _FakeFusion(twist_idx=[3], anomaly_idx=[0])
    trigger = IndustrialTrigger(fusion=fusion, predictor=_InfPredictor())
    t, E = _dummy_args()
    result = trigger.analyze(t, E)
    assert result.trigger_type == IndustrialTriggerType.STRUCTURE
    assert result.location == 3


def test_anomaly_gdy_reszta_pusta():
    fusion = _FakeFusion(anomaly_idx=[4])
    trigger = IndustrialTrigger(fusion=fusion, predictor=_InfPredictor())
    t, E = _dummy_args()
    result = trigger.analyze(t, E)
    assert result.triggered is True
    assert result.trigger_type == IndustrialTriggerType.ANOMALY
    assert result.location == 4


def test_none_gdy_wszystko_puste():
    fusion = _FakeFusion()
    trigger = IndustrialTrigger(fusion=fusion, predictor=_InfPredictor())
    t, E = _dummy_args()
    result = trigger.analyze(t, E)
    assert result.triggered is False
    assert result.trigger_type == IndustrialTriggerType.NONE
    assert result.location is None


def test_get_last_zwraca_ostatni_wynik():
    fusion = _FakeFusion(anomaly_idx=[1])
    trigger = IndustrialTrigger(fusion=fusion, predictor=_InfPredictor())
    t, E = _dummy_args()
    result = trigger.analyze(t, E)
    assert trigger.get_last() is result
