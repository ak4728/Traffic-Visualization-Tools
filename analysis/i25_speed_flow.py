"""
I-25 NB speed-flow analysis  (CDOT station 000501_NB — I-25 S/O SH 6, Denver)
=============================================================================
Builds the empirical volume-speed diagram from CDOT detector exports, derives
travel time from speed, shows its relationship with volume, and fits a BPR
volume-delay function to the observations.

Data (kept in a git-ignored folder)
-----------------------------------
  VOLUME_*.xlsx : CDOT TCDS hourly count export — metadata block, then 24 rows
                  "00:00 - 01:00 | count".  One file per day.
  SPEED_*.xls   : CDOT "Excel Bin Count" export — actually an HTML page whose
                  second table holds hourly counts in 15 speed bins
                  (0-20, 20-25, ..., 80-85, 85-999) plus a Total column.
Hourly mean speed = bin-midpoint weighted average.  Speed and volume are
joined on (date, hour) so every observation is a real hour on I-25 NB.

Usage
-----
  python i25_speed_flow.py                       # scan the default data folders
  python i25_speed_flow.py --data "some\\folder"
  python i25_speed_flow.py --length 2.0 --lanes 4 --capacity 2100
  python i25_speed_flow.py --demo                # synthetic data, pipeline test

  --lanes N divides volume into per-lane flow (capacity then means per-lane).

Outputs
-------
  <out>/i25_speed_flow.png   2x2 summary: speed-flow, fundamental diagram,
                             travel time vs volume, fitted VDF
  <out>/i25_bpr_fit.png      standalone t/t0 vs v/c with the BPR fit
  console: free-flow speed, capacity, fitted alpha & beta, R^2
"""

import argparse
import glob
import os
import re
import sys

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit

TEAL, RED, BLUE, AMBER, GRAY = "#0e7c86", "#a4161a", "#2c5378", "#b45309", "#8a94a3"

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DIRS = [
    os.path.join(HERE, "..", "traffic-modeling-training", "Volume Speed Data"),
    os.path.join(HERE, "..", "data"),
]


# ──────────────────────────────────────────────────────────────────────
#  CDOT parsers
# ──────────────────────────────────────────────────────────────────────
def parse_volume_xlsx(path):
    """CDOT TCDS hourly count export -> DataFrame(date, hour, volume)."""
    df = pd.read_excel(path, header=None)
    date = None
    rows = []
    for _, r in df.iterrows():
        cells = [str(c).strip() for c in r.tolist() if str(c).strip() not in ("", "nan")]
        if not cells:
            continue
        if date is None and "Start Date" in cells:
            i = cells.index("Start Date")
            if i + 1 < len(cells):
                date = pd.to_datetime(cells[i + 1], errors="coerce")
        m = re.match(r"^(\d{1,2}):\d{2}\s*-\s*\d{1,2}:\d{2}$", cells[0])
        if m:
            nums = [float(c) for c in cells[1:] if re.match(r"^\d+(\.\d+)?$", c)]
            if nums:
                rows.append({"hour": int(m.group(1)), "volume": nums[0]})
    if date is None or pd.isna(date) or not rows:
        return None
    out = pd.DataFrame(rows)
    out["date"] = date.normalize()
    return out


def parse_speed_html(path):
    """CDOT bin-count 'xls' (HTML) -> DataFrame(date, hour, speed, bin_total).

    Mean speed per hour = sum(count * bin midpoint) / sum(count).
    """
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        html = f.read()

    md = re.search(r"Start Date</td><td[^>]*>\s*(\d{1,2}/\d{1,2}/\d{4})", html)
    if not md:
        md = re.search(r"date=(\d{4}-\d{2}-\d{2})", html)
    if not md:
        return None
    date = pd.to_datetime(md.group(1)).normalize()

    # bin headers like "&nbsp;0-20" ... "&nbsp;85-999" in the speed-range table
    bins = re.findall(r"&nbsp;(\d+)-(\d+)</td>", html)
    mids = []
    for lo, hi in bins:
        lo, hi = float(lo), float(hi)
        mids.append((lo + hi) / 2 if hi < 200 else min(lo + 5, 90.0))
    if not mids:
        return None

    rows = []
    for m in re.finditer(
        r"<tr><td>(\d{1,2}):00\s*(AM|PM)</td>((?:<td>\d+</td>)+)</tr>", html
    ):
        h, ap = int(m.group(1)), m.group(2)
        hour = (h % 12) + (12 if ap == "PM" else 0)
        counts = [int(c) for c in re.findall(r"<td>(\d+)</td>", m.group(3))]
        # last cell is the Total column
        binc, total = counts[:-1], counts[-1]
        if len(binc) != len(mids) or total <= 0 or sum(binc) == 0:
            continue
        speed = sum(c * s for c, s in zip(binc, mids)) / sum(binc)
        rows.append({"hour": hour, "speed": speed, "bin_total": total})
    if not rows:
        return None
    out = pd.DataFrame(rows)
    out["date"] = date
    return out


def load_data(data_dirs):
    vol_frames, spd_frames = [], []
    for d in data_dirs:
        if not os.path.isdir(d):
            continue
        for f in sorted(glob.glob(os.path.join(d, "*.xls*"))):
            base = os.path.basename(f)
            if base.upper().startswith("VOLUME"):
                p = parse_volume_xlsx(f)
                tag = "volume"
            elif base.upper().startswith("SPEED"):
                p = parse_speed_html(f)
                tag = "speed"
            else:
                continue
            if p is None:
                print(f"  !! could not parse {base}")
                continue
            print(f"  {base}: {len(p)} hourly rows ({tag}, "
                  f"{p['date'].iloc[0].date()})")
            (vol_frames if tag == "volume" else spd_frames).append(p)

    if not vol_frames or not spd_frames:
        sys.exit("Need both VOLUME_*.xlsx and SPEED_*.xls files in the data "
                 "folder(s). Searched: "
                 + "; ".join(os.path.abspath(d) for d in data_dirs)
                 + "\n(or run with --demo)")

    vol = pd.concat(vol_frames, ignore_index=True)
    spd = pd.concat(spd_frames, ignore_index=True)
    vol = vol.drop_duplicates(subset=["date", "hour"])
    spd = spd.drop_duplicates(subset=["date", "hour"])
    df = pd.merge(spd, vol, on=["date", "hour"], how="inner")
    print(f"  joined on date+hour: {len(df)} observations "
          f"({df['date'].min().date()} ... {df['date'].max().date()})")
    df = df[(df["speed"] > 1) & (df["speed"] < 120) & (df["volume"] > 0)]
    return df.reset_index(drop=True)


def demo_data(n=2500, seed=25):
    """Synthetic I-25-like observations to verify the pipeline."""
    rng = np.random.default_rng(seed)
    cap, ffs = 2000.0, 68.0
    vol = np.clip(rng.beta(1.6, 1.8, n) * 2400, 60, None)
    x = vol / cap
    speed = ffs / (1 + 0.55 * x ** 4.6) * (1 + rng.normal(0, 0.05, n))
    mask = rng.random(n) < np.clip((x - 0.85) * 0.5, 0, 0.35)
    speed[mask] = rng.uniform(12, 38, mask.sum())
    vol[mask] = rng.uniform(0.65, 0.95, mask.sum()) * cap
    return pd.DataFrame({"speed": np.clip(speed, 4, 90), "volume": vol})


# ──────────────────────────────────────────────────────────────────────
#  Analysis
# ──────────────────────────────────────────────────────────────────────
def binned(df, xcol, ycol, nbins=20, min_pts=3):
    edges = np.linspace(df[xcol].min(), df[xcol].max(), nbins + 1)
    mids, med = [], []
    for lo, hi in zip(edges[:-1], edges[1:]):
        sel = df[(df[xcol] >= lo) & (df[xcol] < hi)]
        if len(sel) >= min_pts:
            mids.append((lo + hi) / 2)
            med.append(sel[ycol].median())
    return np.array(mids), np.array(med)


def main():
    ap = argparse.ArgumentParser(description="I-25 NB speed-flow & BPR fit")
    ap.add_argument("--data", default=None,
                    help="data folder (default: 'traffic-modeling-training/"
                         "Volume Speed Data' and 'data/')")
    ap.add_argument("--length", type=float, default=1.0,
                    help="segment length in miles (travel time = length/speed)")
    ap.add_argument("--capacity", type=float, default=None,
                    help="capacity in veh/hr (default: 95th pct of volume)")
    ap.add_argument("--lanes", type=int, default=1,
                    help="divide volume by this to get per-lane flow")
    ap.add_argument("--out", default=None, help="output folder for plots")
    ap.add_argument("--demo", action="store_true",
                    help="run on synthetic data instead of the data folder")
    args = ap.parse_args()

    data_dirs = [args.data] if args.data else DEFAULT_DIRS
    out_dir = args.out or os.path.join(data_dirs[0], "plots")
    os.makedirs(out_dir, exist_ok=True)

    if args.demo:
        print("DEMO MODE — synthetic I-25-like data")
        df = demo_data()
    else:
        print("Loading CDOT detector exports...")
        df = load_data(data_dirs)
    if args.lanes > 1:
        df["volume"] = df["volume"] / args.lanes
        print(f"  volumes divided by {args.lanes} lanes -> per-lane flow")
    print(f"  {len(df)} clean observations")

    # free-flow speed: what people drive when the road is empty —
    # 85th percentile of speeds in the lowest-volume quartile
    low = df[df["volume"] <= df["volume"].quantile(0.25)]
    ffs = low["speed"].quantile(0.85)
    cap = args.capacity or df["volume"].max()        # max observed throughput
    t0 = args.length / ffs * 60                      # free-flow time (min)

    df["tt"] = args.length / df["speed"] * 60        # travel time (min)
    df["xc"] = df["volume"] / cap                    # v/c ratio
    df["ratio"] = df["tt"] / t0                      # t / t0
    df["density"] = df["volume"] / df["speed"]       # veh/mi

    # Two-regime split. The speed-flow curve is double-valued: the same
    # volume occurs at high speed (uncongested) and again at low speed
    # (queue discharge / hypercongestion). BPR is a demand-based function,
    # so it is fitted to the uncongested branch only.
    s_crit = 0.72 * ffs
    df["congested"] = df["speed"] < s_crit
    unc = df[~df["congested"]]
    con = df[df["congested"]]

    # ── BPR fit: t/t0 = 1 + a*(v/c)^b ────────────────────────────────
    def bpr(x, a, b):
        return 1 + a * np.power(np.clip(x, 1e-6, None), b)

    fit_df = unc[unc["ratio"] >= 0.85]               # ignore the >ffs speeders
    (a_fit, b_fit), _ = curve_fit(bpr, fit_df["xc"], fit_df["ratio"],
                                  p0=[0.15, 4.0],
                                  bounds=([0.005, 0.5], [5.0, 15.0]),
                                  maxfev=20000)
    pred = bpr(fit_df["xc"], a_fit, b_fit)
    ss_res = np.sum((fit_df["ratio"] - pred) ** 2)
    ss_tot = np.sum((fit_df["ratio"] - fit_df["ratio"].mean()) ** 2)
    r2 = 1 - ss_res / ss_tot

    print("\n──── results ─────────────────────────────────────")
    print(f"  free-flow speed  (85th pct, low flow): {ffs:6.1f} mph")
    print(f"  capacity used                        : {cap:6.0f} veh/hr"
          + ("" if args.capacity else "  (max observed flow — override with --capacity)"))
    print(f"  regime split at {s_crit:.0f} mph        : "
          f"{len(unc)} uncongested / {len(con)} congested hours "
          f"(BPR fitted to uncongested only)")
    print(f"  free-flow travel time t0 ({args.length} mi)   : {t0:6.2f} min")
    print(f"  BPR fit  t = t0(1 + a(v/c)^b)        : a = {a_fit:.3f}, b = {b_fit:.2f}   R2 = {r2:.3f}")
    print(f"  (classic BPR defaults: a = 0.150, b = 4.00)")

    # ── plots ────────────────────────────────────────────────────────
    plt.rcParams.update({"font.family": "Segoe UI", "font.size": 10,
                         "axes.grid": True, "grid.alpha": 0.3})
    sub = "demo data" if args.demo else \
        "CDOT station 000501_NB — I-25 S/O SH 6 (6th Ave), Denver"

    fig, ax = plt.subplots(2, 2, figsize=(13, 9))
    fig.suptitle(f"I-25 NB — Speed, Flow, Travel Time and the BPR Fit\n{sub}",
                 fontweight="bold")

    # 1. speed vs volume
    a1 = ax[0, 0]
    a1.scatter(unc["volume"], unc["speed"], s=16, alpha=0.55, color=BLUE,
               edgecolors="none", label="uncongested branch")
    a1.scatter(con["volume"], con["speed"], s=16, alpha=0.55, color=RED,
               edgecolors="none", label="congested (queue discharge)")
    bx, by = binned(unc, "volume", "speed")
    a1.plot(bx, by, color=TEAL, lw=2.5, label="binned median (uncongested)")
    a1.axhline(ffs, color=GRAY, ls="--", lw=1.2, label=f"free-flow {ffs:.0f} mph")
    a1.axvline(cap, color=AMBER, ls="--", lw=1.2, label=f"capacity {cap:.0f} veh/hr")
    a1.set_xlabel("volume (veh/hr)"); a1.set_ylabel("speed (mph)")
    a1.set_title("Speed vs volume — the two-branch speed-flow curve")
    a1.legend(fontsize=8)

    # 2. flow vs density (fundamental diagram)
    a2 = ax[0, 1]
    a2.scatter(unc["density"], unc["volume"], s=16, alpha=0.55, color=BLUE,
               edgecolors="none", label="uncongested branch")
    a2.scatter(con["density"], con["volume"], s=16, alpha=0.55, color=RED,
               edgecolors="none", label="congested branch")
    bx, by = binned(df, "density", "volume")
    a2.plot(bx, by, color=TEAL, lw=2.5, label="binned median")
    a2.set_xlabel("density k = q/v (veh/mi)"); a2.set_ylabel("flow q (veh/hr)")
    a2.set_title("Flow vs density — fundamental diagram")
    a2.legend(fontsize=8)

    # 3. travel time vs volume with the fitted BPR
    a3 = ax[1, 0]
    a3.scatter(unc["volume"], unc["tt"], s=16, alpha=0.55, color=BLUE,
               edgecolors="none", label="uncongested branch")
    a3.scatter(con["volume"], con["tt"], s=16, alpha=0.55, color=RED,
               edgecolors="none", label="congested (excluded from fit)")
    vg = np.linspace(0, df["volume"].max(), 200)
    a3.plot(vg, t0 * bpr(vg / cap, a_fit, b_fit), color=TEAL, lw=2.5,
            label=f"BPR fit  a={a_fit:.2f}, b={b_fit:.1f}")
    a3.axhline(t0, color=GRAY, ls="--", lw=1, label=f"t0 = {t0:.2f} min")
    a3.set_xlabel("volume (veh/hr)")
    a3.set_ylabel(f"travel time over {args.length} mi (min) = length/speed")
    a3.set_title("Travel time vs volume — the volume-delay relationship")
    a3.legend(fontsize=8)

    # 4. t/t0 vs v/c: the VDF itself
    a4 = ax[1, 1]
    a4.scatter(unc["xc"], unc["ratio"], s=16, alpha=0.55, color=BLUE,
               edgecolors="none", label="uncongested branch")
    a4.scatter(con["xc"], con["ratio"], s=16, alpha=0.55, color=RED,
               edgecolors="none", label="congested (excluded from fit)")
    xg = np.linspace(0, max(1.4, df["xc"].max()), 200)
    a4.plot(xg, bpr(xg, a_fit, b_fit), color=TEAL, lw=2.5,
            label=f"fitted BPR (a={a_fit:.2f}, b={b_fit:.1f}, R2={r2:.2f})")
    a4.plot(xg, bpr(xg, 0.15, 4.0), color=AMBER, lw=1.8, ls="--",
            label="classic BPR (0.15, 4)")
    a4.axvline(1.0, color=GRAY, ls=":", lw=1)
    a4.set_xlabel("v/c ratio"); a4.set_ylabel("t / t0 (travel-time ratio)")
    a4.set_title("The volume-delay function, fitted to the uncongested branch")
    a4.legend(fontsize=8)

    fig.tight_layout(rect=[0, 0, 1, 0.94])
    p1 = os.path.join(out_dir, "i25_speed_flow.png")
    fig.savefig(p1, dpi=140)

    # standalone VDF figure
    fig2, a = plt.subplots(figsize=(8, 5.5))
    a.scatter(unc["xc"], unc["ratio"], s=18, alpha=0.55, color=BLUE,
              edgecolors="none", label="uncongested hours (t/t0 from speed)")
    a.scatter(con["xc"], con["ratio"], s=18, alpha=0.55, color=RED,
              edgecolors="none", label="congested hours (excluded from fit)")
    a.plot(xg, bpr(xg, a_fit, b_fit), color=TEAL, lw=3,
           label=f"fitted BPR: 1 + {a_fit:.3f}*(v/c)^{b_fit:.2f}")
    a.plot(xg, bpr(xg, 0.15, 4.0), color=AMBER, lw=2, ls="--",
           label="classic BPR (0.15, 4)")
    a.axvline(1.0, color=GRAY, ls=":", lw=1)
    a.set_xlabel("v/c ratio"); a.set_ylabel("t / t0")
    a.set_title(f"I-25 NB volume-delay function — R2 = {r2:.3f}")
    a.legend()
    fig2.tight_layout()
    p2 = os.path.join(out_dir, "i25_bpr_fit.png")
    fig2.savefig(p2, dpi=140)

    print(f"\n  plots saved:\n    {p1}\n    {p2}")


if __name__ == "__main__":
    main()
