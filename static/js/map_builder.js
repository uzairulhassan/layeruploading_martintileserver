let MAP_DATA = null;
let ALL_LAYERS = [];
let GL_MAP = null;
let MAP_ID = null;
let SELECTED_SHARE_USER = null;
const ADDED_MAPBOX_LAYER_IDS = [];

function openModal(id) { document.getElementById(id).classList.remove("hidden"); }
function closeModal(id) { document.getElementById(id).classList.add("hidden"); }
document.querySelectorAll("[data-close-modal]").forEach((btn) => {
  btn.addEventListener("click", () => closeModal(btn.dataset.closeModal));
});

function tableNameFromTileUrl(tileUrl) {
  return tileUrl.split("/").filter(Boolean).pop();
}

async function init() {
  const root = document.getElementById("builder-root");
  mapboxgl.accessToken = root.dataset.mapboxToken || "";
  MAP_ID = root.dataset.mapId || "";

  if (!MAP_ID) {
    document.getElementById("create-panel").classList.remove("hidden");
    document.getElementById("create-map-btn").addEventListener("click", createMap);
    return;
  }

  document.getElementById("builder-panel").classList.remove("hidden");
  await loadMap();
}

async function createMap() {
  const name = document.getElementById("new-map-name").value.trim();
  if (!name) return;
  const res = await Auth.apiFetch("/api/maps/", {
    method: "POST",
    body: { name, basemap_style: "mapbox://styles/mapbox/streets-v12", center_lng: 0, center_lat: 0, zoom: 2 },
  });
  if (res.ok) {
    const data = await res.json();
    window.location.href = `/maps/${data.id}/`;
  }
}

async function loadMap() {
  const res = await Auth.apiFetch(`/api/maps/${MAP_ID}/`);
  if (!res.ok) {
    document.getElementById("builder-panel").innerHTML = `<p class="muted">Map not found or access denied.</p>`;
    return;
  }
  MAP_DATA = await res.json();

  document.getElementById("map-name-input").value = MAP_DATA.name;
  document.getElementById("basemap-select").value = MAP_DATA.basemap_style;

  const readOnly = MAP_DATA.my_permission === "view";
  document.getElementById("permission-note").textContent = readOnly
    ? "You have view-only access to this map."
    : `Your access: ${MAP_DATA.my_permission}`;
  document.getElementById("save-map-btn").classList.toggle("hidden", readOnly);
  document.getElementById("share-map-btn").classList.toggle("hidden", MAP_DATA.my_permission !== "owner");
  document.getElementById("map-name-input").disabled = readOnly;
  document.getElementById("basemap-select").disabled = readOnly;
  document.querySelector("#builder-panel .map-sidebar h3:last-of-type").classList.toggle("hidden", readOnly);
  document.getElementById("available-layers").classList.toggle("hidden", readOnly);

  if (!GL_MAP) {
    GL_MAP = new mapboxgl.Map({
      container: "map-canvas",
      style: MAP_DATA.basemap_style,
      center: [MAP_DATA.center_lng, MAP_DATA.center_lat],
      zoom: MAP_DATA.zoom,
    });
    GL_MAP.addControl(new mapboxgl.NavigationControl(), "top-right");
    GL_MAP.on("load", renderMapLayers);
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

function renderActiveLayers() {
  const container = document.getElementById("active-layers");
  const layers = [...MAP_DATA.map_layers].sort((a, b) => b.order - a.order);
  const readOnly = MAP_DATA.my_permission === "view";

  if (!layers.length) {
    container.innerHTML = `<p class="muted">No layers added yet.</p>`;
    return;
  }

  container.innerHTML = layers.map((ml) => `
    <div class="layer-row" data-map-layer-id="${ml.id}">
      <input type="checkbox" data-toggle-visible ${ml.visible ? "checked" : ""} ${readOnly ? "disabled" : ""}>
      <span class="layer-name">${ml.layer_detail.name}</span>
      <input type="range" min="0" max="1" step="0.05" value="${ml.opacity}" data-opacity ${readOnly ? "disabled" : ""}>
      ${!readOnly ? `
        <button class="btn btn-sm" data-move="up" title="Bring forward">↑</button>
        <button class="btn btn-sm" data-move="down" title="Send back">↓</button>
        <button class="btn btn-sm btn-danger" data-remove title="Remove from map">✕</button>
      ` : ""}
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
    container.innerHTML = `<p class="muted">All your layers are already on this map.</p>`;
    return;
  }

  container.innerHTML = remaining.map((l) => `
    <div class="layer-row">
      <span class="layer-name">${l.name}</span>
      <button class="btn btn-sm" data-add-layer="${l.id}">Add</button>
    </div>
  `).join("");

  container.querySelectorAll("[data-add-layer]").forEach((btn) => {
    btn.addEventListener("click", () => addLayerToMap(btn.dataset.addLayer));
  });
}

async function addLayerToMap(layerId) {
  await Auth.apiFetch(`/api/maps/${MAP_ID}/layers/`, { method: "POST", body: { layer: layerId } });
  await refreshAfterLayerChange();
}

async function removeMapLayer(mapLayerId) {
  await Auth.apiFetch(`/api/maps/${MAP_ID}/layers/${mapLayerId}/`, { method: "DELETE" });
  await refreshAfterLayerChange();
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
}

function renderMapLayers() {
  if (!GL_MAP || !GL_MAP.isStyleLoaded()) return;
  clearMapboxLayers();

  const sorted = [...MAP_DATA.map_layers].sort((a, b) => a.order - b.order);
  sorted.forEach((ml) => addMapboxLayer(ml));
}

function addMapboxLayer(mapLayer) {
  const layer = mapLayer.layer_detail;
  const sourceId = `src-${layer.id}`;
  const tableName = tableNameFromTileUrl(layer.tile_url);

  if (!GL_MAP.getSource(sourceId)) {
    GL_MAP.addSource(sourceId, {
      type: "vector",
      tiles: [`${layer.tile_url}/{z}/{x}/{y}`],
      minzoom: 0,
      maxzoom: 22,
    });
  }

  const style = layer.style || {};
  const visibility = mapLayer.visible ? "visible" : "none";
  const geomType = layer.geometry_type;

  if (geomType === "Point" || geomType === "MultiPoint") {
    const id = `layer-${mapLayer.id}-circle`;
    GL_MAP.addLayer({
      id, source: sourceId, "source-layer": tableName, type: "circle",
      layout: { visibility },
      paint: {
        "circle-color": style.color || "#1f6feb",
        "circle-radius": 5,
        "circle-stroke-color": style.strokeColor || "#0b2e63",
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
        "line-color": style.color || "#1f6feb",
        "line-width": style.strokeWidth ?? 2,
        "line-opacity": mapLayer.opacity ?? style.opacity ?? 1,
      },
    });
    ADDED_MAPBOX_LAYER_IDS.push(id);
  } else {
    const id = `layer-${mapLayer.id}-fill`;
    const outlineId = `layer-${mapLayer.id}-outline`;
    GL_MAP.addLayer({
      id, source: sourceId, "source-layer": tableName, type: "fill",
      layout: { visibility },
      paint: {
        "fill-color": style.color || "#1f6feb",
        "fill-opacity": mapLayer.opacity ?? style.opacity ?? 0.6,
      },
    });
    GL_MAP.addLayer({
      id: outlineId, source: sourceId, "source-layer": tableName, type: "line",
      layout: { visibility },
      paint: {
        "line-color": style.strokeColor || "#0b2e63",
        "line-width": style.strokeWidth ?? 1,
      },
    });
    ADDED_MAPBOX_LAYER_IDS.push(id, outlineId);
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
      paint: { "text-color": labelConfig.color || "#1c2733" },
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
  openModal("share-modal");
}

function renderShareList() {
  const list = document.getElementById("share-list");
  const shares = MAP_DATA.shares || [];
  if (!shares.length) {
    list.innerHTML = `<li>Not shared with anyone yet.</li>`;
    return;
  }
  list.innerHTML = shares.map((s) => `
    <li>${s.shared_with_detail.display_name} — ${s.permission}
      <button class="btn btn-link" data-remove-share="${s.shared_with_detail.id}">remove</button>
    </li>
  `).join("");
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
    document.getElementById("share-results").innerHTML = results.map((u) => `
      <div class="layer-row" data-user-id="${u.id}" style="cursor:pointer;">${u.display_name} (${u.username})</div>
    `).join("") || "No users found.";
    document.querySelectorAll("#share-results [data-user-id]").forEach((row) => {
      row.addEventListener("click", () => {
        SELECTED_SHARE_USER = results.find((u) => String(u.id) === row.dataset.userId);
        document.getElementById("share-search").value = SELECTED_SHARE_USER.display_name;
        document.getElementById("share-results").innerHTML = "";
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
