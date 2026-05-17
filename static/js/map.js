/**
 * OrbitVision — Leaflet.js 2D Satellite Map (EarthSphere 2D)
 * Works in all browsers including sandboxed iframes. Primary view mode.
 */

let leafletMap = null;
let satMarkers = {};
let orbitPolylines = {};
let futurePolylines = {};
let gsMarkers = {};
const SAT_MAP_COLORS = {
  'Space Station': '#ffdd00',
  'Communication': '#00d4ff',
  'Navigation': '#00ff88',
  'Weather': '#ff6b35',
  'Science': '#a855f7',
  'Debris': '#ff3355',
  'Various': '#7799aa',
};

function getSatColor(sat) {
  return SAT_MAP_COLORS[sat.sat_type || sat.type] || '#00d4ff';
}

function initLeafletMap(containerId) {
  const container = document.getElementById(containerId);
  if (!container || leafletMap) return;

  leafletMap = L.map(containerId, {
    center: [20, 0],
    zoom: 2,
    zoomControl: true,
    attributionControl: true,
    minZoom: 1,
    maxZoom: 8,
  });

  // Dark theme tiles
  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; <a href="https://carto.com/">CARTO</a> &copy; OpenStreetMap contributors',
    subdomains: 'abcd',
    maxZoom: 19,
  }).addTo(leafletMap);

  // Equator line
  L.polyline([[0, -180], [0, 180]], {
    color: 'rgba(0,212,255,0.15)', weight: 1, dashArray: '4,8'
  }).addTo(leafletMap);

  // Ethiopia marker
  const ethiopiaIcon = L.divIcon({
    className: '',
    html: `<div style="width:10px;height:10px;background:#00ff88;border:2px solid #003322;border-radius:50%;box-shadow:0 0 6px #00ff88;"></div>`,
    iconSize: [10, 10],
    iconAnchor: [5, 5],
  });
  L.marker([9.035, 38.745], { icon: ethiopiaIcon })
    .addTo(leafletMap)
    .bindPopup('<b style="color:#00ff88">📍 Addis Ababa, Ethiopia</b><br>EthioPass Observer Location')
    .bindTooltip('Addis Ababa — EthioPass Observer');

  leafletMap.on('click', function(e) {
    const coordHud = document.getElementById('coords-hud');
    if (coordHud) {
      coordHud.innerHTML = `
        <div style="font-size:9px;letter-spacing:1px;margin-bottom:3px;">📍 CURSOR</div>
        <div>LAT <b>${e.latlng.lat.toFixed(4)}°</b></div>
        <div>LON <b>${e.latlng.lng.toFixed(4)}°</b></div>
      `;
    }
  });
}

function updateMapSatellites(satellites) {
  if (!leafletMap) return;
  const keep = new Set(satellites.map(s => s.id));

  // Remove stale
  Object.keys(satMarkers).forEach(id => {
    if (!keep.has(id)) {
      leafletMap.removeLayer(satMarkers[id]);
      delete satMarkers[id];
    }
  });

  satellites.forEach(sat => {
    if (sat.lat == null || sat.lon == null) return;
    const color = getSatColor(sat);
    const isISS = sat.name && sat.name.includes('ISS');
    const size = isISS ? 12 : 7;

    const icon = L.divIcon({
      className: '',
      html: `<div style="width:${size}px;height:${size}px;background:${color};border-radius:50%;border:1px solid rgba(0,0,0,0.4);box-shadow:0 0 ${isISS?8:4}px ${color};cursor:pointer;${isISS ? 'transform:rotate(45deg);border-radius:2px;' : ''}"></div>`,
      iconSize: [size, size],
      iconAnchor: [size/2, size/2],
    });

    const popupContent = `
      <div style="font-family:monospace;min-width:180px;">
        <div style="font-size:12px;font-weight:700;color:${color};margin-bottom:6px;">${sat.name}</div>
        <div style="font-size:10px;color:#aaa;">NORAD ${sat.id}</div>
        <hr style="border-color:#333;margin:5px 0;">
        <div style="font-size:10px;line-height:1.8;">
          <div>LAT: <b>${sat.lat?.toFixed(4)}°</b></div>
          <div>LON: <b>${sat.lon?.toFixed(4)}°</b></div>
          <div>ALT: <b>${sat.alt?.toFixed(1)} km</b></div>
          <div>SPD: <b>${sat.speed_kmh?.toFixed(0)} km/h</b></div>
          <div>Type: <b>${sat.sat_type || sat.type || 'Unknown'}</b></div>
          <div>Country: <b>${sat.country || 'Unknown'}</b></div>
        </div>
        <button onclick="window.selectSatellite && selectSatellite('${sat.id}')"
          style="margin-top:6px;width:100%;background:#00d4ff;color:#000;border:none;padding:4px;border-radius:4px;cursor:pointer;font-family:monospace;font-size:10px;font-weight:700;">
          📡 View Full Profile
        </button>
      </div>`;

    if (satMarkers[sat.id]) {
      satMarkers[sat.id].setLatLng([sat.lat, sat.lon]);
      satMarkers[sat.id].setIcon(icon);
    } else {
      const marker = L.marker([sat.lat, sat.lon], { icon })
        .addTo(leafletMap)
        .bindPopup(popupContent, { maxWidth: 220 })
        .bindTooltip(`${isISS ? '🛸' : '🛰'} ${sat.name} — ${sat.alt?.toFixed(0)} km`, { direction: 'top' })
        .on('click', () => {
          if (window.selectSatellite) window.selectSatellite(sat.id);
        });
      satMarkers[sat.id] = marker;
    }
  });
}

function drawMapOrbitPath(satId, path, color = '#00d4ff', opacity = 0.6) {
  if (!leafletMap || !path || path.length < 2) return;
  if (orbitPolylines[satId]) {
    leafletMap.removeLayer(orbitPolylines[satId]);
    delete orbitPolylines[satId];
  }

  // Split at antimeridian crossings to avoid wrap-around lines
  const segments = [];
  let current = [];
  for (let i = 0; i < path.length; i++) {
    const p = path[i];
    if (current.length > 0) {
      const prev = current[current.length - 1];
      if (Math.abs(p.lon - prev[1]) > 180) {
        segments.push(current);
        current = [];
      }
    }
    current.push([p.lat, p.lon]);
  }
  if (current.length > 0) segments.push(current);

  const polylines = segments.map(seg =>
    L.polyline(seg, { color, weight: 1.5, opacity, dashArray: null })
  );
  const group = L.layerGroup(polylines).addTo(leafletMap);
  orbitPolylines[satId] = group;
}

function drawMapFuturePath(satId, path, color = '#00ff88', opacity = 0.5) {
  if (!leafletMap || !path || path.length < 2) return;
  if (futurePolylines[satId]) {
    leafletMap.removeLayer(futurePolylines[satId]);
    delete futurePolylines[satId];
  }
  const segments = [];
  let current = [];
  for (let i = 0; i < path.length; i++) {
    const p = path[i];
    if (current.length > 0) {
      const prev = current[current.length - 1];
      if (Math.abs(p.lon - prev[1]) > 180) { segments.push(current); current = []; }
    }
    current.push([p.lat, p.lon]);
  }
  if (current.length > 0) segments.push(current);
  const polylines = segments.map(seg =>
    L.polyline(seg, { color, weight: 1, opacity, dashArray: '5,5' })
  );
  const group = L.layerGroup(polylines).addTo(leafletMap);
  futurePolylines[satId] = group;
}

function clearMapOrbitLines() {
  Object.values(orbitPolylines).forEach(l => l && leafletMap && leafletMap.removeLayer(l));
  Object.values(futurePolylines).forEach(l => l && leafletMap && leafletMap.removeLayer(l));
  orbitPolylines = {};
  futurePolylines = {};
}

function addMapGroundStation(gs) {
  if (!leafletMap) return;
  const icon = L.divIcon({
    className: '',
    html: `<div title="${gs.name}" style="width:8px;height:8px;background:#ff6b35;transform:rotate(45deg);border:1px solid #000;box-shadow:0 0 4px #ff6b35;"></div>`,
    iconSize: [8, 8], iconAnchor: [4, 4],
  });
  const m = L.marker([gs.lat, gs.lon], { icon })
    .addTo(leafletMap)
    .bindTooltip(`📡 ${gs.name} (${gs.country})`, { direction: 'top' });
  gsMarkers[gs.id] = m;
}

function flyMapTo(lat, lon, zoom = 4) {
  if (leafletMap) leafletMap.flyTo([lat, lon], zoom, { duration: 1.2 });
}

function setMapViewMode(mode) {
  if (!leafletMap) return;
  if (mode === 'night') {
    document.getElementById('map').style.filter = 'brightness(0.7) hue-rotate(200deg)';
  } else if (mode === 'security') {
    document.getElementById('map').style.filter = 'brightness(0.8) hue-rotate(90deg) saturate(1.5)';
  } else {
    document.getElementById('map').style.filter = '';
  }
}
