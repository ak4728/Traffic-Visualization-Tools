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
- BPR `t = t0·(1 + α(v/c)^β)` is fitted with `scipy.optimize.curve_fit` and
  compared against the classic α=0.15, β=4.
- Every VDF family from the Chapter 3 explorer is also fitted to the same
  uncongested observations: BPR, Akçelik (HCM 2000, J), Combined link+node
  (k₄ and g/C, node capacity tied to link capacity), Conical (Spiess, α),
  Generalized cost (constant money term over classic BPR), and Logit VDF
  (c₁, c₂, c₃). Akçelik and Conical treat v/c = 1 as a hard wall, so they are
  fitted on v/c ≤ 1 only.

With the Aug 1–29, 2026 month of data (672 hourly observations; Aug 12 lacks
a volume file): ffs ≈ 69.3 mph, capacity ≈ 7,570 veh/hr (95th pct, all lanes),
415 uncongested / 257 congested hours, throughput up to v/c ≈ 1.10.
Fits (R²): Combined 0.76 (k₄≈1.01, g/C≈0.88) > Logit 0.75 (c₁=6, c₂≈1.93,
c₃≈3.4) > BPR 0.72 (α≈0.25, β≈2.74) > Generalized cost 0.67 ≫ Akçelik 0.19 >
Conical (negative). The last two fail honestly: Akçelik stays flat until
v/c ≈ 1 and Spiess's conical forces t = 2·t0 exactly at capacity, while the
observed near-capacity hours sit at only t/t0 ≈ 1.2–1.35.

These fitted values are the default slider positions in the Chapter 3 VDF
explorer (`Optimization.html` Part 1), which also embeds the 672 compiled
observations as dots.

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
