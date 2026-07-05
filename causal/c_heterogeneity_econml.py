"""
Causal layer - Step C: heterogeneity and non-stationarity (EconML).

Steps A and B estimated a single AVERAGE effect of the Po on chlorophyll. This
step asks a different, more ambitious question: does that effect VARY?

Two sub-questions, treated with different confidence given the data at hand:

  1. TEMPORAL heterogeneity (main analysis): has the Po effect changed across
     the 2018-2023 seasons? This is the more defensible question: each year
     contributes hundreds of cell-day rows, so there is real variation to
     learn from. A changing effect would be consistent with the documented
     northern-Adriatic oligotrophication trend (declining phosphorus loads).

  2. SPATIAL heterogeneity (descriptive only): does the effect vary with
     distance from the Po mouth? With only 5 cells this is descriptive, not
     statistically defensible - reported as an illustration, not a claim.

Method: EconML's CausalForestDML, a Double Machine Learning causal forest.
Unlike step A/B's single linear coefficient, it lets the estimated effect
depend on heterogeneity features (X), while still adjusting for confounders
(W) via flexible ML nuisance models - the DML equivalent of DoWhy's backdoor
adjustment, but allowing non-linearity and a per-observation effect.

ESECUZIONE:  python causal/c_heterogeneity_econml.py
"""

import numpy as np
import pandas as pd
from econml.dml import CausalForestDML
from lightgbm import LGBMRegressor
from sklearn.model_selection import GroupKFold

FEATURES_CSV = "data/processed/features.csv"

TREATMENT = "po_k"                 # Po discharge (t-7), in 1000 m^3/s
OUTCOME = "chl"
CONFOUNDERS = ["doy_sin", "doy_cos", "sst", "wind_speed"]   # nuisance controls (W)
HETEROGENEITY_TIME = ["year"]                                # X for temporal CATE
HETEROGENEITY_SPACE = ["dist_po_km"]                         # X for spatial CATE (descriptive)


def load():
    df = pd.read_csv(FEATURES_CSV, parse_dates=["ts"])
    df = df.dropna(subset=["po_discharge_lag7", OUTCOME] + CONFOUNDERS + ["dist_po_km"]).copy()
    df["po_k"] = df["po_discharge_lag7"] / 1000.0
    return df


def fit_forest(df, X_cols):
    """
    Fits CausalForestDML with continuous treatment. Nuisance models (predicting
    Y and T from confounders) use LightGBM, matching the predictive layer.
    Cross-fitting is grouped by year, so a season is never used to help
    predict itself (mirrors the temporal split used for the predictive model).
    """
    Y = df[OUTCOME].values
    Tt = df[TREATMENT].values
    X = df[X_cols].values
    W = df[CONFOUNDERS].values
    groups = df["year"].values

    est = CausalForestDML(
        model_y=LGBMRegressor(n_estimators=100, max_depth=4, verbose=-1),
        model_t=LGBMRegressor(n_estimators=100, max_depth=4, verbose=-1),
        discrete_treatment=False,
        cv=GroupKFold(n_splits=min(5, len(np.unique(groups)))),
        n_estimators=500,
        min_samples_leaf=20,
        random_state=42,
    )
    est.fit(Y, Tt, X=X, W=W, groups=groups)
    return est


def main():
    df = load()
    print(f"Usable rows: {len(df)}  |  years: {sorted(df['year'].unique())}  |  cells: {df['cell_code'].nunique()}")

    # --- 1. TEMPORAL heterogeneity (main analysis) -------------------------
    print("\n=== Temporal heterogeneity: has the Po effect changed 2018-2023? ===")
    est_time = fit_forest(df, HETEROGENEITY_TIME)

    years = sorted(df["year"].unique())
    X_years = pd.DataFrame({"year": years})
    cate = est_time.effect(X_years.values)
    lo, hi = est_time.effect_interval(X_years.values, alpha=0.10)

    print("\nEstimated Po effect (mg/m^3 of chlorophyll per +1000 m^3/s), by year:")
    print(f"{'year':>6} {'effect':>9} {'90% interval':>18}")
    for y, e, l, h in zip(years, cate, lo, hi):
        print(f"{y:>6} {e:>9.2f} {'[' + f'{l:.2f}, {h:.2f}' + ']':>18}")

    ate = est_time.ate(df[HETEROGENEITY_TIME].values)
    print(f"\nAverage effect across all years (for reference, compare to Step B's +3.14): {ate:+.2f}")

    trend = np.polyfit(years, cate, 1)[0]
    print(f"\nLinear trend across years: {trend:+.3f} mg/m^3 per +1000 m^3/s, per year")
    if trend < 0:
        print("-> The estimated effect DECLINES over 2018-2023: directionally consistent with")
        print("   the documented oligotrophication of the northern Adriatic (weaker nutrient")
        print("   response as background nutrient levels fall). Six years is a short window:")
        print("   read this as a suggestive signal, not a confirmed trend.")
    else:
        print("-> The estimated effect does not decline over this window; no evidence here of")
        print("   a weakening Po effect. Six years is a short window for a trend claim either way.")

    # --- 2. SPATIAL heterogeneity (descriptive only) ------------------------
    print("\n=== Spatial heterogeneity (descriptive - only 5 cells, not a statistical claim) ===")
    est_space = fit_forest(df, HETEROGENEITY_SPACE)
    cells = df[["cell_code", "dist_po_km"]].drop_duplicates().sort_values("dist_po_km")
    cate_space = est_space.effect(cells[["dist_po_km"]].values)
    print("\nEstimated Po effect by cell, ordered by distance from the Po mouth:")
    for (_, row), e in zip(cells.iterrows(), cate_space):
        print(f"  {row.cell_code:8s}  dist={row.dist_po_km:6.1f} km   effect={e:+.2f}")
    print("\nWith 5 cells this pattern is illustrative only: not enough spatial units for a")
    print("statistically defensible heterogeneity claim. Reported for transparency, not as a result.")

    print("\n=== Honest summary ===")
    print("EconML lets the Po effect vary instead of forcing one number. The temporal")
    print("analysis (6 seasons, hundreds of rows each) is the defensible one; the spatial")
    print("analysis (5 cells) is descriptive. Both rely on the same unconfoundedness")
    print("assumption as Steps A/B, and the same caveats (unobserved confounding, temporal")
    print("autocorrelation) apply. More seasons would strengthen both, and would make a")
    print("genuine per-transect (rather than per-demo-cell) analysis possible.")


if __name__ == "__main__":
    main()
