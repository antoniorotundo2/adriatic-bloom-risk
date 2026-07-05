"""
Causal layer - Step C: heterogeneous effects with a causal forest (EconML).

Steps A, A-bis and B all estimate a SINGLE average effect of Po discharge on
chlorophyll. This step asks a more ambitious question: does that effect VARY?

  - Spatially: is the Po effect stronger near the delta (Casalborsetti) and
    weaker towards Cattolica?
  - Temporally: has the effect changed over 2018-2023, consistent with the
    documented northern-Adriatic oligotrophication trend?

Method: CausalForestDML (EconML). Like Step B, it uses double machine learning
to remove the influence of confounders, but instead of one coefficient it
fits a flexible model of how the treatment effect varies with chosen
"heterogeneity" variables (here: distance to the Po mouth, and year).

Confounders (W): season (cyclic) and wind - the same choice as Step A-bis,
and for the same documented reason: SST has valid coverage for only 2 of the
5 cells in this dataset, and including it would silently shrink this analysis
to those 2 cells (see causal/README.md, Limitations).

HONESTY NOTE (read before trusting any heterogeneity numbers below): the
dataset has only 5 distinct spatial units and 6 years. A causal forest is
designed for many more distinct units; with so few, "heterogeneity" estimates
are exploratory descriptions of this specific sample, not a validated general
pattern. Confidence intervals are reported and should be inspected, not just
point estimates.

RUN:  python causal/d_causal_forest.py
"""

import numpy as np
import pandas as pd
from econml.dml import CausalForestDML
from sklearn.ensemble import GradientBoostingRegressor

FEATURES_CSV = "data/processed/features.csv"

TREATMENT = "po_discharge_lag7"
OUTCOME = "chl"
CONTROLS = ["doy_sin", "doy_cos", "wind_speed"]   # W: same choice as Step A-bis (SST excluded, see note above)
HETEROGENEITY = ["dist_po_km", "year_num"]         # X: what the effect is allowed to vary with


def load():
    df = pd.read_csv(FEATURES_CSV, parse_dates=["ts"])
    df["year_num"] = df["ts"].dt.year.astype(float)
    needed = [TREATMENT, OUTCOME] + CONTROLS + HETEROGENEITY
    df = df.dropna(subset=needed).copy()
    df["po_k"] = df[TREATMENT] / 1000.0
    return df


def check_coverage(df):
    n_cells = df["cell_code"].nunique()
    n_years = df["year_num"].nunique()
    print(f"Usable rows: {len(df)}  |  cells: {n_cells}  |  years: {n_years}")
    if n_cells < 5:
        print(f"WARNING: only {n_cells}/5 cells have complete data for the chosen "
              f"controls/heterogeneity variables - results below would not cover "
              f"the full coastline. Stopping short of fitting the forest.")
        return False
    return True


def main():
    df = load()
    if not check_coverage(df):
        return

    Y = df[OUTCOME].values
    Tt = df["po_k"].values
    W = df[CONTROLS].values
    X = df[HETEROGENEITY].values

    print(f"\nHeterogeneity variables: {HETEROGENEITY}")
    print(f"  distinct distance-to-Po values (~= number of cells): {df['dist_po_km'].nunique()}")
    print(f"  distinct years: {df['year_num'].nunique()}")
    print("These are the only axes of variation the forest can use for X - with so")
    print("few distinct values, treat the effect estimates below as exploratory.\n")

    est = CausalForestDML(
        model_y=GradientBoostingRegressor(n_estimators=200, max_depth=3, random_state=42),
        model_t=GradientBoostingRegressor(n_estimators=200, max_depth=3, random_state=42),
        n_estimators=500,
        min_samples_leaf=20,
        max_depth=5,
        cv=3,
        random_state=42,
    )
    est.fit(Y, Tt, X=X, W=W)

    # --- Heterogeneity by cell (average distance-to-Po per cell) -----------
    cells = df.groupby("cell_code").agg(dist_po_km=("dist_po_km", "first")).sort_values("dist_po_km")
    year_mid = df["year_num"].median()
    X_by_cell = np.column_stack([cells["dist_po_km"].values,
                                  np.full(len(cells), year_mid)])
    effect_by_cell = est.effect(X_by_cell)
    lo_by_cell, hi_by_cell = est.effect_interval(X_by_cell, alpha=0.1)

    print("=== Effect by coastal cell (at the median year), ordered near -> far from the Po ===")
    for code, dist, eff, lo, hi in zip(cells.index, cells["dist_po_km"], effect_by_cell, lo_by_cell, hi_by_cell):
        print(f"  {code:6s}  dist={dist:6.1f} km   effect={eff:+.3f}  (90% CI: {lo:+.3f}, {hi:+.3f}) mg/m^3 per +1000 m^3/s")

    # --- Heterogeneity by year (at the median cell distance) ---------------
    years = sorted(df["year_num"].unique())
    dist_mid = df["dist_po_km"].median()
    X_by_year = np.column_stack([np.full(len(years), dist_mid), years])
    effect_by_year = est.effect(X_by_year)
    lo_by_year, hi_by_year = est.effect_interval(X_by_year, alpha=0.1)

    print("\n=== Effect by year (at the median cell distance) ===")
    for yr, eff, lo, hi in zip(years, effect_by_year, lo_by_year, hi_by_year):
        print(f"  {int(yr)}   effect={eff:+.3f}  (90% CI: {lo:+.3f}, {hi:+.3f}) mg/m^3 per +1000 m^3/s")

    print("\n=== Interpretation guide ===")
    print("- If effects near the Po (small dist_po_km) are consistently higher than")
    print("  far cells, and the confidence intervals do not overlap much, that is a")
    print("  spatial-heterogeneity signal worth reporting - though still descriptive")
    print("  of these 5 cells, not a validated general law.")
    print("- If the yearly effect trends downward over 2018-2023, that would be")
    print("  directionally consistent with the documented oligotrophication of the")
    print("  northern Adriatic - an interesting hypothesis to state explicitly, not")
    print("  a confirmed finding: 6 points are too few to establish a trend rigorously.")
    print("- Wide, overlapping confidence intervals across cells or years mean the")
    print("  forest cannot distinguish them from a single constant effect - the honest")
    print("  conclusion in that case is 'no detectable heterogeneity with this data',")
    print("  which is itself a valid, reportable result.")


if __name__ == "__main__":
    main()
