"""
Layer 7 (causal) - Step A: transparent baseline.

Question: what is the effect of the Po discharge on chlorophyll, once REMOVED
the seasonal and thermal confounders?

Transparent method (no black box): we compare three things, in order.
  1. RAW correlation Po <-> chlorophyll (confounded by season).
  2. Regression of chlorophyll on Po WITHOUT controls (apparent effect).
  3. Regression of chlorophyll on Po WITH the confounders (season, SST):
     the Po coefficient here is the first "adjusted" effect estimate.

The comparison between step 2 and step 3 IS the story: it shows how much of the
apparent Po-chlorophyll link was actually season.

Honest note: this is a transparent but linear estimate; Step C (DoWhy) will
formalise the reasoning with a DAG, identification and refuters.

Run:  python causal/a_transparent_estimate.py
"""

import pandas as pd
import statsmodels.formula.api as smf

FEATURES_CSV = "data/processed/features.csv"

# Treatment: Po discharge lagged by 7 days (the driver the predictive model
# flagged as dominant). Confounders: season (cyclic) and temperature.
TREATMENT = "po_discharge_lag7"
OUTCOME = "chl"
CONFOUNDERS = ["doy_sin", "doy_cos", "sst"]


def fit():
    """Fit the naive and adjusted regressions. Returns (df, m_naive, m_adj),
    the raw statsmodels results - reused by causal/plots.py so the figures
    are guaranteed to show the same numbers this script prints."""
    df = pd.read_csv(FEATURES_CSV, parse_dates=["ts"])
    df = df.dropna(subset=[TREATMENT, OUTCOME] + CONFOUNDERS).copy()
    # Standardise Po in units of 1000 m^3/s, so the coefficient reads as
    # "chlorophyll change per +1000 m^3/s of discharge".
    df["po_k"] = df[TREATMENT] / 1000.0
    m_naive = smf.ols(f"{OUTCOME} ~ po_k", data=df).fit()
    formula = f"{OUTCOME} ~ po_k + doy_sin + doy_cos + sst"
    m_adj = smf.ols(formula, data=df).fit()
    return df, m_naive, m_adj


def main():
    df, m_naive, m_adj = fit()
    print(f"Usable rows (no missing values): {len(df)}")

    # --- 1. Raw correlation ------------------------------------------------
    r = df["po_k"].corr(df[OUTCOME])
    print(f"\n1) Raw correlation Po <-> chlorophyll:  r = {r:.3f}")
    print("   (expected weak/misleading: season moves Po and chlorophyll together)")

    # --- 2. APPARENT effect (no controls) ----------------------------------
    b_naive = m_naive.params["po_k"]
    print("\n2) APPARENT Po effect (no controls):")
    print(f"   {b_naive:+.3f} mg/m^3 of chlorophyll per +1000 m^3/s   "
          f"(95% CI: {m_naive.conf_int().loc['po_k',0]:+.3f}, {m_naive.conf_int().loc['po_k',1]:+.3f})")

    # --- 3. ADJUSTED effect (with confounders) -----------------------------
    b_adj = m_adj.params["po_k"]
    ci_lo, ci_hi = m_adj.conf_int().loc["po_k"]
    print("\n3) ADJUSTED Po effect (controlling for season and SST):")
    print(f"   {b_adj:+.3f} mg/m^3 of chlorophyll per +1000 m^3/s   "
          f"(95% CI: {ci_lo:+.3f}, {ci_hi:+.3f})")

    # --- The story: how much was season? -----------------------------------
    print("\n=== Reading ===")
    delta = b_naive - b_adj
    print(f"Apparent effect:  {b_naive:+.3f}")
    print(f"Adjusted effect:  {b_adj:+.3f}")
    print(f"Difference explained by confounders: {delta:+.3f} "
          f"({100*delta/b_naive:.0f}% of the apparent, if same sign)")
    if ci_lo > 0:
        print("-> Even adjusted, the Po effect stays positive and significant.")
    elif ci_hi < 0:
        print("-> Adjusted, the Po effect is negative and significant (to interpret).")
    else:
        print("-> Adjusted, the Po effect is NOT statistically distinguishable from zero:")
        print("   most of the apparent link was season. Honest and informative result.")

    print("\nNote: linear, transparent estimate. Step C (DoWhy) formalises the")
    print("DAG, identification and robustness tests (refuters).")


if __name__ == "__main__":
    main()
