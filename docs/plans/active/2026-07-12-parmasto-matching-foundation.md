# Parmasto-style matching foundation

Status: **Deferred foundation; no implementation stage currently open.**

When resumed: **define the comparison cohort before any scoring work.**

## Agent handoff

- Status: Deferred foundation.
- Last completed stage: Structured observation summaries, cloud/public access, preparation-context filtering, and observation-balanced species profiles are complete.
- Current/next stage: None open. When this plan is resumed, define the comparison cohort and its user controls before implementing a score.
- Relevant commits: `41d3e2c`, `390efe0`, `20ed420`, `d0db5f3`.
- Important decisions:
  - Compare only from real measured summaries.
  - Species statistics are based on observation/specimen means, not pooled spores.
  - Use biological between-observation spread, not SEM, as the comparison scale.
  - Keep L/W/Q explanations visible rather than hiding them behind one score.
  - The comparison population must be inspectable and controllable by the user.
  - Community statistics are evidence, not ground truth.
  - Historical literature is a separate evidence source to interrogate, not the truth against which observations are judged.
- Do not:
  - use midpoint-estimated means;
  - use SEM as biological tolerance;
  - weight species means by number of spores;
  - silently combine incompatible measurement contexts;
  - introduce covariance/Mahalanobis scoring in the first slice;
  - manufacture Parmasto-style statistics from ordinary literature ranges;
  - persist a green/yellow/red result as if it were primary evidence.
- Remaining work: cohort definition and selection, transparent comparison, presentation thresholds, historical-reference comparison, and later richer Parmasto-style modelling.

---

## Goal

Build a transparent biometric comparison system for spores.

The immediate purpose is not to make a black-box species identification. It is to let a user ask:

> How does this observation compare with a selected population of measured observations for this taxon?

The selected population must remain visible and controllable.

Later, the same framework should allow historical literature references to be compared with modern measured populations so that inherited reference values can be examined rather than assumed correct merely because they have been repeatedly published.

The system may eventually support identification assistance, but the underlying measurements, population selection, and dimension-specific differences must remain inspectable.

---

## Scope and terminology

Until an identification-assistance phase is explicitly opened, prefer **comparison** terminology over **matching** terminology in UI and implementation.

Examples:

- comparison cohort
- comparison model
- comparison distance
- dimension-specific deviation
- community population

The plan filename and title may retain “matching” for continuity, but future agents should not interpret that as approval for premature match/no-match logic.

---

## Existing implemented foundation

The current data pipeline already provides the main statistical building blocks:

```text
individual spore measurements
        ↓
observation/specimen summary
        ↓
observation-balanced species profile
```

Each measured observation can supply:

```text
Lm
Wm
Qm
n_paired

within-observation statistics
measurement/preparation context
```

Species profiles are based on unweighted observation means:

```text
grand_Lm = mean(observation Lm)
grand_Wm = mean(observation Wm)
grand_Qm = mean(observation Qm)
```

and expose between-observation variability:

```text
sd_Lm
sd_Wm
sd_Qm
```

A specimen with 300 measured spores must not outweigh another valid specimen with 20 measured spores merely because more spores were measured.

Structured observation summaries are available through the cloud/public data pipeline, including measurement context. Current public/community infrastructure already supports filtering by preparation context, and the species-profile work is observation-balanced rather than pooled-spore weighted.

This foundation should be reused rather than replaced by a separate matching data model.

---

## Query observation

A query observation must have a real measured summary:

```text
query_Lm
query_Wm
query_Qm
query_n_paired
```

Do not compare from midpoint-estimated means.

The query should retain its measurement context so the user can decide whether the comparison population should use the same preparation/microscopy conditions.

---

## Comparison cohort

A species profile used for comparison must not be treated as one fixed global population.

The user must be able to define the comparison cohort.

Candidate filters include:

```text
taxon

country
region
date / month / season

sample type
sample source
fresh / dried where represented

mount reagent
stain reagent
contrast method

minimum n_paired

contributor
```

Filters should operate on observation/context summaries, not on a pooled table of individual spores.

Where several context filters are selected, they must refer to the same observation-summary context rather than being satisfied by unrelated contexts within one observation.

### Manual selection

The user should eventually be able to inspect the observations contributing to the cohort and include/exclude individual observations.

Example:

```text
Mycena leptocephala

Fresh · water · DIC
Norway + Sweden

☑ Observation A   Norway   n=42
☑ Observation B   Sweden   n=31
☐ Observation C   Norway   n=24   KOH
☑ Observation D   Norway   n=37
```

Changing the selected observations must recompute the profile.

Manual exclusions are analysis choices. They must not alter or hide the original community data.

### Cohort summary

Always expose enough information to understand the population being compared:

```text
number of observations
number of contributors
total paired spores
active preparation filters
geographic/date filters
contributor dominance where relevant
```

A comparison result without its cohort description is incomplete.

---

## Observation-balanced comparison profile

Given the selected eligible observation summaries:

```text
m = number of observations
u = number of contributors
N = total paired spores
```

compute:

```text
grand_Lm
grand_Wm
grand_Qm

sd_Lm
sd_Wm
sd_Qm
```

using unweighted observation means.

`N` is descriptive and may be used for eligibility/quality checks. It is not the weight used to calculate the canonical species mean.

The profile must be recomputed after filtering or manual inclusion/exclusion.

---

## Candidate transparent comparison baseline

**This is a candidate transparent baseline for later empirical evaluation, not an approved scoring model.**

A first experimental slice could use separate standardized deviations:

```text
zL = (query_Lm - grand_Lm) / max(sd_Lm, minimum_L_tolerance)

zW = (query_Wm - grand_Wm) / max(sd_Wm, minimum_W_tolerance)

zQ = (query_Qm - grand_Qm) / max(sd_Qm, minimum_Q_tolerance)
```

A simple combined distance could then be evaluated:

```text
distance = sqrt(zL² + zW² + zQ²)
```

The dimension-specific values should remain primary.

A future result should be explainable as, for example:

```text
L: close to selected population
W: close to selected population
Q: unusually high relative to selected population
```

rather than exposing only an opaque score.

### Minimum tolerances

The minimum L/W/Q tolerances are not yet defined.

They exist to prevent an artificially tiny observed SD from making the comparison unreasonably strict.

They must be chosen explicitly before implementation and covered by statistical fixtures.

Do not substitute SEM.

---

## Traffic-light presentation

A green/yellow/red indicator may later sit on top of the transparent comparison.

Conceptually:

```text
green   observation lies comfortably within the selected population
yellow  observation is marginal or unusual in one or more dimensions
red     observation differs substantially from the selected population
```

Also support:

```text
insufficient data
```

The traffic light is a presentation shortcut, not the statistical model.

It must always be possible to inspect:

```text
query Lm/Wm/Qm
community Lm/Wm/Qm
between-observation SD
zL/zW/zQ
number of observations
number of contributors
active filters / selected observations
```

Do not use language implying a probability that the taxonomic identification is correct.

Exact green/yellow/red thresholds are deliberately deferred until they can be defined and tested against real taxa.

---

## Small and weak populations

The comparison must degrade explicitly when little community data exists.

Possible population states include:

```text
insufficient measured data
provisional
community-supported
strong
```

Existing profile-status logic may inform this, but comparison eligibility and traffic-light thresholds must be defined deliberately rather than inferred from UI labels.

A species represented by one or two observations must not produce a high-confidence-looking result merely because its measured SD is small.

---

## Historical literature references

Published references are a separate evidence source from the community observation population.

The long-term objective is to allow both to be shown against the same measured population:

```text
                 selected community population
                          │
              ┌───────────┴───────────┐
              │                       │
     query observation        literature reference
```

This allows questions such as:

- Does this observation look typical of comparable modern observations?
- Does an old published reference agree with the same population?
- Does the answer change with preparation method or geography?
- Are several later references actually independent measurements, or repetitions of an older source?

Historical references must retain provenance and measurement context where known.

Relevant context may include:

```text
published taxon name
current mapped taxon
source/citation
original measurement vs secondary citation
sample/specimen count
number of spores
fresh/dried state
mount medium
stain
contrast/microscopy method
geographic origin
voucher/specimen
measurement convention
```

Missing context should remain `not reported`; it is not itself evidence that the reference is poor.

### Citation lineage and measurement independence

Later reference provenance should distinguish, where evidence permits:

- source reports measurements made by its authors;
- source explicitly derives or cites measurements from another source;
- source appears to reproduce an earlier published range;
- measurement provenance is unknown.

Repeated publication of the same underlying measurements must not be treated as independent biometric evidence.

This is a future requirement. Do not add citation-lineage schema merely to support the current reference UI.

### Parmasto-format literature data

Where a reference supplies Parmasto-style means/variation values, preserve and display them directly.

Do not manufacture Parmasto statistics from an ordinary min/max or literature range.

Conventional ranges may still be plotted and inspected, but they do not automatically enter the same statistical score as measured observation means.

---

## Tolerance intervals

Tolerance intervals may be added later:

```text
grand mean ± k * sd
```

but `k` must correspond to a defined statistical interpretation and adequate sample size.

For small populations any interval must be clearly provisional.

Do not present an arbitrary `k × SD` band as a formal confidence or tolerance interval.

---

## Later statistical model

Once enough independent observations exist, evaluate a fuller Parmasto-style comparison.

Possible later work includes:

```text
within-individual / within-specimen variability
between-specimen variability

effects of preparation and measurement context

geographic variation

contributor effects

covariance between L, W and Q

Mahalanobis distance using covariance of observation means
```

The richer model should be driven by actual accumulated data rather than added because the mathematics is available.

---

## Reproducibility

A comparison should eventually be reproducible from:

```text
query observation/version
taxon
selected filters
selected/excluded observation IDs
statistics version
comparison-model version
```

The UI does not necessarily need to persist every exploratory comparison, but the calculation itself must be deterministic.

If saved comparison sets are added later, persist the cohort definition rather than only the resulting green/yellow/red value.

---

## Methodological basis

Before any scoring stage is opened, this plan should pin down the exact Parmasto & Parmasto source(s) that motivate the species/specimen variability treatment and document which elements Sporely intends to adopt.

The plan should distinguish:

- methods directly adopted from Parmasto & Parmasto;
- methods merely inspired by their specimen-balanced approach;
- later statistical additions developed specifically for Sporely.

Do not use “Parmasto-style” as a loose justification for an algorithm that has not been tied back to the cited method.

---

## Proposed implementation sequence

### Stage 1 — Comparison cohort

Define the data contract for:

- eligible observation summaries;
- contextual filters;
- manual observation inclusion/exclusion;
- cohort metadata.

No comparison score yet.

### Stage 2 — Recomputed selected profile

Produce observation-balanced Lm/Wm/Qm and between-observation SD from the exact selected cohort.

Verify desktop/web calculations against shared statistical fixtures.

### Stage 3 — Transparent comparison experiment

Evaluate the candidate L/W/Q standardized-deviation calculation.

Expose dimension-specific results and combined distance.

Do not treat the candidate equations as approved until their numerical behavior has been reviewed on real taxa.

### Stage 4 — Comparison UI

Allow users to inspect and change:

- filters;
- contributing observations;
- cohort statistics.

Show the query observation beside the selected community population.

### Stage 5 — Traffic-light summary

Only after thresholds have been explicitly chosen and empirically reviewed:

- define green/yellow/red thresholds;
- add the compact visual indicator;
- keep underlying numerical evidence visible.

### Stage 6 — Literature reference against community

Allow registered historical/current references to appear against the same selected community population.

Preserve provenance and measurement context.

Do not manufacture missing statistics.

### Stage 7 — Advanced Parmasto model

Consider:

- fuller variance decomposition;
- covariance;
- Mahalanobis distance;
- effects of preparation/geography;
- empirically calibrated thresholds.

Only open this stage when enough data exists to justify it.

---

## Relationship to the reference-system UI plan

The current reference-system UI work should not invent its own match/verdict logic.

Its job is to register, preserve, select, and display references and their existing context.

Future community comparison, traffic-light summaries, and historical-reference-vs-community analysis belong here in the Parmasto comparison plan.

If the reference UI exposes comparison-related placeholders, they should remain neutral until this plan opens an implementation stage.

---

## Acceptance for the current foundation

Already satisfied or expected from the completed statistics work:

- Data needed for later comparison exists.
- No fake means are used.
- Species profiles use observation-balanced means.
- Species profiles expose between-observation SD.
- Measurement contexts can be represented separately.
- Structured observation summaries are available to the public/community layer.

Before implementation of the comparison system begins:

- The comparison cohort contract is explicit.
- Users can see what observations and contexts enter a comparison.
- Filters do not silently mix incompatible measurement contexts.
- Dimension-specific comparison behavior is defined.
- Minimum tolerances are defined and tested.
- The candidate baseline has been evaluated on real taxa before it becomes approved design.
- Traffic-light thresholds remain deferred until real-data behavior has been evaluated.
- Historical literature references remain separate from community-derived statistics and are not treated as ground truth.
- The exact Parmasto & Parmasto methodological basis is cited and mapped to the parts Sporely actually adopts.
