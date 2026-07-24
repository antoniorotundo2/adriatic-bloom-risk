"""
Unit tests for the pure functions in pipeline/features.py: distance, variable
detection, per-cell temporal features, and the SST nearest-VALID-pixel search
(a regression test for the masked/land pixel bug documented in
causal/README.md, "SST data coverage"). None of these need a database or
real satellite downloads.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

import features as f


def test_haversine_zero_for_same_point():
    assert f.haversine_km(12.30, 44.53, 12.30, 44.53) == pytest.approx(0.0, abs=1e-9)


def test_haversine_known_distance():
    # Casalborsetti to Cattolica, roughly 65 km along the Romagna coast.
    d = f.haversine_km(12.30, 44.53, 12.75, 43.97)
    assert 60 < d < 75


def test_detect_var_matches_case_insensitively():
    ds = xr.Dataset({"CHL": (("x",), [1.0, 2.0])})
    assert f.detect_var(ds, {"chl", "chlorophyll"}) == "CHL"


def test_detect_var_raises_when_not_found():
    ds = xr.Dataset({"other": (("x",), [1.0])})
    with pytest.raises(ValueError):
        f.detect_var(ds, {"chl"})


def test_add_features_cyclic_encoding_is_unit_norm():
    cells = pd.DataFrame([{"cell_code": "aa", "cx": 12.5, "cy": 44.5}])
    df = pd.DataFrame({
        "cell_code": ["aa", "aa"],
        "ts": pd.to_datetime(["2020-03-01", "2020-08-15"]),
        "chl": [1.0, 2.0],
    })
    out = f.add_features(df, cells)
    norm = out["doy_sin"] ** 2 + out["doy_cos"] ** 2
    assert norm.apply(lambda v: v == pytest.approx(1.0, abs=1e-9)).all()


def test_add_features_distance_from_po_mouth():
    cells = pd.DataFrame([{"cell_code": "at_mouth", "cx": f.PO_MOUTH[0], "cy": f.PO_MOUTH[1]}])
    df = pd.DataFrame({"cell_code": ["at_mouth"], "ts": pd.to_datetime(["2020-01-01"]), "chl": [1.0]})
    out = f.add_features(df, cells)
    assert out["dist_po_km"].iloc[0] == pytest.approx(0.0, abs=0.1)


def test_add_features_rolling_median_does_not_bridge_year_boundary():
    cells = pd.DataFrame([{"cell_code": "aa", "cx": 12.5, "cy": 44.5}])
    dec = pd.date_range("2019-12-26", "2019-12-31", freq="D")   # 6 rows, high values
    jan = pd.date_range("2020-01-01", "2020-01-03", freq="D")   # 3 rows, low values
    df = pd.DataFrame({
        "cell_code": "aa",
        "ts": list(dec) + list(jan),
        "chl": [100.0] * len(dec) + [1.0] * len(jan),
    })
    out = f.add_features(df, cells)
    # by the 3rd January row there are enough (cell, 2020) observations for
    # the rolling median (min_periods=3); if the window bridged the winter
    # gap into 2019's high values, the median would not be exactly 1.0.
    third_jan_median = out.loc[out["ts"] == jan[2], "chl_med_7d"].iloc[0]
    assert third_jan_median == pytest.approx(1.0)


def _write_sst_dataset(path, masked_lon, masked_lat, valid_lon, valid_lat):
    """A tiny 3x3 grid, one day, with a single masked (all-NaN) pixel and the
    rest valid, mimicking the real masked/land pixel found in production."""
    lons = sorted({masked_lon, valid_lon, valid_lon + 0.05, valid_lon - 0.05})
    lats = sorted({masked_lat, valid_lat, valid_lat + 0.05, valid_lat - 0.05})
    data = np.full((1, len(lats), len(lons)), 290.0)  # Kelvin, like the real product
    lat_idx = lats.index(masked_lat)
    lon_idx = lons.index(masked_lon)
    data[0, lat_idx, lon_idx] = np.nan
    ds = xr.Dataset(
        {"analysed_sst": (("time", "latitude", "longitude"), data)},
        coords={"time": [pd.Timestamp("2020-06-01")], "latitude": lats, "longitude": lons},
    )
    ds.to_netcdf(path)


def test_read_sst_skips_masked_pixel_for_nearest_valid(tmp_path, monkeypatch):
    cell_lon, cell_lat = 12.30, 44.53
    nc_path = tmp_path / "sst_romagna_2020.nc"
    _write_sst_dataset(nc_path, masked_lon=cell_lon, masked_lat=cell_lat,
                        valid_lon=cell_lon + 0.05, valid_lat=cell_lat)
    monkeypatch.setattr(f, "SST_GLOB", str(tmp_path / "sst_romagna_*.nc"))

    cells = pd.DataFrame([{"cell_code": "cb_05", "cx": cell_lon, "cy": cell_lat}])
    out = f.read_sst(cells)

    # the literal nearest coordinate is masked: without the fix this would be empty.
    assert len(out) == 1
    assert out["sst"].iloc[0] == pytest.approx(290.0 - 273.15, abs=0.01)
