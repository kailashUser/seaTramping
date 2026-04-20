"""Replace canvas ZONE 2 block with Plotly dark-map version in app.py."""

NEW_BLOCK = '''\
        # ═══════════════════════════════════════════════════════════════
        # ZONE 2 — Dark maritime map (Plotly scattermapbox, carto-darkmatter)
        # ═══════════════════════════════════════════════════════════════

        import json as _json2

        voyage_data_vj = []
        for leg in legs_list_vj:
            op   = leg.get('origin_port', '')
            dp   = leg.get('dest_port', '')
            pl   = leg.get('profit_loss', leg.get('profit', 0))

            # Laden route — real sea routes with geodesic fallback
            lats2, lons2 = _get_sea_route_lats_lons_vj(op, dp, port_coords_vj)

            # Ballast route
            _bp = leg.get('ballast_from_port', '')
            _get_ballast_lats, _get_ballast_lons = [], []
            if _bp and _bp != op and _bp in port_coords_vj and op in port_coords_vj:
                _get_ballast_lats, _get_ballast_lons = _get_sea_route_lats_lons_vj(
                    _bp, op, port_coords_vj
                )

            voyage_data_vj.append({
                'from':         op,
                'to':           dp,
                'comm':         leg.get('commodity', ''),
                'pl':           round(pl),
                'days':         round(leg.get('total_days', 0), 1),
                'nm':           _calc_nm_vj(op, dp),
                'rate':         round(leg.get('freight_rate', 0), 2),
                'cargo':        round(leg.get('cargo_mt', 0)),
                'cum':          round(leg.get('cum_profit', 0)),
                'lats':         lats2,
                'lons':         lons2,
                'ballast_from': _bp,
                'ballast_lats': _get_ballast_lats,
                'ballast_lons': _get_ballast_lons,
                'ballast_days': round(leg.get('ballast_days', 0), 1),
                'laden_days':   round(leg.get('laden_days', 0), 1),
                'olat': port_coords_vj[op][0] if op in port_coords_vj else 0,
                'olon': port_coords_vj[op][1] if op in port_coords_vj else 0,
                'dlat': port_coords_vj[dp][0] if dp in port_coords_vj else 0,
                'dlon': port_coords_vj[dp][1] if dp in port_coords_vj else 0,
            })

        all_ports_vj2 = [
            {'name': p,
             'lat':  port_coords_vj[p][0],
             'lon':  port_coords_vj[p][1]}
            for p in (set(l.get('origin_port', '') for l in legs_list_vj)
                      | set(l.get('dest_port', '') for l in legs_list_vj))
            if p and p in port_coords_vj
        ]
        if all_ports_vj2:
            _clat2 = sum(p['lat'] for p in all_ports_vj2) / len(all_ports_vj2)
            _clon2 = sum(p['lon'] for p in all_ports_vj2) / len(all_ports_vj2)
        else:
            _clat2, _clon2 = 8.0, 108.0

        voyage_json2 = _json2.dumps(voyage_data_vj)
        ports_json2  = _json2.dumps(all_ports_vj2)
        centre_json2 = _json2.dumps({'lat': _clat2, 'lon': _clon2})

        # ── Dark Plotly scattermapbox map ─────────────────────────────
        MARITIME_HTML = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#0a1628; font-family:-apple-system,sans-serif; }}
#map {{ width:100%; height:480px; border-radius:10px; overflow:hidden; }}
.controls {{ display:flex; align-items:center; gap:8px; margin:8px 0 4px; flex-wrap:wrap; }}
.btn {{ background:#1a3a5c; color:white; border:none; padding:7px 16px;
        border-radius:8px; font-size:12px; cursor:pointer; min-width:80px; }}
.btn:hover {{ background:#2d5986; }}
.btn-sec {{ background:#0f172a; color:#94a3b8; border:1px solid #334155;
             padding:7px 14px; border-radius:8px; font-size:12px; cursor:pointer; }}
.btn-sec:hover {{ background:#1e293b; }}
select {{ padding:6px 10px; border-radius:8px; border:1px solid #334155;
          font-size:12px; background:#1e293b; color:#e2e8f0; cursor:pointer; }}
.badge {{ background:#1e293b; color:#7dd3fc; padding:6px 12px; border-radius:8px;
          font-size:12px; font-weight:500; border:1px solid #334155; white-space:nowrap; }}
.stats {{ display:grid; grid-template-columns:repeat(7,1fr); gap:5px; margin-top:4px; }}
.stat {{ background:#1e293b; border-radius:8px; padding:6px 10px; border:1px solid #334155; }}
.stat-lbl {{ font-size:9px; color:#64748b; text-transform:uppercase; letter-spacing:.05em; }}
.stat-val {{ font-size:12px; font-weight:500; color:#e2e8f0; margin-top:2px;
             white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
</style>
</head>
<body>
<div id="map"></div>
<div class="controls">
  <button class="btn" id="btnPlay" onclick="togglePlay()">&#9654; Play</button>
  <button class="btn-sec" onclick="resetAnim()">&#8635; Reset</button>
  <select id="spdSel" onchange="setSpd(this.value)">
    <option value="120">Slow</option>
    <option value="60" selected>Normal</option>
    <option value="30">Fast</option>
    <option value="15">Very Fast</option>
  </select>
  <input type="range" id="scrub" min="0" max="100" value="0" step="1"
         style="flex:1;min-width:80px;accent-color:#3b82f6">
  <span class="badge" id="voyBadge">V 1 / —</span>
</div>
<div class="stats">
  <div class="stat"><div class="stat-lbl">Route</div>
    <div class="stat-val" id="sRoute">—</div></div>
  <div class="stat"><div class="stat-lbl">Phase</div>
    <div class="stat-val" id="sPhase">—</div></div>
  <div class="stat"><div class="stat-lbl">Commodity</div>
    <div class="stat-val" id="sComm">—</div></div>
  <div class="stat"><div class="stat-lbl">Distance</div>
    <div class="stat-val" id="sNm">—</div></div>
  <div class="stat"><div class="stat-lbl">Voyage P&amp;L</div>
    <div class="stat-val" id="sPl">—</div></div>
  <div class="stat"><div class="stat-lbl">Cumulative</div>
    <div class="stat-val" id="sCum">$0</div></div>
  <div class="stat"><div class="stat-lbl">Days elapsed</div>
    <div class="stat-val" id="sDays">0 d</div></div>
</div>
<script src="https://cdn.jsdelivr.net/npm/plotly.js-dist@2.26.0/plotly.min.js"></script>
<script>
const VOYAGES   = {voyage_json2};
const ALL_PORTS = {ports_json2};
const CENTRE    = {centre_json2};

const traces = [];

// 1. Background port dots
traces.push({{
  type:'scattermapbox',
  lat: ALL_PORTS.map(p => p.lat),
  lon: ALL_PORTS.map(p => p.lon),
  mode:'markers',
  marker:{{size:5, color:'#64748b', opacity:0.5}},
  hoverinfo:'skip', showlegend:false, name:'bg_ports'
}});

// 2. Background voyage arcs (ballast grey + laden coloured)
VOYAGES.forEach((v, vi) => {{
  if (v.ballast_lats && v.ballast_lats.length > 1) {{
    traces.push({{
      type:'scattermapbox',
      lat: v.ballast_lats, lon: v.ballast_lons, mode:'lines',
      line:{{width:1.5, color:'rgba(148,163,184,0.25)'}},
      opacity:1, hoverinfo:'skip', showlegend:false, name:'ballast_'+vi
    }});
  }}
  if (!v.lats.length) return;
  const col = v.pl >= 0 ? '#22c55e' : '#ef4444';
  traces.push({{
    type:'scattermapbox',
    lat: v.lats, lon: v.lons, mode:'lines',
    line:{{width:2, color:col}}, opacity:0.22,
    hoverinfo:'skip', showlegend:false, name:'arc_'+vi
  }});
}});

// 3. Port markers
const portCoords = {{}};
ALL_PORTS.forEach(p => {{ portCoords[p.name] = {{lat:p.lat, lon:p.lon}}; }});
const portsSeen = {{}};
VOYAGES.forEach(v => {{
  if (!portsSeen[v.from]) portsSeen[v.from] = 'load';
  if (!portsSeen[v.to])   portsSeen[v.to]   = 'disch';
}});
const loadNames  = Object.keys(portsSeen).filter(n => portsSeen[n]==='load'  && portCoords[n]);
const dischNames = Object.keys(portsSeen).filter(n => portsSeen[n]==='disch' && portCoords[n]);

traces.push({{
  type:'scattermapbox',
  lat: loadNames.map(n => portCoords[n].lat),
  lon: loadNames.map(n => portCoords[n].lon),
  mode:'markers+text', text: loadNames,
  marker:{{size:9, color:'#3b82f6', opacity:0.85}},
  textposition:'top right', textfont:{{size:9, color:'#cbd5e1'}},
  hoverinfo:'text', showlegend:false, name:'load_ports'
}});
traces.push({{
  type:'scattermapbox',
  lat: dischNames.map(n => portCoords[n].lat),
  lon: dischNames.map(n => portCoords[n].lon),
  mode:'markers+text', text: dischNames,
  marker:{{size:9, color:'#dc2626', opacity:0.85}},
  textposition:'top right', textfont:{{size:9, color:'#cbd5e1'}},
  hoverinfo:'text', showlegend:false, name:'disch_ports'
}});

// 4. Active traces (initially empty, updated by Plotly.restyle)
const ACTIVE_BALLAST_IDX = traces.length;
traces.push({{
  type:'scattermapbox', lat:[], lon:[], mode:'lines',
  line:{{width:3, color:'rgba(148,163,184,0.85)'}},
  opacity:1, hoverinfo:'skip', showlegend:false, name:'active_ballast'
}});

const ACTIVE_ARC_IDX = traces.length;
traces.push({{
  type:'scattermapbox', lat:[], lon:[], mode:'lines',
  line:{{width:5, color:'#f59e0b'}},
  opacity:1, hoverinfo:'skip', showlegend:false, name:'active_arc'
}});

// 5. Vessel marker
const VESSEL_IDX = traces.length;
traces.push({{
  type:'scattermapbox',
  lat:[CENTRE.lat], lon:[CENTRE.lon], mode:'markers',
  marker:{{size:14, color:'#f59e0b', symbol:'circle'}},
  hoverinfo:'skip', showlegend:false, name:'vessel'
}});

const layout = {{
  mapbox:{{
    style:'carto-darkmatter',
    zoom:4.2,
    center:{{lat:CENTRE.lat, lon:CENTRE.lon}}
  }},
  height:480,
  margin:{{l:0, r:0, t:0, b:0}},
  paper_bgcolor:'rgba(10,22,40,0)',
  plot_bgcolor:'rgba(10,22,40,0)',
  showlegend:false,
  hoverlabel:{{bgcolor:'#1e293b', bordercolor:'#334155',
               font:{{size:12, color:'#e2e8f0'}}}},
}};

Plotly.newPlot('map', traces, layout, {{
  responsive:true, displayModeBar:false, scrollZoom:true
}});

// Animation state
let playing=false, spd=60, curV=0, t=0, cumDays=0;
let phase='ballast';
let lastTs=null, raf=null;

function setSpd(v) {{ spd=parseInt(v); }}

function togglePlay() {{
  playing=!playing;
  document.getElementById('btnPlay').textContent = playing ? '&#9646;&#9646; Pause' : '&#9654; Play';
  if (playing && !raf) {{ lastTs=null; raf=requestAnimationFrame(tick); }}
}}

function resetAnim() {{
  playing=false;
  document.getElementById('btnPlay').textContent='&#9654; Play';
  if(raf){{ cancelAnimationFrame(raf); raf=null; }}
  curV=0; t=0; cumDays=0; phase='ballast';
  Plotly.restyle('map', {{lat:[[]], lon:[[]]}}, [ACTIVE_BALLAST_IDX, ACTIVE_ARC_IDX]);
  Plotly.restyle('map', {{lat:[[CENTRE.lat]], lon:[[CENTRE.lon]]}}, [VESSEL_IDX]);
  document.getElementById('scrub').value=0;
  updateHUD();
}}

function tick(ts) {{
  if(!lastTs) lastTs=ts;
  const dt=(ts-lastTs)/1000; lastTs=ts;
  if(playing) advance(dt);
  updateHUD();
  if(playing) raf=requestAnimationFrame(tick);
  else raf=null;
}}

function advance(dt) {{
  const v=VOYAGES[curV]; if(!v) return;
  const hasBallast = v.ballast_lats && v.ballast_lats.length > 1;
  const phaseDays  = phase==='ballast' ? Math.max(v.ballast_days||0, 0.3)
                                        : Math.max(v.laden_days || v.days || 1, 0.3);
  t += (dt * 1000) / (spd * phaseDays);
  cumDays += dt * phaseDays / phaseDays;  // increment by actual dt

  if (t >= 1) {{
    t = 0;
    if (phase==='ballast' && hasBallast) {{
      phase = 'laden';
    }} else {{
      curV++;
      phase = 'ballast';
      if (curV >= VOYAGES.length) {{
        curV=VOYAGES.length-1; t=1; playing=false;
        document.getElementById('btnPlay').textContent='&#9654; Play';
        if(raf){{ cancelAnimationFrame(raf); raf=null; }}
      }}
    }}
  }}

  const progress = Math.min(t, 1);
  const v2 = VOYAGES[curV]; if(!v2) return;
  const isBallastPhase = (phase==='ballast');

  // Update active ballast trace
  if (v2.ballast_lats && v2.ballast_lats.length > 1 && isBallastPhase) {{
    const end = Math.floor(progress * v2.ballast_lats.length);
    Plotly.restyle('map', {{
      lat: [v2.ballast_lats.slice(0, end+1)],
      lon: [v2.ballast_lons.slice(0, end+1)]
    }}, [ACTIVE_BALLAST_IDX]);
  }} else {{
    Plotly.restyle('map', {{lat:[[]], lon:[[]]}}, [ACTIVE_BALLAST_IDX]);
  }}

  // Update active laden trace
  if (!isBallastPhase && v2.lats.length) {{
    const end = Math.floor(progress * v2.lats.length);
    Plotly.restyle('map', {{
      lat: [v2.lats.slice(0, end+1)],
      lon: [v2.lons.slice(0, end+1)]
    }}, [ACTIVE_ARC_IDX]);
  }} else {{
    Plotly.restyle('map', {{lat:[[]], lon:[[]]}}, [ACTIVE_ARC_IDX]);
  }}

  // Update vessel position
  const arcLat = isBallastPhase ? v2.ballast_lats : v2.lats;
  const arcLon = isBallastPhase ? v2.ballast_lons : v2.lons;
  if (arcLat && arcLat.length) {{
    const idx = Math.min(Math.floor(progress * arcLat.length), arcLat.length-1);
    Plotly.restyle('map', {{lat:[[arcLat[idx]]], lon:[[arcLon[idx]]]}}, [VESSEL_IDX]);
  }}

  // Scrub bar
  const overall = (curV + (isBallastPhase ? 0 : 0.5) + progress*0.5) / VOYAGES.length;
  document.getElementById('scrub').value = Math.round(overall*100);
}}

function updateHUD() {{
  const v = VOYAGES[curV] || VOYAGES[VOYAGES.length-1];
  const cumPl = VOYAGES.slice(0, curV).reduce((s,x) => s+x.pl, 0);
  const isBallastPhase = (phase==='ballast');

  document.getElementById('sRoute').textContent =
    v.from.split(' ')[0] + ' \u2192 ' + v.to.split(' ')[0];

  const phaseEl = document.getElementById('sPhase');
  phaseEl.textContent = isBallastPhase ? '\u25a1 Ballast' : '\u25a6 Laden';
  phaseEl.style.color = isBallastPhase ? '#94a3b8' : '#4ade80';

  document.getElementById('sComm').textContent = v.comm || '—';
  document.getElementById('sNm').textContent   = (v.nm||0).toLocaleString() + ' NM';
  document.getElementById('sPl').textContent   = (v.pl>=0?'+':'') + '$' + (v.pl||0).toLocaleString();
  document.getElementById('sCum').textContent  = (cumPl>=0?'+':'') + '$' + cumPl.toLocaleString();
  document.getElementById('sDays').textContent = Math.round(cumDays) + ' d';
  document.getElementById('voyBadge').textContent = 'V ' + (curV+1) + ' / ' + VOYAGES.length;
}}

// Scrub bar manual seek
document.getElementById('scrub').addEventListener('input', function(e) {{
  if(playing){{ playing=false; document.getElementById('btnPlay').textContent='&#9654; Play';
                if(raf){{ cancelAnimationFrame(raf); raf=null; }} }}
  const pct = parseInt(e.target.value) / 100;
  curV  = Math.min(Math.floor(pct * VOYAGES.length), VOYAGES.length-1);
  t=0; phase='ballast'; cumDays=0;
  Plotly.restyle('map', {{lat:[[]], lon:[[]]}}, [ACTIVE_BALLAST_IDX, ACTIVE_ARC_IDX]);
  updateHUD();
}});

updateHUD();
</script>
</body>
</html>"""
'''

with open('app.py', encoding='utf-8') as f:
    lines = f.readlines()

total = len(lines)
print(f'Total lines before: {total}')

# Find the boundaries
start_line = None
end_line   = None
for i, l in enumerate(lines, 1):
    if '# ZONE 2' in l and 'Maritime canvas' in l and start_line is None:
        start_line = i
    if '</html>"""' in l and start_line is not None and end_line is None:
        end_line = i

print(f'Replacing lines {start_line} to {end_line}')

before = ''.join(lines[:start_line - 1])
after  = ''.join(lines[end_line:])
new_content = before + NEW_BLOCK + '\n' + after

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

with open('app.py', encoding='utf-8') as f:
    new_lines = f.readlines()
print(f'Total lines after:  {len(new_lines)}')
print('Done.')
