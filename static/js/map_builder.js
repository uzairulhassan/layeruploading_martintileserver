/* Map Builder: full-bleed map with floating layers panel. */

let MAP_DATA = null;
let ALL_LAYERS = [];
let GL_MAP = null;
let MAP_ID = null;
let FEATURE_POPUP = null;
const ADDED_MAPBOX_LAYER_IDS = [];

/* Keep in sync with geotrak-maps-component/src/featurePopup.js */
const SKIP_FEATURE_KEYS = new Set([
  "geom", "geometry", "gid", "ogc_fid", "fid", "objectid", "object_id", "id",
  "kml_color", "kml_stroke", "kml_width", "kml_fill", "kml_outline",
]);
const MAX_POPUP_FIELDS = 8;

const ICON_POINT = `<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="7" cy="12" r="2.1" fill="currentColor"/><circle cx="12" cy="12" r="2.1" fill="currentColor"/><circle cx="17" cy="12" r="2.1" fill="currentColor"/></svg>`;
const ICON_LINE = `<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4 16.5 10 7.5l4 5 6-8" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
const ICON_POLY = `<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M7 6.5h8.5L18.5 12 14 17.5H7.5L5 12 7 6.5Z" fill="currentColor" opacity="0.85"/></svg>`;
const ICON_MENU = `<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="5.5" r="1.5" fill="currentColor"/><circle cx="12" cy="12" r="1.5" fill="currentColor"/><circle cx="12" cy="18.5" r="1.5" fill="currentColor"/></svg>`;
const PERMISSION_LABELS = { owner: "Owner", edit: "Can edit", view: "View only" };

function setHidden(el, hidden) {
  if (!el) return;
  el.classList.toggle("hidden", !!hidden);
}

function geometryIcon(geomType) {
  if (geomType === "Point" || geomType === "MultiPoint") return ICON_POINT;
  if (geomType === "LineString" || geomType === "MultiLineString") return ICON_LINE;
  return ICON_POLY;
}

function opacityPct(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return 100;
  return Math.round(Math.min(1, Math.max(0, n)) * 100);
}

function isReadOnly() {
  return MAP_DATA?.my_permission === "view";
}

function isMapOwner() {
  return MAP_DATA?.my_permission === "owner";
}

function hasUsableBounds(bounds) {
  return (
    Array.isArray(bounds) &&
    bounds.length === 4 &&
    bounds.every((v) => typeof v === "number" && Number.isFinite(v))
  );
}

/* -- Panel chrome -- */

function setBuilderTab(tab) {
  document.querySelectorAll("[data-builder-tab]").forEach((btn) => {
    const active = btn.dataset.builderTab === tab;
    btn.classList.toggle("is-active", active);
    btn.setAttribute("aria-selected", String(active));
  });
  document.querySelectorAll(".layers-tab-panel").forEach((panel) => {
    setHidden(panel, panel.id !== `panel-${tab}`);
  });
}

function setLayersPanelOpen(open) {
  document.getElementById("layers-panel")?.classList.toggle("is-collapsed", !open);
  document.getElementById("layers-fab")?.setAttribute("aria-expanded", String(open));
}

function updateLayersBadge() {
  const badge = document.getElementById("layers-count-badge");
  if (badge) badge.textContent = String(MAP_DATA?.map_layers?.length || 0);
}

let BASEMAP_RESTORE_TOKEN = 0;

function applyBasemapStyle(styleUrl) {
  const select = document.getElementById("basemap-select");
  if (select) select.value = styleUrl;
  if (!GL_MAP) return;

  // setStyle wipes custom sources/layers. Old IDs are invalid after the swap.
  const token = ++BASEMAP_RESTORE_TOKEN;
  closeFeaturePopup();
  ADDED_MAPBOX_LAYER_IDS.length = 0;
  GL_MAP.setStyle(styleUrl);

  const restore = () => {
    if (token !== BASEMAP_RESTORE_TOKEN || !GL_MAP || !MAP_DATA) return;
    if (!GL_MAP.isStyleLoaded()) return;
    renderMapLayers();
  };

  GL_MAP.once("style.load", () => {
    // Restore immediately, then again on idle in case the first pass raced the style swap.
    requestAnimationFrame(restore);
    GL_MAP.once("idle", restore);
  });
}

function closeOpenLayerMenus(except = null) {
  document.querySelectorAll(".layer-menu-dropdown").forEach((menu) => {
    if (menu === except) return;
    setHidden(menu, true);
    menu.closest(".layer-menu")?.querySelector("[data-layer-menu]")?.setAttribute("aria-expanded", "false");
  });
}

function bindBuilderChrome() {
  document.querySelectorAll("[data-builder-tab]").forEach((btn) => {
    btn.addEventListener("click", () => setBuilderTab(btn.dataset.builderTab));
  });

  document.getElementById("layers-panel-collapse")?.addEventListener("click", () => setLayersPanelOpen(false));
  document.getElementById("layers-fab")?.addEventListener("click", () => {
    const collapsed = document.getElementById("layers-panel")?.classList.contains("is-collapsed");
    setLayersPanelOpen(!!collapsed);
  });

  document.getElementById("add-layer-btn")?.addEventListener("click", () => {
    const picker = document.getElementById("add-layer-picker");
    const open = picker?.classList.contains("hidden");
    setHidden(picker, !open);
    document.getElementById("add-layer-btn")?.classList.toggle("is-open", !!open);
  });
  document.getElementById("apply-stack-order-btn")?.addEventListener("click", applyRecommendedStackOrder);

  document.getElementById("basemap-select")?.addEventListener("change", (event) => {
    applyBasemapStyle(event.target.value);
  });
  document.getElementById("save-map-btn")?.addEventListener("click", saveMapMeta);
  document.getElementById("share-map-btn")?.addEventListener("click", openShareModal);
  document.getElementById("edit-map-name-btn")?.addEventListener("click", toggleMapNameEditing);

  document.addEventListener("click", (event) => {
    if (!event.target.closest(".layer-menu")) closeOpenLayerMenus();
  });
}

/* -- Init / load -- */

async function init() {
  const root = document.getElementById("builder-root");
  mapboxgl.accessToken = root.dataset.mapboxToken || "";
  MAP_ID = root.dataset.mapId || "";
  if (!MAP_ID) {
    console.error("Map builder requires a map id.");
    return;
  }
  bindBuilderChrome();
  bindShareModal();
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
    document.getElementById("builder-panel").innerHTML =
      `<div class="builder-error"><p class="muted">Map not found or access denied.</p></div>`;
    return;
  }
  MAP_DATA = await res.json();

  document.getElementById("map-name-input").value = MAP_DATA.name;
  document.getElementById("basemap-select").value = MAP_DATA.basemap_style;
  updateLayersBadge();

  const readOnly = isReadOnly();
  const permissionValue = document.getElementById("permission-value");
  if (permissionValue) {
    permissionValue.textContent =
      PERMISSION_LABELS[MAP_DATA.my_permission] || MAP_DATA.my_permission || "-";
  }
  setHidden(document.getElementById("save-map-btn"), readOnly);
  setHidden(document.getElementById("share-map-btn"), !isMapOwner());
  setHidden(document.getElementById("edit-map-name-btn"), readOnly);
  setHidden(document.getElementById("add-layer-btn"), readOnly);
  setHidden(document.getElementById("apply-stack-order-btn"), readOnly);
  document.getElementById("map-name-input").disabled = readOnly;
  document.getElementById("basemap-select").disabled = readOnly;

  if (!GL_MAP) {
    GL_MAP = new mapboxgl.Map({
      container: "map-canvas",
      style: MAP_DATA.basemap_style,
      center: [MAP_DATA.center_lng, MAP_DATA.center_lat],
      zoom: MAP_DATA.zoom,
    });
    GL_MAP.addControl(new mapboxgl.NavigationControl({ visualizePitch: true }), "top-right");
    GL_MAP.addControl(new mapboxgl.ScaleControl({ maxWidth: 120 }), "bottom-left");
    bindFeatureInspect();
    GL_MAP.on("load", () => {
      renderMapLayers();
      if (shouldAutoFitOnLoad()) fitMapToLayers({ animate: true });
    });
  } else {
    renderMapLayers();
  }

  renderActiveLayers();
  if (!readOnly) await loadAvailableLayers();
}

/* -- Layer list UI -- */

function renderActiveLayers() {
  const container = document.getElementById("active-layers");
  const layers = [...MAP_DATA.map_layers].sort((a, b) => b.order - a.order);
  const readOnly = isReadOnly();
  updateLayersBadge();

  const stackBtn = document.getElementById("apply-stack-order-btn");
  if (stackBtn) stackBtn.disabled = readOnly || !layers.length;

  if (!layers.length) {
    container.innerHTML = `<p class="layer-empty">No layers on this map yet. Use Add Layer to compose one.</p>`;
    renderMapLegendPanel();
    return;
  }

  const orders = layers.map((ml) => ml.order);
  const maxOrder = Math.max(...orders);
  const minOrder = Math.min(...orders);

  container.innerHTML = layers.map((ml) => {
    const pct = opacityPct(ml.opacity);
    const name = Auth.escapeHtml(ml.layer_detail.name);
    const geom = ml.layer_detail.geometry_type || "";
    const canBringForward = ml.order < maxOrder;
    const canSendBack = ml.order > minOrder;
    return `
    <div class="layer-control-row${!ml.visible ? " is-off" : ""}" data-map-layer-id="${ml.id}" style="--opacity-pct:${pct}%">
      <input class="layer-check" type="checkbox" data-toggle-visible ${ml.visible ? "checked" : ""} ${readOnly ? "disabled" : ""} aria-label="Toggle ${name}">
      <span class="layer-type-icon" title="${Auth.escapeHtml(geom || "Layer")}">${geometryIcon(geom)}</span>
      <span class="layer-name" title="${name}">${name}</span>
      <span class="layer-opacity-pct" data-opacity-label>${pct}%</span>
      ${!readOnly ? `
      <div class="layer-menu">
        <button type="button" class="layer-menu-btn" data-layer-menu aria-haspopup="true" aria-expanded="false" title="Layer options" aria-label="Layer options">
          ${ICON_MENU}
        </button>
        <div class="layer-menu-dropdown hidden" role="menu">
          ${canBringForward ? `<button type="button" role="menuitem" data-move="up">Bring forward</button>` : ""}
          ${canSendBack ? `<button type="button" role="menuitem" data-move="down">Send back</button>` : ""}
          <button type="button" role="menuitem" class="is-danger" data-remove>Remove</button>
        </div>
      </div>
      ` : `<span class="layer-menu" aria-hidden="true"></span>`}
      <input class="layer-opacity-slider" type="range" min="0" max="1" step="0.05" value="${ml.opacity}" data-opacity ${readOnly ? "disabled" : ""} aria-label="Opacity for ${name}">
    </div>`;
  }).join("");

  container.querySelectorAll("[data-map-layer-id]").forEach((row) => {
    const mapLayerId = row.dataset.mapLayerId;
    row.querySelector("[data-toggle-visible]").addEventListener("change", (e) => {
      row.classList.toggle("is-off", !e.target.checked);
      updateMapLayer(mapLayerId, { visible: e.target.checked });
    });

    const opacityInput = row.querySelector("[data-opacity]");
    const opacityLabel = row.querySelector("[data-opacity-label]");
    if (opacityInput) {
      opacityInput.addEventListener("input", () => {
        const pct = opacityPct(opacityInput.value);
        row.style.setProperty("--opacity-pct", `${pct}%`);
        if (opacityLabel) opacityLabel.textContent = `${pct}%`;
      });
      opacityInput.addEventListener("change", (e) => {
        updateMapLayer(mapLayerId, { opacity: parseFloat(e.target.value) });
      });
    }

    const menuBtn = row.querySelector("[data-layer-menu]");
    const menu = row.querySelector(".layer-menu-dropdown");
    menuBtn?.addEventListener("click", (event) => {
      event.stopPropagation();
      const willOpen = menu?.classList.contains("hidden");
      closeOpenLayerMenus(willOpen ? menu : null);
      if (!menu) return;
      setHidden(menu, !willOpen);
      menuBtn.setAttribute("aria-expanded", String(!!willOpen));
    });
    row.querySelector("[data-remove]")?.addEventListener("click", () => removeMapLayer(mapLayerId));
    row.querySelectorAll("[data-move]").forEach((btn) => {
      btn.addEventListener("click", () => moveLayer(mapLayerId, btn.dataset.move));
    });
  });
  renderMapLegendPanel();
}

function renderMapLegendPanel() {
  const root = document.getElementById("map-legend");
  if (!root || !window.GeoLayersLegend) return;
  const sections = GeoLayersLegend.legendSectionsFromMapLayers(MAP_DATA?.map_layers || []);
  const collapsed = root.classList.contains("is-collapsed");
  GeoLayersLegend.renderMapLegend(root, sections, { collapsed });
}

async function loadAvailableLayers() {
  const res = await Auth.apiFetch("/api/layers/?page_size=500");
  const data = await res.json();
  ALL_LAYERS = data.results || data;
  renderAvailableLayers();
}

function renderAvailableLayers() {
  const container = document.getElementById("available-layers");
  if (!container) return;
  const onMapIds = new Set(MAP_DATA.map_layers.map((ml) => ml.layer_detail.id));
  const remaining = ALL_LAYERS.filter((l) => !onMapIds.has(l.id));

  if (!remaining.length) {
    container.innerHTML = `<p class="layer-empty">All your layers are already on this map.</p>`;
    return;
  }

  // KML/KMZ uploads share a group id — offer one "Add group" control plus per-layer Add.
  const groups = new Map();
  remaining.forEach((layer) => {
    const groupId = layer.group || layer.group_detail?.id;
    if (!groupId) return;
    if (!groups.has(String(groupId))) {
      groups.set(String(groupId), {
        id: groupId,
        name: layer.group_detail?.name || "KML/KMZ group",
        format: String(layer.group_detail?.source_format || "").toUpperCase(),
        layers: [],
      });
    }
    groups.get(String(groupId)).layers.push(layer);
  });

  const groupBlocks = [...groups.values()]
    .filter((g) => g.layers.length > 1)
    .map((g) => {
      const label = g.format ? `${g.format}: ${g.name}` : g.name;
      return `
      <div class="add-layer-item add-layer-group">
        <span class="layer-type-icon">${geometryIcon("MultiPolygon")}</span>
        <span class="layer-name" title="${Auth.escapeHtml(label)}">${Auth.escapeHtml(label)} (${g.layers.length})</span>
        <button type="button" class="btn btn-sm btn-primary" data-add-group="${g.id}">Add all</button>
      </div>`;
    })
    .join("");

  const layerBlocks = remaining.map((l) => `
    <div class="add-layer-item">
      <span class="layer-type-icon">${geometryIcon(l.geometry_type || "")}</span>
      <span class="layer-name" title="${Auth.escapeHtml(l.name)}">${Auth.escapeHtml(l.name)}</span>
      <button type="button" class="btn btn-sm btn-primary" data-add-layer="${l.id}">Add</button>
    </div>
  `).join("");

  container.innerHTML = groupBlocks + layerBlocks;

  container.querySelectorAll("[data-add-layer]").forEach((btn) => {
    btn.addEventListener("click", () => addLayerToMap(btn.dataset.addLayer));
  });
  container.querySelectorAll("[data-add-group]").forEach((btn) => {
    btn.addEventListener("click", () => addGroupToMap(btn.dataset.addGroup));
  });
}

/* -- Layer CRUD / map rendering -- */

async function addLayerToMap(layerId) {
  const res = await Auth.apiFetch(`/api/maps/${MAP_ID}/layers/`, {
    method: "POST",
    body: { layer: layerId },
  });
  if (!res.ok) {
    Toast.error(await Toast.fromResponse(res, "Could not add layer to map."));
    return;
  }
  await refreshAfterLayerChange();
  fitMapToLayers({ preferLayerId: layerId });
  window.setTimeout(() => fitMapToLayers({ preferLayerId: layerId, animate: true }), 400);
  Toast.success("Layer added to map.");
}

async function addGroupToMap(groupId) {
  const res = await Auth.apiFetch(`/api/maps/${MAP_ID}/layers/`, {
    method: "POST",
    body: { group: groupId },
  });
  if (!res.ok) {
    Toast.error(await Toast.fromResponse(res, "Could not add KML/KMZ group to map."));
    return;
  }
  await refreshAfterLayerChange();
  fitMapToLayers();
  window.setTimeout(() => fitMapToLayers({ animate: true }), 400);
  Toast.success("Group added to map.");
}

async function removeMapLayer(mapLayerId) {
  try {
    const res = await Auth.apiFetch(`/api/maps/${MAP_ID}/layers/${mapLayerId}/`, { method: "DELETE" });
    if (!res.ok && res.status !== 204) {
      throw new Error(await Toast.fromResponse(res, "Could not remove layer from map."));
    }
    await refreshAfterLayerChange();
    Toast.success("Layer removed from map.");
  } catch (err) {
    Toast.error(err.message || "Could not remove layer from map.");
  }
}

async function updateMapLayer(mapLayerId, payload) {
  try {
    const res = await Auth.apiFetch(`/api/maps/${MAP_ID}/layers/${mapLayerId}/`, { method: "PATCH", body: payload });
    if (!res.ok) {
      throw new Error(await Toast.fromResponse(res, "Could not update layer."));
    }
    await refreshAfterLayerChange();
  } catch (err) {
    Toast.error(err.message || "Could not update layer.");
  }
}

async function moveLayer(mapLayerId, direction) {
  const sorted = [...MAP_DATA.map_layers].sort((a, b) => a.order - b.order);
  const idx = sorted.findIndex((ml) => String(ml.id) === String(mapLayerId));
  const swapWith = direction === "up" ? idx + 1 : idx - 1;
  if (swapWith < 0 || swapWith >= sorted.length) return;
  [sorted[idx], sorted[swapWith]] = [sorted[swapWith], sorted[idx]];

  try {
    const res = await Auth.apiFetch(`/api/maps/${MAP_ID}/reorder/`, {
      method: "POST",
      body: { order: sorted.map((ml) => ml.id) },
    });
    if (!res.ok) {
      throw new Error(await Toast.fromResponse(res, "Could not reorder layers."));
    }
    await refreshAfterLayerChange();
  } catch (err) {
    Toast.error(err.message || "Could not reorder layers.");
  }
}

async function applyRecommendedStackOrder() {
  if (isReadOnly()) return;
  const res = await Auth.apiFetch(`/api/maps/${MAP_ID}/apply-recommended-order/`, {
    method: "POST",
    body: {},
  });
  if (!res.ok) {
    Toast.error(await Toast.fromResponse(res, "Could not apply recommended stack order."));
    return;
  }
  await refreshAfterLayerChange();
  Toast.success("Stack order updated.");
}

async function refreshAfterLayerChange() {
  const res = await Auth.apiFetch(`/api/maps/${MAP_ID}/`);
  MAP_DATA = await res.json();
  updateLayersBadge();
  renderActiveLayers();
  if (!isReadOnly()) renderAvailableLayers();
  renderMapLayers();
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

  if (Math.abs(minX - maxX) < 1e-9 && Math.abs(minY - maxY) < 1e-9) {
    GL_MAP.flyTo({ center: [minX, minY], zoom: 12, essential: true });
    return true;
  }

  GL_MAP.fitBounds(
    [[minX, minY], [maxX, maxY]],
    { padding: 48, maxZoom: 16, duration: animate ? 900 : 0, essential: true }
  );
  return true;
}

function closeFeaturePopup() {
  FEATURE_POPUP?.remove();
}

function featureAtPoint(point) {
  if (!GL_MAP) return null;
  const ids = [...ADDED_MAPBOX_LAYER_IDS].reverse().filter((id) => GL_MAP.getLayer(id));
  if (!ids.length) return null;
  return GL_MAP.queryRenderedFeatures(point, { layers: ids })[0] || null;
}

function mapLayerForFeature(feature) {
  const sourceId = String(feature?.source || "");
  if (!sourceId.startsWith("src-")) return null;
  const layerId = sourceId.slice(4);
  return MAP_DATA?.map_layers?.find((ml) => String(ml.layer_detail?.id) === layerId) || null;
}

/** Simple label: road_name → Road name (same as geotrak-maps-component). */
function simpleFieldLabel(name) {
  const spaced = String(name || "")
    .trim()
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ");
  if (!spaced) return "";
  const lower = spaced.toLowerCase();
  return lower.charAt(0).toUpperCase() + lower.slice(1);
}

function isBlankValue(value) {
  return value == null || (typeof value === "string" && value.trim() === "");
}

function formatAttrValue(value) {
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number" && Number.isFinite(value)) {
    return Number.isInteger(value) ? String(value) : String(Math.round(value * 1e4) / 1e4);
  }
  return String(value ?? "").trim();
}

function propertyByName(properties, fieldName) {
  if (!properties || !fieldName) return undefined;
  if (Object.prototype.hasOwnProperty.call(properties, fieldName)) return properties[fieldName];
  const wanted = String(fieldName).toLowerCase();
  const match = Object.keys(properties).find((key) => key.toLowerCase() === wanted);
  return match === undefined ? undefined : properties[match];
}

function pickTitleField(properties, mapLayer) {
  const labelField = mapLayer?.layer_detail?.label_config?.field;
  if (labelField && !isBlankValue(propertyByName(properties, labelField))) return labelField;
  return (
    Object.keys(properties || {}).find(
      (key) => /^(name|title|label)$/i.test(key) && !isBlankValue(properties[key]),
    )
    || Object.keys(properties || {}).find(
      (key) => /name|title|label/i.test(key) && !isBlankValue(properties[key]),
    )
    || null
  );
}

function orderedAttributeEntries(properties, mapLayer, skipKeys) {
  const skip = new Set([...SKIP_FEATURE_KEYS, ...skipKeys].map((key) => String(key).toLowerCase()));
  const seen = new Set();
  const entries = [];

  const push = (name, value) => {
    const key = name.toLowerCase();
    if (!name || skip.has(key) || seen.has(key) || isBlankValue(value)) return;
    if (key.startsWith("kml_")) return;
    seen.add(key);
    entries.push([name, value]);
  };

  (mapLayer?.layer_detail?.attribute_schema || []).forEach((col) => {
    if (col?.name) push(col.name, propertyByName(properties, col.name));
  });
  Object.keys(properties || {}).forEach((name) => push(name, properties[name]));
  return entries.slice(0, MAX_POPUP_FIELDS);
}

function buildFeaturePopupHtml(feature) {
  const mapLayer = mapLayerForFeature(feature);
  const layer = mapLayer?.layer_detail;
  const properties = feature?.properties || {};
  const titleField = pickTitleField(properties, mapLayer);
  const title = titleField ? formatAttrValue(propertyByName(properties, titleField)) : "";
  const attrs = orderedAttributeEntries(properties, mapLayer, titleField ? [titleField] : []);

  const rows = attrs.map(([name, value]) => `
    <div class="feature-popup-row">
      <span class="feature-popup-key">${Auth.escapeHtml(simpleFieldLabel(name))}</span>
      <span class="feature-popup-val">${Auth.escapeHtml(formatAttrValue(value))}</span>
    </div>
  `).join("");

  return `
    <div class="feature-popup">
      <p class="feature-popup-layer">${Auth.escapeHtml(layer?.name || "Layer")}</p>
      ${title ? `<p class="feature-popup-title">${Auth.escapeHtml(title)}</p>` : ""}
      ${rows
        ? `<div class="feature-popup-attrs">${rows}</div>`
        : `<p class="feature-popup-empty">No details</p>`}
    </div>
  `;
}

function showFeaturePopup(feature, lngLat) {
  if (!GL_MAP || !feature) return;
  if (!FEATURE_POPUP) {
    FEATURE_POPUP = new mapboxgl.Popup({
      closeButton: true,
      closeOnClick: false,
      maxWidth: "16.5rem",
      offset: 10,
      className: "feature-popup-wrap",
    });
  }
  FEATURE_POPUP.setLngLat(lngLat).setHTML(buildFeaturePopupHtml(feature)).addTo(GL_MAP);
}

function bindFeatureInspect() {
  if (!GL_MAP) return;
  GL_MAP.on("click", (event) => {
    const feature = featureAtPoint(event.point);
    if (!feature) {
      closeFeaturePopup();
      return;
    }
    showFeaturePopup(feature, event.lngLat);
  });
  GL_MAP.on("mousemove", (event) => {
    GL_MAP.getCanvas().style.cursor = featureAtPoint(event.point) ? "pointer" : "";
  });
  GL_MAP.on("mouseleave", () => {
    GL_MAP.getCanvas().style.cursor = "";
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeFeaturePopup();
  });
}

function clearMapboxLayers() {
  closeFeaturePopup();
  if (!GL_MAP) {
    ADDED_MAPBOX_LAYER_IDS.length = 0;
    return;
  }
  const layerIds = ADDED_MAPBOX_LAYER_IDS.splice(0, ADDED_MAPBOX_LAYER_IDS.length);
  layerIds.forEach((id) => {
    if (GL_MAP.getLayer(id)) GL_MAP.removeLayer(id);
  });
  const sources = GL_MAP.getStyle()?.sources || {};
  Object.keys(sources).forEach((sourceId) => {
    if (sourceId.startsWith("src-") && GL_MAP.getSource(sourceId)) {
      GL_MAP.removeSource(sourceId);
    }
  });
}

function renderMapLayers() {
  if (!GL_MAP || !MAP_DATA) return;
  if (!GL_MAP.isStyleLoaded()) {
    GL_MAP.once("style.load", () => {
      GL_MAP.once("idle", renderMapLayers);
    });
    return;
  }
  clearMapboxLayers();
  window.GeoLayersIcons?.ensureGeoLayersIcons(GL_MAP, collectRequiredIconsFromMap());
  [...MAP_DATA.map_layers]
    .sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
    .forEach((ml) => addMapboxLayer(ml));
}

function addInvisibleHitLayers(mapLayer, sourceId, tableName, geomType, visibility) {
  const needsPointHit = !geomType || geomType === "Point" || geomType === "MultiPoint" || geomType === "Geometry";
  const needsLineHit = !geomType || geomType === "LineString" || geomType === "MultiLineString" || geomType === "Geometry";
  if (needsPointHit) {
    const id = `layer-${mapLayer.id}-hit-circle`;
    GL_MAP.addLayer({
      id, source: sourceId, "source-layer": tableName, type: "circle",
      layout: { visibility },
      paint: {
        "circle-radius": 16,
        "circle-opacity": 0,
        "circle-stroke-width": 0,
      },
    });
    ADDED_MAPBOX_LAYER_IDS.push(id);
  }
  if (needsLineHit) {
    const id = `layer-${mapLayer.id}-hit-line`;
    GL_MAP.addLayer({
      id, source: sourceId, "source-layer": tableName, type: "line",
      layout: { visibility },
      paint: {
        "line-width": 16,
        "line-opacity": 0,
      },
    });
    ADDED_MAPBOX_LAYER_IDS.push(id);
  }
}

function collectRequiredIconsFromMap() {
  // Prefer server-built required_icons from MapLayerSerializer (same as share styles).
  const icons = new Set();
  (MAP_DATA?.map_layers || []).forEach((ml) => {
    (ml.required_icons || []).forEach((id) => {
      if (typeof id === "string" && id) icons.add(id);
    });
  });
  return [...icons];
}

function addMapboxLayer(mapLayer) {
  const layer = mapLayer.layer_detail;
  if (!layer?.xyz_url) return;

  const sourceId = `src-${layer.id}`;
  const tableName = layer.source_layer;
  if (!tableName) return;

  if (GL_MAP.getSource(sourceId)) GL_MAP.removeSource(sourceId);

  GL_MAP.addSource(sourceId, {
    type: "vector",
    tiles: [layer.xyz_url],
    minzoom: 0,
    maxzoom: 22,
  });

  const visibility = mapLayer.visible ? "visible" : "none";
  const geomType = layer.geometry_type || "";
  (mapLayer.style_layers || []).forEach((styleLayer) => {
    if (!styleLayer?.id) return;
    GL_MAP.addLayer(styleLayer);
    ADDED_MAPBOX_LAYER_IDS.push(styleLayer.id);
  });

  addInvisibleHitLayers(mapLayer, sourceId, tableName, geomType, visibility);
}

async function saveMapMeta() {
  const btn = document.getElementById("save-map-btn");
  if (btn) btn.disabled = true;
  try {
    const center = GL_MAP.getCenter();
    const res = await Auth.apiFetch(`/api/maps/${MAP_ID}/`, {
      method: "PATCH",
      body: {
        name: document.getElementById("map-name-input").value,
        basemap_style: document.getElementById("basemap-select").value,
        center_lng: center.lng,
        center_lat: center.lat,
        zoom: GL_MAP.getZoom(),
      },
    });
    if (!res.ok) {
      throw new Error(await Toast.fromResponse(res, "Could not save map."));
    }
    Toast.success("Map saved.");
  } catch (err) {
    Toast.error(err.message || "Could not save map.");
  } finally {
    if (btn) btn.disabled = false;
  }
}

/* -- Share modal (GeoTrak Layers users + external share) -- */

function openRevokeLinkModal(linkId) {
  document.getElementById("revoke-link-id").value = linkId;
  Auth.openModal("revoke-link-modal");
}

function renderShareList() {
  ShareUi.renderPeopleList(MAP_DATA?.shares || [], {
    canRemove: isMapOwner(),
    onRemove: async (userId) => {
      try {
        const res = await Auth.apiFetch(`/api/maps/${MAP_ID}/unshare/`, {
          method: "POST",
          body: { user_id: userId },
        });
        if (!res.ok) {
          throw new Error(await Toast.fromResponse(res, "Could not remove access."));
        }
        await refreshAfterLayerChange();
        renderShareList();
        Toast.success("Access removed.");
      } catch (err) {
        Toast.error(err.message || "Could not remove access.");
      }
    },
  });
}

function openShareModal() {
  const owner = isMapOwner();
  setHidden(document.getElementById("share-people-owner"), !owner);
  setHidden(document.getElementById("share-people-viewer"), owner);
  setHidden(document.getElementById("external-owner-only"), !owner);
  setHidden(document.getElementById("external-viewer-note"), owner);

  ShareUi.prepareOpen({
    subtitleEl: document.getElementById("builder-share-sub"),
    subtitle: MAP_DATA?.name
      ? `Sharing "${MAP_DATA.name}"`
      : "Share with GeoTrak Layers users or create an external link",
  });
  renderShareList();
  if (owner) {
    ShareUi.loadShareLinks({
      listUrl: `/api/maps/${MAP_ID}/share-links/`,
      includeLayerCount: true,
      onRevoke: (linkId) => openRevokeLinkModal(linkId),
    });
  }
  Auth.openModal("share-modal");
}

function bindShareModal() {
  ShareUi.bindModal({
    includeLayerCount: true,
    canManage: () => isMapOwner(),
    getResourceId: () => MAP_ID,
    getRevokeResourceId: () => MAP_ID,
    shareUrl: (id) => `/api/maps/${id}/share/`,
    shareLinksUrl: (id) => `/api/maps/${id}/share-links/`,
    revokeUrl: (id, linkId) => `/api/maps/${id}/share-links/${linkId}/`,
    shareSuccess: "Map shared.",
    shareError: "Could not share map.",
    onRevoke: (_mapId, linkId) => openRevokeLinkModal(linkId),
    afterPeopleChange: async () => {
      await refreshAfterLayerChange();
      renderShareList();
    },
  });
}

document.addEventListener("DOMContentLoaded", init);
