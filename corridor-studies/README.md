# Corridor Study Dashboard

A generic, multi-corridor version of the 72nd Avenue dashboard. One `index.html`
engine + one small JS config file per corridor. A dropdown in the sidebar header
switches corridors. **No API keys anywhere** (OpenStreetMap + Esri tiles).

Works straight from `file://` — no web server needed (configs are plain `<script>`
files, not fetched JSON).

## Adding a corridor

1. Create `corridors/<your-corridor>.js` that calls `window.registerCorridor({...})`
   (copy `arvada-72nd.js` as a template).
2. Add the filename to `corridors/manifest.js`.

That's it. Every data block is **optional** — leave out what you don't have and
that layer's row shows a "No data" badge with its toggle disabled.

## Config schema

```js
window.registerCorridor({
  id:     'my-corridor',            // unique, used in the URL hash
  name:   '72nd Avenue',
  agency: 'City of Arvada',
  center: [39.8272, -105.1188],     // [lat, lon]
  zoom:   15,

  // Direction slots — works for EB/WB or NB/SB corridors. The `key` is the
  // suffix used in all per-direction data properties (ADT_EAST, speed_NORTH, …)
  dirs: [
    { key:'EAST', label:'Eastbound', short:'EB', arrow:'▶' },
    { key:'WEST', label:'Westbound', short:'WB', arrow:'◀' }
  ],

  // ── StreetLight (optional) ──
  streetlight: {
    ranges: { adt:[0,15000], speed:[20,50], tti:[0,2] },   // legend/color ranges
    geojson: { /* FeatureCollection of LineStrings. Per-feature properties:
      name, length_mi, Total_ADT, and per direction key K:
      ADT_K, speed_K, freeflow_K, tti_K, p85spd_K, congested_K,
      hourly: { K: [ {h:'7am-8am', v:volume, s:speed}, … ] } */ },
    hourly: { /* corridor-wide profile: { K: [ {h, v, s}, … ] } */ }
  },

  // ── INRIX (optional) — segments colored by speed / free-flow ratio ──
  inrix: {
    geojson: { /* FeatureCollection of LineStrings. Properties:
      name, and per direction key K: speed_K, freeflow_K */ }
  },

  // ── Replica (optional) — floating panel with mode share + top O-D pairs ──
  replica: {
    note: 'Replica Fall 2025 — typical weekday',
    modeShare: { labels:['Drive','Carpool','Transit','Walk','Bike'], values:[72,11,6,8,3] },
    odPairs: [ { name:'Olde Town → Denver CBD', trips: 3400 }, … ]
  },

  // ── Count station / TCDS (optional) ──
  tcds: {
    station: { id:'203149', label:'72nd Ave E/O Oak St', lat:39.82717, lon:-105.1175 },
    aadt:  { years:['2011', …], aadt:[15483, …], growth:[0, …] },
    dates: ['2025-04-15', …],
    // per-date hourly arrays keyed by the LOWERCASE dir short name (eb/wb or nb/sb)
    hourly: { '2025-04-15': { hours:[0,…,23], eb:[…], wb:[…] }, … }
  },

  // ── Safety (optional) ──
  crashes: [ { id, lat, lon, severity:0-3, sev_label, location, year, ped:bool, bike:bool }, … ],

  // ── Equity (optional) ──
  equity: { note:'Equity Index Score (DRCOG 2023)', min:13, max:19,
            geojson:{ /* polygons with properties NAME, index_score, index_q,
                         population, pct_poc, pct_low_income */ } },

  // ── Transit stops (optional) ──
  transit: { label:'RTD Bus Stops',
             stops:[ { id, name, lat, lon, routes, direction:'N'|'S'|'E'|'W' }, … ] },

  // ── Schools (optional) ──
  schools: [ { name, lat, lon, type:'High School'|'Middle School'|'Elementary'|'Charter School' }, … ],

  // ── Population & employment forecast (optional) ──
  taz: { note:'8 TAZs near corridor — DRCOG 2025',
         years:[2023,2030,2040,2050], hh:[…], pop:[…], emp:[…] },

  // ── Complete Streets (optional) ──
  completeStreets: {
    banner:   [ { name:'72nd Ave', score:'6', label:'Regional Connector' }, … ],
    overview: [ { title:'Congestion Mobility — 2021', rows:[ ['Segment','Seg0147'], … ] }, … ]
  }
});
```

## Notes

- The original single-corridor page (`../72nd_corridor_map.html`) is untouched;
  `corridors/arvada-72nd.js` holds the same data in the generic schema.
- Corridor choice persists in the URL hash (`index.html#arvada-72nd`), so a link
  can point a reviewer at a specific corridor.
- Raw data exports (StreetLight/INRIX/Replica CSVs, crash records, …) should NOT
  be committed if they are license-restricted — keep them in a git-ignored folder
  and commit only the processed config file, same as the existing `data/` policy.
