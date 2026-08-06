/**
 * Voyage HUD, drawn with Canvas 2D.
 *
 * The overlay has to live in a canvas rather than the DOM: both toDataURL and
 * MediaRecorder capture canvas pixels only, so a DOM overlay is invisible to
 * every recording path. Drawing it here means the live view, the QA frames and
 * the exported video are the same pixels by construction.
 *
 * Everything is laid out against a 1280x720 design and scaled by height, so it
 * holds up at 720p or 4K.
 */

const FONT = "'Segoe UI',system-ui,sans-serif";

const STATUS = {
  laden:     { label: 'LADEN PASSAGE', bg: '#065f46', fg: '#6ee7b7' },
  ballast:   { label: 'BALLAST',       bg: '#78350f', fg: '#fcd34d' },
  load:      { label: 'LOADING',       bg: '#1e3a8a', fg: '#93c5fd' },
  discharge: { label: 'DISCHARGING',   bg: '#581c87', fg: '#d8b4fe' },
};

const money = n =>
  (n < 0 ? '-$' : '$') + Math.abs(Math.round(n)).toLocaleString('en-US');

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function shadowed(ctx, fn) {
  ctx.save();
  ctx.shadowColor = 'rgba(0,0,0,.85)';
  ctx.shadowBlur = 7;
  ctx.shadowOffsetY = 1;
  fn();
  ctx.restore();
}

/**
 * @param ctx  2D context of the output canvas
 * @param o    { w, h, meta, day, totalDays, state, voyage, prevCum,
 *               startDate, minimap }
 */
export function drawHUD(ctx, o) {
  const { w, h, meta, day, totalDays, state, voyage } = o;
  const s = h / 720;
  const P = 28 * s;

  ctx.textBaseline = 'alphabetic';

  // ── top scrim ────────────────────────────────────────────────────────────
  const grad = ctx.createLinearGradient(0, 0, 0, 130 * s);
  grad.addColorStop(0, 'rgba(2,8,16,.86)');
  grad.addColorStop(1, 'rgba(2,8,16,0)');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, w, 130 * s);

  // ── vessel identity ──────────────────────────────────────────────────────
  shadowed(ctx, () => {
    ctx.fillStyle = '#e8eef6';
    ctx.font = `700 ${22 * s}px ${FONT}`;
    ctx.fillText(meta.vessel_name || 'VESSEL', P, P + 18 * s);

    ctx.fillStyle = '#8aa2bd';
    ctx.font = `${12 * s}px ${FONT}`;
    const sub = [
      meta.vessel_imo && 'IMO ' + meta.vessel_imo,
      meta.dwt && Math.round(meta.dwt).toLocaleString('en-US') + ' DWT',
      o.hull,
      meta.flag,
    ].filter(Boolean).join('   ·   ');
    ctx.fillText(sub, P, P + 36 * s);
  });

  // ── clock, top right ─────────────────────────────────────────────────────
  shadowed(ctx, () => {
    // Measure the suffix first, then right-align the big number against it, so
    // the pair sits inside the margin instead of running off the edge.
    const dayTxt = String(Math.floor(day));
    const sufTxt = ` / ${Math.round(totalDays)} DAYS`;

    ctx.font = `${14 * s}px ${FONT}`;
    const sufW = ctx.measureText(sufTxt).width;

    ctx.textAlign = 'right';
    ctx.fillStyle = '#8aa2bd';
    ctx.fillText(sufTxt, w - P, P + 30 * s);

    ctx.fillStyle = '#e8eef6';
    ctx.font = `200 ${40 * s}px ${FONT}`;
    ctx.fillText(dayTxt, w - P - sufW, P + 30 * s);

    ctx.fillStyle = '#8aa2bd';
    ctx.font = `${12 * s}px ${FONT}`;
    const d = new Date(o.startDate.getTime() + day * 86400000);
    ctx.fillText(d.toUTCString().slice(5, 16).toUpperCase(), w - P, P + 50 * s);
  });
  ctx.textAlign = 'left';

  // ── status pill + leg, bottom left ───────────────────────────────────────
  const st = STATUS[state.status] || { label: state.status.toUpperCase(), bg: '#334155', fg: '#cbd5e1' };
  const pillY = h - P - 74 * s;

  ctx.font = `700 ${11 * s}px ${FONT}`;
  const pillW = ctx.measureText(st.label).width + 26 * s;
  ctx.fillStyle = st.bg;
  roundRect(ctx, P, pillY, pillW, 22 * s, 11 * s);
  ctx.fill();
  ctx.fillStyle = st.fg;
  ctx.fillText(st.label, P + 13 * s, pillY + 15 * s);

  const seg = state.seg;
  const route = seg.type === 'port' ? seg.port : `${seg.from}  →  ${seg.to}`;
  let detail;
  if (seg.type === 'port') {
    detail = `${seg.mode === 'load' ? 'Loading' : 'Discharging'} `
           + `${Math.round(seg.cargo_mt).toLocaleString('en-US')} MT ${seg.commodity}`;
  } else if (state.status === 'laden') {
    detail = `${Math.round(voyage.cargo_mt).toLocaleString('en-US')} MT ${voyage.commodity}`
           + `   ·   ${Math.round(seg.nm).toLocaleString('en-US')} nm`;
  } else {
    detail = `Ballast   ·   ${Math.round(seg.nm).toLocaleString('en-US')} nm to load port`;
  }

  shadowed(ctx, () => {
    ctx.fillStyle = '#f1f6fb';
    ctx.font = `600 ${26 * s}px ${FONT}`;
    ctx.fillText(route, P, h - P - 26 * s);
    ctx.fillStyle = '#9fb4cc';
    ctx.font = `${13 * s}px ${FONT}`;
    ctx.fillText(detail, P, h - P - 6 * s);
  });

  // ── P&L, bottom right ────────────────────────────────────────────────────
  shadowed(ctx, () => {
    ctx.textAlign = 'right';
    ctx.fillStyle = '#e8eef6';
    ctx.font = `300 ${32 * s}px ${FONT}`;
    ctx.fillText(money(o.cumProfit), w - P, h - P - 30 * s);

    ctx.fillStyle = '#8aa2bd';
    ctx.font = `${11 * s}px ${FONT}`;
    ctx.fillText('CUMULATIVE P&L', w - P, h - P - 14 * s);
    ctx.font = `${12 * s}px ${FONT}`;
    ctx.fillText(`VOYAGE ${voyage.voyage_num} OF ${o.nVoyages}   ·   ${voyage.commodity}`,
                 w - P, h - P + 4 * s);
    ctx.textAlign = 'left';
  });

  // ── progress bar ─────────────────────────────────────────────────────────
  ctx.fillStyle = 'rgba(255,255,255,.10)';
  ctx.fillRect(0, h - 3 * s, w, 3 * s);
  const g2 = ctx.createLinearGradient(0, 0, w, 0);
  g2.addColorStop(0, '#0ea5e9');
  g2.addColorStop(1, '#22d3ee');
  ctx.fillStyle = g2;
  ctx.fillRect(0, h - 3 * s, w * (day / totalDays), 3 * s);
}

/**
 * Route overview inset. Draws directly into the output canvas so it is part of
 * the recorded frame.
 */
export function drawMinimap(ctx, o) {
  const { w, h, segs, ports, day, proj, vessel } = o;
  const s = h / 720;
  const MW = 230 * s, MH = 190 * s, MX = 28 * s, MY = 96 * s;

  ctx.save();
  ctx.fillStyle = 'rgba(3,10,20,.62)';
  roundRect(ctx, MX, MY, MW, MH, 7 * s);
  ctx.fill();
  ctx.strokeStyle = 'rgba(255,255,255,.13)';
  ctx.lineWidth = 1;
  ctx.stroke();
  ctx.clip();

  // fit all route geometry into the inset
  let x0 = Infinity, x1 = -Infinity, z0 = Infinity, z1 = -Infinity;
  for (const sg of segs) {
    if (!sg.path) continue;
    for (const [lo, la] of sg.path) {
      const X = proj.x(lo), Z = proj.z(la);
      if (X < x0) x0 = X; if (X > x1) x1 = X;
      if (Z < z0) z0 = Z; if (Z > z1) z1 = Z;
    }
  }
  const pad = 14 * s;
  const k = Math.min((MW - pad * 2) / (x1 - x0), (MH - pad * 2) / (z1 - z0));
  const ox = MX + (MW - (x1 - x0) * k) / 2, oz = MY + (MH - (z1 - z0) * k) / 2;
  const tx = X => ox + (X - x0) * k, tz = Z => oz + (Z - z0) * k;

  ctx.lineWidth = 1.4 * s;
  for (const sg of segs) {
    if (!sg.path) continue;
    const done = day >= sg.end_day, active = day >= sg.start_day && day <= sg.end_day;
    ctx.strokeStyle = active ? '#38bdf8'
      : done ? (sg.type === 'laden' ? 'rgba(16,185,129,.8)' : 'rgba(245,158,11,.65)')
             : 'rgba(255,255,255,.10)';
    ctx.beginPath();
    sg.path.forEach(([lo, la], i) => {
      const X = tx(proj.x(lo)), Z = tz(proj.z(la));
      i ? ctx.lineTo(X, Z) : ctx.moveTo(X, Z);
    });
    ctx.stroke();
  }

  ctx.fillStyle = '#64748b';
  for (const p of Object.values(ports)) {
    ctx.fillRect(tx(proj.x(p.lon)) - 1.4 * s, tz(proj.z(p.lat)) - 1.4 * s, 2.8 * s, 2.8 * s);
  }

  const VX = tx(proj.x(vessel.lon)), VZ = tz(proj.z(vessel.lat));
  ctx.fillStyle = '#f8fafc';
  ctx.beginPath(); ctx.arc(VX, VZ, 4 * s, 0, 7); ctx.fill();
  ctx.strokeStyle = 'rgba(56,189,248,.9)';
  ctx.lineWidth = 1.8 * s;
  ctx.beginPath(); ctx.arc(VX, VZ, 8.5 * s, 0, 7); ctx.stroke();

  ctx.restore();
}
