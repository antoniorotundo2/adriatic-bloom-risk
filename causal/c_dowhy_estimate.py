"""
Layer 7 (causal) - Step C: formal reasoning with DoWhy.

Same problem as Step A (effect of Po on chlorophyll), but through DoWhy's
rigorous four-step causal workflow:

  1. MODEL      - declare the DAG: who causes what (Po -> chlorophyll, with
                  season/SST/wind as confounders, stratification as a mediator
                  that must NOT be adjusted for the total effect).
  2. IDENTIFY   - DoWhy derives which variables to adjust for (backdoor).
  3. ESTIMATE   - estimate the effect with the identified strategy.
  4. REFUTE     - stress-test the estimate:
                  * placebo: replace Po with noise -> the effect must VANISH
                  * random common cause: add a fake confounder -> estimate must HOLD
                  * random subset: drop data at random -> estimate STABLE

Reading: if placebo ~0 and the other two leave the estimate almost unchanged,
the result is robust. Otherwise, it must be reported as fragile.

Run:  python causal/c_dowhy_estimate.py
"""

import pandas as pd
from dowhy import CausalModel

FEATURES_CSV = "data/processed/features.csv"

TREATMENT = "po_k"          # Po discharge (in 1000 m^3/s) lagged by 7 days
OUTCOME = "chl"
CONFOUNDERS = ["doy_sin", "doy_cos", "sst", "wind_speed"]  # season, temperature, wind


def build_dataframe():
    df = pd.read_csv(FEATURES_CSV, parse_dates=["ts"])
    df = df.dropna(subset=["po_discharge_lag7", OUTCOME] + CONFOUNDERS).copy()
    df["po_k"] = df["po_discharge_lag7"] / 1000.0
    return df


def build_dag():
    """DAG in DOT syntax. Stratification is a declared mediator but NOT included
    among the confounders: for the TOTAL effect of Po it must not be adjusted."""
    edges = []
    # Confounders cause both the treatment and the outcome (backdoor paths)
    for c in CONFOUNDERS:
        edges.append(f"{c} -> {TREATMENT};")
        edges.append(f"{c} -> {OUTCOME};")
    # Effect of interest
    edges.append(f"{TREATMENT} -> {OUTCOME};")
    nodes = " ".join(f"{n};" for n in [TREATMENT, OUTCOME] + CONFOUNDERS)
    return "digraph { " + nodes + " " + " ".join(edges) + " }"


def main():
    df = build_dataframe()
    print(f"Usable rows: {len(df)}")

    model = CausalModel(
        data=df,
        treatment=TREATMENT,
        outcome=OUTCOME,
        graph=build_dag(),
    )

    # 2. Identification (DoWhy chooses what to adjust for)
    identified = model.identify_effect(proceed_when_unidentifiable=True)

    # 3. Estimation (linear regression on the identified backdoor strategy)
    estimate = model.estimate_effect(
        identified,
        method_name="backdoor.linear_regression",
    )
    effect = estimate.value
    print("\n=== Estimated causal effect (DoWhy) ===")
    print(f"  Effect of Po on chlorophyll: {effect:+.3f} mg/m^3 per +1000 m^3/s")

    # 4. Refuters - the robustness tests
    print("\n=== Robustness tests (refuters) ===")

    placebo = model.refute_estimate(
        identified, estimate,
        method_name="placebo_treatment_refuter",
        placebo_type="permute", num_simulations=30)
    print("\n[Placebo] replace Po with random noise:")
    print(f"  real effect: {effect:+.3f}   ->  placebo effect: {placebo.new_effect:+.3f}")
    print("  EXPECTED: placebo ~ 0. If close to zero, the real effect is not an artefact.")

    rcc = model.refute_estimate(
        identified, estimate,
        method_name="random_common_cause", num_simulations=30)
    print("\n[Random common cause] add a fake confounder:")
    print(f"  original effect: {effect:+.3f}   ->  with fake cause: {rcc.new_effect:+.3f}")
    print("  EXPECTED: almost unchanged. If it holds, the estimate is robust to extra confounders.")

    subset = model.refute_estimate(
        identified, estimate,
        method_name="data_subset_refuter",
        subset_fraction=0.8, num_simulations=30)
    print("\n[Random subset] re-estimate on 80% of the data:")
    print(f"  original effect: {effect:+.3f}   ->  on subset: {subset.new_effect:+.3f}")
    print("  EXPECTED: stable. If it barely changes, the estimate does not hinge on a few points.")

    print("\n=== Honest note ===")
    print("Estimate from observational data: valid UNDER the DAG assumptions (no")
    print("unobserved confounding, correct form). Refuters test robustness, they")
    print("do not prove causality. Confounders not included (currents, other")
    print("rivers) and temporal autocorrelation remain limits to declare.")
    print("Step D (EconML) will estimate the heterogeneity of the effect.")


if __name__ == "__main__":
    main()
