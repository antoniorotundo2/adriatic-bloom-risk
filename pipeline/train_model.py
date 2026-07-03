"""
Layer 3 - Predictive model (chlorophyll regression + derived risk).

What it does, and why each choice:
  * TARGET: chlorophyll (mg/m^3) - the only quantity we actually observe.
  * PREDICTORS: only environmental DRIVERS (Po, SST, wind, season, distance
    from the Po). NOT past chlorophyll: the model learns the dynamics, not the
    trivial "tomorrow ~ today" persistence.
  * HONEST BASELINE: compare against persistence (yesterday's chl). A serious
    model should beat it.
  * TEMPORAL VALIDATION: train on the past, calibrate in the middle, test on the
    future. Never a random split (that would peek into the future).
  * UNCERTAINTY: split-conformal -> every prediction has an interval whose ~90%
    coverage is VALIDATED on the test set.
  * RISK %: probability that chlorophyll exceeds the CELL's high threshold (local
    90th percentile). Uses the same conformal residuals: no absolute threshold
    that would make the model just learn geography.
  * SST NaNs: SST (coarse pixel near the shore) has many gaps -> filled by
    interpolating in time within each cell (smooth field, legitimate interpolation).

Run (with the docker containers up):  python pipeline/train_model.py
"""

import lightgbm as lgb
import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

DB_URL = "postgresql+psycopg2://sit_user:sit_password@localhost:5432/sit_microalghe"
FEATURES_CSV = "data/processed/features.csv"
MODEL_VERSION = "lgbm-conformal-0.1"
CONF_LEVEL = 0.90

# Exogenous drivers only: past chlorophyll is NOT included (no persistence).
DRIVER_FEATURES = ["sst", "wind_speed", "po_discharge", "po_discharge_lag7",
                   "month", "doy_sin", "doy_cos", "dist_po_km"]


def load():
    df = pd.read_csv(FEATURES_CSV, parse_dates=["ts"])
    df["year"] = df["ts"].dt.year
    df = df.sort_values(["cell_code", "ts"]).reset_index(drop=True)
    # Fill SST gaps by interpolating in time WITHIN each (cell, year)
    df["sst"] = df.groupby(["cell_code", "year"])["sst"].transform(
        lambda s: s.interpolate(limit_direction="both"))
    # Persistence baseline: previous day's chlorophyll, within each (cell, year)
    df["chl_lag1"] = df.groupby(["cell_code", "year"])["chl"].shift(1)
    return df


def temporal_split(df):
    """
    With multiple years: train on past years, calibrate on the second-to-last,
    test on the last UNSEEN year (realistic validation). With a single year:
    fall back to a 60/20/20 split by date.
    """
    years = sorted(df["year"].unique())
    if len(years) >= 3:
        test_y, calib_y = years[-1], years[-2]
        train = df[df.year < calib_y]
        calib = df[df.year == calib_y]
        test = df[df.year == test_y]
        print(f"Split by year -> train:{years[0]}-{calib_y-1}  calib:{calib_y}  test:{test_y}")
    else:
        dates = np.sort(df["ts"].unique())
        d1, d2 = dates[int(0.60*len(dates))], dates[int(0.80*len(dates))]
        train = df[df.ts < d1]; calib = df[(df.ts >= d1) & (df.ts < d2)]; test = df[df.ts >= d2]
        print(f"Split by date (single year) -> train:{len(train)} calib:{len(calib)} test:{len(test)}")
    return train, calib, test


def main():
    df = load()
    train, calib, test = temporal_split(df)

    model = lgb.LGBMRegressor(
        n_estimators=200, learning_rate=0.05, num_leaves=15,
        min_child_samples=20, subsample=0.8, colsample_bytree=0.8,
        random_state=42, verbose=-1)
    model.fit(train[DRIVER_FEATURES], train["chl"])

    # --- Conformal calibration: signed residuals on the calibration set ---
    calib_resid = calib["chl"].values - model.predict(calib[DRIVER_FEATURES])
    q = np.quantile(np.abs(calib_resid), CONF_LEVEL)   # 90% interval half-width

    # --- Honest evaluation on the test set (unseen future) ---
    test_pred = model.predict(test[DRIVER_FEATURES])
    mae_model = np.mean(np.abs(test["chl"].values - test_pred))
    persist = test.dropna(subset=["chl_lag1"])
    mae_persist = np.mean(np.abs(persist["chl"].values - persist["chl_lag1"].values))
    coverage = np.mean(np.abs(test["chl"].values - test_pred) <= q)

    print("\n=== Test-set evaluation ===")
    print(f"  MAE model (from drivers):    {mae_model:.3f} mg/m^3")
    print(f"  MAE persistence (chl y'day): {mae_persist:.3f} mg/m^3")
    verdict = "beats" if mae_model < mae_persist else "does NOT beat"
    print(f"  -> the model {verdict} persistence")
    print(f"  90% interval coverage:       {coverage:.1%} (expected ~90%)")
    print(f"  Interval half-width q:       +/-{q:.2f} mg/m^3")

    print("\n=== Driver importance (gain) ===")
    imp = pd.Series(model.feature_importances_, index=DRIVER_FEATURES).sort_values(ascending=False)
    print(imp.to_string())

    # --- Per-cell high threshold (local 90th percentile of chlorophyll) ---
    thr = df.groupby("cell_code")["chl"].quantile(0.90).to_dict()

    # --- Predictions for each cell's latest available date (map "current" state) ---
    rows = []
    for cell_code, g in df.groupby("cell_code"):
        r = g.sort_values("ts").iloc[-1]                      # last row of the cell
        Xrow = g.sort_values("ts").iloc[[-1]][DRIVER_FEATURES]
        yhat = float(model.predict(Xrow)[0])
        chl_lo, chl_hi = max(0.0, yhat - q), yhat + q
        tau = thr[cell_code]
        # Risk = P(chlorophyll > cell threshold), estimated from conformal residuals
        exceed = float(np.mean((yhat + calib_resid) > tau))
        # Risk band: widens when the chlorophyll prediction is uncertain
        wnorm = min(1.0, (chl_hi - chl_lo) / max(tau, 0.1))
        risk_lo = max(0.0, exceed - 0.5 * wnorm)
        risk_hi = min(1.0, exceed + 0.5 * wnorm)
        rows.append({
            "cell_id": int(r["cell_id"]), "ts": pd.to_datetime(r["ts"]).date(),
            "risk_estimate": round(float(exceed), 3), "risk_lower": round(float(risk_lo), 3),
            "risk_upper": round(float(risk_hi), 3), "chl_pred": round(float(yhat), 3),
            "chl_lower": round(float(chl_lo), 3), "chl_upper": round(float(chl_hi), 3),
            "threshold": round(float(tau), 3),
        })

    store(rows)
    print(f"\nWrote {len(rows)} real predictions to PostGIS (version {MODEL_VERSION}).")
    print("Now rebuild the API and open the map:  docker compose up --build -d")


def store(rows):
    engine = create_engine(DB_URL)
    with engine.begin() as conn:
        # Add the chlorophyll columns if missing (idempotent)
        for col in ("chl_pred", "chl_lower", "chl_upper", "threshold"):
            conn.execute(text(f"ALTER TABLE predictions ADD COLUMN IF NOT EXISTS {col} NUMERIC;"))
        # Replace the demo seed data with the model's real predictions
        conn.execute(text("DELETE FROM predictions WHERE model_version LIKE 'seed-demo%';"))
        for r in rows:
            conn.execute(text("""
                INSERT INTO predictions
                    (cell_id, ts, risk_estimate, risk_lower, risk_upper,
                     confidence_level, model_version, chl_pred, chl_lower, chl_upper, threshold)
                VALUES
                    (:cell_id, :ts, :risk_estimate, :risk_lower, :risk_upper,
                     0.90, :model_version, :chl_pred, :chl_lower, :chl_upper, :threshold)
                ON CONFLICT (cell_id, ts) DO UPDATE SET
                    risk_estimate=EXCLUDED.risk_estimate, risk_lower=EXCLUDED.risk_lower,
                    risk_upper=EXCLUDED.risk_upper, model_version=EXCLUDED.model_version,
                    chl_pred=EXCLUDED.chl_pred, chl_lower=EXCLUDED.chl_lower,
                    chl_upper=EXCLUDED.chl_upper, threshold=EXCLUDED.threshold;
            """), {**r, "model_version": MODEL_VERSION})


if __name__ == "__main__":
    main()
