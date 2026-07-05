"""
Causal layer - Step B: two-way fixed-effects robustness check.

Adds a stronger, still fully transparent control on top of Step A (transparent
estimate) and Step B (DoWhy): a two-way fixed-effects regression that adjusts
for confounders we did NOT explicitly model.

Idea: include one dummy variable per cell and one per year. This absorbs:
  - everything constant over time within a cell (bathymetry, distance to
    shore, local exposure - unobserved but time-invariant confounders);
  - everything common to all cells within a given year (an unusually warm
    year, an anomalous rainy season - unobserved but cell-invariant shocks).

The Po effect is then identified from the *within-cell, within-year*
variation only - a much stricter bar than Step A's regression, and a direct,
cheap answer to the "unobserved confounding" limitation stated in Steps A/B.

This does not require any new library: it is an OLS regression with
categorical (dummy) variables, using statsmodels (already a dependency).

RUN:  python causal/c_fixed_effects.py
"""

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

FEATURES_CSV = "data/processed/features.csv"

TREATMENT = "po_discharge_lag7"
OUTCOME = "chl"
# NOTE: SST is deliberately excluded here. Diagnosis on this dataset showed
# valid SST only for 2 of 5 cells (cb_05, la_05) across all six years - the
# nearest-pixel SST retrieval falls on a masked/land pixel for the other
# three cells in this reprocessed product, not missing at random. Including
# SST would silently shrink this robustness check to 2 cells, defeating its
# purpose. Season (day-of-year) and wind are used instead, both complete
# across all five cells.
CONFOUNDERS = ["doy_sin", "doy_cos", "wind_speed"]


def main():
    df = pd.read_csv(FEATURES_CSV, parse_dates=["ts"])
    df = df.dropna(subset=[TREATMENT, OUTCOME] + CONFOUNDERS).copy()
    df["po_k"] = df[TREATMENT] / 1000.0
    df["year"] = df["ts"].dt.year.astype(str)          # categorical, not numeric
    n_cells = df["cell_code"].nunique()
    print(f"Usable rows: {len(df)}  |  cells: {n_cells}  |  years: {df['year'].nunique()}")
    if n_cells < 5:
        print(f"WARNING: only {n_cells}/5 cells have complete data for the chosen "
              f"confounders - the fixed-effects estimate below is not representative "
              f"of the full coastline. Check which confounder is dropping cells "
              f"(e.g. via per-cell dropna counts) before trusting this result.")

    # --- Baseline (same as Step A, for direct comparison): pooled OLS ------
    pooled = smf.ols(f"{OUTCOME} ~ po_k + doy_sin + doy_cos + wind_speed", data=df).fit()
    b_pooled = pooled.params["po_k"]
    ci_pooled = pooled.conf_int().loc["po_k"]

    # --- Two-way fixed effects: + C(cell) + C(year) ------------------------
    # C(...) tells statsmodels/patsy to treat the variable as categorical,
    # i.e. to fit one dummy (intercept shift) per cell and per year.
    formula = f"{OUTCOME} ~ po_k + doy_sin + doy_cos + wind_speed + C(cell_code) + C(year)"
    fe_model = smf.ols(formula, data=df).fit()
    b_fe = fe_model.params["po_k"]
    ci_fe = fe_model.conf_int().loc["po_k"]

    print("\n=== Po effect: pooled OLS vs two-way fixed effects ===")
    print(f"  Pooled (Step A-style):      {b_pooled:+.3f} mg/m^3 per +1000 m^3/s   "
          f"(95% CI: {ci_pooled[0]:+.3f}, {ci_pooled[1]:+.3f})")
    print(f"  Cell + year fixed effects:  {b_fe:+.3f} mg/m^3 per +1000 m^3/s   "
          f"(95% CI: {ci_fe[0]:+.3f}, {ci_fe[1]:+.3f})")

    delta_pct = 100 * (b_fe - b_pooled) / b_pooled
    print(f"\n  Change from adding fixed effects: {delta_pct:+.1f}%")
    if ci_fe[0] > 0:
        print("  -> The Po effect survives this much stricter control: still positive")
        print("     and significant net of any time-invariant cell traits and any")
        print("     year-specific shock common to all cells.")
    elif ci_fe[1] < 0:
        print("  -> Under fixed effects the estimated effect turns negative/significant.")
        print("     This warrants a closer look before trusting the pooled estimate.")
    else:
        print("  -> Under this stricter control the effect is not distinguishable from")
        print("     zero: some of the pooled estimate may reflect confounders that were")
        print("     absorbed by the cell/year dummies (e.g. a spatial or annual pattern).")

    print("\nNote: fixed effects absorb confounders correlated with cell identity or")
    print("year, but not confounders that vary within a cell-year (e.g. a within-season")
    print("event uncorrelated with the modelled drivers). This remains an observational")
    print("estimate, not a demonstrated causal effect.")


if __name__ == "__main__":
    main()
