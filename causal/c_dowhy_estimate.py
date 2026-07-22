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
                  * sensitivity to unobserved confounding: how strong would a
                    confounder we did NOT measure need to be to explain the
                    effect away? (Cinelli & Hazlett partial-R^2 bound)

Reading: if placebo ~0 and the other refuters leave the estimate almost
unchanged (including under a plausible hidden confounder), the result is
robust. Otherwise, it must be reported as fragile.

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

    # Unlike the three refuters above (which test robustness to method and
    # data), this one addresses the "unobserved confounding" limitation
    # directly declared in causal/README.md: how strong would a confounder we
    # never measured (currents, other river inputs, solar radiation) need to
    # be, relative to SST (the strongest confounder actually in the model), to
    # explain the estimated effect away? Cinelli & Hazlett (2020) partial-R^2
    # bound, benchmarked against SST.
    sensitivity = model.refute_estimate(
        identified, estimate,
        method_name="add_unobserved_common_cause",
        simulation_method="linear-partial-R2",
        benchmark_common_causes=["sst"],
        effect_fraction_on_treatment=[1, 2, 3],
        effect_fraction_on_outcome=[1, 2, 3],
        plot_estimate=False,
    )
    rv = sensitivity.stats["robustness_value"]
    rv_alpha = sensitivity.stats["robustness_value_alpha"]
    bench = sensitivity.benchmarking_results
    print("\n[Sensitivity to unobserved confounding] Cinelli & Hazlett partial-R^2 bound:")
    print(f"  Robustness value: {rv:.3f}  ->  a confounder explaining more than {100*rv:.1f}% of the")
    print("  residual variance of BOTH Po discharge and chlorophyll would be needed to fully")
    print("  explain the effect away (bring it to zero).")
    print(f"  At the 5% significance level, that threshold drops to {100*rv_alpha:.1f}%.")
    print("\n  Benchmarked against SST (the strongest confounder actually in the model): a hidden")
    print(f"  confounder as strong as SST would leave the estimate at {bench['bias_adjusted_estimate'].iloc[0]:+.3f}"
          f" (95% CI {bench['bias_adjusted_lower_CI'].iloc[0]:+.3f}, {bench['bias_adjusted_upper_CI'].iloc[0]:+.3f});"
          f" even 3x as strong as SST, at {bench['bias_adjusted_estimate'].iloc[-1]:+.3f} (95% CI"
          f" {bench['bias_adjusted_lower_CI'].iloc[-1]:+.3f}, {bench['bias_adjusted_upper_CI'].iloc[-1]:+.3f}).")
    print("  EXPECTED: a plausible hidden confounder (comparable to, or a few times stronger than,")
    print("  SST) should not be enough to flip the sign or erase significance. If it were, the")
    print("  estimate would be fragile to unobserved confounding rather than merely untested for it.")

    print("\n=== Honest note ===")
    print("Estimate from observational data: valid UNDER the DAG assumptions (no")
    print("unobserved confounding, correct form). Refuters test robustness, they")
    print("do not prove causality. The sensitivity analysis above bounds, but does")
    print("not eliminate, the unobserved-confounding limit; temporal autocorrelation")
    print("remains a separate limit to declare (see causal/README.md).")
    print("Step D (EconML) will estimate the heterogeneity of the effect.")


if __name__ == "__main__":
    main()
