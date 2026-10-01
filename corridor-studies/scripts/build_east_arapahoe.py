"""Rebuild corridors/east-arapahoe.js from the raw exports in "corridor data/".

Inputs (git-ignored), under "corridor data/East Arapahoe Rd/":
    TMC_Identification.csv                      INRIX TMC geometry + lengths
    East-Arapahoe-Road.csv                      INRIX 5-min speeds per TMC
    2087472_Arapahoe_Road/                      StreetLight Corridor Study export
        2087472_Arapahoe_Road_corridor_study.csv
        Shapefile/2087472_Arapahoe_Road_osm_segment.zip
    ../Statewide Crash Data/*.xlsx              CDOT statewide crash listings

Output (committed):
    corridors/east-arapahoe.js

StreetLight: 160 directional OSM segments (geometry from the export shapefile,
parsed with a minimal stdlib reader) with All-Days ADT / speed / free-flow /
TTI / 85th pct / congested flag plus hourly volume+speed profiles.
INRIX: per-TMC day-average speed + reference (free-flow) speed on straight
start->end chords. Crashes: statewide listings buffer-filtered to the
corridor (see filter_crashes_to_corridor.py; default 250 ft).

Run from anywhere:
    python corridor-studies/scripts/build_east_arapahoe.py [--buffer-ft 250]
"""
import argparse, csv, json, os, re, struct, zipfile
from collections import defaultdict

from filter_crashes_to_corridor import filter_crashes

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "corridor data", "East Arapahoe Rd")
CRASH_DIR = os.path.join(HERE, "..", "corridor data", "Statewide Crash Data")
STL = os.path.join(DATA, "2087472_Arapahoe_Road")
OUT = os.path.join(HERE, "..", "corridors", "east-arapahoe.js")

ap = argparse.ArgumentParser()
ap.add_argument("--buffer-ft", type=float, default=250.0)
a = ap.parse_args()


# ── minimal shapefile reader (polylines + dbf), stdlib only ───────────
def read_shapefile_zip(zip_path):
    """Returns [(record_attrs_dict, [[lon,lat], ...]), ...] from a zipped shapefile."""
    zp = zipfile.ZipFile(zip_path)
    shp = zp.read([n for n in zp.namelist() if n.endswith(".shp")][0])
    dbf = zp.read([n for n in zp.namelist() if n.endswith(".dbf")][0])
    # dbf: header -> field descriptors -> fixed-width records
    nrec = struct.unpack("<I", dbf[4:8])[0]
    hsz, rsz = struct.unpack("<HH", dbf[8:12])
    fields, p = [], 32
    while dbf[p] != 0x0D:
        name = dbf[p:p + 11].split(b"\x00")[0].decode()
        fields.append((name, dbf[p + 16]))
        p += 32
    attrs = []
    for i in range(nrec):
        rec = dbf[hsz + i * rsz: hsz + (i + 1) * rsz][1:]  # skip deletion flag
        row, off = {}, 0
        for name, flen in fields:
            row[name] = rec[off:off + flen].decode("latin-1").strip()
            off += flen
        attrs.append(row)
    # shp: 100-byte header, then records (big-endian header, little-endian content)
    lines, p = [], 100
    while p < len(shp):
        clen = struct.unpack(">I", shp[p + 4:p + 8])[0] * 2
        body = shp[p + 8: p + 8 + clen]
        p += 8 + clen
        shape_type = struct.unpack("<i", body[0:4])[0]
        if shape_type in (3, 13):          # PolyLine / PolyLineZ
            n_parts, n_pts = struct.unpack("<ii", body[36:44])
            pts_off = 44 + 4 * n_parts
            pts = [list(struct.unpack("<dd", body[pts_off + 16 * k: pts_off + 16 * k + 16]))
                   for k in range(n_pts)]
            lines.append([[round(x, 6), round(y, 6)] for x, y in pts])
        else:
            lines.append([])
    return list(zip(attrs, lines))


# ── StreetLight corridor study -> directional segment features ────────
HOURLY_RE = re.compile(r"^\d+: \d+(?:am|pm) \((.+)\)$")   # hourly parts only
stl_geom = {r["segment_id"]: line
            for r, line in read_shapefile_zip(
                os.path.join(STL, "Shapefile", "2087472_Arapahoe_Road_osm_segment.zip"))}

by_zone = defaultdict(dict)   # zone id -> day part -> row
zone_meta = {}
with open(os.path.join(STL, "2087472_Arapahoe_Road_corridor_study.csv"),
          newline="", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        if not r["Day Type"].startswith("0:"):
            continue
        zid = r["Zone ID"]
        by_zone[zid][r["Day Part"]] = r
        zone_meta[zid] = (r["Zone Cardinal Direction"],
                          float(r["Line Zone Length (Miles)"]))

sl_feats, hourly_acc = [], defaultdict(lambda: defaultdict(lambda: [0.0, 0.0, 0]))
max_adt = 0
for zid, parts in by_zone.items():
    card, length = zone_meta[zid]
    key = "EAST" if card == "EAST" else "WEST"
    short = "EB" if key == "EAST" else "WB"
    allday = parts.get("00: All Day (12am-12am)")
    geom = stl_geom.get(zid)
    if not allday or not geom:
        continue
    adt = round(float(allday["Average Daily Segment Traffic (StL Volume)"]))
    max_adt = max(max_adt, adt)
    hourly = []
    for dp in sorted(p for p in parts if HOURLY_RE.match(p)):
        row = parts[dp]
        label = HOURLY_RE.match(dp).group(1)
        v = round(float(row["Average Daily Segment Traffic (StL Volume)"]))
        s = float(row["Avg Segment Speed (mph)"])
        hourly.append({"h": label, "v": v, "s": s})
        acc = hourly_acc[key][dp]
        acc[0] += v; acc[1] += s * v; acc[2] += 1
    sl_feats.append({
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": geom},
        "properties": {
            "name": f"E Arapahoe Rd ({short}) · {length:.2f} mi",
            f"ADT_{key}": adt,
            f"speed_{key}": float(allday["Avg Segment Speed (mph)"]),
            f"freeflow_{key}": float(allday["Free Flow Speed (mph)"]),
            f"tti_{key}": float(allday["Travel Time Index"]),
            f"p85spd_{key}": float(allday["85th Speed Percentile"]),
            f"congested_{key}": allday["Congested Segment"].strip().lower() == "true",
            "length_mi": length,
            "hourly": {key: hourly},
        },
    })

sl_hourly = {}
for key, dps in hourly_acc.items():
    prof = []
    for dp in sorted(dps):
        v_sum, sv_sum, n = dps[dp]
        prof.append({"h": HOURLY_RE.match(dp).group(1),
                     "v": round(v_sum / n),
                     "s": round(sv_sum / v_sum, 1) if v_sum else 0})
    sl_hourly[key] = prof
adt_cap = (max_adt // 5000 + 1) * 5000
print(f"StreetLight: {len(sl_feats)} segments, max ADT {max_adt}, hourly dirs {list(sl_hourly)}")

# ── INRIX: per-TMC day-average + reference speed ──────────────────────
speeds, refs = defaultdict(list), defaultdict(list)
with open(os.path.join(DATA, "East-Arapahoe-Road.csv"), newline="", encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        try:
            speeds[row["tmc_code"]].append(float(row["speed"]))
            refs[row["tmc_code"]].append(float(row["reference_speed"]))
        except (KeyError, ValueError):
            continue

feats = []
with open(os.path.join(DATA, "TMC_Identification.csv"), newline="", encoding="utf-8-sig") as f:
    for t in csv.DictReader(f):
        tmc = t["tmc"]
        if tmc not in speeds:
            continue
        key = "EAST" if t["direction"] == "EASTBOUND" else "WEST"
        short = "EB" if key == "EAST" else "WB"
        feats.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [
                [float(t["start_longitude"]), float(t["start_latitude"])],
                [float(t["end_longitude"]),   float(t["end_latitude"])]]},
            "properties": {
                "name": f"Arapahoe Rd @ {t['intersection']} ({short})",
                "tmc": tmc,
                "length_mi": round(float(t["miles"]), 3),
                f"speed_{key}": round(sum(speeds[tmc]) / len(speeds[tmc]), 1),
                f"freeflow_{key}": round(sum(refs[tmc]) / len(refs[tmc]), 1),
            },
        })
print(f"INRIX: {len(feats)} TMC segments")

# ── Crashes: statewide listings -> corridor buffer ────────────────────
crashes = filter_crashes(os.path.join(DATA, "TMC_Identification.csv"),
                         CRASH_DIR, a.buffer_ft)
years = sorted({c["year"] for c in crashes})
print(f"crashes: {len(crashes)} within {a.buffer_ft:.0f} ft ({years[0]}-{years[-1]})" if crashes else "crashes: none")

# ── Emit the corridor config ──────────────────────────────────────────
gj = json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":"))
cj = json.dumps(crashes, separators=(",", ":"))
sgj = json.dumps({"type": "FeatureCollection", "features": sl_feats}, separators=(",", ":"))
shj = json.dumps(sl_hourly, separators=(",", ":"))
slash2 = "/" * 2
src = (
    f"{slash2} East Arapahoe Road (CO-88), Arapahoe County CO.\n"
    f"{slash2} GENERATED by scripts/build_east_arapahoe.py - do not edit by hand.\n"
    f"{slash2} StreetLight: Corridor Study 2087472 (Jan 2025 - Aug 2026), {len(sl_feats)} directional OSM segments.\n"
    f"{slash2} INRIX: 18 TMCs, 5-min speeds -> day mean; free-flow = INRIX reference speed.\n"
    f"{slash2} Crashes: CDOT statewide listings filtered to a {a.buffer_ft:.0f} ft corridor buffer.\n"
    f"{slash2} Raw exports live in the git-ignored 'corridor data/' folder.\n"
    "window.registerCorridor({\n"
    "  id: 'east-arapahoe',\n"
    "  name: 'East Arapahoe Road',\n"
    "  agency: 'Arapahoe County, CO',\n"
    "  center: [39.5948, -104.8447],\n"
    "  zoom: 13,\n"
    "  dirs: [\n"
    "    { key:'EAST', label:'Eastbound', short:'EB', arrow:'\\u25B6' },\n"
    "    { key:'WEST', label:'Westbound', short:'WB', arrow:'\\u25C0' }\n"
    "  ],\n"
    "  streetlight: {\n"
    f"    ranges: {{ adt:[0,{adt_cap}], adtDir:{adt_cap}, speed:[20,55], tti:[1,2] }},\n"
    f"    geojson: {sgj},\n"
    f"    hourly: {shj}\n"
    "  },\n"
    f"  inrix: {{ geojson: {gj} }},\n"
    f"  crashes: {cj}\n"
    "});\n"
)
with open(OUT, "w", encoding="utf-8") as f:
    f.write(src)
print(f"wrote {os.path.normpath(OUT)} ({os.path.getsize(OUT)/1024:.0f} KB)")
