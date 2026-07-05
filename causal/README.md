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
- **Step A-bis — fixed-effects robustness check** (`c_fixed_effects.py`): a
  two-way fixed-effects regression (cell and year dummies) adjusting for
  unobserved, time-invariant per-cell confounders and year-specific shocks
  common to all cells. Stricter control, no extra library cost.
- **Step B — DoWhy** (`b_dowhy_estimate.py`): explicit DAG, formal identification
  of the adjustment strategy, estimation and refutation tests.
- **Step C — causal forest** (`d_causal_forest.py`): CausalForestDML (EconML)
  estimating whether the Po effect varies spatially (by distance to the Po
  mouth) and temporally (by year), instead of a single average effect.

## Results (2018–2023 data, 5 coastal cells)

| Analysis | Estimated Po effect |
|---|---|
| Raw correlation (Po t-7 vs chlorophyll) | r = 0.42 |
| Apparent effect (no controls) | +3.34 mg/m³ per +1000 m³/s |
| Adjusted effect — Step A (season, SST) | +3.18 mg/m³ per +1000 m³/s |
| Formal effect — Step B, DoWhy (season, SST, wind) | +3.14 mg/m³ per +1000 m³/s |
| Fixed-effects effect — Step A-bis (season, wind, cell + year dummies) | +2.34 mg/m³ per +1000 m³/s |

Seasonal and thermal confounders explain only ~5% of the apparent effect: the
Po -> chlorophyll link is not a seasonal artefact. The effect survives an even
stricter test: adjusting for cell and year fixed effects - which absorb any
time-invariant trait of each cell and any shock common to all cells in a given
year - still leaves a positive, significant estimate (+2.34, an 8% reduction
from the pooled estimate using the same confounders). The estimate narrows as
controls get stricter, but does not collapse to zero.

### Robustness tests (Step B)

| Refuter | Expected | Result |
|---|---|---|
| Placebo (Po replaced with noise) | ~0 | +0.02 |
| Random common cause (fake confounder) | unchanged | +3.14 |
| Random subset (80% of the data) | stable | +3.13 |

The estimate is consistent across the two approaches and robust to the standard
refutation tests.

## Interpretation

Holding season, temperature and wind fixed, a 1000 m³/s increase in the Po
discharge is associated, seven days later, with about +3.1 mg/m³ of chlorophyll.
Over the observed discharge range (~460–3970 m³/s) the effect is of the order of
10 mg/m³, sizeable relative to the coastal medians.

## Limitations (to read alongside the results)

- **Unobserved confounding**: the refuters test robustness to method and data,
  not the existence of confounders absent from the dataset (currents, other
  river inputs, solar radiation). If they exist, part of the estimated effect
  may belong to them. This is the structural limit of observational causal
  inference.
- **Temporal autocorrelation**: discharge and chlorophyll are autocorrelated
  series; standard confidence intervals tend to be too narrow. The point
  estimate is more reliable than its stated precision.
- **Linear form** and fine scale (5 cells, 6 seasons): indicative, not
  definitive. Extending to more cells and years would strengthen it.
- **SST data coverage**: the nearest-pixel SST retrieval is valid for only 2 of
  the 5 cells across all six seasons (the other three fall on a masked/land
  pixel in this reprocessed product) - not missing at random, but a systematic
  gap tied to the grid-coastline alignment. Including SST as a confounder would
  silently shrink any analysis to those 2 cells; Step A-bis therefore uses
  season and wind (both complete across all 5 cells) instead. Steps A and B,
  which do include SST, are consequently estimated on a smaller effective
  sample than Step A-bis.

Correct phrasing of the results: *effect estimated and robust under the declared
assumptions*, not *causal effect proven*.
