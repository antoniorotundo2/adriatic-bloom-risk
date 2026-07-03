"""
Layer 2b-i - Wind ingestion (ERA5, Climate Data Store), multi-year.
One request per year (era5_wind_YYYY.nc). Resumable (skips years already present).
Each year is a queued CDS job: with several years, expect substantial waiting.
Run: python pipeline/ingest_wind.py

Prerequisites (once):
  1. ECMWF account: https://cds.climate.copernicus.eu
  2. Put your token in ~/.cdsapirc :
       url: https://cds.climate.copernicus.eu/api
       key: <YOUR-TOKEN>
  3. Accept the licence of "ERA5 hourly data on single levels" on its page.
"""

import os
import cdsapi

CDS_URL = "https://cds.climate.copernicus.eu/api"
DATASET = "reanalysis-era5-single-levels"
AREA = [44.60, 12.20, 43.90, 12.90]           # N, W, S, E
MONTHS = ["04", "05", "06", "07", "08", "09"]
YEARS = [2018, 2019, 2020, 2021, 2022, 2023]
OUTPUT_DIR = "data/raw"


def main():
    client = cdsapi.Client(url=CDS_URL)        # key read from ~/.cdsapirc
    for year in YEARS:
        out = os.path.join(OUTPUT_DIR, f"era5_wind_{year}.nc")
        if os.path.exists(out):
            print(f"[{year}] already present, skipping.")
            continue
        print(f"[{year}] ERA5 request (queued, please wait)...")
        request = {
            "product_type": ["reanalysis"],
            "variable": ["10m_u_component_of_wind", "10m_v_component_of_wind"],
            "year": [str(year)], "month": MONTHS,
            "day": [f"{d:02d}" for d in range(1, 32)],
            "time": [f"{h:02d}:00" for h in range(24)],
            "data_format": "netcdf", "download_format": "unarchived", "area": AREA,
        }
        client.retrieve(DATASET, request, out)
    print("\nDone. Next: python pipeline/ingest_po_discharge.py")


if __name__ == "__main__":
    main()
