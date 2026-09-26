let MAP_DATA = null;
let ALL_LAYERS = [];
let GL_MAP = null;
let MAP_ID = null;
let SELECTED_SHARE_USER = null;
const ADDED_MAPBOX_LAYER_IDS = [];

function tableNameFromTileUrl(tileUrl) {
  return (tileUrl || "").split("/").filter(Boolean).pop();
}

function sourceLayerName(layer) {
  return layer.source_layer || tableNameFromTileUrl(layer.tile_url);
}

function hasUsableBounds(bounds) {
  return (
    Array.isArray(bounds) &&
    bounds.length === 4 &&
    bounds.every((v) => typeof v === "number" && Number.isFinite(v))
  );
}

async function init() {
  const root = document.getElementById("builder-root");
  mapboxgl.accessToken = root.dataset.mapboxToken || "";
  MAP_ID = root.dataset.mapId || "";
  await loadMap();
}

async function loadMap() {
  const res = await Auth.apiFetch(`/api/maps/${MAP_ID}/`);
  if (!res.ok) {
    document.getElementById("builder-panel").innerHTML = `<div class="builder-error"><p class="muted">Map not found or access denied.</p></div>`;
    return;
  }
  MAP_DATA = await res.json();

  const nameInput = document.getElementById("map-name-input");
  nameInput.value = MAP_DATA.name;
  nameInput.readOnly = true;
  nameInput.classList.remove("is-editing");

  document.getElementById("basemap-select").value = MAP_DATA.basemap_style;

  const readOnly = MAP_DATA.my_permission === "view";
  const accessValue = document.getElementById("permission-value");
  const accessBadge = document.getElementById("access-badge");
  accessBadge.classList.remove("is-owner", "is-edit", "is-view");
  if (readOnly) {
    accessValue.textContent = "View only";
    accessBadge.classList.add("is-view");
  } else if (MAP_DATA.my_permission === "owner") {
    accessValue.textContent = "Owner";
    accessBadge.classList.add("is-owner");
  } else {
    accessValue.textContent = "Can edit";
    accessBadge.classList.add("is-edit");
  }

  document.getElementById("save-map-btn").classList.toggle("hidden", readOnly);
  document.getElementById("share-map-btn").classList.toggle("hidden", MAP_DATA.my_permission !== "owner");
  document.getElementById("edit-map-name-btn").classList.toggle("hidden", readOnly);
  document.getElementById("basemap-select").disabled = readOnly;
  document.getElementById("available-layers-section").classList.toggle("hidden", readOnly);

  if (!GL_MAP) {
    GL_MAP = new mapboxgl.Map({
      container: "map-canvas",
      style: MAP_DATA.basemap_style,
      center: [MAP_DATA.center_lng, MAP_DATA.center_lat],
      zoom: MAP_DATA.zoom,
    });
    GL_MAP.addControl(new mapboxgl.NavigationControl(), "top-right");
    GL_MAP.on("load", () => {
      renderMapLayers();
      // Always frame layer extents when the map still has the create defaults,
      // or when layers exist but the saved view is empty ocean (0,0).
      if (shouldAutoFitOnLoad()) fitMapToLayers({ animate: true });
    });
  } else {
    renderMapLayers();
  }

  renderActiveLayers();
  if (!readOnly) await loadAvailableLayers();

  document.getElementById("save-map-btn").onclick = saveMapMeta;
  document.getElementById("share-map-btn").onclick = () => openShareModal();
  document.getElementById("basemap-select").onchange = (event) => {
    GL_MAP.setStyle(event.target.value);
    GL_MAP.once("style.load", renderMapLayers);
  };
}

function setMapNameEditing(enabled) {
  const input = document.getElementById("map-name-input");
  const btn = document.getElementById("edit-map-name-btn");
  if (!input || !btn || btn.classList.contains("hidden")) return;
  input.readOnly = !enabled;
  input.classList.toggle("is-editing", enabled);
  btn.classList.toggle("is-active", enabled);
  btn.title = enabled ? "Done editing" : "Edit map name";
  btn.setAttribute("aria-label", enabled ? "Done editing" : "Edit map name");
  if (enabled) {
    input.focus();
    input.select();
  } else {
    input.blur();
  }
}

document.getElementById("edit-map-name-btn").addEventListener("mousedown", (event) => {
  event.preventDefault();
});

document.getElementById("edit-map-name-btn").addEventListener("click", () => {
  const input = document.getElementById("map-name-input");
  setMapNameEditing(input.readOnly);
});

document.getElementById("map-name-input").addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    setMapNameEditing(false);
  }
  if (event.key === "Escape") {
    event.preventDefault();
    event.target.value = MAP_DATA?.name || event.target.value;
    setMapNameEditing(false);
  }
});

document.getElementById("map-name-input").addEventListener("blur", () => {
  setMapNameEditing(false);
});

function layerControlIcon(name) {
  const icons = {
    up: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14"/><path d="M6 11l6-6 6 6"/></svg>',
    down: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 19V5"/><path d="M6 13l6 6 6-6"/></svg>',
    remove: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>',
  };
  return icons[name] || "";
}

function renderActiveLayers() {
  const container = document.getElementById("active-layers");
  const layers = [...MAP_DATA.map_layers].sort((a, b) => b.order - a.order);
  const readOnly = MAP_DATA.my_permission === "view";

  if (!layers.length) {
    container.innerHTML = `<div class="builder-empty">No layers added yet.</div>`;
    return;
  }

  container.innerHTML = layers.map((ml) => `
    <div class="builder-layer-card" data-map-layer-id="${ml.id}">
      <div class="builder-layer-top">
        <label class="builder-layer-check">
          <input type="checkbox" data-toggle-visible ${ml.visible ? "checked" : ""} ${readOnly ? "disabled" : ""}>
          <span class="layer-name">${ml.layer_detail.name}</span>
        </label>
        ${!readOnly ? `
          <div class="builder-layer-actions">
            <button type="button" class="layer-icon-btn" data-move="up" title="Bring forward" aria-label="Bring forward">${layerControlIcon("up")}</button>
            <button type="button" class="layer-icon-btn" data-move="down" title="Send back" aria-label="Send back">${layerControlIcon("down")}</button>
            <button type="button" class="layer-icon-btn is-danger" data-remove title="Remove from map" aria-label="Remove from map">${layerControlIcon("remove")}</button>
          </div>
        ` : ""}
      </div>
      <div class="builder-layer-opacity">
        <span class="builder-opacity-label">Opacity</span>
        <input type="range" min="0" max="1" step="0.05" value="${ml.opacity}" data-opacity ${readOnly ? "disabled" : ""}>
      </div>
    </div>
  `).join("");

  container.querySelectorAll("[data-map-layer-id]").forEach((row) => {
    const mapLayerId = row.dataset.mapLayerId;
    row.querySelector("[data-toggle-visible]").addEventListener("change", (e) => {
      updateMapLayer(mapLayerId, { visible: e.target.checked });
    });
    const opacityInput = row.querySelector("[data-opacity]");
    if (opacityInput) {
      opacityInput.addEventListener("change", (e) => {
        updateMapLayer(mapLayerId, { opacity: parseFloat(e.target.value) });
      });
    }
    const removeBtn = row.querySelector("[data-remove]");
    if (removeBtn) removeBtn.addEventListener("click", () => removeMapLayer(mapLayerId));
    row.querySelectorAll("[data-move]").forEach((btn) => {
      btn.addEventListener("click", () => moveLayer(mapLayerId, btn.dataset.move));
    });
  });
}

async function loadAvailableLayers() {
  const res = await Auth.apiFetch("/api/layers/?page_size=200");
  const data = await res.json();
  ALL_LAYERS = data.results || data;
  renderAvailableLayers();
}

function renderAvailableLayers() {
  const container = document.getElementById("available-layers");
  const onMapIds = new Set(MAP_DATA.map_layers.map((ml) => ml.layer_detail.id));
  const remaining = ALL_LAYERS.filter((l) => !onMapIds.has(l.id));

  if (!remaining.length) {
    container.innerHTML = `<div class="builder-empty">All your layers are already on this map.</div>`;
    return;
  }

  container.innerHTML = remaining.map((l) => `
    <div class="builder-layer-card is-available">
      <span class="layer-name">${l.name}</span>
      <button type="button" class="btn btn-sm btn-primary" data-add-layer="${l.id}">Add</button>
    </div>
  `).join("");

  container.querySelectorAll("[data-add-layer]").forEach((btn) => {
    btn.addEventListener("click", () => addLayerToMap(btn.dataset.addLayer));
  });
}

async function addLayerToMap(layerId) {
  const res = await Auth.apiFetch(`/api/maps/${MAP_ID}/layers/`, {
    method: "POST",
    body: { layer: layerId },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    alert(body.detail || "Could not add layer to map.");
    return;
  }
  await refreshAfterLayerChange();
  // Fit immediately, then once more after the style/sources settle.
  fitMapToLayers({ preferLayerId: layerId });
  window.setTimeout(() => fitMapToLayers({ preferLayerId: layerId, animate: true }), 400);
}

async function removeMapLayer(mapLayerId) {
  await Auth.apiFetch(`/api/maps/${MAP_ID}/layers/${mapLayerId}/`, { method: "DELETE" });
  await refreshAfterLayerChange();
}

function shouldAutoFitOnLoad() {
  if (!MAP_DATA?.map_layers?.length) return false;
  const nearNullIsland =
    Math.abs(MAP_DATA.center_lng) < 0.01 && Math.abs(MAP_DATA.center_lat) < 0.01;
  const lowZoom = (MAP_DATA.zoom ?? 0) <= 3;
  return nearNullIsland || lowZoom;
}

function fitMapToLayers({ preferLayerId = null, animate = true } = {}) {
  if (!GL_MAP || !MAP_DATA) return false;

  let boundsList = [];
  if (preferLayerId) {
    const preferred = MAP_DATA.map_layers.find(
      (ml) => String(ml.layer_detail.id) === String(preferLayerId)
    );
    if (hasUsableBounds(preferred?.layer_detail?.bounds)) {
      boundsList = [preferred.layer_detail.bounds];
    }
  }
  if (!boundsList.length) {
    boundsList = MAP_DATA.map_layers
      .map((ml) => ml.layer_detail?.bounds)
      .filter(hasUsableBounds);
  }
  if (!boundsList.length) return false;

  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  boundsList.forEach(([x1, y1, x2, y2]) => {
    minX = Math.min(minX, x1, x2);
    minY = Math.min(minY, y1, y2);
    maxX = Math.max(maxX, x1, x2);
    maxY = Math.max(maxY, y1, y2);
  });
  if (![minX, minY, maxX, maxY].every(Number.isFinite)) return false;

  // Degenerate point extent
  if (Math.abs(minX - maxX) < 1e-9 && Math.abs(minY - maxY) < 1e-9) {
    GL_MAP.flyTo({ center: [minX, minY], zoom: 12, essential: true });
    return true;
  }

  // Tiny extents still need a sensible zoom
  const pad = 48;
  GL_MAP.fitBounds(
    [[minX, minY], [maxX, maxY]],
    { padding: pad, maxZoom: 16, duration: animate ? 900 : 0, essential: true }
  );
  return true;
}


async function updateMapLayer(mapLayerId, payload) {
  await Auth.apiFetch(`/api/maps/${MAP_ID}/layers/${mapLayerId}/`, { method: "PATCH", body: payload });
  await refreshAfterLayerChange();
}

async function moveLayer(mapLayerId, direction) {
  const sorted = [...MAP_DATA.map_layers].sort((a, b) => a.order - b.order);
  const idx = sorted.findIndex((ml) => String(ml.id) === String(mapLayerId));
  const swapWith = direction === "up" ? idx + 1 : idx - 1;
  if (swapWith < 0 || swapWith >= sorted.length) return;
  [sorted[idx], sorted[swapWith]] = [sorted[swapWith], sorted[idx]];

  await Auth.apiFetch(`/api/maps/${MAP_ID}/reorder/`, {
    method: "POST",
    body: { order: sorted.map((ml) => ml.id) },
  });
  await refreshAfterLayerChange();
}

async function refreshAfterLayerChange() {
  const res = await Auth.apiFetch(`/api/maps/${MAP_ID}/`);
  MAP_DATA = await res.json();
  renderActiveLayers();
  renderAvailableLayers();
  renderMapLayers();
}

function clearMapboxLayers() {
  while (ADDED_MAPBOX_LAYER_IDS.length) {
    const id = ADDED_MAPBOX_LAYER_IDS.pop();
    if (GL_MAP.getLayer(id)) GL_MAP.removeLayer(id);
  }
  // Drop vector sources too so re-added layers always pick up fresh tile URLs
  // (critical after delete + re-upload of the same logical dataset).
  const style = GL_MAP.getStyle();
  const sources = style?.sources || {};
  Object.keys(sources).forEach((sourceId) => {
    if (sourceId.startsWith("src-") && GL_MAP.getSource(sourceId)) {
      GL_MAP.removeSource(sourceId);
    }
  });
}

function renderMapLayers() {
  if (!GL_MAP) return;
  if (!GL_MAP.isStyleLoaded()) {
    GL_MAP.once("style.load", () => renderMapLayers());
    return;
  }
  clearMapboxLayers();

  const sorted = [...MAP_DATA.map_layers].sort((a, b) => a.order - b.order);
  sorted.forEach((ml) => addMapboxLayer(ml));
}

function addMapboxLayer(mapLayer) {
  const layer = mapLayer.layer_detail;
  if (!layer?.tile_url) return;

  const sourceId = `src-${layer.id}`;
  const tableName = sourceLayerName(layer);
  if (!tableName) return;

  if (GL_MAP.getSource(sourceId)) {
    GL_MAP.removeSource(sourceId);
  }

  GL_MAP.addSource(sourceId, {
    type: "vector",
    tiles: [`${layer.tile_url.replace(/\/$/, "")}/{z}/{x}/{y}`],
    minzoom: 0,
    maxzoom: 22,
  });

  const style = { ...(layer.style || {}), ...(mapLayer.style_override || {}) };
  const visibility = mapLayer.visible ? "visible" : "none";
  const geomType = layer.geometry_type || "";

  if (geomType === "Point" || geomType === "MultiPoint") {
    const id = `layer-${mapLayer.id}-circle`;
    GL_MAP.addLayer({
      id, source: sourceId, "source-layer": tableName, type: "circle",
      layout: { visibility },
      paint: {
        "circle-color": style.color || "#0F2D53",
        "circle-radius": 5,
        "circle-stroke-color": style.strokeColor || "#0a2140",
        "circle-stroke-width": style.strokeWidth ?? 1,
        "circle-opacity": mapLayer.opacity ?? style.opacity ?? 0.8,
      },
    });
    ADDED_MAPBOX_LAYER_IDS.push(id);
  } else if (geomType === "LineString" || geomType === "MultiLineString") {
    const id = `layer-${mapLayer.id}-line`;
    GL_MAP.addLayer({
      id, source: sourceId, "source-layer": tableName, type: "line",
      layout: { visibility },
      paint: {
        "line-color": style.color || "#0F2D53",
        "line-width": style.strokeWidth ?? 2,
        "line-opacity": mapLayer.opacity ?? style.opacity ?? 1,
      },
    });
    ADDED_MAPBOX_LAYER_IDS.push(id);
  } else {
    // Polygon / MultiPolygon / Geometry fallback — fill + outline covers most cases
    const id = `layer-${mapLayer.id}-fill`;
    const outlineId = `layer-${mapLayer.id}-outline`;
    GL_MAP.addLayer({
      id, source: sourceId, "source-layer": tableName, type: "fill",
      layout: { visibility },
      paint: {
        "fill-color": style.color || "#0F2D53",
        "fill-opacity": mapLayer.opacity ?? style.opacity ?? 0.6,
      },
    });
    GL_MAP.addLayer({
      id: outlineId, source: sourceId, "source-layer": tableName, type: "line",
      layout: { visibility },
      paint: {
        "line-color": style.strokeColor || "#0a2140",
        "line-width": style.strokeWidth ?? 1,
      },
    });
    ADDED_MAPBOX_LAYER_IDS.push(id, outlineId);

    // If type is unknown Geometry, also add a line layer so road networks still show
    if (geomType === "Geometry" || !geomType) {
      const lineId = `layer-${mapLayer.id}-line-fallback`;
      GL_MAP.addLayer({
        id: lineId, source: sourceId, "source-layer": tableName, type: "line",
        layout: { visibility },
        paint: {
          "line-color": style.color || "#0F2D53",
          "line-width": style.strokeWidth ?? 2,
          "line-opacity": mapLayer.opacity ?? style.opacity ?? 1,
        },
      });
      ADDED_MAPBOX_LAYER_IDS.push(lineId);
    }
  }

  const labelConfig = layer.label_config || {};
  if (labelConfig.field) {
    const labelId = `layer-${mapLayer.id}-label`;
    GL_MAP.addLayer({
      id: labelId, source: sourceId, "source-layer": tableName, type: "symbol",
      layout: {
        visibility,
        "text-field": ["get", labelConfig.field],
        "text-size": labelConfig.size || 12,
        "text-anchor": "top",
      },
      paint: { "text-color": labelConfig.color || "#0F2D53" },
    });
    ADDED_MAPBOX_LAYER_IDS.push(labelId);
  }
}

async function saveMapMeta() {
  const center = GL_MAP.getCenter();
  await Auth.apiFetch(`/api/maps/${MAP_ID}/`, {
    method: "PATCH",
    body: {
      name: document.getElementById("map-name-input").value,
      basemap_style: document.getElementById("basemap-select").value,
      center_lng: center.lng,
      center_lat: center.lat,
      zoom: GL_MAP.getZoom(),
    },
  });
  const btn = document.getElementById("save-map-btn");
  const original = btn.textContent;
  btn.textContent = "Saved!";
  setTimeout(() => { btn.textContent = original; }, 1200);
}

// ---- Share modal ----
function openShareModal() {
  document.getElementById("share-search").value = "";
  document.getElementById("share-results").innerHTML = "";
  document.getElementById("share-submit").disabled = true;
  SELECTED_SHARE_USER = null;
  renderShareList();
  Auth.openModal("share-modal");
}

function renderShareList() {
  const list = document.getElementById("share-list");
  const shares = MAP_DATA.shares || [];
  if (!shares.length) {
    list.innerHTML = `<li class="share-empty">Not shared with anyone yet.</li>`;
    return;
  }
  list.innerHTML = shares.map((s) => Auth.renderSharePerson(s.shared_with_detail, {
    permission: s.permission,
    actionHtml: `<button type="button" class="btn btn-sm row-remove" data-remove-share="${s.shared_with_detail.id}">Remove</button>`,
  })).join("");
  list.querySelectorAll("[data-remove-share]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await Auth.apiFetch(`/api/maps/${MAP_ID}/unshare/`, { method: "POST", body: { user_id: btn.dataset.removeShare } });
      await refreshAfterLayerChange();
      renderShareList();
    });
  });
}

let shareSearchTimeout;
document.getElementById("share-search").addEventListener("input", (event) => {
  clearTimeout(shareSearchTimeout);
  const query = event.target.value.trim();
  if (!query) {
    document.getElementById("share-results").innerHTML = "";
    return;
  }
  shareSearchTimeout = setTimeout(async () => {
    const res = await Auth.apiFetch(`/api/auth/users/?search=${encodeURIComponent(query)}`);
    const data = await res.json();
    const results = data.results || data;
    const box = document.getElementById("share-results");
    if (!results.length) {
      box.innerHTML = `<p class="share-empty-inline muted">No users found.</p>`;
      return;
    }
    box.innerHTML = `<div class="share-results-list">${results.map((u) => Auth.renderShareHit(u)).join("")}</div>`;
    box.querySelectorAll("[data-user-id]").forEach((row) => {
      row.addEventListener("click", () => {
        SELECTED_SHARE_USER = results.find((u) => String(u.id) === row.dataset.userId);
        document.getElementById("share-search").value = SELECTED_SHARE_USER.display_name || SELECTED_SHARE_USER.username;
        box.innerHTML = "";
        document.getElementById("share-submit").disabled = false;
      });
    });
  }, 250);
});

document.getElementById("share-submit").addEventListener("click", async () => {
  if (!SELECTED_SHARE_USER) return;
  const permission = document.getElementById("share-permission").value;
  await Auth.apiFetch(`/api/maps/${MAP_ID}/share/`, {
    method: "POST",
    body: { shared_with: SELECTED_SHARE_USER.id, permission },
  });
  await refreshAfterLayerChange();
  renderShareList();
  document.getElementById("share-submit").disabled = true;
  SELECTED_SHARE_USER = null;
  document.getElementById("share-search").value = "";
});

document.addEventListener("DOMContentLoaded", init);
