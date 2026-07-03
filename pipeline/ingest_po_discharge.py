"""
Layer 2b-ii - Po discharge ingestion (GloFAS, Early Warning Data Store), multi-year.
One request per year (po_discharge_YYYY.nc). Resumable (skips years already present).
Each year is a queued EWDS job: with several years, expect substantial waiting.
Run: python pipeline/ingest_po_discharge.py

Note - different data store from wind: ERA5 lives on the Climate Data Store (CDS),
GloFAS on the Early Warning Data Store (EWDS). The same ECMWF account and token
work for both: only the URL differs (set below), and the GloFAS licence must be
accepted on the EWDS site.
"""

import os
import cdsapi

EWDS_URL = "https://ewds.climate.copernicus.eu/api"
DATASET = "cems-glofas-historical"
AREA = [45.05, 11.40, 44.70, 12.70]           # N, W, S, E (lower Po)
MONTHS = ["04", "05", "06", "07", "08", "09"]
YEARS = [2018, 2019, 2020, 2021, 2022, 2023]
OUTPUT_DIR = "data/raw"


def main():
    client = cdsapi.Client(url=EWDS_URL)       # key read from ~/.cdsapirc
    for year in YEARS:
        out = os.path.join(OUTPUT_DIR, f"po_discharge_{year}.nc")
        if os.path.exists(out):
            print(f"[{year}] already present, skipping.")
            continue
        print(f"[{year}] GloFAS request (queued, please wait)...")
        request = {
            "system_version": ["version_4_0"], "hydrological_model": ["lisflood"],
            "product_type": ["consolidated"],
            "variable": ["river_discharge_in_the_last_24_hours"],
            "hyear": [str(year)], "hmonth": MONTHS,
            "hday": [f"{d:02d}" for d in range(1, 32)],
            "data_format": "netcdf", "download_format": "unarchived", "area": AREA,
        }
        client.retrieve(DATASET, request, out)
    print("\nDone. Next: python pipeline/features.py")


if __name__ == "__main__":
    main()
