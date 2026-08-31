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
- `--capacity` — veh/hr for the v/c ratio (default: max observed flow)
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
  (c₁, c₂, c₃).

With the Aug 23–29, 2026 week of data: ffs ≈ 69 mph, capacity ≈ 8,360 veh/hr
(all lanes), 104 uncongested / 64 congested hours. Fits (R²): Logit 0.84 >
Combined 0.82 ≈ BPR 0.82 (α≈0.36, β≈3.3) > Conical 0.81 ≈ Akçelik 0.80 >
Generalized cost 0.56.

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
