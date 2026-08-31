# I-25 NB speed-flow analysis

`i25_speed_flow.py` builds the volume-speed diagram from CDOT detector exports
(station 000501_NB — I-25 S/O SH 6 / 6th Ave, Denver), derives travel time from
speed, shows the travel-time-vs-volume relationship, and fits a BPR
volume-delay function to the observations.

## Data (never committed)

Detector files live in `traffic-modeling-training/Volume Speed Data/` (or
`data/`) — both folders are git-ignored so raw detector data never reaches the
repo. Two CDOT export formats are parsed:

- `VOLUME_*.xlsx` — TCDS hourly count export: metadata block, then 24 rows of
  `00:00 - 01:00 | count`. One file per day.
- `SPEED_*.xls` — the "Excel Bin Count" export, which is actually an HTML page.
  Its second table holds hourly counts in 15 speed bins (0-20, 20-25, …,
  80-85, 85+). Hourly mean speed = bin-midpoint weighted average.

Speed and volume are joined on (date, hour), so every point is a real hour on
I-25 NB.

## Run

```powershell
python analysis\i25_speed_flow.py                 # scan default data folders
python analysis\i25_speed_flow.py --length 2.0    # segment length in miles
python analysis\i25_speed_flow.py --capacity 8400 --lanes 4
python analysis\i25_speed_flow.py --demo          # synthetic data, pipeline test
```

- `--length` — travel time = length / speed (default 1 mile)
- `--capacity` — veh/hr for the v/c ratio (default: 95th percentile of hourly
  volume — a sustainable rate; using the max observed hour would force every
  v/c ≤ 1 by construction)
- `--lanes` — divides volume to get per-lane flow
- `--demo` — synthetic I-25-like data to verify the pipeline

## Method notes

- Free-flow speed = 85th percentile of speeds in the lowest-volume quartile.
- The observed speed-flow curve is **double-valued**: the same volume occurs
  once at high speed (uncongested) and again at low speed (queue discharge /
  hypercongestion). Since BPR is a demand-based function, observations below
  0.72·ffs are classified as the congested branch and **excluded from the
  fit** — they are still plotted (in red) so the two branches are visible.
- **Demand reconstruction (shown, not fitted):** congested hours are also
  placed at a reconstructed demand v/c — the median volume for the same
  hour-of-day and day type on days that hour flowed freely, never less than
  the hour's own throughput. A single station only sees ~1 mile of a queue
  that extends miles upstream, so this shifts points by only ≈ +0.06 v/c —
  it cannot recover corridor demand, and those hours stay out of the fits.
- **BPR** `t = t0·(1 + α(v/c)^β)`: two fits are reported — both parameters
  free, and the headline calibration with **β fixed at the engineering
  standard 4** and α calibrated. Sub-capacity data identifies β only weakly
  (pinning β = 4 costs almost no R²), and β governs the oversaturated range
  that throughput data cannot observe, so the β = 4 prior is the defensible
  choice.
- Every VDF family from the Chapter 3 explorer is also fitted: BPR (β=4),
  Akçelik (HCM 2000, J), Combined link+node (k₄ and g/C), Conical (Spiess,
  α), Generalized cost (money term), Logit VDF (c₁, c₂, c₃). Akçelik and
  Conical treat v/c = 1 as a hard wall, so they are fitted on v/c ≤ 1 only.

With the Aug 1–29, 2026 month of data (672 hourly observations; Aug 12 lacks
a volume file) and capacity 7,200 veh/hr (4 lanes × 1,800): ffs ≈ 69.3 mph,
415 uncongested / 257 congested hours. BPR: α=0.216, β=2.74 free
(R²=0.720) vs **α=0.220, β=4 fixed (R²=0.692)** — the headline. Other
families (R²): Combined 0.76 > Logit 0.75 > Generalized cost 0.73 ≫
Akçelik 0.22 > Conical (negative; it forces t = 2·t0 exactly at capacity
while the data sits near 1.25 there).

These fitted values are the default slider positions in the Chapter 3 VDF
explorer (`Optimization.html` Part 1), which also embeds the 672 compiled
observations as dots (congested hours at their reconstructed demand v/c).

## Outputs

Saved next to the data in `…/Volume Speed Data/plots/` (also git-ignored):

1. **Speed vs volume** — the two-branch speed-flow curve with binned medians,
   free-flow speed and capacity reference lines
2. **Flow vs density** — fundamental diagram (k = q/v), branches colored
3. **Travel time vs volume** — the volume-delay relationship with the fitted
   BPR overlaid
4. **t/t0 vs v/c** — the VDF itself: fitted BPR vs the classic BPR (0.15, 4),
   the same function explored in Chapter 3's VDF tool
5. **i25_vdf_all_fits.png** — all six VDF families fitted over the data,
   colors matching the Chapter 3 explorer
6. **i25_points.js** — the compiled `[v/c, t/t0, congested]` observations as a
   JS array; this array is embedded in `Optimization.html` Part 1, which shows
   the I-25 hours as dots behind the VDF curves
