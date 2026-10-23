let MAP_DATA = null;
let ALL_LAYERS = [];
let GL_MAP = null;
let MAP_ID = null;
let SELECTED_SHARE_USER = null;
const ADDED_MAPBOX_LAYER_IDS = [];

function sourceLayerName(layer) {
  return layer.source_layer;
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
  if (!MAP_ID) {
    console.error("Map builder requires a map id.");
    return;
  }
  await loadMap();
}

function toggleMapNameEditing() {
  const input = document.getElementById("map-name-input");
  const btn = document.getElementById("edit-map-name-btn");
  if (!input || input.disabled) return;
  const editing = input.classList.toggle("is-editing");
  input.readOnly = !editing;
  btn?.classList.toggle("is-active", editing);
  if (editing) {
    input.focus();
    input.select();
  }
}

async function loadMap() {
  const res = await Auth.apiFetch(`/api/maps/${MAP_ID}/`);
  if (!res.ok) {
    document.getElementById("builder-panel").innerHTML = `<div class="builder-error"><p class="muted">Map not found or access denied.</p></div>`;
    return;
  }
  MAP_DATA = await res.json();

  document.getElementById("map-name-input").value = MAP_DATA.name;
  document.getElementById("basemap-select").value = MAP_DATA.basemap_style;

  const readOnly = MAP_DATA.my_permission === "view";
  const permissionLabels = { owner: "Owner", edit: "Can edit", view: "View only" };
  const permissionValue = document.getElementById("permission-value");
  if (permissionValue) {
    permissionValue.textContent =
      permissionLabels[MAP_DATA.my_permission] || MAP_DATA.my_permission || "—";
  }
  document.getElementById("save-map-btn").classList.toggle("hidden", readOnly);
  document.getElementById("share-map-btn").classList.toggle("hidden", MAP_DATA.my_permission !== "owner");
  document.getElementById("map-name-input").disabled = readOnly;
  document.getElementById("basemap-select").disabled = readOnly;
  const editNameBtn = document.getElementById("edit-map-name-btn");
  if (editNameBtn) {
    editNameBtn.classList.toggle("hidden", readOnly);
    editNameBtn.onclick = () => toggleMapNameEditing();
  }
  document.getElementById("available-layers-section")?.classList.toggle("hidden", readOnly);
  document.getElementById("available-layers").classList.toggle("hidden", readOnly);

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
  if (!layer?.xyz_url) return;

  const sourceId = `src-${layer.id}`;
  const tableName = sourceLayerName(layer);
  if (!tableName) return;

  if (GL_MAP.getSource(sourceId)) {
    GL_MAP.removeSource(sourceId);
  }

  GL_MAP.addSource(sourceId, {
    type: "vector",
    tiles: [layer.xyz_url],
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

// ---- Share modal (people + Map URL) ----
const ICON_COPY = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="8.5" y="8.5" width="10" height="12" rx="1.5" stroke="currentColor" stroke-width="1.7"/><path d="M15.5 8.5V6.2A1.7 1.7 0 0 0 13.8 4.5H6.2A1.7 1.7 0 0 0 4.5 6.2v7.6A1.7 1.7 0 0 0 6.2 15.5H8.5" stroke="currentColor" stroke-width="1.7"/></svg>`;
const ICON_TRASH = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 7.5h14M10 7.5V5.8A1.3 1.3 0 0 1 11.3 4.5h1.4A1.3 1.3 0 0 1 14 5.8V7.5M8.5 7.5v11.2A1.3 1.3 0 0 0 9.8 20h4.4a1.3 1.3 0 0 0 1.3-1.3V7.5" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
const ICON_USERS = `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="9" cy="8" r="3.1" stroke="currentColor" stroke-width="1.6"/><path d="M3.8 18.2c.7-2.7 2.8-4.2 5.2-4.2s4.5 1.5 5.2 4.2" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><circle cx="16.5" cy="9" r="2.4" stroke="currentColor" stroke-width="1.6"/><path d="M15.2 14.2c1.7.2 3.2 1.2 3.9 3.2" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>`;
const ICON_LINK = `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M10.2 13.8a4.2 4.2 0 0 1 0-5.9l2.1-2.1a4.2 4.2 0 0 1 5.9 5.9l-1 1" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><path d="M13.8 10.2a4.2 4.2 0 0 1 0 5.9l-2.1 2.1a4.2 4.2 0 1 1-5.9-5.9l1-1" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>`;

function isMapOwner() {
  return MAP_DATA?.my_permission === "owner";
}

function setShareTab(tab) {
  const peopleTab = document.getElementById("share-tab-people");
  const externalTab = document.getElementById("share-tab-external");
  const peoplePanel = document.getElementById("share-panel-people");
  const externalPanel = document.getElementById("share-panel-external");
  const isExternal = tab === "external";
  peopleTab.classList.toggle("is-active", !isExternal);
  externalTab.classList.toggle("is-active", isExternal);
  peopleTab.setAttribute("aria-selected", String(!isExternal));
  externalTab.setAttribute("aria-selected", String(isExternal));
  peoplePanel.classList.toggle("is-active", !isExternal);
  externalPanel.classList.toggle("is-active", isExternal);
  peoplePanel.hidden = isExternal;
  externalPanel.hidden = !isExternal;
  if (isExternal) {
    externalPanel.classList.add("is-entering");
    window.setTimeout(() => externalPanel.classList.remove("is-entering"), 280);
    loadMapShareLinks();
  }
}

function openShareModal() {
  document.getElementById("share-search").value = "";
  document.getElementById("share-results").innerHTML = "";
  document.getElementById("share-submit").disabled = true;
  SELECTED_SHARE_USER = null;

  const owner = isMapOwner();
  document.getElementById("share-people-owner").classList.toggle("hidden", !owner);
  document.getElementById("share-people-viewer").classList.toggle("hidden", owner);
  document.getElementById("external-owner-only").classList.toggle("hidden", !owner);
  document.getElementById("map-external-viewer-note").classList.toggle("hidden", owner);
  document.getElementById("map-external-copy-status").textContent = "";
  document.getElementById("map-external-copy-status").classList.remove("is-visible");
  resetMapExternalCreateForm();

  setShareTab("people");
  renderShareList();
  Auth.openModal("share-modal");
}

function renderShareList() {
  const list = document.getElementById("share-list");
  const shares = MAP_DATA.shares || [];
  if (!shares.length) {
    list.innerHTML = `
      <li class="share-empty">
        <div class="share-empty-state">
          <span class="share-empty-icon">${ICON_USERS}</span>
          <span>Not shared with anyone yet.</span>
        </div>
      </li>`;
    return;
  }
  list.innerHTML = shares.map((s) => `
    <li>${Auth.escapeHtml(s.shared_with_detail.display_name)} — ${Auth.escapeHtml(s.permission)}
      <button type="button" class="btn btn-link" data-remove-share="${s.shared_with_detail.id}">remove</button>
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

function getMapExternalLinkType() {
  const selected = document.querySelector('input[name="map-external-link-type"]:checked');
  return selected?.value || "expiring";
}

function syncMapExternalExpiryControls() {
  const isPermanent = getMapExternalLinkType() === "permanent";
  const expiryWrap = document.getElementById("map-external-expiry-wrap");
  const expiryInput = document.getElementById("map-external-expiry");
  expiryWrap?.classList.toggle("hidden", isPermanent);
  if (expiryInput) expiryInput.disabled = isPermanent;
}

function resetMapExternalCreateForm() {
  const expiring = document.querySelector('input[name="map-external-link-type"][value="expiring"]');
  if (expiring) expiring.checked = true;
  const expiryInput = document.getElementById("map-external-expiry");
  if (expiryInput) {
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 7);
    expiryInput.value = tomorrow.toISOString().slice(0, 10);
  }
  document.getElementById("map-external-create-error")?.classList.add("hidden");
  syncMapExternalExpiryControls();
}

function formatExpiry(isoString) {
  const date = new Date(isoString);
  return date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function formatMapExpiryLabel(link) {
  if (link.never_expires || !link.expires_at) {
    return `<span class="external-pill external-pill-live"><span class="external-pill-dot" aria-hidden="true"></span>No expiry</span>`;
  }
  if (link.is_expired) {
    return `<span class="external-pill external-pill-expired"><span class="external-pill-dot" aria-hidden="true"></span>Expired ${formatExpiry(link.expires_at)}</span>`;
  }
  return `<span class="external-pill"><span class="external-pill-dot" aria-hidden="true"></span>Expires ${formatExpiry(link.expires_at)}</span>`;
}

async function loadMapShareLinks() {
  if (!isMapOwner()) return;
  const list = document.getElementById("map-external-links-list");
  list.innerHTML = `<li class="share-empty">Loading…</li>`;
  const res = await Auth.apiFetch(`/api/maps/${MAP_ID}/share-links/`);
  if (!res.ok) {
    list.innerHTML = `<li class="share-empty">Could not load share links.</li>`;
    return;
  }
  renderMapShareLinks(await res.json());
}

function renderMapShareLinks(links) {
  const list = document.getElementById("map-external-links-list");
  if (!links.length) {
    list.innerHTML = `
      <li class="share-empty">
        <div class="share-empty-state">
          <span class="share-empty-icon">${ICON_LINK}</span>
          <span>No active links.</span>
        </div>
      </li>`;
    return;
  }
  list.innerHTML = links.map((link) => {
    const mapUrl = Auth.escapeHtml(link.style_url);
    const requests = Number(link.total_requests || 0).toLocaleString();
    const lastUsed = link.last_used_at ? formatExpiry(link.last_used_at) : "Never";
    const layerCount = Number(link.layer_count || 0);
    return `
    <li class="external-link-card">
      <div class="external-link-top">
        <div class="external-link-badges">
          ${formatMapExpiryLabel(link)}
          ${link.is_blocked ? `<span class="external-pill external-pill-blocked"><span class="external-pill-dot" aria-hidden="true"></span>Blocked</span>` : ""}
        </div>
        <div class="external-link-actions">
          <button type="button" class="btn btn-sm external-action-btn" data-copy-map-url="${mapUrl}">${ICON_COPY}<span>Copy Map URL</span></button>
          <button type="button" class="btn btn-sm btn-danger external-action-btn" data-revoke-map-link="${link.id}">${ICON_TRASH}<span>Revoke</span></button>
        </div>
      </div>

      <div class="external-field">
        <span class="external-field-label">Map URL</span>
        <input class="external-input" type="text" readonly value="${mapUrl}" aria-label="Map URL">
      </div>

      <div class="external-stats" aria-label="Usage">
        <div class="external-stat">
          <span class="external-stat-label">Layers</span>
          <span class="external-stat-value">${layerCount}</span>
        </div>
        <div class="external-stat">
          <span class="external-stat-label">Times used</span>
          <span class="external-stat-value">${requests}</span>
        </div>
        <div class="external-stat">
          <span class="external-stat-label">Last used</span>
          <span class="external-stat-value">${Auth.escapeHtml(lastUsed)}</span>
        </div>
      </div>
    </li>`;
  }).join("");

  list.querySelectorAll("[data-copy-map-url]").forEach((btn) => {
    btn.addEventListener("click", () => copyMapShareUrl(btn.dataset.copyMapUrl, btn, "Map URL copied."));
  });
  list.querySelectorAll("[data-revoke-map-link]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm("Revoke this link? Anyone using it will lose access right away.")) return;
      await Auth.apiFetch(`/api/maps/${MAP_ID}/share-links/${btn.dataset.revokeMapLink}/`, { method: "DELETE" });
      await loadMapShareLinks();
    });
  });
}

async function copyMapShareUrl(text, btn, message) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const input = document.createElement("input");
    input.value = text;
    document.body.appendChild(input);
    input.select();
    document.execCommand("copy");
    input.remove();
  }
  const status = document.getElementById("map-external-copy-status");
  status.textContent = message;
  status.classList.add("is-visible");
  document.querySelectorAll("#map-external-links-list .is-copied").forEach((el) => el.classList.remove("is-copied"));
  btn?.classList.add("is-copied");
  window.setTimeout(() => {
    status.classList.remove("is-visible");
    btn?.classList.remove("is-copied");
  }, 1800);
}

document.querySelectorAll("[data-share-tab]").forEach((tab) => {
  tab.addEventListener("click", () => setShareTab(tab.dataset.shareTab));
});

document.querySelectorAll('input[name="map-external-link-type"]').forEach((input) => {
  input.addEventListener("change", syncMapExternalExpiryControls);
});

document.getElementById("map-external-create-btn").addEventListener("click", async () => {
  if (!isMapOwner()) return;
  const errorBox = document.getElementById("map-external-create-error");
  errorBox.classList.add("hidden");

  const isPermanent = getMapExternalLinkType() === "permanent";
  const expiryValue = document.getElementById("map-external-expiry").value;
  let body = { expires_at: null };

  if (!isPermanent) {
    if (!expiryValue) {
      errorBox.textContent = "Choose an expiry date.";
      errorBox.classList.remove("hidden");
      return;
    }
    body = { expires_at: new Date(`${expiryValue}T23:59:59`).toISOString() };
  }

  const btn = document.getElementById("map-external-create-btn");
  btn.disabled = true;
  try {
    const res = await Auth.apiFetch(`/api/maps/${MAP_ID}/share-links/`, {
      method: "POST",
      body,
    });
    if (!res.ok) {
      const errBody = await res.json().catch(() => ({}));
      throw new Error(errBody.expires_at?.[0] || errBody.detail || "Could not generate the link.");
    }
    resetMapExternalCreateForm();
    await loadMapShareLinks();
  } catch (err) {
    errorBox.textContent = err.message;
    errorBox.classList.remove("hidden");
  } finally {
    btn.disabled = false;
  }
});

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
      <div class="share-hit" data-user-id="${u.id}">${u.display_name} (${u.username})</div>
    `).join("") || `<p class="muted">No users found.</p>`;
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
  if (!SELECTED_SHARE_USER || !isMapOwner()) return;
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
