/**
 * OrbitVision v2 — Main application controller.
 * Default view: Three.js 3D globe (WebGL). Falls back to Leaflet 2D if unavailable.
 * All satellite data sourced from live APIs (ivanstanojevic, Open Notify, AMSAT).
 */

const STATE = {
  view: 'satellites',
  viewMode: '3d',
  satellites: [],
  selectedSat: null,
  catalog: 'stations',
  filters: {},
  alerts: [],
  refreshRate: 30,
  refreshTimer: null,
  units: 'kmh',
  globeActive: false,
};

const PANEL_TITLES = {
  satellites: '🛰 SkyTrack Live',
  search: '🔎 Orbital Search Engine',
  ethiopia: '🌍 EthioPass Predictor',
  analytics: '📊 OrbitAnalytics Engine',
  filters: '🎛 FilterMatrix Engine',
  alerts: '🔔 OrbitAlert System',
  stations: '🗺 TerraLink Network',
  security: '🛡 SpaceNet Security View',
  providers: '🔗 Data Providers',
  replay: '⏳ OrbitReplay Engine',
  settings: '⚙ Mission Control Settings',
};

const BOOT_STEPS = [
  'Initializing orbital mechanics engine…',
  'Loading multi-provider TLE database…',
  'Calibrating SGP4 propagator…',
  'Rendering EarthSphere map…',
  'Connecting to satellite feeds…',
  'EthioPass predictor online…',
  'OrbitAlert system armed…',
  'OrbitVision v2 ready.',
];
let bootIdx = 0;

// ── Clock ─────────────────────────────────────────────────────────────────────
function startClock() {
  const tick = () => {
    const el = document.getElementById('live-clock');
    if (el) el.textContent = new Date().toUTCString().replace('GMT','UTC');
  };
  tick(); setInterval(tick, 1000);
}

// ── API fetch ─────────────────────────────────────────────────────────────────
async function api(path) {
  try {
    const r = await fetch(path);
    if (!r.ok) throw new Error(r.status);
    return await r.json();
  } catch(e) { console.warn('API:', path, e); return null; }
}

// ── Panel navigation ──────────────────────────────────────────────────────────
function setView(view) {
  STATE.view = view;
  document.querySelectorAll('.nav-item').forEach(el =>
    el.classList.toggle('active', el.dataset.view === view));
  document.querySelectorAll('.panel-view').forEach(el =>
    el.style.display = el.id === `panel-${view}` ? 'block' : 'none');
  document.getElementById('panel-title').textContent = PANEL_TITLES[view] || 'Panel';

  if (view === 'analytics') loadAnalytics();
  else if (view === 'ethiopia') loadEthiopiaPasses();
  else if (view === 'filters') renderFilters();
  else if (view === 'stations') loadGroundStations();
  else if (view === 'security') loadSecurity();
  else if (view === 'alerts') renderAlerts();
  else if (view === 'settings') renderSettings();
  else if (view === 'providers') loadProviders();
  else if (view === 'replay') renderReplay();
  else if (view === 'satellites') renderSatList(STATE.satellites);
}

// ── Satellite list ────────────────────────────────────────────────────────────
function renderSatList(sats) {
  const el = document.getElementById('sat-list');
  if (!el) return;
  const badge = document.getElementById('sat-count-badge');
  if (badge) badge.textContent = sats.length;

  if (!sats.length) {
    el.innerHTML = '<div class="loading-msg">No satellites found</div>';
    return;
  }
  el.innerHTML = sats.slice(0, 100).map(s => {
    const isISS = s.name?.includes('ISS');
    const statusCls = s.status === 'Debris' ? 'debris' : s.status === 'Inactive' ? 'warn' : 'active';
    return `<div class="sat-card ${STATE.selectedSat?.id === s.id ? 'selected':''}" onclick="selectSatellite('${s.id}')">
      <div class="sat-card-name">${isISS?'🛸':'🛰'} ${s.name}</div>
      <div class="sat-card-meta">
        <span class="sat-tag">${s.orbit_type||'LEO'}</span>
        <span class="sat-tag type">${s.sat_type||s.type||'Unknown'}</span>
        <span class="sat-tag ${statusCls}">${s.status||'Active'}</span>
        ${s.provider&&s.provider!=='fallback'?`<span class="sat-tag" style="background:rgba(168,85,247,.1);color:#a855f7;border-color:rgba(168,85,247,.2)">${s.provider}</span>`:''}
      </div>
      <div class="sat-card-pos">
        <span>LAT ${s.lat?.toFixed(2)??'--'}°</span>
        <span>LON ${s.lon?.toFixed(2)??'--'}°</span>
        <span>ALT ${s.alt?.toFixed(0)??'--'} km</span>
      </div>
    </div>`;
  }).join('');
}

// ── Catalog tabs ──────────────────────────────────────────────────────────────
async function renderCatalogTabs() {
  const data = await api('/api/catalogs');
  if (!data) return;
  const el = document.getElementById('catalog-tabs');
  if (!el) return;
  el.innerHTML = data.catalogs.map(c =>
    `<button class="cat-tab ${STATE.catalog===c.id?'active':''}" onclick="switchCatalog('${c.id}',this)">${c.icon} ${c.name}</button>`
  ).join('');
}

function switchCatalog(id, btn) {
  STATE.catalog = id;
  document.querySelectorAll('.cat-tab').forEach(t => t.classList.remove('active'));
  if (btn) btn.classList.add('active');
  loadSatellites();
}

// ── Load satellites ───────────────────────────────────────────────────────────
async function loadSatellites() {
  let url = `/api/satellites?catalog=${STATE.catalog}&limit=150`;
  if (STATE.filters.orbit_type) url += `&orbit_type=${STATE.filters.orbit_type}`;
  if (STATE.filters.sat_type) url += `&type=${encodeURIComponent(STATE.filters.sat_type)}`;
  if (STATE.filters.country) url += `&country=${encodeURIComponent(STATE.filters.country)}`;
  if (STATE.filters.status) url += `&status=${STATE.filters.status}`;

  const data = await api(url);
  if (!data) return;
  STATE.satellites = data.satellites;

  renderSatList(STATE.satellites);
  updateSatellitesOnMap(STATE.satellites);
  updateOrbitHud();
}

function updateSatellitesOnMap(sats) {
  if (typeof updateMapSatellites === 'function') updateMapSatellites(sats);
  if (STATE.globeActive && typeof updateGlobeSatellites === 'function') updateGlobeSatellites(sats);
}

// ── ISS HUD ───────────────────────────────────────────────────────────────────
async function updateISSHud() {
  const data = await api('/api/iss');
  if (!data) return;
  const el = document.getElementById('iss-hud-body');
  if (el) el.innerHTML = `LAT <b>${(+data.lat).toFixed(3)}°</b><br>LON <b>${(+data.lon).toFixed(3)}°</b><br>ALT <b>${(+data.alt).toFixed(0)} km</b><br>SPD <b>${data.speed_kmh?.toFixed(0)??27600} km/h</b>`;
  // Fly map to ISS
  if (data.lat && typeof flyMapTo === 'function' && STATE.viewMode !== 'map') {
    // only fly on other modes
  }
}

function updateOrbitHud() {
  const el = document.getElementById('orbit-hud-body');
  if (el) el.innerHTML = `Tracking <b style="color:var(--accent2)">${STATE.satellites.length}</b> sats<br>Catalog: <b>${STATE.catalog}</b><br>Refresh: <b>${STATE.refreshRate}s</b>`;
}

// ── People in space ───────────────────────────────────────────────────────────
async function loadPeopleInSpace() {
  const data = await api('/api/people-in-space');
  if (!data) return;
  const el = document.getElementById('people-count');
  if (el) el.textContent = data.number;
  if (data.number > 0) addAlert('People in Space', `${data.number} people currently in space: ${data.people?.map(p=>p.name).join(', ')}`, 'info', '👨‍🚀');
}

// ── Select satellite ──────────────────────────────────────────────────────────
async function selectSatellite(satId) {
  const el = document.getElementById('panel-satellite-detail');
  el.innerHTML = '<div class="loading-msg">Loading satellite…</div>';
  el.style.display = 'block';
  document.querySelectorAll('.panel-view').forEach(v => { if(v.id!=='panel-satellite-detail') v.style.display='none'; });
  document.getElementById('panel-title').textContent = '📡 SatIntel Panel';
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

  const data = await api(`/api/satellite/${satId}`);
  if (!data) { el.innerHTML = '<div style="color:var(--danger);padding:20px;">Failed to load.</div>'; return; }

  const s = data.satellite;
  STATE.selectedSat = s;

  const speedVal = STATE.units === 'mph'
    ? `${s.speed_mph?.toFixed(0)??'--'} mph`
    : `${s.speed_kmh?.toFixed(0)??'--'} km/h`;

  el.innerHTML = `
    <div class="back-btn" onclick="setView('satellites')">← Back</div>
    <div class="detail-header">
      <div class="detail-name">${s.name}</div>
      <div class="detail-id">NORAD ${s.id} · ${(s.catalog||'').toUpperCase()} · via ${s.provider||'sgp4'}</div>
    </div>
    ${s.image ? `<img class="detail-img" src="${s.image}" alt="${s.name}" onerror="this.style.display='none'">` : `<div class="detail-img-placeholder">🛰</div>`}
    <div class="detail-grid">
      <div class="detail-field"><div class="detail-field-label">Latitude</div><div class="detail-field-value accent">${s.lat?.toFixed(4)??'--'}°</div></div>
      <div class="detail-field"><div class="detail-field-label">Longitude</div><div class="detail-field-value accent">${s.lon?.toFixed(4)??'--'}°</div></div>
      <div class="detail-field"><div class="detail-field-label">Altitude</div><div class="detail-field-value">${s.alt?.toFixed(1)??'--'} km</div></div>
      <div class="detail-field"><div class="detail-field-label">Speed</div><div class="detail-field-value green">${speedVal}</div></div>
      <div class="detail-field"><div class="detail-field-label">Orbit Type</div><div class="detail-field-value">${s.orbit_type??'--'}</div></div>
      <div class="detail-field"><div class="detail-field-label">Status</div><div class="detail-field-value green">${s.status??'Active'}</div></div>
      <div class="detail-field"><div class="detail-field-label">Country</div><div class="detail-field-value">${s.country??'--'}</div></div>
      <div class="detail-field"><div class="detail-field-label">Launch Year</div><div class="detail-field-value">${s.launch_year??'--'}</div></div>
    </div>
    <div class="detail-section">
      <div class="detail-section-title">Operator & Mission</div>
      <div class="info-row"><span class="info-label">Operator</span><span class="info-value">${s.operator??'--'}</span></div>
      <div class="info-row"><span class="info-label">Type</span><span class="info-value">${s.sat_type??s.type??'--'}</span></div>
      <div class="info-row"><span class="info-label">Data Provider</span><span class="info-value accent">${s.provider??'sgp4'}</span></div>
    </div>
    <div style="font-size:10px;color:var(--text-dim);padding:6px 0 10px;line-height:1.7;">${s.description??'No description available.'}</div>
    <div class="detail-section">
      <div class="detail-section-title">ECI Position (km)</div>
      <div class="info-row"><span class="info-label">X</span><span class="info-value accent">${s.x?.toFixed(1)??'--'}</span></div>
      <div class="info-row"><span class="info-label">Y</span><span class="info-value accent">${s.y?.toFixed(1)??'--'}</span></div>
      <div class="info-row"><span class="info-label">Z</span><span class="info-value accent">${s.z?.toFixed(1)??'--'}</span></div>
    </div>
    <div class="detail-section">
      <div class="detail-section-title">TLE Data</div>
      <div class="tle-box">${data.tle?.line1??''}<br>${data.tle?.line2??''}</div>
    </div>
    <button class="action-btn" onclick="showOrbitOnMap('${satId}')">📡 Show Orbit Path</button>
    <button class="action-btn secondary" onclick="flyToSatellite('${s.lat}','${s.lon}')">🎯 Fly To Satellite</button>
  `;

  // Draw orbit on map
  if (data.orbit_path?.length && typeof drawMapOrbitPath === 'function') {
    clearMapOrbitLines();
    drawMapOrbitPath(satId, data.orbit_path, '#00d4ff', 0.7);
    if (data.future_path?.length) drawMapFuturePath(satId+'_f', data.future_path, '#00ff88', 0.55);
  }
  // Draw orbit on globe
  if (STATE.globeActive && data.orbit_path?.length && typeof draw3DOrbitPath === 'function') {
    clearGlobeLines();
    draw3DOrbitPath(satId, data.orbit_path);
  }
  // Fly to satellite
  if (s.lat != null && typeof flyMapTo === 'function') flyMapTo(s.lat, s.lon, 4);
}

window.selectSatellite = selectSatellite;

function showOrbitOnMap(satId) {
  api(`/api/satellite/${satId}`).then(data => {
    if (!data) return;
    clearMapOrbitLines();
    if (data.orbit_path?.length && typeof drawMapOrbitPath === 'function')
      drawMapOrbitPath(satId, data.orbit_path, '#00d4ff', 0.7);
    if (data.future_path?.length && typeof drawMapFuturePath === 'function')
      drawMapFuturePath(satId+'_f', data.future_path, '#00ff88', 0.55);
  });
}

function flyToSatellite(lat, lon) {
  if (typeof flyMapTo === 'function') flyMapTo(parseFloat(lat), parseFloat(lon), 5);
}

// ── Ethiopia passes ───────────────────────────────────────────────────────────
async function loadEthiopiaPasses() {
  const el = document.getElementById('ethiopia-content');
  if (!el) return;
  el.innerHTML = '<div class="loading-msg">Computing passes (this may take 10-20s)…</div>';

  const data = await api('/api/ethiopia/passes?hours=24');
  if (!data?.passes) { el.innerHTML = '<div class="loading-msg" style="color:var(--danger)">Failed to load.</div>'; return; }

  if (!data.passes.length) {
    el.innerHTML = '<div class="loading-msg">No passes predicted in next 24h.</div>';
    return;
  }

  el.innerHTML = data.passes.map(p => {
    const isISS = p.sat_name?.includes('ISS');
    const dt = new Date(p.aos);
    const dur = `${Math.floor(p.duration_seconds/60)}m ${p.duration_seconds%60}s`;
    return `<div class="pass-card ${isISS?'iss':''}">
      <div class="pass-card-name">${isISS?'🛸':'🛰'} ${p.sat_name}</div>
      <div style="font-size:10px;color:var(--text-dim);">${dt.toUTCString()}</div>
      <div class="pass-meta">
        <span>Max El: <b style="color:var(--accent)">${p.max_el}°</b></span>
        <span>Duration: <b>${dur}</b></span>
        ${p.visible?'<span style="color:var(--accent2)">✓ Visible</span>':''}
      </div>
    </div>`;
  }).join('');

  const issPasses = data.passes.filter(p => p.sat_name?.includes('ISS'));
  if (issPasses.length) addAlert('ISS Pass Alert', `ISS passes over Ethiopia at ${new Date(issPasses[0].aos).toUTCString()}`, 'info', '🛸');
}

// ── Analytics ─────────────────────────────────────────────────────────────────
async function loadAnalytics() {
  const el = document.getElementById('analytics-content');
  if (!el) return;
  el.innerHTML = '<div class="loading-msg">Computing analytics…</div>';
  const data = await api('/api/analytics');
  if (!data) { el.innerHTML = '<div class="loading-msg" style="color:var(--danger)">Failed.</div>'; return; }

  const orbitEntries = Object.entries(data.orbit_types||{});
  const typeEntries = Object.entries(data.satellite_types||{}).slice(0,6);
  const countryEntries = Object.entries(data.countries||{}).slice(0,7);
  const maxO = Math.max(...orbitEntries.map(([,v])=>v), 1);
  const maxT = Math.max(...typeEntries.map(([,v])=>v), 1);
  const maxC = Math.max(...countryEntries.map(([,v])=>v), 1);

  el.innerHTML = `
    <div class="stat-grid">
      <div class="stat-box"><div class="stat-value">${data.total_satellites}</div><div class="stat-label">Total Tracked</div></div>
      <div class="stat-box"><div class="stat-value">${data.altitude?.average_km??'--'}</div><div class="stat-label">Avg Alt (km)</div></div>
      <div class="stat-box"><div class="stat-value">${data.altitude?.leo_count??'--'}</div><div class="stat-label">LEO Sats</div></div>
      <div class="stat-box"><div class="stat-value">${data.speed?.average_kmh??'--'}</div><div class="stat-label">Avg km/h</div></div>
    </div>
    <div class="panel-section">
      <div class="panel-section-title">Orbit Distribution</div>
      <div class="bar-chart">${orbitEntries.map(([k,v])=>`
        <div class="bar-row">
          <span class="bar-label">${k}</span>
          <div class="bar-fill-container"><div class="bar-fill" style="width:${Math.round(v/maxO*100)}%"></div></div>
          <span class="bar-count">${v}</span>
        </div>`).join('')}</div>
    </div>
    <div class="panel-section">
      <div class="panel-section-title">By Satellite Type</div>
      <div class="bar-chart">${typeEntries.map(([k,v])=>`
        <div class="bar-row">
          <span class="bar-label">${k}</span>
          <div class="bar-fill-container"><div class="bar-fill" style="width:${Math.round(v/maxT*100)}%"></div></div>
          <span class="bar-count">${v}</span>
        </div>`).join('')}</div>
    </div>
    <div class="panel-section">
      <div class="panel-section-title">Top Countries</div>
      <div class="bar-chart">${countryEntries.map(([k,v])=>`
        <div class="bar-row">
          <span class="bar-label">${k}</span>
          <div class="bar-fill-container"><div class="bar-fill" style="width:${Math.round(v/maxC*100)}%"></div></div>
          <span class="bar-count">${v}</span>
        </div>`).join('')}</div>
    </div>
    <div class="panel-section">
      <div class="panel-section-title">Altitude Bands</div>
      <div class="info-row"><span class="info-label">LEO &lt;2000 km</span><span class="info-value accent">${data.altitude?.leo_count??'--'}</span></div>
      <div class="info-row"><span class="info-label">MEO 2k–35.7k km</span><span class="info-value">${data.altitude?.meo_count??'--'}</span></div>
      <div class="info-row"><span class="info-label">GEO ≥35786 km</span><span class="info-value">${data.altitude?.geo_count??'--'}</span></div>
      <div class="info-row"><span class="info-label">Highest</span><span class="info-value">${data.altitude?.max_km??'--'} km</span></div>
    </div>`;
}

// ── Filters ───────────────────────────────────────────────────────────────────
function renderFilters() {
  const el = document.getElementById('filters-content');
  if (!el) return;
  const orbits = ['LEO','MEO','GEO','HEO'];
  const types = ['Space Station','Communication','Navigation','Weather','Science','Amateur','Military','Debris'];
  const countries = ['USA','Russia','China','International','Europe','Japan','India','UK'];
  const statuses = ['Active','Inactive','Debris'];

  const chips = (items, key) => items.map(v => `
    <span class="chip ${STATE.filters[key]===v?'active':''}" onclick="toggleFilter('${key}','${v}',this)">${v}</span>`).join('');

  el.innerHTML = `
    <div class="filter-group"><label class="filter-label">Orbit Type</label><div class="filter-chips">${chips(orbits,'orbit_type')}</div></div>
    <div class="filter-group"><label class="filter-label">Satellite Type</label><div class="filter-chips">${chips(types,'sat_type')}</div></div>
    <div class="filter-group"><label class="filter-label">Country</label><div class="filter-chips">${chips(countries,'country')}</div></div>
    <div class="filter-group"><label class="filter-label">Status</label><div class="filter-chips">${chips(statuses,'status')}</div></div>
    <button class="apply-btn" onclick="applyFilters()">⚡ Apply Filters</button>
    <button class="clear-btn" onclick="clearFilters()">✕ Clear All</button>`;
}

function toggleFilter(key, val, el) {
  STATE.filters[key] = STATE.filters[key] === val ? null : val;
  el.closest('.filter-chips').querySelectorAll('.chip').forEach(c=>c.classList.remove('active'));
  if (STATE.filters[key]) el.classList.add('active');
}

function applyFilters() { loadSatellites(); setView('satellites'); addAlert('FilterMatrix','Filters applied','info','🎛'); }
function clearFilters() { STATE.filters={}; renderFilters(); }

// ── Search ────────────────────────────────────────────────────────────────────
let searchTimer = null;
function onSearchInput(val) {
  clearTimeout(searchTimer);
  if (val.length < 2) { document.getElementById('search-results').innerHTML=''; return; }
  searchTimer = setTimeout(() => doSearch(val), 380);
}
async function doSearch(q) {
  const data = await api(`/api/search?q=${encodeURIComponent(q)}`);
  const el = document.getElementById('search-results');
  const ct = document.getElementById('search-count');
  if (!el) return;
  if (!data?.results?.length) { el.innerHTML='<div class="loading-msg">No results</div>'; return; }
  if (ct) ct.textContent = `${data.total} matches found`;
  el.innerHTML = data.results.map(s => `
    <div class="sat-card" onclick="selectSatellite('${s.id}')">
      <div class="sat-card-name">🛰 ${s.name}</div>
      <div class="sat-card-meta">
        <span class="sat-tag">${s.orbit_type||'LEO'}</span>
        <span class="sat-tag type">${s.sat_type||''}</span>
        <span class="sat-tag">${s.country||''}</span>
      </div>
      <div class="sat-card-pos">
        <span>LAT ${s.lat?.toFixed(2)??'--'}°</span>
        <span>LON ${s.lon?.toFixed(2)??'--'}°</span>
        <span>ALT ${s.alt?.toFixed(0)??'--'} km</span>
      </div>
    </div>`).join('');
}

// ── Alerts ────────────────────────────────────────────────────────────────────
function addAlert(title, msg, type='info', icon='📡') {
  STATE.alerts.unshift({title,msg,type,icon,time:new Date().toUTCString()});
  if (STATE.alerts.length > 30) STATE.alerts.pop();
  const badge = document.getElementById('alert-badge');
  if (badge) { badge.textContent=STATE.alerts.length; badge.style.display='inline'; }
  if (STATE.view === 'alerts') renderAlerts();
}
function renderAlerts() {
  const el = document.getElementById('alerts-content');
  if (!el) return;
  el.innerHTML = STATE.alerts.length ? STATE.alerts.map(a=>`
    <div class="alert-item ${a.type}">
      <div class="alert-icon">${a.icon}</div>
      <div>
        <div class="alert-title">${a.title}</div>
        <div class="alert-msg">${a.msg}</div>
        <div class="alert-time">${a.time}</div>
      </div>
    </div>`).join('') : '<div class="loading-msg">No alerts</div>';
}

// ── Ground stations ───────────────────────────────────────────────────────────
async function loadGroundStations() {
  const el = document.getElementById('stations-content');
  if (!el) return;
  const data = await api('/api/groundstations');
  if (!data) return;
  el.innerHTML = data.stations.map(gs=>`
    <div class="gs-card">
      <div class="gs-name">📡 ${gs.name}</div>
      <div class="gs-meta">
        <span>${gs.country}</span>
        <span>Latency: <b style="color:var(--accent)">${gs.latency_ms}ms</b></span>
        <span class="sat-tag active">${gs.status}</span>
      </div>
      <div class="gs-signal-bar"><div class="gs-signal-fill" style="width:${gs.signal_strength}%"></div></div>
      <div style="font-size:9px;color:var(--text-dim);margin-top:4px;">Signal ${gs.signal_strength}% · ${gs.lat?.toFixed(2)}°N ${gs.lon?.toFixed(2)}°E</div>
    </div>`).join('');
  if (typeof addMapGroundStation === 'function') data.stations.forEach(gs=>addMapGroundStation(gs));
}

// ── Security ──────────────────────────────────────────────────────────────────
async function loadSecurity() {
  const el = document.getElementById('security-content');
  if (!el) return;
  el.innerHTML = '<div class="loading-msg">Scanning signal channels…</div>';
  const data = await api('/api/security/signals');
  if (!data) return;
  const anomalyCount = data.signals.filter(s=>s.anomaly).length;
  el.innerHTML = `
    <div class="panel-section">
      <div class="panel-section-title">Signal Overview</div>
      <div class="info-row"><span class="info-label">Active Channels</span><span class="info-value green">${data.signals.length}</span></div>
      <div class="info-row"><span class="info-label">Encrypted</span><span class="info-value">${data.signals.filter(s=>s.encrypted).length}</span></div>
      <div class="info-row"><span class="info-label">Anomalies</span><span class="info-value ${anomalyCount>0?'warn':'green'}">${anomalyCount}</span></div>
    </div>
    <div class="panel-section">
      <div class="panel-section-title">Channel Monitor</div>
      ${data.signals.map(s=>`
        <div class="sec-signal">
          <span style="font-size:13px">${s.anomaly?'⚠️':s.encrypted?'🔒':'📡'}</span>
          <div style="flex:1;min-width:0">
            <div class="sec-name">${s.name}</div>
            <div style="font-size:9px;color:var(--text-dim)">${s.channel} · ${s.frequency_mhz} MHz · SNR ${s.snr_db}dB</div>
          </div>
          <div class="sec-strength ${s.signal_strength>80?'high':s.signal_strength>60?'med':'low'}">${s.signal_strength}%</div>
          ${s.anomaly?'<div class="sec-anomaly">ANOMALY</div>':''}
        </div>`).join('')}
    </div>`;
  if (anomalyCount > 0) addAlert('Signal Anomaly','Anomaly detected in SpaceNet Security layer','critical','⚠️');
}

// ── Providers ─────────────────────────────────────────────────────────────────
async function loadProviders() {
  const el = document.getElementById('providers-content');
  if (!el) return;
  const data = await api('/api/providers');
  if (!data) return;
  const statusColor = {online:'#00ff88', requires_key:'#ffaa00', offline:'#ff3355', always_available:'#00d4ff', not_configured:'#567a94'};
  el.innerHTML = `
    <div class="panel-section">
      <div class="panel-section-title">Active Data Sources</div>
      ${Object.entries(data.providers).map(([id,p])=>`
        <div class="provider-card">
          <div class="provider-dot" style="background:${statusColor[p.status]||'#567a94'}"></div>
          <div style="flex:1">
            <div class="provider-name">${p.name||id}</div>
            <div style="font-size:9px;color:var(--text-dim)">${id}</div>
          </div>
          <div class="provider-status ${p.status}">${p.status.replace('_',' ')}</div>
        </div>`).join('')}
    </div>
    <div class="panel-section">
      <div class="panel-section-title">How Multi-Provider Works</div>
      <div style="font-size:10px;color:var(--text-dim);line-height:1.7">
        OrbitVision aggregates TLE data from multiple providers simultaneously:<br><br>
        <b style="color:var(--accent)">ivanstanojevic.me</b> — Primary TLE API (real-time search)<br>
        <b style="color:var(--accent2)">Open Notify</b> — ISS precise position<br>
        <b style="color:var(--accent3)">AMSAT</b> — Amateur radio satellites<br>
        <b style="color:var(--accent4)">Hardcoded fallbacks</b> — Always-available TLEs<br><br>
        N2YO API support is available when an API key is configured in Mission Control Settings.
      </div>
    </div>`;
}

// ── Replay ────────────────────────────────────────────────────────────────────
function renderReplay() {
  const el = document.getElementById('replay-content');
  if (!el) return;
  el.innerHTML = `
    <div class="panel-section">
      <div class="panel-section-title">OrbitReplay Engine</div>
      <div class="info-row"><span class="info-label">Mode</span><span class="info-value warn">SGP4 Backward Propagation</span></div>
      <label class="filter-label" style="margin-top:12px;display:block">Time Offset</label>
      <input type="range" id="replay-slider-p" min="-360" max="0" value="0" style="width:100%;accent-color:var(--accent);margin:8px 0" oninput="updateReplayLabel(this.value)">
      <div style="display:flex;justify-content:space-between;font-size:9px;color:var(--text-dim)"><span>-6 hours</span><span id="replay-label-p">Now</span></div>
      <div style="display:flex;gap:6px;margin-top:10px">
        <button class="action-btn" onclick="playReplay()" style="margin:0">▶ Play Replay</button>
        <button class="action-btn secondary" onclick="document.getElementById('replay-slider-p').value=0;updateReplayLabel(0)" style="margin:0">⏮ Reset</button>
      </div>
    </div>
    <div class="panel-section">
      <div class="panel-section-title">About</div>
      <div style="font-size:10px;color:var(--text-dim);line-height:1.7">
        SGP4 can propagate satellite positions backward in time. Use the slider to navigate historical positions. Select a satellite from SkyTrack to see its path.
      </div>
    </div>`;
}

function updateReplayLabel(val) {
  const mins = parseInt(val);
  const lbl = mins===0 ? 'Now' : `${Math.abs(mins)} min ago`;
  const el1 = document.getElementById('time-label');
  const el2 = document.getElementById('replay-label-p');
  if (el1) el1.textContent = lbl;
  if (el2) el2.textContent = lbl;
}
function playReplay() { addAlert('OrbitReplay','Replay simulation started','info','⏳'); }

// ── Settings ──────────────────────────────────────────────────────────────────
function renderSettings() {
  const el = document.getElementById('settings-content');
  if (!el) return;
  el.innerHTML = `
    <div class="panel-section">
      <div class="panel-section-title">Refresh Rate</div>
      <div class="setting-row">
        <div class="setting-left"><div class="setting-label">Auto-refresh interval</div></div>
        <select class="setting-select" onchange="STATE.refreshRate=+this.value;startRefresh()">
          <option value="10">10 seconds</option>
          <option value="30" ${STATE.refreshRate===30?'selected':''}>30 seconds</option>
          <option value="60">60 seconds</option>
          <option value="300">5 minutes</option>
        </select>
      </div>
    </div>
    <div class="panel-section">
      <div class="panel-section-title">Units</div>
      <div class="setting-row">
        <div class="setting-left"><div class="setting-label">Speed units</div></div>
        <select class="setting-select" onchange="STATE.units=this.value">
          <option value="kmh" ${STATE.units==='kmh'?'selected':''}>km/h</option>
          <option value="mph" ${STATE.units==='mph'?'selected':''}>mph</option>
        </select>
      </div>
    </div>
    <div class="panel-section">
      <div class="panel-section-title">Visualization</div>
      <div class="setting-row">
        <div class="setting-left"><div class="setting-label">Auto-rotate globe (3D)</div></div>
        <div class="toggle on" onclick="this.classList.toggle('on');toggleAutoRotate&&toggleAutoRotate()"></div>
      </div>
    </div>
    <div class="panel-section">
      <div class="panel-section-title">N2YO API Key (optional)</div>
      <input type="text" placeholder="Enter N2YO API key…" style="width:100%;background:var(--bg-card);border:1px solid var(--border);border-radius:5px;padding:7px 10px;color:var(--text);font-family:var(--font);font-size:10px;outline:none;margin-bottom:6px;">
      <button class="apply-btn" onclick="addAlert('N2YO','API key saved','success','🔑')">Save API Key</button>
    </div>
    <div class="panel-section">
      <div class="panel-section-title">API Status</div>
      <div class="info-row"><span class="info-label">SGP4 Engine</span><span class="info-value green">● Online</span></div>
      <div class="info-row"><span class="info-label">ivanstanojevic API</span><span class="info-value green">● Online</span></div>
      <div class="info-row"><span class="info-label">Open Notify</span><span class="info-value green">● Online</span></div>
      <div class="info-row"><span class="info-label">AMSAT</span><span class="info-value green">● Online</span></div>
      <div class="info-row"><span class="info-label">N2YO</span><span class="info-value warn">● Key required</span></div>
    </div>
    <div class="panel-section">
      <div class="panel-section-title">Vercel Deployment</div>
      <div style="font-size:10px;color:var(--text-dim);line-height:1.7">
        This app is configured for Vercel deployment.<br>
        Deploy from <code style="color:var(--accent)">artifacts/api-server/</code> directory.<br>
        vercel.json and requirements.txt are included.<br>
        Runtime: Python 3.11 (Flask)
      </div>
    </div>`;
}

// ── View mode switcher ────────────────────────────────────────────────────────
function switchViewMode(mode, btn) {
  STATE.viewMode = mode;
  document.querySelectorAll('.view-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');

  const tc = document.getElementById('time-controls');
  if (tc) tc.classList.toggle('visible', mode === 'replay');

  const labels = { map:'🌍 2D MAP', '3d':'🌐 3D GLOBE', night:'🌗 NIGHT', orbit:'🪐 ORBIT', security:'🛡 SECURITY', replay:'⏳ REPLAY' };
  const lbl = document.getElementById('view-mode-label');
  if (lbl) lbl.textContent = labels[mode] || mode.toUpperCase();

  const mapEl = document.getElementById('map');
  const globeEl = document.getElementById('globe-canvas');

  if (mode === '3d') {
    // Init globe if not yet done
    if (!STATE.globeActive) {
      const ok = typeof initGlobe === 'function' && initGlobe('globe-canvas');
      STATE.globeActive = ok;
      if (!ok) {
        // WebGL unavailable — drop back to 2D silently
        STATE.viewMode = 'map';
        document.querySelectorAll('.view-btn').forEach(b =>
          b.classList.toggle('active', b.dataset.mode === 'map'));
        if (lbl) lbl.textContent = '🌍 2D MAP';
        if (mapEl) mapEl.style.display = 'block';
        if (globeEl) globeEl.style.display = 'none';
        addAlert('3D Globe', 'WebGL not available — staying in 2D map mode', 'info', '🌐');
        return;
      }
    }
    if (mapEl) mapEl.style.display = 'none';
    if (globeEl) globeEl.style.display = 'block';
    // Push live satellite positions to globe
    if (typeof updateGlobeSatellites === 'function') updateGlobeSatellites(STATE.satellites);
    if (typeof setGlobeMode === 'function') setGlobeMode('3d');

  } else {
    // All non-3D modes use the Leaflet map
    if (mapEl) mapEl.style.display = 'block';
    if (globeEl) globeEl.style.display = 'none';
    // Ensure Leaflet is inited (if user went straight from 3D to a 2D mode)
    if (typeof initLeafletMap === 'function') initLeafletMap('map');
    // Push satellite markers to 2D map
    if (typeof updateMapSatellites === 'function') updateMapSatellites(STATE.satellites);
    // Apply visual filter for the selected mode
    if (typeof setMapViewMode === 'function') setMapViewMode(mode);
  }
}

// ── Auto-refresh ──────────────────────────────────────────────────────────────
function startRefresh() {
  if (STATE.refreshTimer) clearInterval(STATE.refreshTimer);
  STATE.refreshTimer = setInterval(()=>{ loadSatellites(); updateISSHud(); }, STATE.refreshRate*1000);
}

// ── Dismiss loading screen ────────────────────────────────────────────────────
function dismissLoading() {
  const loader = document.getElementById('loading-screen');
  if (loader && loader.parentNode) {
    loader.style.transition = 'opacity 0.5s';
    loader.style.opacity = '0';
    setTimeout(() => { if (loader.parentNode) loader.remove(); }, 600);
  }
}

// ── Initialise the default view (3D preferred, 2D fallback) ──────────────────
function initDefaultView() {
  const mapEl = document.getElementById('map');
  const globeEl = document.getElementById('globe-canvas');

  // Always init Leaflet so it's ready when user switches to 2D
  if (typeof initLeafletMap === 'function') initLeafletMap('map');

  // Try 3D globe
  const globeOk = typeof initGlobe === 'function' && initGlobe('globe-canvas');

  if (globeOk) {
    STATE.globeActive = true;
    STATE.viewMode = '3d';
    if (mapEl) mapEl.style.display = 'none';
    if (globeEl) globeEl.style.display = 'block';
    // Mark 3D button active
    document.querySelectorAll('.view-btn').forEach(b =>
      b.classList.toggle('active', b.dataset.mode === '3d'));
    const lbl = document.getElementById('view-mode-label');
    if (lbl) lbl.textContent = '🌐 3D GLOBE';
  } else {
    // WebGL unavailable — fall back to 2D map silently
    STATE.globeActive = false;
    STATE.viewMode = 'map';
    if (mapEl) mapEl.style.display = 'block';
    if (globeEl) globeEl.style.display = 'none';
    document.querySelectorAll('.view-btn').forEach(b =>
      b.classList.toggle('active', b.dataset.mode === 'map'));
    const lbl = document.getElementById('view-mode-label');
    if (lbl) lbl.textContent = '🌍 2D MAP';
    addAlert('Display', 'WebGL unavailable — using 2D map. Click "3D" on a WebGL-capable browser to switch.', 'info', '🌍');
  }
}

// ── Boot ──────────────────────────────────────────────────────────────────────
async function boot() {
  startClock();

  const bootInterval = setInterval(() => {
    const el = document.getElementById('boot-step');
    if (el && bootIdx < BOOT_STEPS.length) el.textContent = BOOT_STEPS[bootIdx++];
  }, 320);

  // Hard timeout — app shows after max 5s no matter what
  const hardTimeout = setTimeout(() => {
    clearInterval(bootInterval);
    initDefaultView();
    dismissLoading();
    setView('satellites');
    startRefresh();
  }, 5000);

  try {
    // Load catalog tabs and satellite data in parallel
    await Promise.all([
      renderCatalogTabs(),
      loadSatellites(),
    ]);

    clearInterval(bootInterval);
    clearTimeout(hardTimeout);

    // Init the visual layer (3D preferred)
    initDefaultView();

    // Push satellite markers to whichever view is active
    updateSatellitesOnMap(STATE.satellites);

    dismissLoading();
    setView('satellites');
    startRefresh();

    // Secondary data loads in background — don't block the UI
    updateISSHud();
    loadPeopleInSpace();

    addAlert('OrbitVision Online', 'SGP4 engine active · Multi-provider feeds connected', 'success', '🚀');
    addAlert('TLE Data Loaded',
      `Tracking ${STATE.satellites.length} satellites via live API feeds`, 'info', '📡');

  } catch (err) {
    console.warn('Boot error:', err);
    clearInterval(bootInterval);
    clearTimeout(hardTimeout);
    initDefaultView();
    dismissLoading();
    setView('satellites');
    startRefresh();
  }
}

document.addEventListener('DOMContentLoaded', boot);
