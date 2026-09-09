# Pre-publication checklist — the ten things reviewers catch

Derived from an external review of a real multi-region land-use report. Work
through it before anything leaves your organisation.

## A. Wording

- [ ] **1. Never write "remaining forest".**
  Hansen loss is not netted against regrowth.
  ✗ "849,905 ha of forest remained in 2025"
  ✓ "849,905 ha had >30 % canopy in 2000 and no loss detected through 2025"
  ✗ "15 % of the forest was lost"
  ✓ "loss was detected on 15 % of the area with >30 % canopy in 2000"

- [ ] **2. Never write "recovered" for canopy returning.**
  ✓ "classified as tree cover in the 2021 land-cover map" — which includes
  plantations, tree crops and young regrowth.

- [ ] **3. Do not name a water body class you have not seen.**
  "New permanent water" covers ponds, reservoirs, channel migration and tides.
  Call it aquaculture only after looking at true-colour imagery.

## B. Strength of inference

- [ ] **4. Do not convert a statistical gap into a causal claim.**
  Harvested area (flow, double-cropping counted twice) vs land cover (stock,
  ~77 % accurate) are different quantities.
  ✗ "the same land rotates between forest and field — that is the reality"
  ✓ "the large gap is consistent with multiple cropping, rotational farming,
  fallow, and classification error on sloped smallholdings"

- [ ] **5. Compare like with like.**
  ✗ "289 ha (2019→2026, Sentinel-2 bare ground) vs 18,415 ha (2023–25, Hansen
  loss) — two orders of magnitude apart"
  ✓ recompute both with the same metric and the same window, then give the ratio
  as a real number ("3.3 % of the total", "about 30× larger").

- [ ] **6. State the period a cross-tabulation covers.**
  A 2021 land-cover map cannot tell you what happened to land cleared in 2023.
  Say which share of the total is therefore unassessed.

- [ ] **7. Keep observation and interpretation in separate paragraphs.**
  In an executive summary, interpretation stops at "suggests" / "is consistent
  with". Assertions belong next to the numbers that support them.

## C. Method

- [ ] **8. Use a common valid mask for any two-date comparison**, and print the
  valid-pixel percentage. Masking each date independently lets a difference in
  cloud cover appear as change.

- [ ] **9. Check that the parts sum to the whole.** If zone totals do not match
  the aggregate, find out why (boundary provenance, rasterization, coastline) and
  put the difference in a footnote. Do not ship a table that silently disagrees
  with itself.

- [ ] **10. Evaluate threshold dependence — and report it either way.** Recompute
  with at least one alternative threshold (canopy 10/30/50 %, NDVI cut-off,
  occurrence cut-off). If the conclusion changes, say by how much; do not fix
  the desired conclusion first and look for a threshold that gives it.

- [ ] **11. Map area is not a statistical area estimate.** A pixel tally on a
  classified map carries the map's classification error. Hansen's own usage
  notes say definitive area estimates should not be made from loss-pixel counts.
  For a defensible area figure, sample with reference data and give a
  confidence interval; otherwise call it "mapped area".

## D. Attribution

- [ ] Every dataset cited in the form its provider asks for (see `data_catalog.md`)
- [ ] Boundary sources cited **per level** where they differ
- [ ] Copernicus wording: `Contains modified Copernicus Sentinel data [year].`
      without `processed by ESA` on your own analysis
- [ ] Dataset **versions and periods** stated in the body text, and confirmed to be
      the newest at the time of writing
- [ ] A run manifest kept with the outputs: input files, versions, scene IDs, AOI,
      period, thresholds, grid/stride, valid share, software environment

## E. Sensitivity and scope

- [ ] Confidential material scoped **by section and figure number**, not by chapter
      (a whole-chapter exclusion usually removes innocent content and keeps
      the sensitive number somewhere else)
- [ ] A separate file generated for external distribution — deleting pages from a
      PDF leaves the figures in the body text
- [ ] No legality claim derived from satellite data alone; zoning maps show what is
      permitted in principle, not whether a permit exists
- [ ] For work about someone else's country or region: consider whether local
      partners should be co-authors *before* publication, not after
