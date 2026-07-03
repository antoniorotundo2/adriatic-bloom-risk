-- Initial SIT schema: monitoring stations, coastal cells and predictions.
-- Uncertainty (risk_lower / risk_upper) is native to the schema from the start,
-- not a column added later: it comes from conformal prediction (see
-- pipeline/train_model.py), computed together with the point estimate.

CREATE EXTENSION IF NOT EXISTS postgis;

-- In-situ monitoring stations (e.g. ARPAE-Daphne transects).
CREATE TABLE IF NOT EXISTS stations (
    id          SERIAL PRIMARY KEY,
    code        TEXT NOT NULL UNIQUE,      -- e.g. 'cesenatico_0.5km'
    name        TEXT NOT NULL,
    distance_km NUMERIC,                   -- distance from shore (0.5 / 3 km)
    geom        GEOMETRY(Point, 4326) NOT NULL
);

-- Grid of coastal cells on which the model produces a prediction.
CREATE TABLE IF NOT EXISTS coastal_cells (
    id          SERIAL PRIMARY KEY,
    cell_code   TEXT NOT NULL UNIQUE,
    label       TEXT,                      -- e.g. 'Cesenatico North'
    geom        GEOMETRY(Polygon, 4326) NOT NULL
);

-- Predictions: one row per cell x date. The point estimate and the confidence
-- interval always travel together, never separately.
CREATE TABLE IF NOT EXISTS predictions (
    id              SERIAL PRIMARY KEY,
    cell_id         INTEGER NOT NULL REFERENCES coastal_cells(id),
    ts              DATE NOT NULL,
    risk_estimate   NUMERIC NOT NULL,      -- model point estimate [0,1]
    risk_lower      NUMERIC NOT NULL,      -- interval lower bound (conformal)
    risk_upper      NUMERIC NOT NULL,      -- interval upper bound (conformal)
    confidence_level NUMERIC DEFAULT 0.90, -- target coverage level (e.g. 90%)
    model_version   TEXT,                  -- tracks which model produced the row
    chl_pred        NUMERIC,               -- predicted chlorophyll (mg/m^3)
    chl_lower       NUMERIC,               -- chlorophyll interval lower bound
    chl_upper       NUMERIC,               -- chlorophyll interval upper bound
    threshold       NUMERIC,               -- cell high threshold (local 90th pct)
    UNIQUE (cell_id, ts)
);

CREATE INDEX IF NOT EXISTS idx_predictions_ts ON predictions (ts);
CREATE INDEX IF NOT EXISTS idx_stations_geom ON stations USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_cells_geom ON coastal_cells USING GIST (geom);

-- ---------------------------------------------------------------------------
-- Demo (seed) data to run the system immediately, without waiting for the
-- ARPAE-Daphne data. Five indicative cells along the Romagna coast, from the
-- Po mouth (most nutrient-exposed area) to Cattolica.
-- Coordinates are indicative and should be replaced with the real grid.
-- ---------------------------------------------------------------------------

INSERT INTO coastal_cells (cell_code, label, geom) VALUES
('cb_05', 'Casalborsetti', ST_GeomFromText('POLYGON((12.29 44.52, 12.31 44.52, 12.31 44.54, 12.29 44.54, 12.29 44.52))', 4326)),
('la_05', 'Lido Adriano', ST_GeomFromText('POLYGON((12.32 44.41, 12.34 44.41, 12.34 44.43, 12.32 44.43, 12.32 44.41))', 4326)),
('ce_05', 'Cesenatico', ST_GeomFromText('POLYGON((12.40 44.19, 12.42 44.19, 12.42 44.21, 12.40 44.21, 12.40 44.19))', 4326)),
('ri_05', 'Rimini', ST_GeomFromText('POLYGON((12.57 44.07, 12.59 44.07, 12.59 44.09, 12.57 44.09, 12.57 44.07))', 4326)),
('ca_05', 'Cattolica', ST_GeomFromText('POLYGON((12.74 43.96, 12.76 43.96, 12.76 43.98, 12.74 43.98, 12.74 43.96))', 4326))
ON CONFLICT (cell_code) DO NOTHING;

INSERT INTO predictions (cell_id, ts, risk_estimate, risk_lower, risk_upper, confidence_level, model_version)
SELECT id, CURRENT_DATE,
       v.risk_estimate, v.risk_lower, v.risk_upper, 0.90, 'seed-demo-0.1'
FROM coastal_cells
JOIN (VALUES
    ('cb_05', 0.58, 0.40, 0.74),
    ('la_05', 0.49, 0.33, 0.65),
    ('ce_05', 0.31, 0.18, 0.46),
    ('ri_05', 0.22, 0.11, 0.35),
    ('ca_05', 0.17, 0.07, 0.29)
) AS v(cell_code, risk_estimate, risk_lower, risk_upper) USING (cell_code)
ON CONFLICT (cell_id, ts) DO NOTHING;
