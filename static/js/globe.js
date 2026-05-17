/**
 * EarthSphere 3D — Three.js globe (optional, activated when WebGL is available).
 * Falls back gracefully to Leaflet 2D map.
 */

let scene, camera, renderer, earthMesh, cloudMesh, animId;
let isDragging3D = false, prevMouse3D = {x:0,y:0};
let rotX = 0, rotY = 0, targetRotX = 0, targetRotY = 0;
let autoRotate = true;
let globeInited = false;
let globeContainer = null;
const sat3DMarkers = {};
const orbit3DLines = [];
let webGLAvailable = null;

function checkWebGL() {
  if (webGLAvailable !== null) return webGLAvailable;
  try {
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
    webGLAvailable = !!ctx;
    if (ctx) {
      const ext = ctx.getExtension('WEBGL_lose_context');
      if (ext) ext.loseContext();
    }
  } catch(e) { webGLAvailable = false; }
  return webGLAvailable;
}

function initGlobe(containerId) {
  if (!checkWebGL()) {
    console.warn('WebGL not available — 3D globe disabled, using 2D map.');
    const notice = document.getElementById('webgl-notice');
    if (notice) notice.style.display = 'flex';
    return false;
  }
  if (typeof THREE === 'undefined') {
    console.warn('Three.js not loaded');
    return false;
  }
  globeContainer = document.getElementById(containerId);
  if (!globeContainer) return false;
  if (globeInited) return true;

  const w = globeContainer.clientWidth, h = globeContainer.clientHeight;
  scene = new THREE.Scene();

  // Stars
  const starGeo = new THREE.BufferGeometry();
  const starPos = new Float32Array(4000 * 3);
  for (let i = 0; i < starPos.length; i++) starPos[i] = (Math.random() - 0.5) * 600;
  starGeo.setAttribute('position', new THREE.BufferAttribute(starPos, 3));
  scene.add(new THREE.Points(starGeo, new THREE.PointsMaterial({color:0xffffff,size:0.6,transparent:true,opacity:0.65})));

  // Camera
  camera = new THREE.PerspectiveCamera(42, w / h, 0.1, 1000);
  camera.position.z = 2.8;

  // Renderer
  try {
    renderer = new THREE.WebGLRenderer({antialias: true, alpha: true, powerPreference: 'default'});
    renderer.setSize(w, h);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    globeContainer.appendChild(renderer.domElement);
  } catch(e) {
    console.warn('WebGL renderer failed:', e);
    return false;
  }

  // Earth — use solid color + procedural lines if texture fails
  const geo = new THREE.SphereGeometry(1, 48, 48);
  const loader = new THREE.TextureLoader();
  loader.crossOrigin = 'anonymous';

  // Earth material — starts as solid deep-ocean blue; upgrades to texture once loaded
  const mat = new THREE.MeshPhongMaterial({ color: 0x1a4a7a, shininess: 12 });
  earthMesh = new THREE.Mesh(geo, mat);
  scene.add(earthMesh);

  // Multiple fallback texture sources (tried in order)
  const earthTexUrls = [
    'https://unpkg.com/three-globe/example/img/earth-blue-marble.jpg',
    'https://cdn.jsdelivr.net/npm/three-globe@2.27.3/example/img/earth-blue-marble.jpg',
    'https://raw.githubusercontent.com/vasturiano/three-globe/master/example/img/earth-blue-marble.jpg',
    'https://raw.githubusercontent.com/mrdoob/three.js/dev/examples/textures/planets/earth_atmos_2048.jpg',
  ];
  const cloudTexUrls = [
    'https://unpkg.com/three-globe/example/img/earth-clouds.png',
    'https://cdn.jsdelivr.net/npm/three-globe@2.27.3/example/img/earth-clouds.png',
    'https://raw.githubusercontent.com/mrdoob/three.js/dev/examples/textures/planets/earth_clouds_1024.png',
  ];

  function tryLoadTexture(urls, idx, onLoaded) {
    if (idx >= urls.length) return;
    loader.load(urls[idx], onLoaded, undefined, () => tryLoadTexture(urls, idx + 1, onLoaded));
  }

  tryLoadTexture(earthTexUrls, 0, (tex) => {
    earthMesh.material.map = tex;
    earthMesh.material.color.set(0xffffff);
    earthMesh.material.needsUpdate = true;
  });

  // Atmosphere glow ring
  const atmMat = new THREE.MeshPhongMaterial({ color: 0x2288ff, transparent: true, opacity: 0.06, side: THREE.FrontSide });
  scene.add(new THREE.Mesh(new THREE.SphereGeometry(1.025, 48, 48), atmMat));

  // Cloud layer
  const cloudMat = new THREE.MeshPhongMaterial({ transparent: true, opacity: 0.22, depthWrite: false });
  cloudMesh = new THREE.Mesh(new THREE.SphereGeometry(1.009, 48, 48), cloudMat);
  tryLoadTexture(cloudTexUrls, 0, (tex) => { cloudMat.map = tex; cloudMat.needsUpdate = true; });
  scene.add(cloudMesh);

  // Lights
  scene.add(new THREE.AmbientLight(0x334455, 0.9));
  const sun = new THREE.DirectionalLight(0xffffff, 1.3);
  sun.position.set(5, 3, 5);
  scene.add(sun);

  // Equator circle
  const eqGeo = new THREE.TorusGeometry(1.01, 0.001, 8, 120);
  scene.add(new THREE.Mesh(eqGeo, new THREE.MeshBasicMaterial({color: 0x00d4ff, transparent: true, opacity: 0.25})));

  // Events
  const el = renderer.domElement;
  el.addEventListener('mousedown', e => { isDragging3D=true; autoRotate=false; prevMouse3D={x:e.clientX,y:e.clientY}; });
  el.addEventListener('mousemove', e => {
    if (!isDragging3D) return;
    targetRotY += (e.clientX - prevMouse3D.x) * 0.005;
    targetRotX += (e.clientY - prevMouse3D.y) * 0.005;
    targetRotX = Math.max(-1.4, Math.min(1.4, targetRotX));
    prevMouse3D = {x:e.clientX, y:e.clientY};
  });
  el.addEventListener('mouseup', () => { isDragging3D=false; });
  el.addEventListener('mouseleave', () => { isDragging3D=false; });
  el.addEventListener('wheel', e => { camera.position.z = Math.max(1.5, Math.min(8, camera.position.z + e.deltaY * 0.002)); }, {passive:true});
  el.addEventListener('click', onGlobeClick);
  window.addEventListener('resize', on3DResize);

  globeInited = true;
  animate3D();
  return true;
}

function animate3D() {
  animId = requestAnimationFrame(animate3D);
  if (autoRotate && !isDragging3D) targetRotY += 0.0012;
  rotX += (targetRotX - rotX) * 0.1;
  rotY += (targetRotY - rotY) * 0.1;
  if (earthMesh) { earthMesh.rotation.x = rotX; earthMesh.rotation.y = rotY; }
  if (cloudMesh) { cloudMesh.rotation.x = rotX; cloudMesh.rotation.y = rotY + 0.0002; }
  renderer && renderer.render(scene, camera);
}

function latLonToXYZ(lat, lon, r = 1.02) {
  const phi = (90 - lat) * Math.PI / 180;
  const theta = (lon + 180) * Math.PI / 180;
  return new THREE.Vector3(
    -r * Math.sin(phi) * Math.cos(theta),
    r * Math.cos(phi),
    r * Math.sin(phi) * Math.sin(theta)
  );
}

function altToRadius(alt) { return 1.0 + (alt / 6371) * 0.85; }

const SAT3D_COLORS = {'Space Station':0xffdd00,'Communication':0x00d4ff,'Navigation':0x00ff88,'Weather':0xff6b35,'Science':0xa855f7,'Debris':0xff3355,'Amateur':0x00ffdd,'Military':0xff9900,'Various':0x7799aa};

function updateGlobeSatellites(satellites) {
  if (!scene || !globeInited) return;
  const keep = new Set(satellites.map(s=>s.id));
  Object.keys(sat3DMarkers).forEach(id => { if(!keep.has(id)){scene.remove(sat3DMarkers[id]);delete sat3DMarkers[id];} });
  satellites.forEach(sat => {
    if (sat.lat==null || sat.lon==null) return;
    const r = altToRadius(sat.alt||400);
    const pos = latLonToXYZ(sat.lat, sat.lon, r);
    const isISS = sat.name?.includes('ISS');
    const color = SAT3D_COLORS[sat.sat_type||sat.type] || 0x00d4ff;
    if (!sat3DMarkers[sat.id]) {
      const geo = isISS ? new THREE.OctahedronGeometry(0.018) : new THREE.SphereGeometry(0.007,6,6);
      const mesh = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({color: isISS?0xffdd00:color}));
      mesh.userData = {sat};
      scene.add(mesh);
      sat3DMarkers[sat.id] = mesh;
    }
    sat3DMarkers[sat.id].position.copy(pos);
    sat3DMarkers[sat.id].userData.sat = sat;
  });
}

function onGlobeClick(e) {
  if (!renderer || !camera) return;
  const rect = renderer.domElement.getBoundingClientRect();
  const mouse = new THREE.Vector2(((e.clientX-rect.left)/rect.width)*2-1, -((e.clientY-rect.top)/rect.height)*2+1);
  const ray = new THREE.Raycaster();
  ray.setFromCamera(mouse, camera);
  const hits = ray.intersectObjects(Object.values(sat3DMarkers));
  if (hits.length > 0 && window.selectSatellite) {
    window.selectSatellite(hits[0].object.userData.sat?.id);
  }
}

function on3DResize() {
  if (!renderer || !camera || !globeContainer) return;
  const w = globeContainer.clientWidth, h = globeContainer.clientHeight;
  camera.aspect = w/h; camera.updateProjectionMatrix();
  renderer.setSize(w,h);
}

function draw3DOrbitPath(satId, path, color=0x00d4ff, opacity=0.65) {
  if (!scene || !path?.length) return;
  const pts = [];
  let prev = null;
  path.forEach(p => {
    const v = latLonToXYZ(p.lat, p.lon, altToRadius(p.alt||400));
    if (!prev || v.distanceTo(prev) < 0.6) pts.push(v);
    else { if(pts.length>1) addGlobeLine(pts.splice(0), color, opacity); pts.push(v); }
    prev = v;
  });
  if (pts.length > 1) addGlobeLine(pts, color, opacity);
}

function addGlobeLine(pts, color, opacity) {
  if (!scene) return;
  const geo = new THREE.BufferGeometry().setFromPoints(pts);
  const line = new THREE.Line(geo, new THREE.LineBasicMaterial({color, transparent:true, opacity}));
  scene.add(line);
  orbit3DLines.push(line);
}

function clearGlobeLines() {
  orbit3DLines.forEach(l => scene?.remove(l));
  orbit3DLines.length = 0;
}

function setGlobeMode(mode) {
  if (!earthMesh) return;
  if (mode==='night') earthMesh.material.color.set(0x112244);
  else if (mode==='orbit') earthMesh.material.color.set(0x0d1e33);
  else if (mode==='security') earthMesh.material.color.set(0x0a1a11);
  else earthMesh.material.color.set(earthMesh.material.map ? 0xffffff : 0x2266aa);
}

function zoomIn() {
  if (renderer) camera.position.z = Math.max(1.5, camera.position.z - 0.35);
  if (leafletMap) leafletMap.zoomIn();
}
function zoomOut() {
  if (renderer) camera.position.z = Math.min(8, camera.position.z + 0.35);
  if (leafletMap) leafletMap.zoomOut();
}
function resetView() {
  if (renderer) { camera.position.z=2.8; targetRotX=0; targetRotY=0; autoRotate=true; }
  if (leafletMap) { leafletMap.setView([20,0],2); }
}
function toggleAutoRotate() { autoRotate=!autoRotate; }
