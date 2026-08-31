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
    # capacity: 95th percentile of hourly volumes — a sustainable rate, not
    # the single best hour ever seen (using max observed would force every
    # v/c <= 1 by construction and hide the oversaturated hours)
    cap = args.capacity or df["volume"].quantile(0.95)
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

    # Demand reconstruction for congested hours. During queue discharge the
    # detector counts THROUGHPUT, not demand, so those hours plot at an
    # artificially low v/c. Proxy the demand with the median volume observed
    # for the same hour-of-day and day type (weekday/weekend) on days when
    # that hour flowed freely; demand is never less than the hour's own
    # throughput. Uncongested hours keep their own volume (count = demand).
    df["weekend"] = pd.to_datetime(df["date"]).dt.dayofweek >= 5
    prof = df[~df["congested"]].groupby(["weekend", "hour"])["volume"].median()

    def demand_of(r):
        if not r.congested:
            return r.volume
        p = prof.get((r.weekend, r.hour), np.nan)
        if pd.isna(p):   # hour congested on every day of this type
            p = df[(df["weekend"] == r.weekend) & (df["hour"] == r.hour)]["volume"].max()
        return max(p, r.volume)

    df["demand"] = df.apply(demand_of, axis=1)
    df["xd"] = df["demand"] / cap                    # demand-based v/c
    unc = df[~df["congested"]]
    con = df[df["congested"]]

    # ── BPR fit: t/t0 = 1 + a*(v/c)^b ────────────────────────────────
    def bpr(x, a, b):
        return 1 + a * np.power(np.clip(x, 1e-6, None), b)

    fit_unc = unc[unc["ratio"] >= 0.85]              # ignore the >ffs speeders
    fit_all = df[df["ratio"] >= 0.85]                # all hours, x = demand v/c

    def r2_of(fn, popt, xs, ys):
        res = ys - fn(xs, *popt)
        return 1 - np.sum(res ** 2) / np.sum((ys - ys.mean()) ** 2)

    # free fit (alpha and beta both estimated from the uncongested branch)
    (a_unc, b_unc), _ = curve_fit(bpr, fit_unc["xc"], fit_unc["ratio"],
                                  p0=[0.15, 4.0],
                                  bounds=([0.005, 0.5], [5.0, 15.0]),
                                  maxfev=20000)
    r2u = r2_of(bpr, (a_unc, b_unc), fit_unc["xc"].values, fit_unc["ratio"].values)

    # engineering fit: beta pinned at the classic 4 (sub-capacity data
    # identifies beta only weakly, and beta governs the oversaturated range
    # the throughput data cannot see), alpha calibrated
    B_FIX = 4.0
    (a_b4,), _ = curve_fit(lambda x, a: bpr(x, a, B_FIX),
                           fit_unc["xc"], fit_unc["ratio"],
                           p0=[0.15], bounds=([0.005], [5.0]), maxfev=20000)
    r2b4 = r2_of(bpr, (a_b4, B_FIX), fit_unc["xc"].values, fit_unc["ratio"].values)
    a_fit, b_fit, r2 = a_b4, B_FIX, r2b4        # headline calibration

    print("\n──── results ─────────────────────────────────────")
    print(f"  free-flow speed  (85th pct, low flow): {ffs:6.1f} mph")
    print(f"  capacity used                        : {cap:6.0f} veh/hr"
          + ("" if args.capacity else "  (95th pct of volume — override with --capacity)"))
    print(f"  regime split at {s_crit:.0f} mph        : "
          f"{len(unc)} uncongested / {len(con)} congested hours")
    shift = (con["xd"] - con["xc"])
    print(f"  demand reconstruction (local queue)  : congested hours moved from "
          f"throughput v/c [{con['xc'].min():.2f}-{con['xc'].max():.2f}] to "
          f"demand v/c [{con['xd'].min():.2f}-{con['xd'].max():.2f}] "
          f"(median shift +{shift.median():.2f})")
    print("    NOTE: a single station sees only ~1 mi of the queue, so the")
    print("    reconstruction cannot recover corridor demand. Charts therefore")
    print("    plot congested hours at their OBSERVED throughput v/c, and those")
    print("    hours stay out of the fits.")
    print(f"  free-flow travel time t0 ({args.length} mi)   : {t0:6.2f} min")
    print(f"  BPR, both params free (uncongested)  : a = {a_unc:.3f}, b = {b_unc:.2f}   R2 = {r2u:.3f}")
    print(f"  BPR, beta fixed at 4 (headline)      : a = {a_b4:.3f}, b = {B_FIX:.2f}   R2 = {r2b4:.3f}")
    print(f"  (classic BPR defaults: a = 0.150, b = 4.00)")

    # ── fit every VDF family from the Chapter 3 explorer ─────────────
    # All are expressed as travel-time ratio r(x) = t/t0 and fitted to the
    # uncongested branch, mirroring traffic-modeling-training/Optimization.html.
    def conical(x, a):
        b = (2 * a - 1) / (2 * a - 2)
        return 2 + np.sqrt(a * a * (1 - x) ** 2 + b * b) - a * (1 - x) - b

    def akcelik(x, J):
        # T = 1 hr analysis period, node delay D0 = 0 (freeway segment)
        T = 1.0
        d_hr = 0.25 * T * ((x - 1) + np.sqrt((x - 1) ** 2 + 8 * J * x / (cap * T)))
        return 1 + 60 * d_hr / t0

    def combined(x, k4, lam):
        # BPR link part scaled by k4 + Webster uniform node delay with the
        # node's capacity tied to the link's (sat*lam = cap), cycle C = 90 s
        Cc = 90.0
        link = k4 * (1 + 0.15 * np.power(x, 4))
        d_uni = Cc * (1 - lam) ** 2 / (2 * np.maximum(1 - lam * np.minimum(x, 1), 0.05))
        return link + d_uni / 60 / t0

    def gencost(x, m):
        # classic BPR time + a constant money term converted to minutes
        return 1 + 0.15 * np.power(x, 4) + m / t0

    def logit_vdf(x, c1, c2, c3):
        return 1 + c1 / (1 + np.exp(c3 * (c2 - x)))

    # capwall=True: the function treats v/c = 1 as a hard wall (it goes
    # near-vertical there), so it is fitted only on v/c <= 1.
    FITS = [
        ("BPR (1964)",           lambda x, a: bpr(x, a, B_FIX),
                                            [0.15],           ([0.005], [5.0]),                  ["a (b=4 fixed)"], False),
        ("Akçelik (HCM 2000)",   akcelik,   [0.8],            ([0.001], [500]),                  ["J"],             True),
        ("Combined link+node",   combined,  [1.0, 0.8],       ([0.5, 0.1], [2.0, 0.98]),         ["k4", "g/C"],     False),
        ("Conical (Spiess 1990)", conical,  [4.0],            ([1.01], [40]),                    ["alpha"],         True),
        ("Generalized cost",     gencost,   [0.05],           ([0.0], [5.0]),                    ["money (min)"],   False),
        ("Logit VDF",            logit_vdf, [1.5, 1.05, 6.0], ([0.05, 0.5, 0.5], [8, 2.5, 40]),  ["c1", "c2", "c3"], False),
    ]
    sub1 = fit_unc[fit_unc["xc"] <= 1.0]
    fitted = {}
    print("\n──── all VDF families, fitted to the uncongested branch ────")
    for name, fn, p0, bounds, labels, capwall in FITS:
        d = sub1 if capwall else fit_unc
        xs, yv = d["xc"].values, d["ratio"].values
        try:
            popt, _ = curve_fit(fn, xs, yv, p0=p0, bounds=bounds, maxfev=40000)
            res = yv - fn(xs, *popt)
            fr2 = 1 - np.sum(res ** 2) / np.sum((yv - yv.mean()) ** 2)
            rmse = np.sqrt(np.mean(res ** 2))
            fitted[name] = (fn, popt, fr2, capwall)
            ptxt = ", ".join(f"{l} = {v:.3f}" for l, v in zip(labels, popt))
            note = "  (fit on v/c<=1 only)" if capwall else ""
            print(f"  {name:<24} {ptxt:<44} R2 = {fr2:6.3f}   RMSE = {rmse:.4f}{note}")
        except Exception as e:
            print(f"  {name:<24} fit failed: {e}")

    # ── classic speed-density models ─────────────────────────────────
    # Fitted on u vs k across BOTH regimes — that is their whole point:
    # one curve through free flow and congestion. q(k) = k·u(k) follows.
    kv, uv = df["density"].values, df["speed"].values

    def gs_u(k, uf, kj):          # Greenshields (1935): linear u-k
        return uf * (1 - k / kj)

    def gb_u(k, uc, kj):          # Greenberg (1959): logarithmic
        return uc * np.log(np.maximum(kj / np.maximum(k, 1e-9), 1e-9))

    def uw_u(k, uf, kc):          # Underwood (1961): exponential
        return uf * np.exp(-k / kc)

    SD = {}
    print("\n──── speed-density models (all hours, u vs k) ────")
    # Greenshields with engineering values pinned: uf = 68 mph (observed
    # free-flow), kj = 450 veh/mi (~112/lane over 4 lanes) — no free params
    GS_UF, GS_KJ = 68.0, 450.0
    gs_p = (GS_UF, GS_KJ)
    SD["Greenshields"] = (gs_u, gs_p, r2_of(gs_u, gs_p, kv, uv))
    print(f"  {'Greenshields':<13} uf = {GS_UF:7.1f}, kj = {GS_KJ:7.1f}   "
          f"R2(u|k) = {SD['Greenshields'][2]:.3f}   "
          f"implied capacity = {GS_UF * GS_KJ / 4:5.0f} veh/hr  (uf, kj pinned)")
    for name, fn, p0, bnd, capfun in [
        ("Greenberg",    gb_u, [35, 600],  ([5, 100], [200, 5000]),
         lambda p: p[0] * p[1] / np.e),              # qmax = uc·kj/e
        ("Underwood",    uw_u, [70, 200],  ([30, 20], [100, 3000]),
         lambda p: p[0] * p[1] / np.e),              # qmax = uf·kc/e
    ]:
        popt, _ = curve_fit(fn, kv, uv, p0=p0, bounds=bnd, maxfev=40000)
        sr2 = r2_of(fn, popt, kv, uv)
        SD[name] = (fn, popt, sr2)
        qm = capfun(popt)
        print(f"  {name:<13} p1 = {popt[0]:7.1f}, p2 = {popt[1]:7.1f}   "
              f"R2(u|k) = {sr2:.3f}   implied capacity = {qm:5.0f} veh/hr")

    SD_COLS = {"Greenshields": "#40663c", "Greenberg": "#7a4b8f", "Underwood": "#b45309"}

    def sd_curves(name, n=300):
        fn, popt, _ = SD[name]
        kmax = popt[1] * (0.999 if name != "Underwood" else 6)
        kk = np.linspace(1, min(kmax, kv.max() * 1.6), n)
        uu = np.clip(fn(kk, *popt), 0, None)
        return kk, uu, kk * uu

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
    for nm in SD:
        kk, uu, qq = sd_curves(nm)
        a1.plot(qq, uu, color=SD_COLS[nm], lw=2,
                label=f"{nm} (R2={SD[nm][2]:.2f})")
    a1.axhline(ffs, color=GRAY, ls="--", lw=1.2, label=f"free-flow {ffs:.0f} mph")
    a1.axvline(cap, color=AMBER, ls="--", lw=1.2, label=f"capacity {cap:.0f} veh/hr")
    a1.set_xlabel("volume (veh/hr)"); a1.set_ylabel("speed (mph)")
    a1.set_title("Speed vs volume — with fitted speed-density models")
    a1.set_xlim(0, df["volume"].max() * 1.08)
    a1.set_ylim(0, min(90, uv.max() * 1.15))
    a1.legend(fontsize=7)

    # 2. flow vs density (fundamental diagram)
    a2 = ax[0, 1]
    a2.scatter(unc["density"], unc["volume"], s=16, alpha=0.55, color=BLUE,
               edgecolors="none", label="uncongested branch")
    a2.scatter(con["density"], con["volume"], s=16, alpha=0.55, color=RED,
               edgecolors="none", label="congested branch")
    for nm in SD:
        kk, uu, qq = sd_curves(nm)
        a2.plot(kk, qq, color=SD_COLS[nm], lw=2,
                label=f"{nm} (R2={SD[nm][2]:.2f})")
    a2.set_xlabel("density k = q/v (veh/mi)"); a2.set_ylabel("flow q (veh/hr)")
    a2.set_xlim(0, kv.max() * 1.05)
    a2.set_ylim(0, df["volume"].max() * 1.12)
    a2.set_title("Flow vs density — fundamental diagram with fitted models")
    a2.legend(fontsize=7)

    # 3. travel time vs OBSERVED volume — the exact mirror of panel 1
    # (tt = length/speed, same x-axis; the reconstructed-demand view lives
    # in panel 4 and the VDF figures, where x must be demand)
    a3 = ax[1, 0]
    a3.scatter(unc["volume"], unc["tt"], s=16, alpha=0.55, color=BLUE,
               edgecolors="none", label="uncongested branch")
    a3.scatter(con["volume"], con["tt"], s=16, alpha=0.55, color=RED,
               edgecolors="none", label="congested (queue discharge)")
    vg = np.linspace(0, df["volume"].max(), 200)
    a3.plot(vg, t0 * bpr(vg / cap, a_fit, b_fit), color=TEAL, lw=2.5,
            label=f"BPR fit  a={a_fit:.2f}, b={b_fit:.1f}")
    a3.axhline(t0, color=GRAY, ls="--", lw=1, label=f"t0 = {t0:.2f} min")
    a3.set_xlabel("volume (veh/hr)")
    a3.set_ylabel(f"travel time over {args.length} mi (min) = length/speed")
    a3.set_title("Travel time vs volume — inverse of the speed-flow curve")
    a3.legend(fontsize=8)

    # 4. t/t0 vs v/c: the VDF itself
    a4 = ax[1, 1]
    a4.scatter(unc["xc"], unc["ratio"], s=16, alpha=0.55, color=BLUE,
               edgecolors="none", label="uncongested branch")
    a4.scatter(con["xc"], con["ratio"], s=16, alpha=0.55, color=RED,
               edgecolors="none",
               label="congested (x = throughput; demand unobservable)")
    xg = np.linspace(0, max(1.4, df["xc"].max()), 200)
    a4.plot(xg, bpr(xg, a_fit, b_fit), color=TEAL, lw=2.5,
            label=f"fitted BPR (a={a_fit:.2f}, b={b_fit:.1f}, R2={r2:.2f})")
    a4.plot(xg, bpr(xg, 0.15, 4.0), color=AMBER, lw=1.8, ls="--",
            label="classic BPR (0.15, 4)")
    a4.axvline(1.0, color=GRAY, ls=":", lw=1)
    a4.set_xlabel("v/c ratio"); a4.set_ylabel("t / t0 (travel-time ratio)")
    a4.set_title("The volume-delay function — β = 4 fixed, α calibrated")
    a4.legend(fontsize=8)

    fig.tight_layout(rect=[0, 0, 1, 0.94])
    p1 = os.path.join(out_dir, "i25_speed_flow.png")
    fig.savefig(p1, dpi=140)

    # standalone VDF figure
    fig2, a = plt.subplots(figsize=(8, 5.5))
    a.scatter(unc["xc"], unc["ratio"], s=18, alpha=0.55, color=BLUE,
              edgecolors="none", label="uncongested hours (t/t0 from speed)")
    a.scatter(con["xc"], con["ratio"], s=18, alpha=0.55, color=RED,
              edgecolors="none",
              label="congested hours (x = throughput; demand unobservable)")
    a.plot(xg, bpr(xg, a_fit, b_fit), color=TEAL, lw=3,
           label=f"fitted BPR: 1 + {a_fit:.3f}*(v/c)^{b_fit:.2f}")
    a.plot(xg, bpr(xg, 0.15, 4.0), color=AMBER, lw=2, ls="--",
           label="classic BPR (0.15, 4)")
    a.axvline(1.0, color=GRAY, ls=":", lw=1)
    a.set_xlabel("v/c ratio"); a.set_ylabel("t / t0")
    a.set_title(f"I-25 NB volume-delay function (β = 4 fixed) — R2 = {r2:.3f}")
    a.legend()
    fig2.tight_layout()
    p2 = os.path.join(out_dir, "i25_bpr_fit.png")
    fig2.savefig(p2, dpi=140)

    # all VDF families over the same observations (colors match the
    # Chapter 3 VDF explorer)
    VDF_COLS = {"BPR (1964)": "#2c5378", "Akçelik (HCM 2000)": "#a4161a",
                "Combined link+node": "#b45309", "Conical (Spiess 1990)": "#0e7c86",
                "Generalized cost": "#4f3f5c", "Logit VDF": "#8c3a4c"}
    fig3, a = plt.subplots(figsize=(10, 6.5))
    a.scatter(unc["xc"], unc["ratio"], s=18, alpha=0.5, color="#7d8da0",
              edgecolors="none", label="uncongested hours")
    a.scatter(con["xc"], con["ratio"], s=18, alpha=0.35, color="#d9a0a3",
              edgecolors="none", label="congested hours (x = throughput)")
    xg2 = np.linspace(0.01, max(1.4, df["xc"].max()), 300)
    for name, (fn, popt, fr2, capwall) in fitted.items():
        note = ", fit on v/c≤1" if capwall else ""
        a.plot(xg2, fn(xg2, *popt), color=VDF_COLS.get(name, "#333"), lw=2.2,
               label=f"{name}  (R2={fr2:.2f}{note})")
    a.axvline(1.0, color=GRAY, ls=":", lw=1)
    a.set_xlabel("v/c ratio (demand-based)"); a.set_ylabel("t / t0 (travel-time ratio)")
    a.set_ylim(0.9, min(5.5, float(np.nanmax(df["ratio"])) + 0.3))
    a.set_title(f"All VDF families fitted to I-25 NB (all hours) — {sub}")
    a.legend(fontsize=8)
    fig3.tight_layout()
    p3 = os.path.join(out_dir, "i25_vdf_all_fits.png")
    fig3.savefig(p3, dpi=140)

    # compiled observations as a JS array, ready to embed in the Chapter 3
    # VDF explorer. x = observed throughput v/c, r = t/t0, c = congested flag
    # (demand during congestion is unobservable from a single station).
    pts = ",".join(
        f"[{r.xc:.3f},{r.ratio:.3f},{1 if r.congested else 0}]"
        for r in df.sort_values(["xc"]).itertuples()
    )
    js = (f"// I-25 NB, CDOT station 000501, {len(df)} hourly obs, "
          f"cap={cap:.0f} veh/hr, ffs={ffs:.1f} mph  [v/c, t/t0, congested] "
          f"(congested at throughput v/c — demand unobservable)\n"
          f"const I25_OBS=[{pts}];\n")
    pjs = os.path.join(out_dir, "i25_points.js")
    with open(pjs, "w", encoding="utf-8") as f:
        f.write(js)

    # raw (flow, speed) pairs for the Chapter X fundamental-diagram page
    # (density follows as k = q/u)
    qu = ",".join(
        f"[{r.volume:.0f},{r.speed:.1f},{1 if r.congested else 0}]"
        for r in df.sort_values(["volume"]).itertuples()
    )
    js2 = (f"// I-25 NB, CDOT station 000501, {len(df)} hourly obs, Aug 2026  "
           f"[flow veh/hr, speed mph, congested]\n"
           f"const I25_QU=[{qu}];\n")
    pjs2 = os.path.join(out_dir, "i25_qu.js")
    with open(pjs2, "w", encoding="utf-8") as f:
        f.write(js2)

    print(f"\n  plots saved:\n    {p1}\n    {p2}\n    {p3}\n  JS points:\n    {pjs}")


if __name__ == "__main__":
    main()
