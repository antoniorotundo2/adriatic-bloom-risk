"""
Causal layer - figures for the technical report and README.

Regenerates the 4 figures referenced in docs/technical-report.md from the
current data/processed/features.csv, by reusing the fit() functions of Steps
A-D - so a figure can never silently drift from the number the corresponding
script prints.

  1. Chlorophyll gradient from the Po delta southward.
  2. Causal effect estimates across methods (apparent, A, B classical/
     clustered, C), with 95% CI - the convergence story from causal/README.md.
  3. Spatial heterogeneity (Step D): effect vs distance to the Po mouth.
  4. Temporal heterogeneity (Step D): effect by year.

Run (after `make features` and with the Step A-D data already computable):
  python causal/plots.py
"""

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import a_transparent_estimate as step_a
import b_fixed_effects as step_b
import c_dowhy_estimate as step_c
import d_causal_forest as step_d

FEATURES_CSV = "data/processed/features.csv"
OUT_DIR = "docs/figures"

CELL_LABELS = {
    "cb_05": "Casalborsetti",
    "la_05": "Lido Adriano",
    "ce_05": "Cesenatico",
    "ri_05": "Rimini",
    "ca_05": "Cattolica",
}


def _style_ax(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def fig_chlorophyll_gradient():
    df = pd.read_csv(FEATURES_CSV)
    g = df.groupby("cell_code").agg(chl=("chl", "median"), dist_po_km=("dist_po_km", "first"))
    g = g.sort_values("dist_po_km")
    labels = [CELL_LABELS[c] for c in g.index]

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(labels, g["chl"], color="#2E86AB")
    ax.set_ylabel("Median chlorophyll-a (mg/m³)")
    ax.set_title("Chlorophyll gradient from the Po delta southward (2018-2023)")
    _style_ax(ax)
    fig.tight_layout()
    fig.savefig(f"{OUT_DIR}/chlorophyll_gradient.png", dpi=150)
    plt.close(fig)


def fig_causal_effects():
    """Forest plot of the single-average-effect estimates. Step C's CI comes
    from the sensitivity analysis's own standard error, since both operate
    on the same underlying backdoor.linear_regression fit."""
    _, m_naive, m_adj = step_a.fit()
    _, pooled, fe_model, fe_model_clustered = step_b.fit()
    _, _, _, estimate_c, sensitivity_c = step_c.fit()

    rows = []

    def add(name, coef, ci_lo, ci_hi):
        rows.append((name, coef, ci_lo, ci_hi))

    b, (lo, hi) = m_naive.params["po_k"], m_naive.conf_int().loc["po_k"]
    add("Apparent (no controls)", b, lo, hi)

    b, (lo, hi) = m_adj.params["po_k"], m_adj.conf_int().loc["po_k"]
    add("Step A (season, SST)", b, lo, hi)

    eff = estimate_c.value
    se = sensitivity_c.stats["standard_error"]
    add("Step C, DoWhy (season, SST, wind)", eff, eff - 1.96 * se, eff + 1.96 * se)

    b, (lo, hi) = fe_model.params["po_k"], fe_model.conf_int().loc["po_k"]
    add("Step B, fixed effects (classical SE)", b, lo, hi)

    b, (lo, hi) = fe_model_clustered.params["po_k"], fe_model_clustered.conf_int().loc["po_k"]
    add("Step B, fixed effects (clustered SE)", b, lo, hi)

    rows = rows[::-1]  # top-to-bottom reading order in the plot
    names = [r[0] for r in rows]
    coefs = [r[1] for r in rows]
    err_lo = [r[1] - r[2] for r in rows]
    err_hi = [r[3] - r[1] for r in rows]

    fig, ax = plt.subplots(figsize=(8.5, 4.5))
    y = range(len(names))
    ax.errorbar(coefs, y, xerr=[err_lo, err_hi], fmt="o", color="#2E86AB",
                ecolor="#2E86AB", capsize=4, markersize=6)
    ax.axvline(0, color="gray", linewidth=1, linestyle="--")
    ax.set_yticks(list(y))
    ax.set_yticklabels(names)
    ax.set_xlabel("Estimated Po effect on chlorophyll (mg/m³ per +1000 m³/s)")
    ax.set_title("Causal effect estimates across methods, with 95% CI")
    _style_ax(ax)
    fig.tight_layout()
    fig.savefig(f"{OUT_DIR}/causal_effects_comparison.png", dpi=150)
    plt.close(fig)


def fig_spatial_heterogeneity(cells):
    fig, ax = plt.subplots(figsize=(7, 4.5))
    labels = [CELL_LABELS[c] for c in cells.index]
    yerr = [cells["effect"] - cells["lo"], cells["hi"] - cells["effect"]]
    ax.errorbar(cells["dist_po_km"], cells["effect"], yerr=yerr, fmt="o-",
                color="#A23B72", capsize=4, markersize=6)
    ax.axhline(0, color="gray", linewidth=1, linestyle="--")
    for x, y, lbl in zip(cells["dist_po_km"], cells["effect"], labels):
        ax.annotate(lbl, (x, y), textcoords="offset points", xytext=(0, 10),
                    ha="center", fontsize=8)
    ax.set_xlabel("Distance to the Po mouth (km)")
    ax.set_ylabel("Estimated Po effect (mg/m³ per +1000 m³/s)")
    ax.set_title("Spatial heterogeneity of the Po effect (Step D, causal forest)")
    _style_ax(ax)
    fig.tight_layout()
    fig.savefig(f"{OUT_DIR}/spatial_heterogeneity.png", dpi=150)
    plt.close(fig)


def fig_temporal_heterogeneity(years):
    fig, ax = plt.subplots(figsize=(7, 4.5))
    yerr = [years["effect"] - years["lo"], years["hi"] - years["effect"]]
    ax.errorbar(years["year_num"], years["effect"], yerr=yerr, fmt="o-",
                color="#F18F01", capsize=4, markersize=6)
    ax.axhline(0, color="gray", linewidth=1, linestyle="--")
    ax.set_xlabel("Year")
    ax.set_ylabel("Estimated Po effect (mg/m³ per +1000 m³/s)")
    ax.set_title("Temporal heterogeneity of the Po effect (Step D, causal forest)")
    ax.set_xticks(years["year_num"])
    _style_ax(ax)
    fig.tight_layout()
    fig.savefig(f"{OUT_DIR}/temporal_heterogeneity.png", dpi=150)
    plt.close(fig)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    print("Figure 1/4: chlorophyll gradient...")
    fig_chlorophyll_gradient()

    print("Figure 2/4: causal effect comparison...")
    fig_causal_effects()

    print("Figure 3/4 & 4/4: heterogeneity (fitting the causal forest)...")
    df = step_d.load()
    cells, years = step_d.fit_and_get_effects(df)
    fig_spatial_heterogeneity(cells)
    fig_temporal_heterogeneity(years)

    print(f"\nWrote 4 figures to {OUT_DIR}/")


if __name__ == "__main__":
    main()
