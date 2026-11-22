let CURRENT_LAYERS = [];

const LAYER_ICONS = {
  pin: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 3.5c-3.6 0-6.5 2.9-6.5 6.5 0 4.6 5.2 11.1 6.1 12.2a.5.5 0 0 0 .8 0c.9-1.1 6.1-7.6 6.1-12.2 0-3.6-2.9-6.5-6.5-6.5Z" stroke="currentColor" stroke-width="1.7"/><circle cx="12" cy="10" r="2.3" stroke="currentColor" stroke-width="1.7"/></svg>',
  map: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M9 4.5 3.5 6.5v13L9 17.5l6 2 5.5-2v-13L15 6.5 9 4.5Z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M9 4.5v13M15 6.5v13" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>',
  fill: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4.5 9.5 12 4.5l7.5 5v9.5L12 21.5 4.5 19V9.5Z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg>',
  points: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="7" cy="12" r="2.2" stroke="currentColor" stroke-width="1.7"/><circle cx="17" cy="7.5" r="2.2" stroke="currentColor" stroke-width="1.7"/><circle cx="16.5" cy="16.5" r="2.2" stroke="currentColor" stroke-width="1.7"/><path d="M9 11.2 15 8.4M9 13l5.4 2.4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
  line: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4 16.5 9.5 8.5 14 14l6-8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  layers: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 4.5 3.5 9 12 13.5 20.5 9 12 4.5Z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M3.5 13 12 17.5 20.5 13" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  user: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="9" r="3.2" stroke="currentColor" stroke-width="1.7"/><path d="M5.5 19c1.4-3 3.7-4.5 6.5-4.5s5.1 1.5 6.5 4.5" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>',
  style: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4 20h16"/><path d="M8 16l9.2-9.2a1.8 1.8 0 0 0-2.5-2.5L5.5 13.5 4 20l6.5-1.5z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg>',
  share: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="18" cy="5" r="2.4" stroke="currentColor" stroke-width="1.7"/><circle cx="6" cy="12" r="2.4" stroke="currentColor" stroke-width="1.7"/><circle cx="18" cy="19" r="2.4" stroke="currentColor" stroke-width="1.7"/><path d="M8.4 13.2l7.2 4.1M15.6 6.7l-7.2 4.1" stroke="currentColor" stroke-width="1.7"/></svg>',
  rename: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 19h14"/><path d="M7.5 15.5 16 7l2.5 2.5-8.5 8.5H7.5v-2.5Z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg>',
  trash: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 7h14"/><path d="M9 7V5h6v2"/><path d="M8 7l1 12h6l1-12" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg>',
};

function geometryTone(geometryType) {
  const g = String(geometryType || "").toLowerCase();
  if (g.includes("point")) return { tone: "blue", icon: "pin", geomIcon: "points" };
  if (g.includes("line")) return { tone: "green", icon: "map", geomIcon: "line" };
  if (g.includes("polygon")) return { tone: "purple", icon: "fill", geomIcon: "fill" };
  return { tone: "blue", icon: "layers", geomIcon: "layers" };
}

function permissionLabel(permission) {
  if (permission === "owner") return "Owner";
  if (permission === "edit") return "Can edit";
  if (permission === "view") return "View only";
  return String(permission || "").replace(/_/g, " ");
}

async function loadLayers() {
  try {
    const res = await Auth.apiFetch("/api/layers/?page_size=500");
    if (!res.ok) {
      throw new Error(await Toast.fromResponse(res, "Could not load layers."));
    }
    const data = await res.json();
    CURRENT_LAYERS = data.results || data;
    renderLayers();
  } catch (err) {
    Toast.error(err.message || "Could not load layers.");
  }
}

function groupBadge(layer) {
  const group = layer.group_detail;
  if (!group) return "";
  const fmt = String(group.source_format || "").toUpperCase();
  const label = fmt ? `${fmt} group` : "Group";
  return `<span class="badge badge-access" title="${Auth.escapeHtml(group.name || "KML/KMZ group")}">${Auth.escapeHtml(label)}</span>`;
}

function renderLayers() {
  const tbody = document.getElementById("layers-tbody");
  if (!CURRENT_LAYERS.length) {
    tbody.innerHTML = `<tr><td colspan="6"><div class="empty-state"><strong>No layers yet</strong>Upload a shapefile (.zip) or KML/KMZ to get started.</div></td></tr>`;
    return;
  }
  tbody.innerHTML = CURRENT_LAYERS.map((layer) => {
    const meta = geometryTone(layer.geometry_type);
    const owner = layer.owner_detail ? (layer.owner_detail.display_name || layer.owner_detail.username) : "";
    return `
    <tr>
      <td>
        <div class="cell-entity">
          <span class="cell-icon tone-${meta.tone}" aria-hidden="true">${LAYER_ICONS[meta.icon]}</span>
          <span class="cell-entity-name">${Auth.escapeHtml(layer.name)}</span>
          ${groupBadge(layer)}
        </div>
      </td>
      <td>
        <div class="cell-meta">
          <span class="cell-meta-icon" aria-hidden="true">${LAYER_ICONS[meta.geomIcon]}</span>
          <span>${Auth.escapeHtml(layer.geometry_type || "—")}</span>
        </div>
      </td>
      <td>
        <div class="cell-meta">
          <span class="cell-meta-icon" aria-hidden="true">${LAYER_ICONS.layers}</span>
          <span>${Number(layer.feature_count || 0).toLocaleString()}</span>
        </div>
      </td>
      <td>
        <div class="cell-meta">
          <span class="cell-meta-icon" aria-hidden="true">${LAYER_ICONS.user}</span>
          <span>${Auth.escapeHtml(owner)}</span>
        </div>
      </td>
      <td><span class="badge badge-access">${Auth.escapeHtml(permissionLabel(layer.my_permission))}</span></td>
      <td class="table-actions">
        <div class="action-btn-row">
          <button type="button" class="action-btn" data-action="style" data-id="${layer.id}" title="Style">
            ${LAYER_ICONS.style}<span>Style</span>
          </button>
          ${layer.my_permission === "owner" ? `
            <button type="button" class="action-btn" data-action="share" data-id="${layer.id}" title="Share">
              ${LAYER_ICONS.share}<span>Share</span>
            </button>
            <button type="button" class="action-btn" data-action="rename" data-id="${layer.id}" title="Rename">
              ${LAYER_ICONS.rename}<span>Rename</span>
            </button>
            <button type="button" class="action-btn is-danger" data-action="delete" data-id="${layer.id}" title="Delete">
              ${LAYER_ICONS.trash}<span>Delete</span>
            </button>
          ` : ""}
        </div>
      </td>
    </tr>
  `;
  }).join("");

  tbody.querySelectorAll("button[data-action]").forEach((btn) => {
    btn.addEventListener("click", () => handleRowAction(btn.dataset.action, btn.dataset.id));
  });
}

function findLayer(id) {
  return CURRENT_LAYERS.find((l) => String(l.id) === String(id));
}

function handleRowAction(action, id) {
  const layer = findLayer(id);
  if (action === "style") openStyleModal(layer);
  if (action === "rename") openRenameModal(layer);
  if (action === "share") openShareModal(layer);
  if (action === "delete") deleteLayer(layer);
}

// ---- Upload ----
const UPLOAD_EXTENSIONS = [".zip", ".kml", ".kmz"];
const UPLOAD_TYPE_ERROR = "Use a .zip shapefile package, or a .kml / .kmz file.";

function uploadFileExtension(filename) {
  const match = /\.([a-z0-9]+)$/i.exec(String(filename || "").trim());
  return match ? `.${match[1].toLowerCase()}` : "";
}

function isAllowedUploadFile(file) {
  return Boolean(file) && UPLOAD_EXTENSIONS.includes(uploadFileExtension(file.name));
}

document.getElementById("open-upload-modal").addEventListener("click", () => {
  Auth.openModal("upload-modal");
});

document.getElementById("upload-file").addEventListener("change", () => {
  const file = document.getElementById("upload-file").files[0];
  if (file && !isAllowedUploadFile(file)) {
    Toast.error(UPLOAD_TYPE_ERROR);
    document.getElementById("upload-file").value = "";
  }
});

document.getElementById("upload-form").addEventListener("submit", async (event) => {
  event.preventDefault();

  const name = document.getElementById("upload-name").value.trim();
  const description = document.getElementById("upload-description").value.trim();
  const file = document.getElementById("upload-file").files[0];

  if (!name) {
    Toast.error("Layer name is required.");
    return;
  }
  if (!file) {
    Toast.error("Choose a file to upload.");
    return;
  }
  if (!isAllowedUploadFile(file)) {
    Toast.error(UPLOAD_TYPE_ERROR);
    return;
  }

  const submitBtn = document.getElementById("upload-submit");
  submitBtn.disabled = true;
  submitBtn.textContent = "Importing…";

  const formData = new FormData();
  formData.append("name", name);
  formData.append("description", description);
  formData.append("file", file);

  try {
    const res = await Auth.apiFetch("/api/layers/", { method: "POST", body: formData });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(Toast.fromApiBody(body, "Upload failed."));
    }
    document.getElementById("upload-form").reset();
    Auth.closeModal("upload-modal");
    await loadLayers();
    if (body.group) {
      const count = body.group.layer_count ?? (body.group.layers || []).length;
      const fmt = String(body.group.source_format || "KML").toUpperCase();
      Toast.success(`${fmt} imported as ${count} layer${count === 1 ? "" : "s"}.`);
    } else {
      Toast.success("Shapefile imported.");
    }
  } catch (err) {
    Toast.error(err.message || "Upload failed.");
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Upload";
  }
});

// ---- Rename ----
function openRenameModal(layer) {
  document.getElementById("rename-id").value = layer.id;
  document.getElementById("rename-name").value = layer.name;
  document.getElementById("rename-description").value = layer.description || "";
  Auth.openModal("rename-modal");
}

document.getElementById("rename-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const id = document.getElementById("rename-id").value;
  const name = document.getElementById("rename-name").value.trim();
  if (!name) {
    Toast.error("Layer name is required.");
    return;
  }
  const payload = {
    name,
    description: document.getElementById("rename-description").value.trim(),
  };
  try {
    const res = await Auth.apiFetch(`/api/layers/${id}/`, { method: "PATCH", body: payload });
    if (!res.ok) {
      throw new Error(await Toast.fromResponse(res, "Could not update layer."));
    }
    Auth.closeModal("rename-modal");
    await loadLayers();
    Toast.success("Layer updated.");
  } catch (err) {
    Toast.error(err.message || "Could not update layer.");
  }
});

// ---- Delete ----
function openDeleteLayerModal(layer) {
  document.getElementById("delete-layer-id").value = layer.id;
  document.getElementById("delete-layer-name").textContent = layer.name;
  Auth.openModal("delete-layer-modal");
}

async function deleteLayer(layer) {
  openDeleteLayerModal(layer);
}

document.getElementById("delete-layer-confirm").addEventListener("click", async () => {
  const id = document.getElementById("delete-layer-id").value;
  if (!id) return;
  const btn = document.getElementById("delete-layer-confirm");
  btn.disabled = true;
  try {
    const res = await Auth.apiFetch(`/api/layers/${id}/`, { method: "DELETE" });
    if (!res.ok && res.status !== 204) {
      throw new Error(await Toast.fromResponse(res, "Could not delete layer."));
    }
    Auth.closeModal("delete-layer-modal");
    await loadLayers();
    Toast.success("Layer deleted.");
  } catch (err) {
    Toast.error(err.message || "Could not delete layer.");
  } finally {
    btn.disabled = false;
  }
});

// ---- Style & labels ----
function normalizeHexColor(value, fallback) {
  const raw = String(value || "").trim();
  if (/^#[0-9a-fA-F]{6}$/.test(raw)) return raw.toLowerCase();
  if (/^#[0-9a-fA-F]{3}$/.test(raw)) {
    return `#${raw[1]}${raw[1]}${raw[2]}${raw[2]}${raw[3]}${raw[3]}`.toLowerCase();
  }
  return fallback;
}

function setColorPair(textId, pickerId, value, fallback) {
  const hex = normalizeHexColor(value, fallback);
  document.getElementById(textId).value = hex;
  document.getElementById(pickerId).value = hex;
}

function bindColorPair(textId, pickerId, fallback, onChange) {
  const text = document.getElementById(textId);
  const picker = document.getElementById(pickerId);
  picker.addEventListener("input", () => {
    text.value = picker.value;
    onChange?.();
  });
  text.addEventListener("input", () => {
    const hex = normalizeHexColor(text.value, "");
    if (hex) picker.value = hex;
    onChange?.();
  });
  text.addEventListener("blur", () => {
    setColorPair(textId, pickerId, text.value, fallback);
    onChange?.();
  });
}

function styleGeometryKind(geometryType) {
  const raw = String(geometryType || "").toLowerCase();
  if (raw.includes("point")) return "point";
  if (raw.includes("line")) return "line";
  return "fill";
}

let STYLE_COLOR_BY_REQ = 0;
let STYLE_ICON_BY_REQ = 0;
let STYLE_ACTIVE_LAYER = null;
let STYLE_COLOR_CATEGORIES = {};
let STYLE_ICON_CATEGORIES = {};
let STYLE_PREVIEW_MAP = null;
let STYLE_PREVIEW_LAYER_IDS = [];
let STYLE_PREVIEW_SOURCE_ID = null;
let STYLE_PREVIEW_REQ = 0;
let STYLE_PREVIEW_TIMER = null;
let STYLE_PREVIEW_FIT_KEY = "";
let STYLE_PREVIEW_EXPANDED = false;
/** Where to put the preview card back after expand (body portal). */
let STYLE_PREVIEW_HOME = null;

const CATEGORY_PALETTE = [
  "#2563eb", "#16a34a", "#ea580c", "#dc2626", "#7c3aed",
  "#0891b2", "#ca8a04", "#db2777", "#4f46e5", "#059669",
  "#9333ea", "#0d9488", "#c2410c", "#be123c", "#1d4ed8",
];

// geolayers_icons.js loads before this file on the layers page.
const STYLE_ICON_OPTIONS = window.GeoLayersIcons?.ICON_OPTIONS || [];

function fieldOptionsHtml(fields, selected, emptyLabel) {
  return `<option value="">${Auth.escapeHtml(emptyLabel)}</option>` +
    fields.map((f) => {
      const sel = f === selected ? " selected" : "";
      return `<option value="${Auth.escapeHtml(f)}"${sel}>${Auth.escapeHtml(f)}</option>`;
    }).join("");
}

function iconOptionsHtml(selected) {
  return STYLE_ICON_OPTIONS.map((opt) => {
    const sel = opt.id === selected ? " selected" : "";
    return `<option value="${Auth.escapeHtml(opt.id)}"${sel}>${Auth.escapeHtml(opt.label)}</option>`;
  }).join("");
}

function readColorByFromDom() {
  const field = document.getElementById("style-color-by-field")?.value || "";
  if (!field) return null;
  const container = document.getElementById("style-color-by-rows");
  const keys = container?._categoryKeys || Object.keys(STYLE_COLOR_CATEGORIES);
  const categories = {};
  keys.forEach((key, idx) => {
    const row = container?.querySelector(`[data-category-index="${idx}"]`);
    const input = row?.querySelector("input[data-color-text]");
    const picker = row?.querySelector("input[type=color]");
    const raw = input?.value || picker?.value || STYLE_COLOR_CATEGORIES[key] || "#888888";
    categories[key] = normalizeHexColor(raw, "#888888");
  });
  if (!Object.keys(categories).length) Object.assign(categories, STYLE_COLOR_CATEGORIES);
  return {
    field,
    default: normalizeHexColor(document.getElementById("style-fill-color").value, "#0F2D53"),
    categories,
  };
}

function clampMarkerSize(value, fallback = 1) {
  const raw = parseFloat(value);
  if (!Number.isFinite(raw)) return fallback;
  return Math.min(4, Math.max(0.25, raw));
}

function readMarkerSizeFromDom() {
  return clampMarkerSize(document.getElementById("style-marker-size")?.value, 1);
}

function normalizeIconCategory(raw, fallbackIcon = "gl-poi", fallbackSize = 1) {
  if (raw && typeof raw === "object" && !Array.isArray(raw)) {
    return {
      icon: raw.icon || fallbackIcon,
      size: clampMarkerSize(raw.size, fallbackSize),
    };
  }
  if (typeof raw === "string" && raw) {
    return { icon: raw, size: fallbackSize };
  }
  return { icon: fallbackIcon, size: fallbackSize };
}

function normalizeIconCategoryMap(categories, fallbackIcon = "gl-poi", fallbackSize = 1) {
  const out = {};
  Object.entries(categories || {}).forEach(([key, raw]) => {
    out[key] = normalizeIconCategory(raw, fallbackIcon, fallbackSize);
  });
  return out;
}

function readMarkerFromDom() {
  if (currentStyleKind() !== "point") return null;
  const type = (document.getElementById("style-marker-type")?.value || "circle") === "icon"
    ? "icon"
    : "circle";
  const size = readMarkerSizeFromDom();
  if (type !== "icon") return { type: "circle", size };

  const defaultIcon = document.getElementById("style-default-icon")?.value || "gl-poi";
  const field = document.getElementById("style-icon-by-field")?.value || "";
  const marker = { type: "icon", icon: defaultIcon, size };
  if (!field) return marker;

  const container = document.getElementById("style-icon-by-rows");
  const keys = container?._iconKeys || Object.keys(STYLE_ICON_CATEGORIES);
  const categories = {};
  keys.forEach((key, idx) => {
    const row = container?.querySelector(`[data-icon-index="${idx}"]`);
    const select = row?.querySelector("select");
    const sizeInput = row?.querySelector("input[data-icon-size]");
    const fallback = normalizeIconCategory(
      STYLE_ICON_CATEGORIES[key],
      defaultIcon,
      size,
    );
    categories[key] = {
      icon: select?.value || fallback.icon || defaultIcon,
      size: clampMarkerSize(sizeInput?.value, fallback.size),
    };
  });
  if (!Object.keys(categories).length) {
    Object.assign(categories, normalizeIconCategoryMap(STYLE_ICON_CATEGORIES, defaultIcon, size));
  }
  marker.iconBy = { field, default: defaultIcon, defaultSize: size, categories };
  return marker;
}

function readStyleFormValues() {
  return {
    color: normalizeHexColor(document.getElementById("style-fill-color").value, "#0F2D53"),
    strokeColor: normalizeHexColor(document.getElementById("style-stroke-color").value, "#0a2140"),
    strokeWidth: Math.max(0, parseFloat(document.getElementById("style-stroke-width").value || "1") || 0),
    opacity: Math.min(1, Math.max(0, parseFloat(document.getElementById("style-opacity").value || "0.6") || 0)),
    colorBy: readColorByFromDom(),
    marker: readMarkerFromDom(),
    labelField: document.getElementById("label-field").value,
    labelColor: normalizeHexColor(document.getElementById("label-color").value, "#0F2D53"),
    labelSize: Math.min(36, Math.max(8, parseInt(document.getElementById("label-size").value || "12", 10) || 12)),
  };
}

async function fetchDistinctAttributeValues(layerId, field) {
  const res = await Auth.apiFetch(
    `/api/layers/${layerId}/attribute-values/?field=${encodeURIComponent(field)}&limit=40`
  );
  if (!res.ok) return null;
  const body = await res.json().catch(() => ({}));
  return Array.isArray(body.values) ? body.values : [];
}

function renderColorByRows(values, categories) {
  const container = document.getElementById("style-color-by-rows");
  if (!container) return;
  const keys = values || [];
  if (!keys.length) {
    container.innerHTML = `<p class="style-panel-hint">No values found for this field.</p>`;
    container.classList.remove("hidden");
    return;
  }
  STYLE_COLOR_CATEGORIES = {};
  container.innerHTML = keys.map((key, idx) => {
    const color = normalizeHexColor(categories[key], CATEGORY_PALETTE[idx % CATEGORY_PALETTE.length]);
    STYLE_COLOR_CATEGORIES[key] = color;
    const safe = Auth.escapeHtml(key);
    const id = `color-by-${idx}`;
    return `
      <div class="style-category-row" data-category-index="${idx}">
        <label for="${id}" title="${safe}">${safe}</label>
        <div class="color-field">
          <input type="color" id="${id}-picker" value="${color}" aria-label="Color for ${safe}">
          <input type="text" id="${id}" data-color-text value="${color}" spellcheck="false">
        </div>
      </div>`;
  }).join("");
  container.classList.remove("hidden");
  keys.forEach((key, idx) => {
    const id = `color-by-${idx}`;
    bindColorPair(id, `${id}-picker`, STYLE_COLOR_CATEGORIES[key], () => {
      const text = document.getElementById(id);
      STYLE_COLOR_CATEGORIES[key] = normalizeHexColor(text?.value, STYLE_COLOR_CATEGORIES[key]);
      updateStylePreview();
    });
  });
  container._categoryKeys = keys;
}

function renderIconByRows(values, categories, defaultIcon, defaultSize = 1) {
  const container = document.getElementById("style-icon-by-rows");
  if (!container) return;
  const keys = values || [];
  if (!keys.length) {
    container.innerHTML = `<p class="style-panel-hint">No values found for this field.</p>`;
    container.classList.remove("hidden");
    return;
  }
  const baseSize = clampMarkerSize(defaultSize, 1);
  STYLE_ICON_CATEGORIES = {};
  container.innerHTML = keys.map((key, idx) => {
    const spec = normalizeIconCategory(categories[key], defaultIcon || "gl-poi", baseSize);
    STYLE_ICON_CATEGORIES[key] = spec;
    const safe = Auth.escapeHtml(key);
    const id = `icon-by-${idx}`;
    return `
      <div class="style-category-row is-icon" data-icon-index="${idx}">
        <label for="${id}" title="${safe}">${safe}</label>
        <select id="${id}" aria-label="Icon for ${safe}">${iconOptionsHtml(spec.icon)}</select>
        <input type="number" id="${id}-size" data-icon-size min="0.25" max="4" step="0.05" value="${spec.size}" aria-label="Size for ${safe}" title="Size">
      </div>`;
  }).join("");
  container.classList.remove("hidden");
  container._iconKeys = keys;
  container.querySelectorAll("select").forEach((select) => {
    select.addEventListener("change", () => {
      const row = select.closest("[data-icon-index]");
      const idx = Number(row?.dataset.iconIndex);
      const key = keys[idx];
      if (!key) return;
      const prev = normalizeIconCategory(STYLE_ICON_CATEGORIES[key], defaultIcon, baseSize);
      STYLE_ICON_CATEGORIES[key] = { icon: select.value, size: prev.size };
      updateStylePreview();
    });
  });
  container.querySelectorAll("input[data-icon-size]").forEach((input) => {
    const sync = () => {
      const row = input.closest("[data-icon-index]");
      const idx = Number(row?.dataset.iconIndex);
      const key = keys[idx];
      if (!key) return;
      const prev = normalizeIconCategory(STYLE_ICON_CATEGORIES[key], defaultIcon, baseSize);
      const size = clampMarkerSize(input.value, prev.size);
      input.value = String(size);
      STYLE_ICON_CATEGORIES[key] = { icon: prev.icon, size };
      updateStylePreview();
    };
    input.addEventListener("input", sync);
    input.addEventListener("change", sync);
  });
}

function clearCategoryRows(containerId) {
  const container = document.getElementById(containerId);
  if (!container) return;
  container.innerHTML = "";
  container.classList.add("hidden");
  delete container._categoryKeys;
  delete container._iconKeys;
}

async function refreshColorByValues(preferredCategories = {}) {
  const layerId = document.getElementById("style-id").value;
  const field = document.getElementById("style-color-by-field")?.value || "";
  const container = document.getElementById("style-color-by-rows");
  const reqId = ++STYLE_COLOR_BY_REQ;
  if (!field) {
    STYLE_COLOR_CATEGORIES = {};
    clearCategoryRows("style-color-by-rows");
    syncStyleFormVisibility();
    updateStylePreview();
    return;
  }
  if (container) {
    container.innerHTML = `<p class="style-panel-hint">Loading values...</p>`;
    container.classList.remove("hidden");
  }
  const values = await fetchDistinctAttributeValues(layerId, field);
  if (reqId !== STYLE_COLOR_BY_REQ) return;
  if (!values) {
    if (container) {
      container.innerHTML = `<p class="style-panel-hint">Could not load values.</p>`;
    }
    syncStyleFormVisibility();
    return;
  }
  renderColorByRows(values, preferredCategories);
  syncStyleFormVisibility();
  updateStylePreview();
}

async function refreshIconByValues(preferredCategories = {}) {
  const layerId = document.getElementById("style-id").value;
  const field = document.getElementById("style-icon-by-field")?.value || "";
  const container = document.getElementById("style-icon-by-rows");
  const defaultIcon = document.getElementById("style-default-icon")?.value || "gl-poi";
  const defaultSize = readMarkerSizeFromDom();
  const reqId = ++STYLE_ICON_BY_REQ;
  if (!field) {
    STYLE_ICON_CATEGORIES = {};
    clearCategoryRows("style-icon-by-rows");
    syncStyleFormVisibility();
    updateStylePreview();
    return;
  }
  if (container) {
    container.innerHTML = `<p class="style-panel-hint">Loading values...</p>`;
    container.classList.remove("hidden");
  }
  const values = await fetchDistinctAttributeValues(layerId, field);
  if (reqId !== STYLE_ICON_BY_REQ) return;
  if (!values) {
    if (container) {
      container.innerHTML = `<p class="style-panel-hint">Could not load values.</p>`;
    }
    syncStyleFormVisibility();
    return;
  }
  renderIconByRows(values, preferredCategories, defaultIcon, defaultSize);
  syncStyleFormVisibility();
  updateStylePreview();
}

function setStyleFieldHidden(id, hidden) {
  document.getElementById(id)?.classList.toggle("hidden", !!hidden);
}

function currentStyleKind() {
  return document.getElementById("style-preview")?.dataset.kind || "line";
}

function isColorByActive() {
  return Boolean(document.getElementById("style-color-by-field")?.value);
}

function isLabelActive() {
  return Boolean(document.getElementById("label-field")?.value);
}

function isPointIconMode() {
  return (
    currentStyleKind() === "point" &&
    (document.getElementById("style-marker-type")?.value || "circle") === "icon"
  );
}

/** Toggle style controls to match share_style paint for the active geometry. */
function syncStyleFormVisibility() {
  const kind = currentStyleKind();
  const colorBy = isColorByActive();
  const labelOn = isLabelActive();
  const pointIcon = isPointIconMode();
  const isPoint = kind === "point";
  const isLine = kind === "line";
  const isFill = kind === "fill";

  setStyleFieldHidden("style-fill-color-wrap", colorBy);
  setStyleFieldHidden("style-stroke-color-wrap", !isFill);
  setStyleFieldHidden(
    "style-stroke-width-wrap",
    pointIcon || !(isLine || isFill || isPoint),
  );

  const widthLabel = document.getElementById("style-stroke-width-label");
  if (widthLabel) {
    if (isFill) widthLabel.textContent = "Outline width";
    else if (isPoint) widthLabel.textContent = "Ring width";
    else widthLabel.textContent = "Width";
  }

  document.getElementById("style-marker-panel")?.classList.toggle("hidden", !isPoint);
  const showIcons = isPoint && pointIcon;
  const iconByOn = showIcons && Boolean(document.getElementById("style-icon-by-field")?.value);
  const hasAttributeFields =
    (document.getElementById("style-color-by-field")?.options?.length || 0) > 1;
  // Same-for-all: show Icon + Size. Icon by attribute: hide those; each row owns icon + size.
  setStyleFieldHidden("style-default-icon-wrap", !showIcons || iconByOn);
  setStyleFieldHidden("style-marker-size-wrap", !(isPoint && (!pointIcon || !iconByOn)));
  setStyleFieldHidden("style-icon-by-wrap", !showIcons || !hasAttributeFields);
  const iconByRows = document.getElementById("style-icon-by-rows");
  if (!showIcons || !hasAttributeFields || !iconByOn) {
    iconByRows?.classList.add("hidden");
  } else if (iconByRows?.childElementCount) {
    iconByRows.classList.remove("hidden");
  }

  setStyleFieldHidden("label-color-wrap", !labelOn);
  setStyleFieldHidden("label-size-wrap", !labelOn);
}

function buildStyleDraftPayload() {
  const values = readStyleFormValues();
  const existingStyle = STYLE_ACTIVE_LAYER?.style || {};
  const kind = currentStyleKind();
  const style = {
    color: values.color,
    opacity: values.opacity,
  };
  if (kind === "fill") {
    style.strokeColor = values.strokeColor;
    style.strokeWidth = values.strokeWidth;
  } else if (kind === "line") {
    style.strokeWidth = values.strokeWidth;
  } else if (kind === "point" && values.marker?.type !== "icon") {
    style.strokeWidth = values.strokeWidth;
  }
  if (existingStyle.useSourceColors && !values.colorBy) {
    style.useSourceColors = true;
  }
  if (values.colorBy) style.colorBy = values.colorBy;
  if (kind === "point" && values.marker) style.marker = values.marker;
  const labelConfig = values.labelField
    ? {
        field: values.labelField,
        color: values.labelColor,
        size: values.labelSize,
      }
    : {};
  return { style, label_config: labelConfig, values };
}

function updateStylePreviewKindBadge(values) {
  const kindBadge = document.getElementById("style-preview-kind");
  if (!kindBadge) return;
  const kind = currentStyleKind();
  const labels = { point: "Point", line: "Line", fill: "Polygon" };
  const base = labels[kind] || "Layer";
  kindBadge.textContent = values?.colorBy?.field
    ? `${base} by ${values.colorBy.field}`
    : base;
}

function setStylePreviewStatus(text) {
  const el = document.getElementById("style-preview-status");
  if (!el) return;
  if (!text) {
    el.classList.add("hidden");
    el.textContent = "";
    return;
  }
  el.textContent = text;
  el.classList.remove("hidden");
}

function clearStylePreviewOverlay() {
  if (!STYLE_PREVIEW_MAP) return;
  STYLE_PREVIEW_LAYER_IDS.forEach((id) => {
    if (STYLE_PREVIEW_MAP.getLayer(id)) STYLE_PREVIEW_MAP.removeLayer(id);
  });
  STYLE_PREVIEW_LAYER_IDS = [];
  if (STYLE_PREVIEW_SOURCE_ID && STYLE_PREVIEW_MAP.getSource(STYLE_PREVIEW_SOURCE_ID)) {
    STYLE_PREVIEW_MAP.removeSource(STYLE_PREVIEW_SOURCE_ID);
  }
  STYLE_PREVIEW_SOURCE_ID = null;
}

function destroyStylePreviewMap() {
  clearTimeout(STYLE_PREVIEW_TIMER);
  STYLE_PREVIEW_TIMER = null;
  if (STYLE_PREVIEW_MAP) {
    STYLE_PREVIEW_MAP.remove();
    STYLE_PREVIEW_MAP = null;
  }
  STYLE_PREVIEW_LAYER_IDS = [];
  STYLE_PREVIEW_SOURCE_ID = null;
  STYLE_PREVIEW_FIT_KEY = "";
}

function fitStylePreviewToBounds(bounds, layerId) {
  if (!STYLE_PREVIEW_MAP || !Array.isArray(bounds) || bounds.length !== 4) return;
  const key = `${layerId}:${bounds.join(",")}`;
  if (STYLE_PREVIEW_FIT_KEY === key) return;
  const [minx, miny, maxx, maxy] = bounds.map(Number);
  if (![minx, miny, maxx, maxy].every(Number.isFinite)) return;
  STYLE_PREVIEW_FIT_KEY = key;
  STYLE_PREVIEW_MAP.fitBounds(
    [
      [minx, miny],
      [maxx, maxy],
    ],
    { padding: 36, maxZoom: 14, duration: 0 },
  );
}

function applyStylePreviewPaint(payload) {
  if (!STYLE_PREVIEW_MAP || !payload?.xyz_url) return;
  clearStylePreviewOverlay();

  const sourceId = payload.source_id || `preview-src-${STYLE_ACTIVE_LAYER?.id || "layer"}`;
  STYLE_PREVIEW_MAP.addSource(sourceId, {
    type: "vector",
    tiles: [payload.xyz_url],
    minzoom: 0,
    maxzoom: 22,
  });
  STYLE_PREVIEW_SOURCE_ID = sourceId;

  window.GeoLayersIcons?.ensureGeoLayersIcons(
    STYLE_PREVIEW_MAP,
    payload.required_icons || [],
  );

  (payload.style_layers || []).forEach((layer) => {
    if (!layer?.id) return;
    STYLE_PREVIEW_MAP.addLayer(layer);
    STYLE_PREVIEW_LAYER_IDS.push(layer.id);
  });

  if (payload.bounds) {
    fitStylePreviewToBounds(payload.bounds, STYLE_ACTIVE_LAYER?.id);
  }
}

async function ensureStylePreviewMap() {
  const container = document.getElementById("style-preview-map");
  const modal = document.getElementById("style-modal");
  if (!container || typeof mapboxgl === "undefined") {
    setStylePreviewStatus("Map preview unavailable.");
    return null;
  }
  if (STYLE_PREVIEW_MAP) {
    STYLE_PREVIEW_MAP.resize();
    return STYLE_PREVIEW_MAP;
  }

  const token = (modal?.dataset.mapboxToken || "").trim();
  if (!token) {
    setStylePreviewStatus("Mapbox token required for live preview.");
    return null;
  }

  mapboxgl.accessToken = token;
  setStylePreviewStatus("Loading map...");

  STYLE_PREVIEW_MAP = new mapboxgl.Map({
    container,
    style: "mapbox://styles/mapbox/streets-v12",
    center: [46.6753, 24.7136],
    zoom: 11,
    attributionControl: false,
    interactive: true,
  });
  STYLE_PREVIEW_MAP.addControl(new mapboxgl.NavigationControl({ showCompass: false }), "top-right");

  await new Promise((resolve) => {
    if (STYLE_PREVIEW_MAP.isStyleLoaded()) resolve();
    else STYLE_PREVIEW_MAP.once("load", resolve);
  });

  setStylePreviewStatus("");
  return STYLE_PREVIEW_MAP;
}

async function refreshStylePreviewNow() {
  const layer = STYLE_ACTIVE_LAYER;
  if (!layer?.id) return;
  const draft = buildStyleDraftPayload();
  updateStylePreviewKindBadge(draft.values);

  const reqId = ++STYLE_PREVIEW_REQ;
  setStylePreviewStatus("Updating style...");
  try {
    const map = await ensureStylePreviewMap();
    if (!map || reqId !== STYLE_PREVIEW_REQ) return;

    const res = await Auth.apiFetch(`/api/layers/${layer.id}/preview-style/`, {
      method: "POST",
      body: {
        style: draft.style,
        label_config: draft.label_config,
      },
    });
    if (reqId !== STYLE_PREVIEW_REQ) return;
    if (!res.ok) {
      throw new Error(await Toast.fromResponse(res, "Could not load preview."));
    }
    const payload = await res.json();
    if (reqId !== STYLE_PREVIEW_REQ) return;

    applyStylePreviewPaint(payload);
    setStylePreviewStatus("");
    requestAnimationFrame(() => STYLE_PREVIEW_MAP?.resize());
  } catch (err) {
    if (reqId !== STYLE_PREVIEW_REQ) return;
    setStylePreviewStatus(err.message || "Preview failed.");
  }
}

function updateStylePreview() {
  clearTimeout(STYLE_PREVIEW_TIMER);
  STYLE_PREVIEW_TIMER = window.setTimeout(() => {
    refreshStylePreviewNow();
  }, 280);
}

function setStylePreviewExpanded(expanded) {
  STYLE_PREVIEW_EXPANDED = !!expanded;
  const card = document.getElementById("style-preview-card");
  const backdrop = document.getElementById("style-preview-backdrop");
  const expandBtn = document.getElementById("style-preview-expand");
  const collapseBtn = document.getElementById("style-preview-collapse");

  if (card) {
    if (STYLE_PREVIEW_EXPANDED) {
      // Move above the style-modal stacking context so the glassy backdrop can sit under the card.
      if (!STYLE_PREVIEW_HOME) {
        STYLE_PREVIEW_HOME = { parent: card.parentNode, next: card.nextSibling };
        const slot = document.createElement("div");
        slot.id = "style-preview-slot";
        slot.className = "style-preview-slot";
        slot.setAttribute("aria-hidden", "true");
        STYLE_PREVIEW_HOME.parent.insertBefore(slot, card);
        document.body.appendChild(card);
      }
      card.classList.add("is-expanded");
    } else {
      card.classList.remove("is-expanded");
      if (STYLE_PREVIEW_HOME?.parent) {
        const slot = document.getElementById("style-preview-slot");
        if (slot?.parentNode) {
          slot.parentNode.replaceChild(card, slot);
        } else if (STYLE_PREVIEW_HOME.next?.parentNode === STYLE_PREVIEW_HOME.parent) {
          STYLE_PREVIEW_HOME.parent.insertBefore(card, STYLE_PREVIEW_HOME.next);
        } else {
          STYLE_PREVIEW_HOME.parent.appendChild(card);
        }
        STYLE_PREVIEW_HOME = null;
      }
    }
  }

  backdrop?.classList.toggle("hidden", !STYLE_PREVIEW_EXPANDED);
  expandBtn?.classList.toggle("hidden", STYLE_PREVIEW_EXPANDED);
  collapseBtn?.classList.toggle("hidden", !STYLE_PREVIEW_EXPANDED);
  if (backdrop) backdrop.setAttribute("aria-hidden", STYLE_PREVIEW_EXPANDED ? "false" : "true");
  requestAnimationFrame(() => {
    STYLE_PREVIEW_MAP?.resize();
  });
}

function closeStyleModal() {
  setStylePreviewExpanded(false);
  destroyStylePreviewMap();
  STYLE_ACTIVE_LAYER = null;
  Auth.closeModal("style-modal");
}

function openStyleModal(layer) {
  STYLE_ACTIVE_LAYER = layer;
  document.getElementById("style-id").value = layer.id;

  const kind = styleGeometryKind(layer.geometry_type);
  const preview = document.getElementById("style-preview");
  if (preview) preview.dataset.kind = kind;

  const style = layer.style || {};
  setColorPair("style-fill-color", "style-fill-color-picker", style.color, "#0F2D53");
  setColorPair("style-stroke-color", "style-stroke-color-picker", style.strokeColor, "#0a2140");
  document.getElementById("style-stroke-width").value = style.strokeWidth ?? 1;
  document.getElementById("style-opacity").value = style.opacity ?? 0.6;

  const fields = (layer.attribute_schema || []).map((f) => f.name).filter(Boolean);
  const colorBy = style.colorBy && typeof style.colorBy === "object" ? style.colorBy : null;
  const colorBySelect = document.getElementById("style-color-by-field");
  if (colorBySelect) {
    colorBySelect.innerHTML = fieldOptionsHtml(fields, colorBy?.field || "", "None");
  }

  const marker = style.marker && typeof style.marker === "object" ? style.marker : {};
  const markerType = document.getElementById("style-marker-type");
  const markerSize = document.getElementById("style-marker-size");
  const defaultIcon = document.getElementById("style-default-icon");
  const iconBySelect = document.getElementById("style-icon-by-field");
  if (markerType) markerType.value = marker.type === "icon" ? "icon" : "circle";
  if (markerSize) {
    const size = Number(marker.size);
    markerSize.value = Number.isFinite(size) ? Math.min(4, Math.max(0.25, size)) : 1;
  }
  if (defaultIcon) {
    defaultIcon.innerHTML = iconOptionsHtml(marker.icon || "gl-poi");
    defaultIcon.value = marker.icon || "gl-poi";
  }
  if (iconBySelect) {
    iconBySelect.innerHTML = fieldOptionsHtml(
      fields,
      marker.iconBy?.field || "",
      "Same for all",
    );
  }

  const labelSelect = document.getElementById("label-field");
  labelSelect.innerHTML = fieldOptionsHtml(fields, "", "None");
  const labelConfig = layer.label_config || {};
  labelSelect.value = labelConfig.field || "";
  setColorPair("label-color", "label-color-picker", labelConfig.color, "#0F2D53");
  document.getElementById("label-size").value = labelConfig.size || 12;

  const hasAttributes = fields.length > 0;
  colorBySelect?.closest(".style-panel")?.classList.toggle("hidden", !hasAttributes);
  labelSelect.closest(".style-panel")?.classList.toggle("hidden", !hasAttributes);
  if (!hasAttributes) {
    if (colorBySelect) colorBySelect.value = "";
    labelSelect.value = "";
  }

  const canEdit = layer.my_permission === "owner" || layer.my_permission === "edit";
  document.getElementById("style-form").querySelectorAll("input,select,button[type=submit]").forEach((el) => {
    el.disabled = !canEdit;
  });
  // Keep expand/collapse usable while editing is locked.
  document.getElementById("style-preview-expand").disabled = false;
  document.getElementById("style-preview-collapse").disabled = false;

  STYLE_COLOR_CATEGORIES = { ...(colorBy?.categories || {}) };
  STYLE_ICON_CATEGORIES = normalizeIconCategoryMap(
    marker.iconBy?.categories || {},
    marker.icon || "gl-poi",
    Number.isFinite(Number(marker.size)) ? Number(marker.size) : 1,
  );
  clearCategoryRows("style-color-by-rows");
  clearCategoryRows("style-icon-by-rows");
  STYLE_PREVIEW_FIT_KEY = "";
  setStylePreviewExpanded(false);
  syncStyleFormVisibility();
  Auth.openModal("style-modal");
  updateStylePreview();
  refreshColorByValues(colorBy?.categories || {});
  if (kind === "point" && marker.type === "icon" && marker.iconBy?.field) {
    refreshIconByValues(marker.iconBy.categories || {});
  }
}

document.getElementById("style-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const id = document.getElementById("style-id").value;
  const payload = buildStyleDraftPayload();
  try {
    const res = await Auth.apiFetch(`/api/layers/${id}/`, {
      method: "PATCH",
      body: {
        style: payload.style,
        label_config: payload.label_config,
      },
    });
    if (!res.ok) {
      throw new Error(await Toast.fromResponse(res, "Could not save style."));
    }
    closeStyleModal();
    await loadLayers();
    Toast.success("Style saved.");
  } catch (err) {
    Toast.error(err.message || "Could not save style.");
  }
});

["style-stroke-width", "style-opacity", "style-marker-size", "label-size"].forEach((id) => {
  const el = document.getElementById(id);
  el?.addEventListener("input", updateStylePreview);
  el?.addEventListener("change", updateStylePreview);
});
document.getElementById("label-field")?.addEventListener("change", () => {
  syncStyleFormVisibility();
  updateStylePreview();
});
document.getElementById("style-color-by-field")?.addEventListener("change", () => {
  STYLE_COLOR_CATEGORIES = {};
  syncStyleFormVisibility();
  refreshColorByValues();
});
document.getElementById("style-marker-type")?.addEventListener("change", () => {
  syncStyleFormVisibility();
  if (document.getElementById("style-marker-type").value === "icon") {
    refreshIconByValues(STYLE_ICON_CATEGORIES);
    return;
  }
  STYLE_ICON_CATEGORIES = {};
  clearCategoryRows("style-icon-by-rows");
  updateStylePreview();
});
document.getElementById("style-default-icon")?.addEventListener("change", updateStylePreview);
document.getElementById("style-icon-by-field")?.addEventListener("change", () => {
  STYLE_ICON_CATEGORIES = {};
  refreshIconByValues();
});

document.getElementById("style-cancel-btn")?.addEventListener("click", closeStyleModal);
document.getElementById("style-preview-expand")?.addEventListener("click", () => {
  setStylePreviewExpanded(true);
});
document.getElementById("style-preview-collapse")?.addEventListener("click", () => {
  setStylePreviewExpanded(false);
});
document.getElementById("style-preview-backdrop")?.addEventListener("click", () => {
  setStylePreviewExpanded(false);
});
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  if (STYLE_PREVIEW_EXPANDED) {
    event.preventDefault();
    setStylePreviewExpanded(false);
    return;
  }
  const modal = document.getElementById("style-modal");
  if (modal && !modal.classList.contains("hidden")) {
    closeStyleModal();
  }
});

// ---- Share (GeoTrak Layers users + external share) ----

function openRevokeLinkModal(layerId, linkId) {
  document.getElementById("revoke-link-layer-id").value = layerId;
  document.getElementById("revoke-link-id").value = linkId;
  Auth.openModal("revoke-link-modal");
}

function renderShareList(layer) {
  ShareUi.renderPeopleList(layer?.shares || [], {
    onRemove: async (userId) => {
      const layerId = document.getElementById("share-layer-id").value;
      try {
        const res = await Auth.apiFetch(`/api/layers/${layerId}/unshare/`, {
          method: "POST",
          body: { user_id: userId },
        });
        if (!res.ok) {
          throw new Error(await Toast.fromResponse(res, "Could not remove access."));
        }
        await loadLayers();
        renderShareList(findLayer(layerId));
        Toast.success("Access removed.");
      } catch (err) {
        Toast.error(err.message || "Could not remove access.");
      }
    },
  });
}

function openShareModal(layer) {
  if (layer.my_permission !== "owner") {
    Toast.error("Only the layer owner can share this layer.");
    return;
  }
  document.getElementById("share-layer-id").value = layer.id;
  ShareUi.prepareOpen({
    subtitleEl: document.getElementById("share-layer-sub"),
    subtitle: layer.name
      ? `Sharing "${layer.name}"`
      : "Share with GeoTrak Layers users or create an external link",
  });
  renderShareList(layer);
  ShareUi.loadShareLinks({
    listUrl: `/api/layers/${layer.id}/share-links/`,
    onRevoke: (linkId) => openRevokeLinkModal(layer.id, linkId),
  });
  Auth.openModal("share-modal");
}

ShareUi.bindModal({
  getResourceId: () => document.getElementById("share-layer-id")?.value,
  getRevokeResourceId: () => document.getElementById("revoke-link-layer-id")?.value,
  shareUrl: (id) => `/api/layers/${id}/share/`,
  shareLinksUrl: (id) => `/api/layers/${id}/share-links/`,
  revokeUrl: (id, linkId) => `/api/layers/${id}/share-links/${linkId}/`,
  shareSuccess: "Layer shared.",
  shareError: "Could not share layer.",
  onRevoke: (layerId, linkId) => openRevokeLinkModal(layerId, linkId),
  afterPeopleChange: async () => {
    const layerId = document.getElementById("share-layer-id").value;
    await loadLayers();
    renderShareList(findLayer(layerId));
  },
});

document.addEventListener("DOMContentLoaded", () => {
  bindColorPair("style-fill-color", "style-fill-color-picker", "#0F2D53", updateStylePreview);
  bindColorPair("style-stroke-color", "style-stroke-color-picker", "#0a2140", updateStylePreview);
  bindColorPair("label-color", "label-color-picker", "#0F2D53", updateStylePreview);
  loadLayers();
});
