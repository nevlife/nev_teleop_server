/* NEV Dashboard — WebSocket telemetry + REST commands */
const MODE_NAMES = {'-1':'IDLE','0':'CTRL','1':'NAV','2':'REMOTE'};
const SRC_NAMES  = {'-1':'NONE','0':'NAV','1':'TELEOP'};
const NS_CODES   = {'0':'OK','1':'HB-DELAY','2':'SOCK-ERR'};
const BRIDGE_FLAGS = {'0':'OK','1':'SRV-CMD','2':'SOCK-ERR','3':'HB-TIMEOUT','4':'CTRL-TIMEOUT'};
const MUX_FLAGS  = {'0':'OK','1':'NAV+NO-TELEOP'};

let ws = null;
let lastState = {};
let estopActive = false;

/* ── Helpers ──────────────────────────────────────────── */
function kv(k, v, color) {
  const style = color ? `color:${color}` : '';
  return `<div class="kv"><span class="k">${k}</span><span class="v" style="${style}">${v}</span></div>`;
}
function sep() { return '<div class="sep">\u2500\u2500\u2500\u2500\u2500</div>'; }
function secHdr(t) { return `<div class="section-hdr">${t}</div>`; }
function dot(on, color) {
  const cls = on ? (color === 'red' ? 'dot red' : 'dot on') : 'dot';
  return `<span class="${cls}"></span>`;
}
function sgn(v) { return (v >= 0 ? '+' : '') + v.toFixed(2); }
function fmtGb(b) { return (b / 1073741824).toFixed(1); }
function fmtRate(bps) {
  if (bps < 1024) return bps.toFixed(0) + 'B/s';
  if (bps < 1048576) return (bps/1024).toFixed(1) + 'K/s';
  return (bps/1048576).toFixed(1) + 'M/s';
}
function bar(pct) {
  const w = Math.max(0, Math.min(100, pct || 0));
  const c = w > 90 ? 'var(--red)' : w > 70 ? 'var(--yellow)' : 'var(--blue)';
  return `<div class="bar-bg"><div class="bar-fill" style="width:${w}%;background:${c}"></div></div>`;
}
function textCls(v, warn, err) {
  if (v >= err) return 'var(--red)';
  if (v >= warn) return 'var(--yellow)';
  return '';
}

/* ── Card Renderers ──────────────────────────────────── */
function renderHunter(hs) {
  const steerDeg = hs.steering_angle ? (hs.steering_angle * 180 / Math.PI).toFixed(1) : '0.0';
  const bv = hs.battery_voltage || 0;
  const batCls = bv < 20 ? 'var(--red)' : bv < 22 ? 'var(--yellow)' : 'var(--green)';
  const err = hs.error_code || 0;
  const errCls = err !== 0 ? 'var(--red)' : '';
  document.getElementById('body-hunter').innerHTML =
    kv('vel', sgn(hs.linear_vel || 0) + ' m/s') +
    kv('steer', steerDeg + ' deg') +
    kv('state', '' + (hs.robot_state || 0)) +
    kv('ctrl', '' + (hs.control_mode || 0)) +
    kv('err', err === 0 ? 'NONE' : '0x' + err.toString(16).toUpperCase(), errCls) +
    kv('bat', bv.toFixed(2) + ' V', batCls);
}

function renderMux(mx) {
  const mode = mx.requested_mode ?? -1;
  const modeCls = mode === 2 ? 'var(--blue)' : mode === -1 ? 'var(--muted)' : '';
  document.getElementById('body-mux').innerHTML =
    kv('mode', MODE_NAMES[mode] || mode, modeCls) +
    kv('src', SRC_NAMES[mx.active_source ?? -1] || '?') +
    kv('remote', dot(mx.remote_enabled) + (mx.remote_enabled ? 'YES' : 'NO')) +
    kv('nav', dot(mx.nav_active) + (mx.nav_active ? 'ON' : 'OFF')) +
    kv('teleop', dot(mx.teleop_active) + (mx.teleop_active ? 'ON' : 'OFF')) +
    kv('final', dot(mx.final_active) + (mx.final_active ? 'ON' : 'OFF'));
}

function renderNetwork(ns) {
  const connected = ns.connected || false;
  const stCls = connected ? 'var(--green)' : 'var(--red)';
  const teleD = ns.tele_delay_ms || 0;
  const rttSrvBot = ns.rtt_server_bot_ms || 0;
  const encD = ns.encode_delay || 0;
  const vidNetD = ns.video_net_delay || 0;
  document.getElementById('body-network').innerHTML =
    kv('status', dot(connected, connected ? '' : 'red') + (NS_CODES[ns.status_code] || '?'), stCls) +
    sep() + secHdr('VIDEO PIPELINE') +
    kv('encode', encD > 0 ? encD.toFixed(1) + ' ms' : '\u2014') +
    kv('veh\u2192srv', vidNetD > 0 ? vidNetD.toFixed(1) + ' ms' : '\u2014') +
    sep() + secHdr('VIDEO BANDWIDTH') +
    kv('veh tx', ns.bw_video_tx > 0 ? ns.bw_video_tx.toFixed(2) + ' Mbps' : '\u2014') +
    kv('srv rx', ns.bw_video_rx > 0 ? ns.bw_video_rx.toFixed(2) + ' Mbps' : '\u2014') +
    sep() + secHdr('TELEMETRY') +
    kv('tele rx', ns.bw_telemetry > 0 ? ns.bw_telemetry.toFixed(2) + ' Mbps' : '\u2014') +
    kv('tele delay', teleD > 0 ? teleD.toFixed(1) + ' ms' : '\u2014') +
    sep() + secHdr('RTT') +
    kv('srv\u2194bot', rttSrvBot > 0 ? rttSrvBot.toFixed(1) + ' ms' : '\u2014');
}

function renderTwist(tv) {
  function row(lx, az) { return sgn(lx) + ' m/s / ' + sgn(az) + ' rad/s'; }
  document.getElementById('body-twist').innerHTML =
    kv('nav', row(tv.nav_lx || 0, tv.nav_az || 0)) +
    kv('teleop', row(tv.teleop_lx || 0, tv.teleop_az || 0)) +
    kv('final', row(tv.final_lx || 0, tv.final_az || 0));
}

function renderEstop(es, ctrl) {
  const active = (es.is_estop || ctrl.estop) || false;
  const card = document.getElementById('card-estop');
  card.className = active ? 'card estop-active' : 'card';
  const bf = es.bridge_flag || 0;
  const mf = es.mux_flag || 0;
  document.getElementById('body-estop').innerHTML =
    kv('status', active ? '<span style="color:var(--red)">\u26A0 E-STOP ACTIVE</span>' : '<span style="color:var(--green)">NORMAL</span>') +
    kv('bridge', BRIDGE_FLAGS[bf] || bf, bf !== 0 ? 'var(--red)' : '') +
    kv('mux', MUX_FLAGS[mf] || mf, mf !== 0 ? 'var(--yellow)' : '');
  // Update E-STOP button
  estopActive = active;
  const btn = document.getElementById('estop-btn');
  btn.textContent = active ? '\u25A0 RELEASE' : '\u25A0 E-STOP';
  btn.className = active ? 'estop-btn active' : 'estop-btn';
}

function renderJoystick(ctrl, stationConnected) {
  const joyCon = ctrl.joystick_connected || false;
  const joyCls = joyCon ? 'var(--green)' : 'var(--red)';
  const staCls = stationConnected ? 'var(--green)' : 'var(--red)';
  document.getElementById('body-joystick').innerHTML =
    kv('station', dot(stationConnected) + (stationConnected ? 'CONNECTED' : 'OFFLINE'), staCls) +
    kv('joystick', dot(joyCon) + (joyCon ? 'CONNECTED' : 'DISCONNECTED'), joyCls) +
    kv('cmd', (ctrl.linear_x || 0).toFixed(3) + ' m/s / ' +
              (ctrl.steer_angle_deg || 0).toFixed(1) + ' deg / ' +
              (ctrl.angular_z || 0).toFixed(4) + ' rad/s');
}

function renderResources(r, gpuList) {
  const cpu = r.cpu_usage || 0;
  const temp = r.cpu_temp || 0;
  const load = r.cpu_load || 0;
  let html = kv('CPU',
    `<span style="color:${textCls(cpu,70,90) || 'var(--text)'}">${cpu.toFixed(1)}%</span>` +
    `&ensp;<span style="color:${textCls(temp,60,80) || 'var(--text)'}">${temp.toFixed(1)}C</span>` +
    `&ensp;load ${load.toFixed(2)}`) + bar(cpu);
  const ramUsed = r.ram_used || 0, ramTotal = r.ram_total || 0;
  const ramPct = ramTotal > 0 ? ramUsed / ramTotal * 100 : 0;
  html += kv('RAM', `${ramUsed} / ${ramTotal} MB`) + bar(ramPct);
  if (gpuList) {
    gpuList.forEach((g, i) => {
      if (!g) return;
      const usage = g.gpu_usage || 0;
      const gtemp = g.gpu_temp || 0;
      html += kv(`GPU${i}`,
        `<span style="color:${textCls(usage,70,90) || 'var(--text)'}">${usage.toFixed(1)}%</span>` +
        `&ensp;<span style="color:${textCls(gtemp,60,80) || 'var(--text)'}">${gtemp.toFixed(0)}C</span>` +
        `&ensp;${(g.gpu_power||0).toFixed(0)}W`) + bar(usage);
      html += kv('', `mem ${Math.round(g.gpu_mem_used||0)} / ${Math.round(g.gpu_mem_total||0)} MB`);
    });
  }
  document.getElementById('body-resources').innerHTML = html;
}

function renderNetifaces(ifaces, resources) {
  if (!ifaces || ifaces.length === 0) {
    document.getElementById('body-netifaces').innerHTML = '<span style="color:var(--muted)">\u2014</span>';
    return;
  }
  let html = '';
  const total = resources.net_total_ifaces || 0;
  const active = resources.net_active_ifaces || 0;
  if (total > 0) html += kv('total', `${active} up / ${total}`);
  ifaces.forEach(iface => {
    if (!iface || !iface.name) return;
    const up = iface.is_up || false;
    const upCls = up ? 'var(--green)' : 'var(--red)';
    const spd = iface.speed_mbps > 0 ? iface.speed_mbps + 'M' : '\u2014';
    html += kv(iface.name, dot(up, up?'':'red') + `<span style="color:${upCls}">${up?'UP':'DOWN'}</span>&ensp;${spd}`);
    html += kv('', `\u2193${fmtRate(iface.in_bps||0)}&ensp;\u2191${fmtRate(iface.out_bps||0)}`);
  });
  document.getElementById('body-netifaces').innerHTML = html;
}

function renderDisk(partitions) {
  if (!partitions || partitions.length === 0) {
    document.getElementById('body-disk').innerHTML = '<span style="color:var(--muted)">\u2014</span>';
    return;
  }
  let html = '';
  partitions.forEach(p => {
    if (!p || !p.mountpoint) return;
    const pct = p.percent || 0;
    const cls = textCls(pct, 70, 90);
    html += kv(p.mountpoint,
      `${fmtGb(p.used_bytes||0)} / ${fmtGb(p.total_bytes||1)} GB` +
      `  <span style="color:${cls || 'var(--text)'}">${pct.toFixed(0)}%</span>`) + bar(pct);
  });
  document.getElementById('body-disk').innerHTML = html;
}

function renderAlerts(alerts) {
  if (!alerts || alerts.length === 0) {
    document.getElementById('body-alerts').innerHTML = '<span style="color:var(--muted)">\u2014</span>';
    return;
  }
  let html = '';
  alerts.forEach(a => {
    const cls = a.level === 'error' ? 'alert-error' : a.level === 'warn' ? 'alert-warn' : '';
    html += `<div class="alert-item ${cls}">\u25B2 ${a.message || ''}</div>`;
  });
  document.getElementById('body-alerts').innerHTML = html;
}

/* ── Badges ──────────────────────────────────────────── */
function updateBadges(s) {
  const vehBadge = document.getElementById('badge-veh');
  const robotAge = s.robot_age ?? -1;
  if (robotAge < 0) { vehBadge.className = 'badge'; vehBadge.textContent = 'VEH'; }
  else if (robotAge < 2) { vehBadge.className = 'badge ok'; vehBadge.textContent = 'VEH'; }
  else { vehBadge.className = 'badge error'; vehBadge.textContent = `VEH ${robotAge.toFixed(0)}s`; }

  document.getElementById('badge-stas').className = 'badge ' + (s.station_connected ? 'ok' : 'error');
  document.getElementById('badge-joy').className = 'badge ' + ((s.control||{}).joystick_connected ? 'ok' : '');
  document.getElementById('badge-rem').className = 'badge ' + (s.remote_enabled ? 'ok' : '');

  // Mode buttons
  const activeMode = (s.mux || {}).requested_mode ?? -1;
  document.querySelectorAll('.mode-btn').forEach(btn => {
    btn.className = parseInt(btn.dataset.mode) === activeMode ? 'mode-btn active' : 'mode-btn';
  });
}

/* ── Refresh ─────────────────────────────────────────── */
function refresh(s) {
  lastState = s;
  renderHunter(s.hunter || {});
  renderMux(s.mux || {});
  renderNetwork(s.network || {});
  renderTwist(s.twist || {});
  renderEstop(s.estop || {}, s.control || {});
  renderJoystick(s.control || {}, s.station_connected || false);
  renderResources(s.resources || {}, s.gpu_list || []);
  renderNetifaces(s.net_interfaces || [], s.resources || {});
  renderDisk(s.disk_partitions || []);
  renderAlerts(s.alerts || []);
  updateBadges(s);

  // Notify video.js of codec (if video page)
  const vs = s.video_stats || {};
  if (typeof onCodecUpdate === 'function' && vs.codec) {
    onCodecUpdate(vs.codec);
  }
}

/* ── WebSocket ───────────────────────────────────────── */
function connectWs() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(`${proto}//${location.host}/ws/telemetry`);

  const statusEl = document.getElementById('ws-status');

  ws.onopen = () => {
    statusEl.className = 'ws-status connected';
    statusEl.textContent = 'WS';
  };
  ws.onclose = () => {
    statusEl.className = 'ws-status disconnected';
    statusEl.textContent = 'WS';
    setTimeout(connectWs, 2000);
  };
  ws.onerror = () => ws.close();
  ws.onmessage = (e) => {
    try { refresh(JSON.parse(e.data)); }
    catch (err) { console.error('parse error', err); }
  };
}

/* ── Commands ────────────────────────────────────────── */
document.querySelectorAll('.mode-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    fetch('/api/cmd/mode', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({mode: parseInt(btn.dataset.mode)}),
    });
  });
});

document.getElementById('estop-btn').addEventListener('click', () => {
  fetch('/api/cmd/estop', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({active: !estopActive}),
  });
});

/* ── Clock ───────────────────────────────────────────── */
setInterval(() => {
  document.getElementById('clock').textContent = new Date().toLocaleTimeString('en-GB');
}, 1000);

/* ── Init ────────────────────────────────────────────── */
connectWs();
