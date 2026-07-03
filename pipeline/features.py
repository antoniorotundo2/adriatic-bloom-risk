"""
Layer 2b - Multi-year feature engineering (robust cleaning + drivers).

Reads ALL downloaded years (data/raw/*_YYYY.nc) and merges them. It:
  1. CLEANS chlorophyll: drops artefacts (>60 mg/m^3), aggregates with the MEDIAN.
  2. Optional DRIVERS: SST (nearest pixel), wind (daily mean speed), Po discharge
     (max over the box = river channel) + 7-day lag.
  3. Temporal/spatial FEATURES. Rolling windows and lag are computed WITHIN each
     season (per year): they must not bridge the winter gap between two seasons.

Run (with the docker containers up):  python pipeline/features.py
"""

import glob
import pathlib

import numpy as np
import pandas as pd
import xarray as xr
from sqlalchemy import create_engine, text

DB_URL = "postgresql+psycopg2://sit_user:sit_password@localhost:5432/sit_microalghe"
CHL_GLOB = "data/raw/chl_romagna_*.nc"
SST_GLOB = "data/raw/sst_romagna_*.nc"
WIND_GLOB = "data/raw/era5_wind_*.nc"
PO_GLOB = "data/raw/po_discharge_*.nc"
OUT = "data/processed/features.csv"

CHL_MAX_VALID = 60.0
MIN_VALID_PIXELS = 1
PO_MOUTH = (12.50, 44.95)


def open_many(pattern):
    """Open and merge along time all files matching the pattern."""
    files = sorted(glob.glob(pattern))
    if not files:
        return None, 0
    ds = xr.open_mfdataset(files, combine="by_coords")
    if "valid_time" in ds.coords and "time" not in ds.coords:
        ds = ds.rename({"valid_time": "time"})
    return ds, len(files)


def haversine_km(lon1, lat1, lon2, lat2):
    r = 6371.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi, dlmb = np.radians(lat2 - lat1), np.radians(lon2 - lon1)
    a = np.sin(dphi/2)**2 + np.cos(p1)*np.cos(p2)*np.sin(dlmb/2)**2
    return 2 * r * np.arcsin(np.sqrt(a))


def detect_var(ds, candidates):
    for name in ds.data_vars:
        if name.lower() in candidates:
            return name
    raise ValueError(f"Variable not found among {candidates}. Available: {list(ds.data_vars)}")


def read_cells(engine):
    q = text("""
        SELECT id AS cell_id, cell_code, label,
               ST_XMin(geom) xmin, ST_XMax(geom) xmax,
               ST_YMin(geom) ymin, ST_YMax(geom) ymax,
               ST_X(ST_Centroid(geom)) cx, ST_Y(ST_Centroid(geom)) cy
        FROM coastal_cells ORDER BY cell_code;
    """)
    with engine.connect() as c:
        return pd.DataFrame(c.execute(q).mappings().all())


def clean_chlorophyll(cells):
    ds, n = open_many(CHL_GLOB)
    if ds is None:
        raise FileNotFoundError("No chlorophyll file found. Run ingest_satellite.py first.")
    print(f"Chlorophyll: {n} file(s)/year(s) merged.")
    var = detect_var(ds, {"chl", "chlorophyll"})
    rows = []
    for _, cell in cells.iterrows():
        # chlorophyll is patchy: average within the cell box (median, robust)
        sub = ds[var].where(
            (ds.longitude >= cell.xmin) & (ds.longitude <= cell.xmax) &
            (ds.latitude >= cell.ymin) & (ds.latitude <= cell.ymax), drop=True)
        if sub.size == 0:
            continue
        sub = sub.where(sub <= CHL_MAX_VALID)                       # drop satellite artefacts
        valid = sub.notnull().sum(dim=["longitude", "latitude"])    # valid pixels per day
        med = sub.median(dim=["longitude", "latitude"], skipna=True)
        for t, m, nv in zip(med["time"].values, med.values, valid.values):
            if pd.notna(m) and nv >= MIN_VALID_PIXELS:
                rows.append({"cell_code": cell.cell_code, "cell_id": int(cell.cell_id),
                             "ts": pd.to_datetime(t).normalize(), "chl": round(float(m), 4)})
    return pd.DataFrame(rows)


def read_sst(cells):
    ds, n = open_many(SST_GLOB)
    if ds is None:
        print("(SST not found: skipping temperature.)")
        return pd.DataFrame(columns=["cell_code", "ts", "sst"])
    print(f"SST: {n} file(s)/year(s) merged.")
    var = detect_var(ds, {"analysed_sst", "sst"})
    rows = []
    for _, cell in cells.iterrows():
        # SST is a smooth field: take the nearest pixel to the cell centroid
        s = ds[var].sel(longitude=cell.cx, latitude=cell.cy, method="nearest")
        for t, v in zip(s["time"].values, s.values):
            if pd.notna(v):
                celsius = float(v) - 273.15 if float(v) > 100 else float(v)  # K -> C
                rows.append({"cell_code": cell.cell_code,
                             "ts": pd.to_datetime(t).normalize(), "sst": round(celsius, 3)})
    return pd.DataFrame(rows)


def read_wind(cells):
    ds, n = open_many(WIND_GLOB)
    if ds is None:
        print("(Wind not found: skipping wind driver.)")
        return pd.DataFrame(columns=["cell_code", "ts", "wind_speed"])
    print(f"Wind: {n} file(s)/year(s) merged.")
    uname = detect_var(ds, {"u10", "10u", "10m_u_component_of_wind"})
    vname = detect_var(ds, {"v10", "10v", "10m_v_component_of_wind"})
    speed = np.sqrt(ds[uname]**2 + ds[vname]**2)
    extra = [d for d in speed.dims if d not in ("time", "latitude", "longitude")]
    if extra:
        speed = speed.mean(dim=extra)
    rows = []
    for _, cell in cells.iterrows():
        s = speed.sel(longitude=cell.cx, latitude=cell.cy, method="nearest")
        daily = s.resample(time="1D").mean()          # hourly -> daily mean
        for t, v in zip(daily["time"].values, daily.values):
            if pd.notna(v):
                rows.append({"cell_code": cell.cell_code,
                             "ts": pd.to_datetime(t).normalize(), "wind_speed": round(float(v), 3)})
    return pd.DataFrame(rows)


def read_po():
    ds, n = open_many(PO_GLOB)
    if ds is None:
        print("(Po discharge not found: skipping Po driver.)")
        return pd.DataFrame(columns=["ts", "po_discharge", "po_discharge_lag7"])
    print(f"Po discharge: {n} file(s)/year(s) merged.")
    disname = next((nm for nm in ds.data_vars if "dis" in nm.lower()), None)
    if disname is None:
        raise ValueError(f"Discharge variable not found. Available: {list(ds.data_vars)}")
    da = ds[disname]
    latdim = "latitude" if "latitude" in da.dims else "lat"
    londim = "longitude" if "longitude" in da.dims else "lon"
    extra = [d for d in da.dims if d not in ("time", latdim, londim)]
    if extra:
        da = da.max(dim=extra)
    series = da.max(dim=[latdim, londim])             # max over the box = Po channel pixel
    df = series.to_dataframe(name="po_discharge").reset_index()
    df["ts"] = pd.to_datetime(df["time"]).dt.normalize()
    df = df[["ts", "po_discharge"]].dropna().sort_values("ts").reset_index(drop=True)
    df["po_discharge"] = df["po_discharge"].round(1)
    # 7-day lag WITHIN each season (do not bridge the winter gap)
    df["year"] = df["ts"].dt.year
    df["po_discharge_lag7"] = df.groupby("year")["po_discharge"].shift(7)
    return df.drop(columns="year")


def add_features(df, cells):
    df = df.sort_values(["cell_code", "ts"]).reset_index(drop=True)
    df["year"] = df["ts"].dt.year
    df["month"] = df["ts"].dt.month
    doy = df["ts"].dt.dayofyear
    df["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)          # cyclic seasonality
    df["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)
    # Rolling medians WITHIN each (cell, year): they do not bridge the winter gap
    g = df.groupby(["cell_code", "year"])["chl"]
    df["chl_med_7d"] = g.transform(lambda s: s.rolling(7, min_periods=3).median())
    df["chl_med_30d"] = g.transform(lambda s: s.rolling(30, min_periods=10).median())
    # Distance from the Po mouth (static per cell): explains the north-south gradient
    dist = {c.cell_code: round(haversine_km(c.cx, c.cy, *PO_MOUTH), 1) for _, c in cells.iterrows()}
    df["dist_po_km"] = df["cell_code"].map(dist)
    return df


def refresh_map(engine, chl_df):
    """Refresh chlorophyll_obs with the cleaned values (latest date per cell only)."""
    latest = chl_df.sort_values("ts").groupby("cell_code").tail(1)
    try:
        with engine.begin() as conn:
            for _, r in latest.iterrows():
                conn.execute(text("""
                    INSERT INTO chlorophyll_obs (cell_id, ts, chl_mean, source)
                    VALUES (:cid, :ts, :chl, 'copernicus_marine_clean')
                    ON CONFLICT (cell_id, ts) DO UPDATE SET
                        chl_mean = EXCLUDED.chl_mean, source = EXCLUDED.source;
                """), {"cid": int(r.cell_id), "ts": r.ts.date(), "chl": float(r.chl)})
        print("Map: chlorophyll_obs refreshed with the latest cleaned values.")
    except Exception as e:
        print(f"(Map refresh skipped: {e})")


def main():
    engine = create_engine(DB_URL)
    cells = read_cells(engine)

    chl = clean_chlorophyll(cells)
    yr = chl["ts"].dt.year
    print(f"\nCleaned chlorophyll: {len(chl)} cell-day rows, years {yr.min()}-{yr.max()}.")
    print("Median chlorophyll per cell (mg/m^3):")
    print(chl.groupby("cell_code")["chl"].median().round(2).to_string())

    df = chl
    for extra in (read_sst(cells), read_wind(cells)):
        if not extra.empty:
            df = df.merge(extra, on=["cell_code", "ts"], how="left")
    po = read_po()
    if not po.empty:
        df = df.merge(po, on="ts", how="left")     # basin-level driver: same value for all cells

    df = add_features(df, cells)

    pathlib.Path("data/processed").mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    print(f"\nWrote {len(df)} feature rows to {OUT}")
    print(f"Columns: {list(df.columns)}")

    refresh_map(engine, chl)


if __name__ == "__main__":
    main()
