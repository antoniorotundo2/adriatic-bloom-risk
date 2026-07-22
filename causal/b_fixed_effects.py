"""
Causal layer - Step B: two-way fixed-effects robustness check.

Adds a stronger, still fully transparent control on top of Step A (transparent
estimate): a two-way fixed-effects regression that adjusts for confounders we
did NOT explicitly model. Step C (DoWhy) formalises the reasoning separately.

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

RUN:  python causal/b_fixed_effects.py
"""

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


def fit():
    """Fit the pooled and two-way fixed-effects models (classical + clustered
    SE). Returns (df, pooled, fe_model, fe_model_clustered) - reused by
    causal/plots.py so the figures match the numbers this script prints."""
    df = pd.read_csv(FEATURES_CSV, parse_dates=["ts"])
    df = df.dropna(subset=[TREATMENT, OUTCOME] + CONFOUNDERS).copy()
    df["po_k"] = df[TREATMENT] / 1000.0
    df["year"] = df["ts"].dt.year.astype(str)          # categorical, not numeric

    # --- Baseline (same as Step A, for direct comparison): pooled OLS ------
    pooled = smf.ols(f"{OUTCOME} ~ po_k + doy_sin + doy_cos + wind_speed", data=df).fit()

    # --- Two-way fixed effects: + C(cell) + C(year) ------------------------
    # C(...) tells statsmodels/patsy to treat the variable as categorical,
    # i.e. to fit one dummy (intercept shift) per cell and per year.
    formula = f"{OUTCOME} ~ po_k + doy_sin + doy_cos + wind_speed + C(cell_code) + C(year)"
    fe_model = smf.ols(formula, data=df).fit()

    # --- Same model, cluster-robust SEs (by cell) ---------------------------
    # Po discharge and chlorophyll are autocorrelated within a cell over time,
    # which the classical (iid-errors) OLS covariance above ignores and tends
    # to understate. Clustering by cell relaxes the independence assumption
    # within each cell's time series while still assuming independence across
    # cells (fine here: cells are spatially distinct coastal transects).
    fe_model_clustered = smf.ols(formula, data=df).fit(
        cov_type="cluster", cov_kwds={"groups": df["cell_code"]}
    )
    return df, pooled, fe_model, fe_model_clustered


def main():
    df, pooled, fe_model, fe_model_clustered = fit()
    n_cells = df["cell_code"].nunique()
    print(f"Usable rows: {len(df)}  |  cells: {n_cells}  |  years: {df['year'].nunique()}")
    if n_cells < 5:
        print(f"WARNING: only {n_cells}/5 cells have complete data for the chosen "
              f"confounders - the fixed-effects estimate below is not representative "
              f"of the full coastline. Check which confounder is dropping cells "
              f"(e.g. via per-cell dropna counts) before trusting this result.")

    b_pooled = pooled.params["po_k"]
    ci_pooled = pooled.conf_int().loc["po_k"]
    b_fe = fe_model.params["po_k"]
    ci_fe = fe_model.conf_int().loc["po_k"]
    ci_fe_c = fe_model_clustered.conf_int().loc["po_k"]

    print("\n=== Po effect: pooled OLS vs two-way fixed effects ===")
    print(f"  Pooled (Step A-style):      {b_pooled:+.3f} mg/m^3 per +1000 m^3/s   "
          f"(95% CI: {ci_pooled[0]:+.3f}, {ci_pooled[1]:+.3f})")
    print(f"  Cell + year fixed effects:  {b_fe:+.3f} mg/m^3 per +1000 m^3/s   "
          f"(95% CI: {ci_fe[0]:+.3f}, {ci_fe[1]:+.3f})  [classical SE]")
    print(f"  Cell + year fixed effects:  {b_fe:+.3f} mg/m^3 per +1000 m^3/s   "
          f"(95% CI: {ci_fe_c[0]:+.3f}, {ci_fe_c[1]:+.3f})  [cluster-robust SE, by cell]")

    width_classical = ci_fe[1] - ci_fe[0]
    width_clustered = ci_fe_c[1] - ci_fe_c[0]
    widening_pct = 100 * (width_clustered - width_classical) / width_classical
    print(f"\n  Interval width, classical vs clustered: {width_classical:.3f} -> "
          f"{width_clustered:.3f} mg/m^3 ({widening_pct:+.0f}%)")
    print("  Only 5 clusters (cells): the cluster-robust CI is itself approximate")
    print("  (few-cluster asymptotics are unreliable below ~20-30 clusters) - read as")
    print("  a directional check on how much the classical CI understates uncertainty,")
    print("  not as a definitive interval.")

    delta_pct = 100 * (b_fe - b_pooled) / b_pooled
    print(f"\n  Change from adding fixed effects: {delta_pct:+.1f}%")
    if ci_fe_c[0] > 0:
        print("  -> The Po effect survives this much stricter control: still positive")
        print("     and significant net of any time-invariant cell traits and any")
        print("     year-specific shock common to all cells.")
    elif ci_fe_c[1] < 0:
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
