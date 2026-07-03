"""
SIT API: serves bloom-risk predictions as GeoJSON, always with a point estimate
plus an uncertainty interval (never a bare number).
"""

from datetime import date
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, text

app = FastAPI(
    title="Adriatic Bloom Risk - Romagna coast",
    description="Phytoplankton bloom-risk mapping with quantified uncertainty.",
    version="0.1.0",
)

DB_URL = "postgresql+psycopg2://sit_user:sit_password@db:5432/sit_microalghe"
engine = create_engine(DB_URL)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/risk")
def get_risk(ts: Optional[date] = Query(None, description="Prediction date (default: most recent available)")):
    """
    Return a GeoJSON FeatureCollection with the bloom risk per coastal cell.
    Every feature ALWAYS carries three linked values: risk_estimate (point
    estimate) and risk_lower / risk_upper (interval at the given confidence
    level) -- never just the central value.
    """
    target_date_clause = "AND p.ts = :ts" if ts else """
        AND p.ts = (SELECT MAX(ts) FROM predictions)
    """
    query = text(f"""
        SELECT
            c.cell_code,
            c.label,
            p.ts,
            p.risk_estimate,
            p.risk_lower,
            p.risk_upper,
            p.confidence_level,
            p.model_version,
            p.chl_pred,
            p.chl_lower,
            p.chl_upper,
            p.threshold,
            ST_AsGeoJSON(c.geom) AS geometry
        FROM coastal_cells c
        JOIN predictions p ON p.cell_id = c.id
        WHERE 1=1 {target_date_clause}
        ORDER BY c.cell_code;
    """)
    with engine.connect() as conn:
        rows = conn.execute(query, {"ts": ts} if ts else {}).mappings().all()

    features = [
        {
            "type": "Feature",
            "geometry": __import__("json").loads(row["geometry"]),
            "properties": {
                "cell_code": row["cell_code"],
                "label": row["label"],
                "date": row["ts"].isoformat(),
                "risk_estimate": float(row["risk_estimate"]),
                "risk_lower": float(row["risk_lower"]),
                "risk_upper": float(row["risk_upper"]),
                "uncertainty_width": float(row["risk_upper"]) - float(row["risk_lower"]),
                "confidence_level": float(row["confidence_level"]),
                "model_version": row["model_version"],
                "chl_pred": float(row["chl_pred"]) if row["chl_pred"] is not None else None,
                "chl_lower": float(row["chl_lower"]) if row["chl_lower"] is not None else None,
                "chl_upper": float(row["chl_upper"]) if row["chl_upper"] is not None else None,
                "threshold": float(row["threshold"]) if row["threshold"] is not None else None,
            },
        }
        for row in rows
    ]
    return {"type": "FeatureCollection", "features": features}


@app.get("/api/stations")
def get_stations():
    """Return the in-situ monitoring stations as GeoJSON points."""
    query = text("""
        SELECT code, name, distance_km, ST_AsGeoJSON(geom) AS geometry
        FROM stations ORDER BY code;
    """)
    with engine.connect() as conn:
        rows = conn.execute(query).mappings().all()

    features = [
        {
            "type": "Feature",
            "geometry": __import__("json").loads(row["geometry"]),
            "properties": {
                "code": row["code"],
                "name": row["name"],
                "distance_km": row["distance_km"],
            },
        }
        for row in rows
    ]
    return {"type": "FeatureCollection", "features": features}


@app.get("/api/chlorophyll")
def get_chlorophyll():
    """
    Return observed chlorophyll-a (real Copernicus Marine data) per coastal
    cell, at the most recent available date, as GeoJSON. Resilient: if the
    table has not been populated by ingestion yet, returns an empty collection
    instead of raising.
    """
    query = text("""
        SELECT c.cell_code, c.label, o.ts, o.chl_mean, ST_AsGeoJSON(c.geom) AS geometry
        FROM coastal_cells c
        JOIN chlorophyll_obs o ON o.cell_id = c.id
        WHERE o.ts = (SELECT MAX(ts) FROM chlorophyll_obs)
        ORDER BY c.cell_code;
    """)
    try:
        with engine.connect() as conn:
            rows = conn.execute(query).mappings().all()
    except Exception:
        # Table not created yet (ingestion not run): no real data available.
        return {"type": "FeatureCollection", "features": []}

    features = [
        {
            "type": "Feature",
            "geometry": __import__("json").loads(row["geometry"]),
            "properties": {
                "cell_code": row["cell_code"],
                "label": row["label"],
                "date": row["ts"].isoformat(),
                "chl_mean": float(row["chl_mean"]) if row["chl_mean"] is not None else None,
            },
        }
        for row in rows
    ]
    return {"type": "FeatureCollection", "features": features}


# Serve the static Leaflet web map at the root, so the whole system is reachable
# from a single URL: API under /api/*, map at /.
app.mount("/", StaticFiles(directory="/app/webmap", html=True), name="webmap")
