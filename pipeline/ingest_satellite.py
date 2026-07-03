"""
Layer 1 - Chlorophyll-a ingestion (Copernicus Marine), multi-year.

Downloads one file per year (chl_romagna_YYYY.nc). Resumable: years already
downloaded are skipped, so you can interrupt and resume.

Prerequisites: Copernicus Marine account + `copernicusmarine login` (once).
Run:           python pipeline/ingest_satellite.py
"""

import os
import copernicusmarine

DATASET_ID = "cmems_obs-oc_med_bgc-plankton_my_l4-gapfree-multi-1km_P1D"
VARIABLE = "CHL"
MIN_LON, MAX_LON = 12.20, 12.90
MIN_LAT, MAX_LAT = 43.90, 44.60

# Years to download: edit the range HERE. More years = stronger model, but
# longer downloads. For a first run you can shorten the list.
YEARS = [2018, 2019, 2020, 2021, 2022, 2023]

OUTPUT_DIR = "data/raw"


def main():
    for year in YEARS:
        out = f"chl_romagna_{year}.nc"
        if os.path.exists(os.path.join(OUTPUT_DIR, out)):
            print(f"[{year}] already present, skipping.")
            continue
        print(f"[{year}] downloading chlorophyll...")
        copernicusmarine.subset(
            dataset_id=DATASET_ID, variables=[VARIABLE],
            minimum_longitude=MIN_LON, maximum_longitude=MAX_LON,
            minimum_latitude=MIN_LAT, maximum_latitude=MAX_LAT,
            start_datetime=f"{year}-04-01", end_datetime=f"{year}-09-30",
            output_filename=out, output_directory=OUTPUT_DIR,
            coordinates_selection_method="outside",
        )
    print("\nDone. Next: python pipeline/ingest_sst.py")


if __name__ == "__main__":
    main()
