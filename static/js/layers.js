let CURRENT_LAYERS = [];
let SELECTED_SHARE_USER = null;

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
  return String(permission || "").replace(/_/g, " ");
}

async function loadLayers() {
  const res = await Auth.apiFetch("/api/layers/");
  const data = await res.json();
  CURRENT_LAYERS = data.results || data;
  renderLayers();
}

function renderLayers() {
  const tbody = document.getElementById("layers-tbody");
  if (!CURRENT_LAYERS.length) {
    tbody.innerHTML = `<tr><td colspan="6"><div class="empty-state"><strong>No layers yet</strong>Upload a shapefile to get started.</div></td></tr>`;
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
          <button type="button" class="action-btn" data-action="share" data-id="${layer.id}" title="Share">
            ${LAYER_ICONS.share}<span>Share</span>
          </button>
          ${layer.my_permission === "owner" ? `
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
document.getElementById("open-upload-modal").addEventListener("click", () => Auth.openModal("upload-modal"));

document.getElementById("upload-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const errorBox = document.getElementById("upload-error");
  errorBox.classList.add("hidden");
  const submitBtn = document.getElementById("upload-submit");
  submitBtn.disabled = true;
  submitBtn.textContent = "Importing…";

  const formData = new FormData();
  formData.append("name", document.getElementById("upload-name").value);
  formData.append("description", document.getElementById("upload-description").value);
  formData.append("file", document.getElementById("upload-file").files[0]);

  try {
    const res = await Auth.apiFetch("/api/layers/", { method: "POST", body: formData });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || JSON.stringify(body));
    }
    document.getElementById("upload-form").reset();
    Auth.closeModal("upload-modal");
    await loadLayers();
  } catch (err) {
    errorBox.textContent = err.message;
    errorBox.classList.remove("hidden");
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
  const payload = {
    name: document.getElementById("rename-name").value,
    description: document.getElementById("rename-description").value,
  };
  const res = await Auth.apiFetch(`/api/layers/${id}/`, { method: "PATCH", body: payload });
  if (res.ok) {
    Auth.closeModal("rename-modal");
    await loadLayers();
  }
});

// ---- Delete ----
async function deleteLayer(layer) {
  if (!confirm(`Delete layer "${layer.name}"? This also drops its data table and cannot be undone.`)) return;
  const res = await Auth.apiFetch(`/api/layers/${layer.id}/`, { method: "DELETE" });
  if (res.ok || res.status === 204) await loadLayers();
}

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

function stylePreviewKind(geometryType) {
  const raw = String(geometryType || "").toLowerCase();
  if (raw.includes("point")) return "point";
  if (raw.includes("line")) return "line";
  return "fill";
}

let STYLE_LABEL_SAMPLE = "";
let STYLE_LABEL_SAMPLE_FIELD = "";
let STYLE_LABEL_SAMPLE_REQ = 0;

function readStyleFormValues() {
  return {
    color: normalizeHexColor(document.getElementById("style-fill-color").value, "#0F2D53"),
    strokeColor: normalizeHexColor(document.getElementById("style-stroke-color").value, "#0a2140"),
    strokeWidth: Math.max(0, parseFloat(document.getElementById("style-stroke-width").value || "1") || 0),
    opacity: Math.min(1, Math.max(0, parseFloat(document.getElementById("style-opacity").value || "0.6") || 0)),
    labelField: document.getElementById("label-field").value,
    labelColor: normalizeHexColor(document.getElementById("label-color").value, "#0F2D53"),
    labelSize: Math.min(36, Math.max(8, parseInt(document.getElementById("label-size").value || "12", 10) || 12)),
  };
}

function truncatePreviewLabel(text, maxLen = 28) {
  const value = String(text || "").trim();
  if (!value) return "";
  if (value.length <= maxLen) return value;
  return `${value.slice(0, maxLen - 1)}…`;
}

function updateStylePreview() {
  const preview = document.getElementById("style-preview");
  const shape = document.getElementById("style-preview-shape");
  const labelEl = document.getElementById("style-preview-label");
  const kindBadge = document.getElementById("style-preview-kind");
  if (!preview || !shape || !labelEl) return;

  const kind = preview.dataset.kind || "line";
  const values = readStyleFormValues();
  const strokeWidth = Math.max(values.strokeWidth, kind === "line" ? 1 : 0);

  const labels = { point: "Point", line: "Line", fill: "Polygon" };
  if (kindBadge) kindBadge.textContent = labels[kind] || "Layer";

  let markup = "";
  if (kind === "point") {
    markup = `
      <circle cx="120" cy="64" r="12"
        fill="${values.color}" fill-opacity="${values.opacity}"
        stroke="${values.strokeColor}" stroke-width="${Math.max(strokeWidth, 1)}"/>
    `;
  } else if (kind === "line") {
    markup = `
      <path d="M24 98 C 60 34, 96 34, 120 70 S 180 108, 216 42"
        fill="none" stroke="${values.color}" stroke-opacity="${values.opacity}"
        stroke-width="${Math.max(strokeWidth, 1.5)}" stroke-linecap="round" stroke-linejoin="round"/>
    `;
  } else {
    markup = `
      <path d="M40 100 L82 36 L144 48 L200 30 L214 100 Z"
        fill="${values.color}" fill-opacity="${values.opacity}"
        stroke="${values.strokeColor}" stroke-width="${Math.max(strokeWidth, 1)}"
        stroke-linejoin="round"/>
    `;
  }
  shape.innerHTML = markup;

  const hasSample =
    values.labelField &&
    STYLE_LABEL_SAMPLE_FIELD === values.labelField &&
    STYLE_LABEL_SAMPLE;
  if (hasSample) {
    labelEl.textContent = truncatePreviewLabel(STYLE_LABEL_SAMPLE);
    labelEl.setAttribute("fill", values.labelColor);
    labelEl.setAttribute("font-size", String(values.labelSize));
    labelEl.removeAttribute("hidden");
  } else {
    labelEl.textContent = "";
    labelEl.setAttribute("hidden", "");
  }
}

async function refreshStyleLabelSample() {
  const layerId = document.getElementById("style-id").value;
  const field = document.getElementById("label-field").value;
  const reqId = ++STYLE_LABEL_SAMPLE_REQ;

  if (!layerId || !field) {
    STYLE_LABEL_SAMPLE = "";
    STYLE_LABEL_SAMPLE_FIELD = "";
    updateStylePreview();
    return;
  }

  STYLE_LABEL_SAMPLE_FIELD = field;
  STYLE_LABEL_SAMPLE = "";
  updateStylePreview();

  const res = await Auth.apiFetch(
    `/api/layers/${layerId}/sample-attribute/?field=${encodeURIComponent(field)}`
  );
  if (reqId !== STYLE_LABEL_SAMPLE_REQ) return;

  if (!res.ok) {
    STYLE_LABEL_SAMPLE = "";
    updateStylePreview();
    return;
  }
  const body = await res.json().catch(() => ({}));
  STYLE_LABEL_SAMPLE = (body.value && String(body.value).trim()) || "";
  STYLE_LABEL_SAMPLE_FIELD = field;
  updateStylePreview();
}

function openStyleModal(layer) {
  document.getElementById("style-id").value = layer.id;

  const kind = stylePreviewKind(layer.geometry_type);
  const preview = document.getElementById("style-preview");
  if (preview) preview.dataset.kind = kind;

  const style = layer.style || {};
  setColorPair("style-fill-color", "style-fill-color-picker", style.color, "#0F2D53");
  setColorPair("style-stroke-color", "style-stroke-color-picker", style.strokeColor, "#0a2140");
  document.getElementById("style-stroke-width").value = style.strokeWidth ?? 1;
  document.getElementById("style-opacity").value = style.opacity ?? 0.6;

  const labelSelect = document.getElementById("label-field");
  const fields = (layer.attribute_schema || []).map((f) => f.name);
  labelSelect.innerHTML = `<option value="">None</option>` +
    fields.map((f) => `<option value="${Auth.escapeHtml(f)}">${Auth.escapeHtml(f)}</option>`).join("");

  const labelConfig = layer.label_config || {};
  labelSelect.value = labelConfig.field || "";
  setColorPair("label-color", "label-color-picker", labelConfig.color, "#0F2D53");
  document.getElementById("label-size").value = labelConfig.size || 12;

  const canEdit = layer.my_permission === "owner" || layer.my_permission === "edit";
  document.getElementById("style-form").querySelectorAll("input,select,button[type=submit]").forEach((el) => {
    el.disabled = !canEdit;
  });

  STYLE_LABEL_SAMPLE = "";
  STYLE_LABEL_SAMPLE_FIELD = "";
  updateStylePreview();
  Auth.openModal("style-modal");
  refreshStyleLabelSample();
}

document.getElementById("style-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const id = document.getElementById("style-id").value;
  const values = readStyleFormValues();
  const payload = {
    style: {
      color: values.color,
      strokeColor: values.strokeColor,
      strokeWidth: values.strokeWidth,
      opacity: values.opacity,
    },
    label_config: {
      field: values.labelField,
      color: values.labelColor,
      size: values.labelSize,
    },
  };
  const res = await Auth.apiFetch(`/api/layers/${id}/`, { method: "PATCH", body: payload });
  if (res.ok) {
    Auth.closeModal("style-modal");
    await loadLayers();
  }
});

["style-stroke-width", "style-opacity", "label-size"].forEach((id) => {
  const el = document.getElementById(id);
  el?.addEventListener("input", updateStylePreview);
  el?.addEventListener("change", updateStylePreview);
});
document.getElementById("label-field")?.addEventListener("change", refreshStyleLabelSample);

// ---- Share (people + External Share) ----
let SHARE_COPY_RESET = null;

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
  if (isExternal) {
    peoplePanel.hidden = true;
    externalPanel.hidden = false;
    externalPanel.classList.add("is-entering");
    window.setTimeout(() => externalPanel.classList.remove("is-entering"), 280);
  } else {
    externalPanel.hidden = true;
    peoplePanel.hidden = false;
    peoplePanel.classList.add("is-entering");
    window.setTimeout(() => peoplePanel.classList.remove("is-entering"), 280);
  }
}

function getExternalLinkType() {
  const selected = document.querySelector('input[name="external-link-type"]:checked');
  return selected?.value === "permanent" ? "permanent" : "expiring";
}

function syncExternalExpiryControls() {
  const isPermanent = getExternalLinkType() === "permanent";
  const expiryWrap = document.getElementById("external-expiry-wrap");
  const expiryInput = document.getElementById("external-expiry");
  expiryWrap?.classList.toggle("is-hidden", isPermanent);
  if (expiryInput) {
    expiryInput.required = !isPermanent;
    expiryInput.disabled = isPermanent;
    if (isPermanent) expiryInput.value = "";
  }
}

function resetExternalCreateForm() {
  const expiring = document.querySelector('input[name="external-link-type"][value="expiring"]');
  if (expiring) expiring.checked = true;
  const expiryInput = document.getElementById("external-expiry");
  const tomorrow = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
  if (expiryInput) {
    expiryInput.min = tomorrow;
    expiryInput.value = "";
  }
  document.getElementById("external-create-error")?.classList.add("hidden");
  syncExternalExpiryControls();
}

function openShareModal(layer) {
  document.getElementById("share-layer-id").value = layer.id;
  document.getElementById("share-search").value = "";
  document.getElementById("share-results").innerHTML = "";
  document.getElementById("share-submit").disabled = true;
  SELECTED_SHARE_USER = null;

  const isOwner = layer.my_permission === "owner";
  document.getElementById("share-people-owner").classList.toggle("hidden", !isOwner);
  document.getElementById("share-people-viewer").classList.toggle("hidden", isOwner);
  document.getElementById("external-owner-only").classList.toggle("hidden", !isOwner);
  document.getElementById("external-viewer-note").classList.toggle("hidden", isOwner);

  document.getElementById("external-copy-status").textContent = "";
  document.getElementById("external-copy-status").classList.remove("is-visible");
  resetExternalCreateForm();

  if (isOwner) {
    renderShareList(layer);
    loadShareLinks(layer.id);
  }
  setShareTab("people");
  Auth.openModal("share-modal");
}

// ---- External share links (optional expiry, revocable) ----
async function loadShareLinks(layerId) {
  const list = document.getElementById("external-links-list");
  list.innerHTML = `<li class="share-empty">Loading…</li>`;
  const res = await Auth.apiFetch(`/api/layers/${layerId}/share-links/`);
  if (!res.ok) {
    list.innerHTML = `<li class="share-empty">Could not load share links.</li>`;
    return;
  }
  const links = await res.json();
  renderShareLinks(layerId, links);
}

function formatExpiry(isoString) {
  const date = new Date(isoString);
  return date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function simplifyGeometryLabel(geometryType, suggestedGeometry) {
  const suggested = String(suggestedGeometry || "").toLowerCase();
  if (suggested === "line" || suggested === "fill" || suggested === "circle") {
    return suggested;
  }
  const raw = String(geometryType || "").toLowerCase();
  if (raw.includes("line")) return "line";
  if (raw.includes("polygon")) return "fill";
  if (raw.includes("point")) return "circle";
  return raw || "—";
}

const ICON_COPY = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="8.5" y="8.5" width="10" height="12" rx="1.5" stroke="currentColor" stroke-width="1.7"/><path d="M15.5 8.5V6.2A1.7 1.7 0 0 0 13.8 4.5H6.2A1.7 1.7 0 0 0 4.5 6.2v7.6A1.7 1.7 0 0 0 6.2 15.5H8.5" stroke="currentColor" stroke-width="1.7"/></svg>`;
const ICON_TRASH = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 7.5h14M10 7.5V5.8A1.3 1.3 0 0 1 11.3 4.5h1.4A1.3 1.3 0 0 1 14 5.8V7.5M8.5 7.5v11.2A1.3 1.3 0 0 0 9.8 20h4.4a1.3 1.3 0 0 0 1.3-1.3V7.5" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
const ICON_USERS = `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="9" cy="8" r="3.1" stroke="currentColor" stroke-width="1.6"/><path d="M3.8 18.2c.7-2.7 2.8-4.2 5.2-4.2s4.5 1.5 5.2 4.2" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><circle cx="16.5" cy="9" r="2.4" stroke="currentColor" stroke-width="1.6"/><path d="M15.2 14.2c1.7.2 3.2 1.2 3.9 3.2" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><path d="M18.2 5.2v3.2M16.6 6.8h3.2" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>`;
const ICON_LINK = `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M10.2 13.8a4.2 4.2 0 0 1 0-5.9l2.1-2.1a4.2 4.2 0 0 1 5.9 5.9l-1 1" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><path d="M13.8 10.2a4.2 4.2 0 0 1 0 5.9l-2.1 2.1a4.2 4.2 0 1 1-5.9-5.9l1-1" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>`;

function formatExpiryLabel(link) {
  if (link.never_expires || !link.expires_at) {
    return `<span class="external-pill external-pill-live"><span class="external-pill-dot" aria-hidden="true"></span>No expiry</span>`;
  }
  if (link.is_expired) {
    return `<span class="external-pill external-pill-expired"><span class="external-pill-dot" aria-hidden="true"></span>Expired ${formatExpiry(link.expires_at)}</span>`;
  }
  return `<span class="external-pill"><span class="external-pill-dot" aria-hidden="true"></span>Expires ${formatExpiry(link.expires_at)}</span>`;
}

function renderShareLinks(layerId, links) {
  const list = document.getElementById("external-links-list");
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
    const geometryLabel = simplifyGeometryLabel(link.geometry_type, link.suggested_geometry);
    const requests = Number(link.total_requests || 0).toLocaleString();
    const lastUsed = link.last_used_at ? formatExpiry(link.last_used_at) : "Never";
    const tileUrl = Auth.escapeHtml(link.xyz_url);
    const sourceLayer = Auth.escapeHtml(link.source_layer);
    return `
    <li class="external-link-card">
      <div class="external-link-top">
        <div class="external-link-badges">
          ${formatExpiryLabel(link)}
          ${link.is_blocked ? `<span class="external-pill external-pill-blocked"><span class="external-pill-dot" aria-hidden="true"></span>Blocked</span>` : ""}
        </div>
        <div class="external-link-actions">
          <button type="button" class="btn btn-sm external-action-btn" data-copy-link="${tileUrl}">${ICON_COPY}<span>Copy URL</span></button>
          <button type="button" class="btn btn-sm btn-danger external-action-btn" data-revoke-link="${link.id}">${ICON_TRASH}<span>Revoke</span></button>
        </div>
      </div>

      <div class="external-field">
        <span class="external-field-label">Tile URL</span>
        <input class="external-input" type="text" readonly value="${tileUrl}" aria-label="Tile URL">
      </div>

      <div class="external-meta-grid">
        <div class="external-field">
          <span class="external-field-label">Source layer</span>
          <div class="external-chip-row">
            <input class="external-input" type="text" readonly value="${sourceLayer}" aria-label="Source layer">
            <button type="button" class="btn btn-sm" data-copy-source="${sourceLayer}">Copy</button>
          </div>
        </div>
        <div class="external-field">
          <span class="external-field-label">Geometry</span>
          <input class="external-input" type="text" readonly value="${Auth.escapeHtml(geometryLabel)}" aria-label="Geometry">
        </div>
      </div>

      <div class="external-stats" aria-label="Usage">
        <div class="external-stat">
          <span class="external-stat-label">Tile requests</span>
          <span class="external-stat-value">${requests}</span>
        </div>
        <div class="external-stat">
          <span class="external-stat-label">Last used</span>
          <span class="external-stat-value">${Auth.escapeHtml(lastUsed)}</span>
        </div>
      </div>
    </li>`;
  }).join("");

  list.querySelectorAll("[data-copy-link]").forEach((btn) => {
    btn.addEventListener("click", () => copyToClipboardWithFeedback(btn.dataset.copyLink, btn, "Tile URL copied."));
  });
  list.querySelectorAll("[data-copy-source]").forEach((btn) => {
    btn.addEventListener("click", () => copyToClipboardWithFeedback(btn.dataset.copySource, btn, "Source layer copied."));
  });
  list.querySelectorAll("[data-revoke-link]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm("Revoke this external share link? Anyone using it will immediately lose access.")) return;
      await Auth.apiFetch(`/api/layers/${layerId}/share-links/${btn.dataset.revokeLink}/`, { method: "DELETE" });
      await loadShareLinks(layerId);
    });
  });
}

document.querySelectorAll('input[name="external-link-type"]').forEach((input) => {
  input.addEventListener("change", syncExternalExpiryControls);
});

document.getElementById("external-create-btn").addEventListener("click", async () => {
  const layer = findLayer(document.getElementById("share-layer-id").value);
  if (!layer) return;
  const errorBox = document.getElementById("external-create-error");
  errorBox.classList.add("hidden");

  const isPermanent = getExternalLinkType() === "permanent";
  const expiryValue = document.getElementById("external-expiry").value;
  let body = { expires_at: null };

  if (!isPermanent) {
    if (!expiryValue) {
      errorBox.textContent = "Choose an expiry date.";
      errorBox.classList.remove("hidden");
      return;
    }
    body = { expires_at: new Date(`${expiryValue}T23:59:59`).toISOString() };
  }

  const btn = document.getElementById("external-create-btn");
  btn.disabled = true;
  try {
    const res = await Auth.apiFetch(`/api/layers/${layer.id}/share-links/`, {
      method: "POST",
      body,
    });
    if (!res.ok) {
      const errBody = await res.json().catch(() => ({}));
      throw new Error(errBody.expires_at?.[0] || errBody.detail || "Could not generate the link.");
    }
    resetExternalCreateForm();
    await loadShareLinks(layer.id);
  } catch (err) {
    errorBox.textContent = err.message;
    errorBox.classList.remove("hidden");
  } finally {
    btn.disabled = false;
  }
});

function renderShareList(layer) {
  const list = document.getElementById("share-list");
  const shares = layer.shares || [];
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
  list.innerHTML = shares.map((s) => Auth.renderSharePerson(s.shared_with_detail, {
    permission: s.permission,
    actionHtml: `<button type="button" class="btn btn-sm row-remove" data-remove-share="${s.shared_with_detail.id}">Remove</button>`,
  })).join("");
  list.querySelectorAll("[data-remove-share]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const layerId = document.getElementById("share-layer-id").value;
      await Auth.apiFetch(`/api/layers/${layerId}/unshare/`, {
        method: "POST",
        body: { user_id: btn.dataset.removeShare },
      });
      await loadLayers();
      renderShareList(findLayer(layerId));
    });
  });
}

let shareSearchTimeout;
document.getElementById("share-search").addEventListener("input", (event) => {
  clearTimeout(shareSearchTimeout);
  const query = event.target.value.trim();
  const box = document.getElementById("share-results");
  if (!query) {
    box.innerHTML = "";
    return;
  }
  shareSearchTimeout = setTimeout(async () => {
    const res = await Auth.apiFetch(`/api/auth/users/?search=${encodeURIComponent(query)}`);
    const data = await res.json();
    const results = data.results || data;
    if (!results.length) {
      box.innerHTML = `<p class="share-empty-inline muted">No users found.</p>`;
      return;
    }
    box.innerHTML = `<div class="share-results-list">${results.map((u) => Auth.renderShareHit(u)).join("")}</div>`;
    box.querySelectorAll("[data-user-id]").forEach((row) => {
      row.addEventListener("click", () => {
        SELECTED_SHARE_USER = results.find((u) => String(u.id) === row.dataset.userId);
        document.getElementById("share-search").value =
          SELECTED_SHARE_USER.display_name || SELECTED_SHARE_USER.username;
        box.innerHTML = "";
        document.getElementById("share-submit").disabled = false;
      });
    });
  }, 250);
});

document.getElementById("share-submit").addEventListener("click", async () => {
  if (!SELECTED_SHARE_USER) return;
  const layerId = document.getElementById("share-layer-id").value;
  const permission = document.getElementById("share-permission").value;
  await Auth.apiFetch(`/api/layers/${layerId}/share/`, {
    method: "POST",
    body: { shared_with: SELECTED_SHARE_USER.id, permission },
  });
  await loadLayers();
  renderShareList(findLayer(layerId));
  document.getElementById("share-submit").disabled = true;
  SELECTED_SHARE_USER = null;
  document.getElementById("share-search").value = "";
});

document.querySelectorAll("[data-share-tab]").forEach((btn) => {
  btn.addEventListener("click", () => setShareTab(btn.dataset.shareTab));
});

async function copyToClipboardWithFeedback(text, button, successText) {
  const status = document.getElementById("external-copy-status");
  clearTimeout(SHARE_COPY_RESET);

  try {
    await copyTextToClipboard(text);
    document.querySelectorAll("#external-links-list .is-copied").forEach((btn) => btn.classList.remove("is-copied"));
    button.classList.add("is-copied");
    status.textContent = successText;
    status.classList.add("is-visible");
    SHARE_COPY_RESET = window.setTimeout(() => {
      button.classList.remove("is-copied");
      status.classList.remove("is-visible");
    }, 1800);
  } catch {
    status.textContent = "Copy failed — select the text and copy manually.";
    status.classList.add("is-visible");
  }
}

/** Clipboard API needs a secure context (HTTPS/localhost). Fall back for plain HTTP hosts. */
function copyTextToClipboard(text) {
  if (navigator.clipboard && window.isSecureContext) {
    return navigator.clipboard.writeText(text);
  }
  return new Promise((resolve, reject) => {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.top = "0";
    textarea.style.left = "-9999px";
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    textarea.setSelectionRange(0, textarea.value.length);
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch (err) {
      document.body.removeChild(textarea);
      reject(err);
      return;
    }
    document.body.removeChild(textarea);
    if (ok) resolve();
    else reject(new Error("execCommand copy failed"));
  });
}

document.addEventListener("DOMContentLoaded", () => {
  bindColorPair("style-fill-color", "style-fill-color-picker", "#0F2D53", updateStylePreview);
  bindColorPair("style-stroke-color", "style-stroke-color-picker", "#0a2140", updateStylePreview);
  bindColorPair("label-color", "label-color-picker", "#0F2D53", updateStylePreview);
  loadLayers();
});
