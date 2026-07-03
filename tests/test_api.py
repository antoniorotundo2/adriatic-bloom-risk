"""
Minimal API tests: check that the endpoints respond and that every returned
prediction always carries an estimate plus an interval (never a bare value).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_risk_endpoint_shape():
    response = client.get("/api/risk")
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "FeatureCollection"
    for feature in body["features"]:
        props = feature["properties"]
        # Design constraint: a prediction without an interval is not allowed.
        assert "risk_estimate" in props
        assert "risk_lower" in props
        assert "risk_upper" in props
        assert props["risk_lower"] <= props["risk_estimate"] <= props["risk_upper"]
