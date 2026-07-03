"""
Layer 2a - Sea surface temperature ingestion (Copernicus Marine), multi-year.
One file per year (sst_romagna_YYYY.nc). Resumable (skips years already present).
Run: python pipeline/ingest_sst.py
"""

import os
import copernicusmarine

DATASET_ID = "cmems_SST_MED_SST_L4_REP_OBSERVATIONS_010_021"
VARIABLE = "analysed_sst"
MIN_LON, MAX_LON = 12.20, 12.90
MIN_LAT, MAX_LAT = 43.90, 44.60
YEARS = [2018, 2019, 2020, 2021, 2022, 2023]
OUTPUT_DIR = "data/raw"


def main():
    for year in YEARS:
        out = f"sst_romagna_{year}.nc"
        if os.path.exists(os.path.join(OUTPUT_DIR, out)):
            print(f"[{year}] already present, skipping.")
            continue
        print(f"[{year}] downloading SST...")
        copernicusmarine.subset(
            dataset_id=DATASET_ID, variables=[VARIABLE],
            minimum_longitude=MIN_LON, maximum_longitude=MAX_LON,
            minimum_latitude=MIN_LAT, maximum_latitude=MAX_LAT,
            start_datetime=f"{year}-04-01", end_datetime=f"{year}-09-30",
            output_filename=out, output_directory=OUTPUT_DIR,
            coordinates_selection_method="outside",
        )
    print("\nDone. Next: python pipeline/ingest_wind.py")


if __name__ == "__main__":
    main()
