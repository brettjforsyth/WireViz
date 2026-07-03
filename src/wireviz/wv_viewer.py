# -*- coding: utf-8 -*-
"""Self-contained interactive HTML viewer for a harness.

Wraps the native grid-snapped SVG (:mod:`wireviz.wv_svg`) in a single HTML file
with pan, zoom, a toggleable snap grid, fit-to-view, and wire hover
highlighting. It has no external dependencies (no CDN scripts, no fonts), so it
works offline and can be opened straight from disk or embedded anywhere.

The harness layout JSON is embedded too, so the same file is both a viewer and
a portable data carrier for downstream tooling.
"""

from typing import Optional

from wireviz.wv_svg import GridConfig, build_layout, export_json, render_svg

_STYLE = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { margin: 0; font-family: system-ui, sans-serif; background: #fafafa;
       color: #111; }
@media (prefers-color-scheme: dark) {
  body { background: #1e1e1e; color: #eee; }
  .toolbar { background: #2a2a2a; border-color: #444; }
  button { background: #333; color: #eee; border-color: #555; }
}
.toolbar { position: fixed; top: 0; left: 0; right: 0; height: 44px;
  display: flex; gap: 8px; align-items: center; padding: 0 12px;
  background: #fff; border-bottom: 1px solid #ddd; z-index: 10; }
.toolbar .title { font-weight: 600; margin-right: auto; }
button { border: 1px solid #ccc; border-radius: 6px; padding: 5px 10px;
  background: #f4f4f4; cursor: pointer; font-size: 13px; }
button:hover { filter: brightness(0.96); }
#stage { position: absolute; top: 44px; left: 0; right: 0; bottom: 0;
  overflow: hidden; cursor: grab; }
#stage.grabbing { cursor: grabbing; }
#stage svg { width: 100%; height: 100%; touch-action: none; }
.wire:hover, .wire-core:hover { stroke-width: 5; }
.wire-core:hover { stroke-width: 3.5; }
.hint { position: fixed; bottom: 8px; right: 12px; font-size: 12px;
  opacity: 0.6; }
""".strip()


_SCRIPT = """
(function () {
  const svg = document.getElementById('harness-svg');
  const stage = document.getElementById('stage');
  const vb = { x: 0, y: 0, w: DATA.width, h: DATA.height };
  const home = { ...vb };
  function apply() {
    svg.setAttribute('viewBox', `${vb.x} ${vb.y} ${vb.w} ${vb.h}`);
  }
  function fit() { Object.assign(vb, home); apply(); }
  // zoom on wheel, centred on the cursor
  stage.addEventListener('wheel', (e) => {
    e.preventDefault();
    const r = stage.getBoundingClientRect();
    const mx = vb.x + (e.clientX - r.left) / r.width * vb.w;
    const my = vb.y + (e.clientY - r.top) / r.height * vb.h;
    const k = e.deltaY > 0 ? 1.1 : 0.9;
    vb.w *= k; vb.h *= k;
    vb.x = mx - (e.clientX - r.left) / r.width * vb.w;
    vb.y = my - (e.clientY - r.top) / r.height * vb.h;
    apply();
  }, { passive: false });
  // pan on drag
  let drag = null;
  stage.addEventListener('pointerdown', (e) => {
    drag = { x: e.clientX, y: e.clientY };
    stage.classList.add('grabbing');
    stage.setPointerCapture(e.pointerId);
  });
  stage.addEventListener('pointermove', (e) => {
    if (!drag) return;
    const r = stage.getBoundingClientRect();
    vb.x -= (e.clientX - drag.x) / r.width * vb.w;
    vb.y -= (e.clientY - drag.y) / r.height * vb.h;
    drag = { x: e.clientX, y: e.clientY };
    apply();
  });
  const end = () => { drag = null; stage.classList.remove('grabbing'); };
  stage.addEventListener('pointerup', end);
  stage.addEventListener('pointerleave', end);
  document.getElementById('fit').addEventListener('click', fit);
  document.getElementById('grid').addEventListener('click', () => {
    const g = svg.querySelector('rect[fill^="url(#grid"]');
    if (g) g.style.display = g.style.display === 'none' ? '' : 'none';
  });
  document.getElementById('zin').addEventListener('click', () => {
    vb.w *= 0.8; vb.h *= 0.8; apply();
  });
  document.getElementById('zout').addEventListener('click', () => {
    vb.w *= 1.25; vb.h *= 1.25; apply();
  });
  apply();
})();
""".strip()


def render_html(
    harness, config: Optional[GridConfig] = None, title: Optional[str] = None
) -> str:
    """Return a standalone interactive HTML viewer for `harness`."""
    cfg = config or GridConfig()
    svg = render_svg(harness, cfg)
    # give the <svg> an id so the viewer script can drive its viewBox
    svg = svg.replace("<svg ", '<svg id="harness-svg" ', 1)
    layout_json = export_json(harness, cfg, indent=0)
    if title is None:
        title = (harness.metadata.get("title") if harness.metadata else None) or "Harness"

    from html import escape

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>{_STYLE}</style>
</head>
<body>
<div class="toolbar">
  <span class="title">{escape(title)}</span>
  <button id="zin">Zoom in</button>
  <button id="zout">Zoom out</button>
  <button id="fit">Fit</button>
  <button id="grid">Grid</button>
</div>
<div id="stage">{svg}</div>
<div class="hint">drag to pan &middot; scroll to zoom</div>
<script>const DATA = {layout_json};</script>
<script>{_SCRIPT}</script>
</body>
</html>
"""


# --- 3D viewer -------------------------------------------------------------

# three.js r128 exposes a global THREE and ships OrbitControls under
# examples/js. Loaded from a CDN, so the 3D viewer (unlike the 2D one) needs
# internet the first time it is opened.
_THREE_CDN = "https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"
_ORBIT_CDN = (
    "https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"
)

_SCRIPT_3D = """
(function () {
  const W = DATA.width, H = DATA.height;
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x1e1e1e);
  const el = document.getElementById('stage3d');
  const camera = new THREE.PerspectiveCamera(
    55, el.clientWidth / el.clientHeight, 1, 100000);
  camera.position.set(0, Math.max(W, H) * 0.8, Math.max(W, H) * 0.9);
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setSize(el.clientWidth, el.clientHeight);
  renderer.setPixelRatio(window.devicePixelRatio);
  el.appendChild(renderer.domElement);
  const controls = new THREE.OrbitControls(camera, renderer.domElement);
  scene.add(new THREE.AmbientLight(0xffffff, 0.7));
  const dir = new THREE.DirectionalLight(0xffffff, 0.8);
  dir.position.set(1, 2, 1);
  scene.add(dir);
  scene.add(new THREE.GridHelper(Math.max(W, H) * 2, 40, 0x555555, 0x333333));
  // map 2D layout (x right, y down) to 3D (x, z); extrude up in y
  const cx = W / 2, cz = H / 2, BOX = 30;
  for (const name in DATA.nodes) {
    const n = DATA.nodes[name];
    const geo = new THREE.BoxGeometry(n.w, BOX, n.h);
    const color = n.kind === 'connector' ? 0x4a78d0 : 0x888888;
    const mesh = new THREE.Mesh(geo,
      new THREE.MeshLambertMaterial({ color }));
    mesh.position.set(n.x + n.w / 2 - cx, BOX / 2, n.y + n.h / 2 - cz);
    scene.add(mesh);
  }
  const WY = BOX + 8;
  for (const w of DATA.wires) {
    const pts = w.points.map(p => new THREE.Vector3(p[0] - cx, WY, p[1] - cz));
    const geo = new THREE.BufferGeometry().setFromPoints(pts);
    const col = new THREE.Color(w.color || '#000000');
    scene.add(new THREE.Line(geo, new THREE.LineBasicMaterial({ color: col })));
  }
  function resize() {
    camera.aspect = el.clientWidth / el.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(el.clientWidth, el.clientHeight);
  }
  window.addEventListener('resize', resize);
  (function loop() {
    requestAnimationFrame(loop);
    controls.update();
    renderer.render(scene, camera);
  })();
})();
""".strip()

_STYLE_3D = """
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body { margin: 0; background: #1e1e1e; color: #eee;
       font-family: system-ui, sans-serif; overflow: hidden; }
.toolbar { position: fixed; top: 0; left: 0; right: 0; height: 44px;
  display: flex; gap: 8px; align-items: center; padding: 0 12px;
  background: #2a2a2a; border-bottom: 1px solid #444; z-index: 10; }
.toolbar .title { font-weight: 600; }
#stage3d { position: absolute; top: 44px; left: 0; right: 0; bottom: 0; }
.hint { position: fixed; bottom: 8px; right: 12px; font-size: 12px;
  opacity: 0.6; }
.nowebgl { padding: 20px; }
""".strip()


def render_html_3d(
    harness, config: Optional[GridConfig] = None, title: Optional[str] = None
) -> str:
    """Return an interactive three.js 3D viewer for `harness`.

    Requires internet the first time it is opened (three.js is loaded from a
    CDN). Components render as 3D blocks and wires as lines routed in 3D on the
    same grid layout as the 2D renderer.
    """
    cfg = config or GridConfig()
    layout_json = export_json(harness, cfg, indent=0)
    if title is None:
        title = (harness.metadata.get("title") if harness.metadata else None) or "Harness 3D"

    from html import escape

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>{_STYLE_3D}</style>
</head>
<body>
<div class="toolbar"><span class="title">{escape(title)} &mdash; 3D</span>
  <span class="hint" style="position:static">drag to orbit &middot; scroll to zoom</span>
</div>
<div id="stage3d"><noscript class="nowebgl">Enable JavaScript to view the 3D harness.</noscript></div>
<script src="{_THREE_CDN}"></script>
<script src="{_ORBIT_CDN}"></script>
<script>const DATA = {layout_json};</script>
<script>{_SCRIPT_3D}</script>
</body>
</html>
"""
