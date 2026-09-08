"""test_api.py -- testy Flask API TIMDR Industrial Predict.

Repo nie mialo dotad zadnych testow warstwy api.py (test_*.py pokrywaly
tylko modul fusion/predict/trigger/bearing_meta_adapter bezposrednio) -
ten plik pokrywa NOWE endpointy /api/bearing/* (dodane przy wpinaniu
bearing_meta_adapter.py w dashboard), nie probuje pokryc calego
istniejacego api.py retroaktywnie.
"""
import pytest

import api as api_module


@pytest.fixture()
def client():
    api_module.app.testing = True
    return api_module.app.test_client()


def test_bearing_scenarios_lists_four_fixtures(client):
    r = client.get("/api/bearing/scenarios")
    assert r.status_code == 200
    ids = {s["id"] for s in r.get_json()}
    assert ids == {"normal", "ir21", "or6_21", "b21"}


def test_bearing_demo_normal_self_comparison_has_zero_rho(client):
    """Zdrowe lozysko porownane samo ze soba -> rho=0 na kazdym oknie
    (ten sam wynik, co test_bearing_meta_adapter.py::
    test_real_data_negative_control_normal_vs_itself_gives_zero_rho)."""
    r = client.get("/api/bearing/demo?fault=normal")
    assert r.status_code == 200
    data = r.get_json()
    assert data["fault"] == "normal"
    states = data["result"]["states"]
    assert len(states) == 4
    assert all(s["rho"] == 0.0 for s in states)


@pytest.mark.parametrize("fault", ["ir21", "or6_21", "b21"])
def test_bearing_demo_fault_has_higher_rho_and_lambda_than_normal(client, fault):
    normal = client.get("/api/bearing/demo?fault=normal").get_json()
    faulty = client.get(f"/api/bearing/demo?fault={fault}").get_json()

    mean_rho_normal = sum(s["rho"] for s in normal["result"]["states"]) / 4
    mean_rho_fault = sum(s["rho"] for s in faulty["result"]["states"]) / 4
    mean_lambda_normal = sum(s["Lambda"] for s in normal["result"]["states"]) / 4
    mean_lambda_fault = sum(s["Lambda"] for s in faulty["result"]["states"]) / 4

    assert mean_rho_fault > mean_rho_normal
    assert mean_lambda_fault > mean_lambda_normal


def test_bearing_demo_unknown_fault_returns_400(client):
    r = client.get("/api/bearing/demo?fault=nieistniejacy")
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_bearing_demo_response_has_magnitude_and_trigger(client):
    r = client.get("/api/bearing/demo?fault=ir21")
    result = r.get_json()["result"]
    assert len(result["magnitude"]) == len(result["states"]) - 1
    assert len(result["phases"]) == len(result["magnitude"])
    assert "triggered" in result["trigger"]
