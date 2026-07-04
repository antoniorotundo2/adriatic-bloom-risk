"""
Minimal API tests.

`test_health` runs everywhere (no database needed). `test_risk_endpoint_shape`
needs a live PostGIS database: it runs locally with the containers up, and is
skipped gracefully in environments without a database (e.g. CI), rather than
failing. When it does run, it enforces the design constraint that every
prediction carries an estimate together with its interval.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_risk_endpoint_shape():
    try:
        response = client.get("/api/risk")
    except Exception as exc:
        pytest.skip(f"database not available in this environment: {exc}")

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
