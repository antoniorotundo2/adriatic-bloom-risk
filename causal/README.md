# Causal layer — effect of the Po discharge on chlorophyll

This layer answers a different question from the predictive one. The predictive
model estimates *where and when* chlorophyll is likely to rise; the causal
analysis estimates *by how much* chlorophyll would change **if** the Po discharge
changed, holding the disturbing factors (season, temperature, wind) fixed.

The distinction matters: the predictive importance of a variable is not its
causal effect. Season, for instance, is highly predictive precisely because it
moves the Po discharge and chlorophyll together, confounding their link.

## Question

What is the effect of the Po discharge (lagged by 7 days) on chlorophyll-a along
the Romagna coast, once adjusted for the seasonal and meteo-marine confounders?

The 7-day lag reflects transport and biological response time; it is also the
driver the predictive model flags as most informative.

## DAG (causal hypotheses)

```
Confounders (season, SST, wind) --> Po discharge (t-7)   [treatment]
Confounders (season, SST, wind) --> Chlorophyll          [outcome]
Po discharge (t-7) --> Chlorophyll                       [estimated effect]
Stratification (mediator) -- not adjusted (total effect)
```

For the **total** effect of the Po the confounders (backdoor paths) are adjusted,
but mediators such as stratification are not.

## Method (four steps)

- **Step A — transparent estimate** (`a_transparent_estimate.py`): regression
  with and without controls, to show how much of the apparent Po-chlorophyll
  link is actually season. Linear, readable line by line.
- **Step B — fixed-effects robustness check** (`b_fixed_effects.py`): a
  two-way fixed-effects regression (cell and year dummies) adjusting for
  unobserved, time-invariant per-cell confounders and year-specific shocks
  common to all cells. Stricter control, no extra library cost.
- **Step C — DoWhy** (`c_dowhy_estimate.py`): explicit DAG, formal identification
  of the adjustment strategy, estimation and refutation tests.
- **Step D — causal forest** (`d_causal_forest.py`): CausalForestDML (EconML)
  estimating whether the Po effect varies spatially (by distance to the Po
  mouth) and temporally (by year), instead of a single average effect.

## Results (2018–2023 data, 5 coastal cells)

| Analysis | Estimated Po effect |
|---|---|
| Raw correlation (Po t-7 vs chlorophyll) | r = 0.42 |
| Apparent effect (no controls) | +3.34 mg/m³ per +1000 m³/s |
| Adjusted effect — Step A (season, SST) | +3.18 mg/m³ per +1000 m³/s |
| Formal effect — Step C, DoWhy (season, SST, wind) | +3.14 mg/m³ per +1000 m³/s |
| Fixed-effects effect — Step B (season, wind, cell + year dummies) | +2.34 mg/m³ per +1000 m³/s |

Seasonal and thermal confounders explain only ~5% of the apparent effect: the
Po -> chlorophyll link is not a seasonal artefact. The effect survives an even
stricter test: adjusting for cell and year fixed effects - which absorb any
time-invariant trait of each cell and any shock common to all cells in a given
year - still leaves a positive, significant estimate (+2.34, an 8% reduction
from the pooled estimate using the same confounders). The estimate narrows as
controls get stricter, but does not collapse to zero.

**Cluster-robust check on Step B (2018-2023 run).** The 95% CI reported above
for Step B uses classical (iid-errors) standard errors, which ignore that Po
discharge and chlorophyll are autocorrelated within each cell over time.
Re-estimating the same model with standard errors clustered by cell widens the
interval from (+2.13, +2.54) to (+1.87, +2.81) - **+131% wider** - but the
conclusion is unchanged: the effect stays positive and distinguishable from
zero. With only 5 clusters the clustered interval is itself an approximation
(few-cluster asymptotics are unreliable below ~20-30 clusters), so read this as
a directional confirmation that the classical CI understates uncertainty, not
as a more precise replacement for it.

### Robustness tests (Step C)

| Refuter | Expected | Result |
|---|---|---|
| Placebo (Po replaced with noise) | ~0 | +0.02 |
| Random common cause (fake confounder) | unchanged | +3.14 |
| Random subset (80% of the data) | stable | +3.13 |

The estimate is consistent across the two approaches and robust to the standard
refutation tests.

**Sensitivity to unobserved confounding.** The three refuters above test
robustness to method and data, not to a confounder we never measured (currents,
other river inputs, solar radiation) - the structural limit noted below. Cinelli
& Hazlett's (2020) partial-R² bound quantifies it instead of leaving it
qualitative: a hidden confounder would need to explain **more than 33.8%** of
the residual variance of both Po discharge and chlorophyll to bring the
estimate to zero (30.99% to erase statistical significance at the 5% level).
Benchmarked against SST - the strongest confounder actually in the model - a
hidden confounder as strong as SST would leave the estimate at +3.06 (95% CI
+2.75, +3.38); even three times as strong as SST, at +2.90 (95% CI +2.60,
+3.20). A plausible hidden confounder is therefore unlikely to explain the
effect away, though this bounds the risk rather than eliminating it.

### Heterogeneous effects (Step D, causal forest)

Steps A, B and C all estimate a single average effect. `d_causal_forest.py`
(CausalForestDML, EconML) asks whether that effect varies spatially (by
distance to the Po mouth) or temporally (by year), using the same controls as
Step B (season, wind - SST excluded for the coverage reason above).

**Spatial pattern (the more solid of the two results).** The estimated effect
decreases monotonically with distance from the Po mouth, and is only
distinguishable from zero in the two cells closest to the delta:

| Cell | Distance to Po | Effect | 90% CI |
|---|---|---|---|
| Casalborsetti | 49 km | +1.75 | (+0.73, +2.77) |
| Lido Adriano | 60 km | +1.13 | (+0.25, +2.01) |
| Cesenatico | 84 km | +0.04 | (−0.28, +0.36) |
| Rimini | 97 km | −0.02 | (−0.16, +0.13) |
| Cattolica | 111 km | −0.07 | (−0.20, +0.07) |

The Po effect appears concentrated near the delta, where it is statistically
distinguishable from zero, and fades to statistically indistinguishable from
zero from Cesenatico southward - consistent with a physical dilution of the
river's influence with distance. This remains a descriptive pattern over 5
cells, not a validated general law, but it is directionally coherent and the
confidence intervals support the qualitative claim (near vs. far).

**Temporal pattern (exploratory, no interpretable trend).** Year-by-year
estimates do not show a usable trend: confidence intervals are wide,
especially at the ends of the series (2018: +90% CI −5.37 to +0.81; 2023:
−0.72 to +2.44), and only 2022 is clearly distinguishable from zero. With 6
yearly points this is expected: a causal forest needs far more distinct units
than a linear trend line to say anything reliable about change over time. No
claim is made here about a link to the documented Adriatic oligotrophication
trend; the data do not support confirming or ruling it out.

**Additional limitation specific to this step**: unlike Steps A/B/C, no
formal refutation test was run for the causal forest (EconML supports
validation approaches, but they were out of scope here). Step D is therefore
the most exploratory of the four analyses, on top of the small-sample caveat
already noted.

## Interpretation

Holding season, temperature and wind fixed, a 1000 m³/s increase in the Po
discharge is associated, seven days later, with about +3.1 mg/m³ of chlorophyll.
Over the observed discharge range (~460–3970 m³/s) the effect is of the order of
10 mg/m³, sizeable relative to the coastal medians. The causal forest (Step D)
adds a spatial qualification to this average: the effect is concentrated near
the Po delta and fades with distance, rather than being uniform along the coast.

## Limitations (to read alongside the results)

- **Unobserved confounding**: the refuters test robustness to method and data,
  not the existence of confounders absent from the dataset (currents, other
  river inputs, solar radiation). If they exist, part of the estimated effect
  may belong to them. This is the structural limit of observational causal
  inference. Quantified for Step C: per the sensitivity analysis above, such a
  confounder would need to be at least as strong as SST (and explain >33.8% of
  residual variance in both Po and chlorophyll) to matter - a bound, not proof
  that no such confounder exists.
- **Temporal autocorrelation**: discharge and chlorophyll are autocorrelated
  series; standard confidence intervals tend to be too narrow. The point
  estimate is more reliable than its stated precision. Quantified for Step B:
  clustering standard errors by cell widens its 95% CI by +131% (see the
  cluster-robust check above) without changing the qualitative conclusion -
  consistent with the narrowness being real but not large enough to overturn
  the result, at least for this check.
- **Linear form** and fine scale (5 cells, 6 seasons): indicative, not
  definitive. Extending to more cells and years would strengthen it.
- **SST data coverage (fixed, results below predate the fix)**: the results
  above were produced when the nearest-pixel SST retrieval was valid for only
  2 of the 5 cells across all six seasons (the other three fell on a
  masked/land pixel in this reprocessed product) - not missing at random, but
  a systematic gap tied to the grid-coastline alignment. `pipeline/features.py`
  (`read_sst`) now searches a small radius around each cell centroid and picks
  the closest pixel that is actually valid, instead of the literal nearest
  coordinate; re-running the pipeline on the real data restores full 5-cell
  SST coverage.
  The Step A/B/C numbers above were estimated before this fix (Step B without
  SST as a deliberate workaround, Steps A/C with SST but on the smaller
  effective sample) and should be refreshed by re-running
  `make ingest && make features && make causal` before being cited as current.

Correct phrasing of the results: *effect estimated and robust under the declared
assumptions*, not *causal effect proven*.
