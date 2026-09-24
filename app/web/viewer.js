"use strict";
/* ═══════════════════════════════════════════════════════════════════════
   3D viewer — displays the STL the OpenCASCADE kernel actually exported.

   The camera, orbit bindings and axis gizmo are carried over unchanged from
   the original Text2CAD shell, so the interaction feel is identical.  What
   changed is where geometry comes from: nothing is constructed in the
   browser any more.  The mesh on screen is the exported solid, so it cannot
   disagree with the CadQuery source shown beside it.

   Z is up, matching CadQuery's convention.
   ═══════════════════════════════════════════════════════════════════════ */

const Viewer = (() => {
  const host = document.querySelector("#gl");
  const scene = new THREE.Scene();
  const renderer = new THREE.WebGLRenderer({
    antialias: true, alpha: true, preserveDrawingBuffer: true,
  });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  host.appendChild(renderer.domElement);

  const cam = new THREE.PerspectiveCamera(38, 1, 0.5, 20000);
  const target = new THREE.Vector3();
  let dist = 300, theta = -Math.PI * 0.28, phi = Math.PI * 0.34;
  let spin = true, wire = false;

  scene.add(new THREE.HemisphereLight(0xEAEEF5, 0x4A4A4A, 0.85));
  const key = new THREE.DirectionalLight(0xffffff, 0.95);
  key.position.set(1, 0.7, 1.4); scene.add(key);
  const fill = new THREE.DirectionalLight(0xC9CFD8, 0.4);
  fill.position.set(-1.2, -0.6, 0.4); scene.add(fill);
  const rim = new THREE.DirectionalLight(0xffffff, 0.28);
  rim.position.set(0, -1, -1); scene.add(rim);

  // Against the design's #4C4C4C viewport rather than the old near-black
  // one: a grid mixed for a dark scene disappears on a mid grey.
  const grid = new THREE.GridHelper(600, 30, 0x6E6E6E, 0x5A5A5A);
  grid.rotation.x = Math.PI / 2; grid.position.z = -0.4;
  grid.material.transparent = true; grid.material.opacity = 0.55;
  scene.add(grid);

  let model = null, radius = 100, extents = null;

  /* ── STL parsing ──────────────────────────────────────────────────────
     CadQuery writes binary STL (80-byte header, uint32 triangle count, then
     50 bytes per facet).  ASCII is handled too, since a hand-supplied file
     may use it.  Parsing here rather than pulling in a loader keeps the app
     free of a second CDN dependency.                                      */

  function isAscii(buffer) {
    // A binary STL's size is exactly 84 + 50n. Trust that over sniffing for
    // the word "solid", which some binary writers also put in the header.
    if (buffer.byteLength < 84) return true;
    const count = new DataView(buffer).getUint32(80, true);
    if (84 + count * 50 === buffer.byteLength) return false;
    const head = new TextDecoder().decode(new Uint8Array(buffer, 0, 5));
    return head.trim().toLowerCase() === "solid";
  }

  function parseBinary(buffer) {
    const view = new DataView(buffer);
    const count = view.getUint32(80, true);
    const positions = new Float32Array(count * 9);
    const normals = new Float32Array(count * 9);
    let offset = 84;
    for (let i = 0; i < count; i++) {
      const nx = view.getFloat32(offset, true);
      const ny = view.getFloat32(offset + 4, true);
      const nz = view.getFloat32(offset + 8, true);
      offset += 12;
      for (let v = 0; v < 3; v++) {
        const p = i * 9 + v * 3;
        positions[p]     = view.getFloat32(offset, true);
        positions[p + 1] = view.getFloat32(offset + 4, true);
        positions[p + 2] = view.getFloat32(offset + 8, true);
        normals[p] = nx; normals[p + 1] = ny; normals[p + 2] = nz;
        offset += 12;
      }
      offset += 2; // attribute byte count
    }
    return { positions, normals };
  }

  function parseAscii(buffer) {
    const text = new TextDecoder().decode(new Uint8Array(buffer));
    const positions = [], normals = [];
    const facets = text.split(/facet\s+normal/i).slice(1);
    for (const facet of facets) {
      const n = facet.trim().split(/\s+/).slice(0, 3).map(Number);
      const verts = [...facet.matchAll(
        /vertex\s+(-?[\d.eE+]+)\s+(-?[\d.eE+]+)\s+(-?[\d.eE+]+)/gi)];
      for (const v of verts.slice(0, 3)) {
        positions.push(+v[1], +v[2], +v[3]);
        normals.push(n[0] || 0, n[1] || 0, n[2] || 1);
      }
    }
    return {
      positions: new Float32Array(positions),
      normals: new Float32Array(normals),
    };
  }

  function buildGeometry(buffer) {
    const { positions, normals } =
      isAscii(buffer) ? parseAscii(buffer) : parseBinary(buffer);
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute("normal", new THREE.BufferAttribute(normals, 3));
    geometry.computeBoundingBox();
    return geometry;
  }

  /* ── model management ─────────────────────────────────────────────── */

  function disposeAll(object) {
    object.traverse(node => {
      if (node.geometry) node.geometry.dispose();
      if (node.material) {
        (Array.isArray(node.material) ? node.material : [node.material])
          .forEach(m => m.dispose());
      }
    });
  }

  function eachMaterial(fn) {
    if (!model) return;
    model.traverse(node => {
      if (node.isMesh) fn(node.material, false);
      if (node.isLineSegments) fn(node.material, true);
    });
  }

  /* ── build reveal ─────────────────────────────────────────────────────
     A new version does not simply pop into place: it fades and scales up over
     ~0.4s so successive refinement iterations read as the part being reworked
     rather than as an unexplained flicker. `building` orbits the camera while
     the pipeline is running, independently of the user's own SPIN toggle.   */
  let reveal = 1;          // 0 → 1 while animating in
  let building = false;

  function startReveal() { reveal = 0; }

  function stepReveal() {
    if (reveal >= 1 || !model) return;
    reveal = Math.min(1, reveal + 0.042);
    const e = 1 - Math.pow(1 - reveal, 3);      // easeOutCubic
    model.scale.setScalar(0.93 + 0.07 * e);
    eachMaterial((m, isLine) => {
      m.transparent = true;
      m.opacity = (isLine ? 0.32 : 1) * e;
    });
    if (reveal >= 1) {
      model.scale.setScalar(1);
      applyModes();                              // restore exact final state
    }
  }

  function applyModes() {
    eachMaterial((m, isLine) => {
      m.needsUpdate = true;
      if (isLine) {
        m.opacity = wire ? 0.95 : 0.32;
      } else {
        m.transparent = wire;
        m.opacity = wire ? 0.06 : 1;
        m.depthWrite = !wire;
      }
    });
  }

  async function load(url) {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`Could not load model (${response.status})`);
    const geometry = buildGeometry(await response.arrayBuffer());

    const group = new THREE.Group();
    const mesh = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({
      color: 0xE8E8E6, metalness: 0.08, roughness: 0.62,
      flatShading: false, side: THREE.DoubleSide,
    }));
    group.add(mesh);

    // Feature edges at 22 degrees, the same threshold the original shell used.
    const edges = new THREE.LineSegments(
      new THREE.EdgesGeometry(geometry, 22),
      new THREE.LineBasicMaterial({
        color: 0x8A8A88, transparent: true, opacity: 0.38,
      }));
    group.add(edges);

    setModel(group, geometry.boundingBox);
    startReveal();
    return geometry.boundingBox;
  }

  function setModel(group, box) {
    if (model) { scene.remove(model); disposeAll(model); }
    model = group; scene.add(group);

    const centre = box.getCenter(new THREE.Vector3());
    group.position.sub(centre);          // orbit about the part, not the origin
    const size = box.getSize(new THREE.Vector3());
    extents = size;
    radius = Math.max(size.x, size.y, size.z, 1) * 0.62;
    grid.scale.setScalar(Math.max(0.5, radius / 100));
    applyModes();

    const step = Math.max(5, Math.round(radius / 2 / 5) * 5);
    const scaleText = document.querySelector("#scaleTxt");
    if (scaleText) scaleText.textContent = `${step} mm`;
  }

  function clear() {
    if (model) { scene.remove(model); disposeAll(model); model = null; }
    extents = null;
  }

  /* ── camera ───────────────────────────────────────────────────────── */

  const ease = k => 1 - Math.pow(1 - k, 3);
  let tween = null;

  function fit(animate) {
    const d = radius / Math.tan(cam.fov * Math.PI / 360) * 1.45;
    if (!animate) { dist = d; return; }
    const from = dist, t0 = performance.now();
    tween = () => {
      const k = Math.min(1, (performance.now() - t0) / 420);
      dist = from + (d - from) * ease(k);
      if (k >= 1) tween = null;
    };
  }

  function view(name, animate) {
    const angles = {
      iso: [-Math.PI * 0.28, Math.PI * 0.34],
      front: [-Math.PI / 2, Math.PI / 2],
      top: [-Math.PI / 2, 0.0001],
      right: [0, Math.PI / 2],
    }[name];
    if (!angles) return;
    spin = false;
    if (!animate) { theta = angles[0]; phi = angles[1]; return; }
    const t0 = performance.now(), from = [theta, phi];
    let to = angles[0];
    while (to - from[0] > Math.PI) to -= Math.PI * 2;
    while (to - from[0] < -Math.PI) to += Math.PI * 2;
    tween = () => {
      const k = Math.min(1, (performance.now() - t0) / 480), e = ease(k);
      theta = from[0] + (to - from[0]) * e;
      phi = from[1] + (angles[1] - from[1]) * e;
      if (k >= 1) tween = null;
    };
  }

  /* LMB rotate · MMB/Ctrl pan · RMB/Shift zoom · wheel zoom */
  let drag = null;
  const canvas = renderer.domElement;
  canvas.addEventListener("contextmenu", e => e.preventDefault());
  canvas.addEventListener("pointerdown", e => {
    canvas.setPointerCapture(e.pointerId);
    const mode = (e.button === 1 || e.ctrlKey) ? "pan"
               : (e.button === 2 || e.shiftKey) ? "zoom" : "rot";
    drag = { mode, x: e.clientX, y: e.clientY };
    spin = false;
    document.querySelector("#spinBtn").classList.remove("on");
  });
  canvas.addEventListener("pointermove", e => {
    if (!drag) return;
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    drag.x = e.clientX; drag.y = e.clientY;
    if (drag.mode === "rot") {
      theta -= dx * 0.0075;
      phi = Math.max(0.02, Math.min(Math.PI - 0.02, phi - dy * 0.0075));
    } else if (drag.mode === "zoom") {
      dist = Math.max(radius * 0.35, Math.min(radius * 22, dist * (1 + dy * 0.006)));
    } else {
      const s = dist * 0.0016;
      const right = new THREE.Vector3()
        .subVectors(cam.position, target).cross(cam.up).normalize();
      const up = new THREE.Vector3().crossVectors(
        right, new THREE.Vector3().subVectors(cam.position, target)).normalize();
      target.addScaledVector(right, -dx * s).addScaledVector(up, -dy * s);
    }
  });
  addEventListener("pointerup", () => { drag = null; });
  canvas.addEventListener("wheel", e => {
    e.preventDefault();
    dist = Math.max(radius * 0.35,
      Math.min(radius * 22, dist * (1 + Math.sign(e.deltaY) * 0.11)));
  }, { passive: false });

  function resize() {
    const w = host.clientWidth, h = host.clientHeight;
    if (!w || !h) return;
    /* setSize must update the canvas CSS size as well as its drawing buffer.
       Passing false left the element with no CSS size at all, so the browser
       laid it out at its width/height attributes - which setPixelRatio had
       multiplied by the display's ratio. On a 2x screen the canvas was drawn
       twice the size of the stage: the grid and the model spilled over the
       right-hand cards, which is what read as the panels being see-through,
       and the overflow swallowed clicks meant for the sliders underneath. */
    renderer.setSize(w, h);
    cam.aspect = w / h;
    cam.updateProjectionMatrix();
  }
  new ResizeObserver(resize).observe(host);
  resize();

  /* The gizmo is a control, not an ornament: it took over from the ISO,
     FRONT, TOP and RIGHT buttons, so each arm is a hit target that looks
     down its own axis, and the hub returns to the isometric. Clicking an
     axis is how every CAD package does this, which is the point - four
     buttons replaced by the thing people already reach for. */
  const axisGroup = document.querySelector("#axG");
  const AXIS_VIEW = { X: "right", Y: "front", Z: "top" };
  function drawAxes() {
    const R = 23, cx = 30, cy = 30;
    const dirs = [
      ["X", new THREE.Vector3(1, 0, 0), "#F2606A"],
      ["Y", new THREE.Vector3(0, 1, 0), "#3DD68C"],
      ["Z", new THREE.Vector3(0, 0, 1), "#4D8DF6"],
    ];
    let svg = `<circle cx="${cx}" cy="${cy}" r="6" fill="#FFBE44" stroke="none"/>`
            + `<circle cx="${cx}" cy="${cy}" r="3" fill="#1E1E1E" stroke="none"/>`;
    // Rotate each axis into camera space, rather than projecting a point.
    //
    // This used to call project() on the world points (1,0,0), (0,1,0) and
    // (0,0,1) - absolute positions, not directions. Their screen positions
    // converge as the camera pulls away from the origin, so the three arms
    // collapsed towards a single spot and the labels stacked on top of each
    // other: on a 44mm part 300 units out, every arm came back at the 12.65
    // floor and the gizmo read as one smudged glyph. It also depended on
    // where `target` happened to be, so the same camera angle drew a
    // different gizmo for a part modelled away from the origin.
    //
    // A direction has no position, so the rotation is the whole answer: x is
    // rightwards on screen and y upwards, foreshortening falls out of their
    // magnitude, and the result is the same at any distance.
    const toView = new THREE.Matrix4().extractRotation(cam.matrixWorldInverse);
    for (const [name, vector, colour] of dirs) {
      // An axis pointing straight at the camera still foreshortens to almost
      // nothing, so keep the direction and keep some foreshortening, but
      // never let an arm disappear under the hub drawn over it.
      const p = vector.clone().applyMatrix4(toView);
      const len = Math.hypot(p.x, p.y) || 1e-6;
      const reach = R * Math.min(1, 0.55 + 0.45 * len);
      const x = cx + (p.x / len) * reach, y = cy - (p.y / len) * reach;
      const lx = cx + (x - cx) * 1.22, ly = cy + (y - cy) * 1.22;
      svg += `<line x1="${cx}" y1="${cy}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}" stroke="${colour}"/>`;
      svg += `<text x="${lx.toFixed(1)}" y="${(ly + 3).toFixed(1)}" fill="${colour}" font-size="8" font-family="monospace" text-anchor="middle" stroke="none">${name}</text>`;
      svg += `<circle class="axhit" data-view="${AXIS_VIEW[name]}" cx="${lx.toFixed(1)}" cy="${ly.toFixed(1)}" r="6.5"><title>${name}</title></circle>`;
    }
    svg += `<circle class="axhit" data-view="iso" cx="${cx}" cy="${cy}" r="6"><title>ISO</title></circle>`;
    // Only when it actually changed. This runs once per animation frame, so
    // rewriting unconditionally replaced the hit targets sixty times a
    // second - which is a lot of DOM for a still camera, and means the
    // circles are never the same element long enough to be clicked.
    if (svg !== lastAxes) {
      lastAxes = svg;
      axisGroup.innerHTML = svg;
    }
  }
  let lastAxes = "";

  /* The gizmo orbits as well as snaps.
     It is the part of the viewport a hand already goes to, and dragging it
     is how every CAD tool spins a model - so it drives the same theta/phi
     the canvas does. A press that does not move is still a click: release
     within a few pixels and the axis under it snaps the view, which is what
     the hit circles are for. Anything further is a turn, and the click is
     swallowed so the view does not jump at the end of it. */
  const gizmo = document.querySelector("#axes");
  let spun = null;
  gizmo.addEventListener("pointerdown", event => {
    // Which arm was under the finger, read now: capturing the pointer
    // retargets every later event to the gizmo itself, so by pointerup the
    // circle that was pressed is no longer the event's target.
    const hit = event.target.closest(".axhit");
    gizmo.setPointerCapture(event.pointerId);
    spun = { x: event.clientX, y: event.clientY, moved: 0, hit };
    spin = false;
    document.querySelector("#spinBtn").classList.remove("on");
    event.preventDefault();
  });
  gizmo.addEventListener("pointermove", event => {
    if (!spun) return;
    const dx = event.clientX - spun.x, dy = event.clientY - spun.y;
    spun.x = event.clientX; spun.y = event.clientY;
    spun.moved += Math.abs(dx) + Math.abs(dy);
    // Faster than the canvas: the gizmo is 116px across, so the same wrist
    // movement has a tenth of the room and would barely turn the part.
    theta -= dx * 0.022;
    phi = Math.max(0.02, Math.min(Math.PI - 0.02, phi - dy * 0.022));
  });
  gizmo.addEventListener("pointerup", () => {
    const press = spun;
    spun = null;
    if (!press || press.moved > 4 || !press.hit) return;
    if (api.onView) api.onView(press.hit.dataset.view);
    view(press.hit.dataset.view, true);
  });
  gizmo.addEventListener("pointercancel", () => { spun = null; });

  (function loop() {
    requestAnimationFrame(loop);
    if (tween) tween();
    stepReveal();
    if ((spin || building) && model) theta += building && !spin ? 0.0022 : 0.0034;
    cam.position.set(
      target.x + dist * Math.sin(phi) * Math.cos(theta),
      target.y + dist * Math.sin(phi) * Math.sin(theta),
      target.z + dist * Math.cos(phi));
    cam.up.set(0, 0, 1);
    cam.lookAt(target);
    renderer.render(scene, cam);
    drawAxes();
  })();

  const api = {
    load, clear, fit, view,
    //: Set by the app so the Spin chip can un-light itself when a fixed
    //: view is chosen from the gizmo.
    onView: null,
    get spin() { return spin; },
    set spin(v) { spin = v; },
    //: Slow orbit while the pipeline works, without touching the SPIN toggle.
    get building() { return building; },
    set building(v) { building = !!v; },
    get extents() { return extents; },
    toggleWire() { wire = !wire; applyModes(); return wire; },
    snapshot(white) {
      const background = scene.background;
      if (white) {
        scene.background = new THREE.Color(0xffffff);
        eachMaterial((m, isLine) => {
          if (isLine) { m.color.set(0x000000); m.opacity = 1; }
          else { m.transparent = true; m.opacity = 0; }
        });
      }
      renderer.render(scene, cam);
      const url = renderer.domElement.toDataURL("image/png");
      if (white) {
        scene.background = background;
        eachMaterial((m, isLine) => { if (isLine) m.color.set(0x8A8A88); });
        applyModes();
      }
      return url;
    },
  };

  return api;
})();
