let CURRENT_LAYERS = [];
let SELECTED_SHARE_USER = null;

function openModal(id) { document.getElementById(id).classList.remove("hidden"); }
function closeModal(id) { document.getElementById(id).classList.add("hidden"); }

document.querySelectorAll("[data-close-modal]").forEach((btn) => {
  btn.addEventListener("click", () => closeModal(btn.dataset.closeModal));
});

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
  tbody.innerHTML = CURRENT_LAYERS.map((layer) => `
    <tr>
      <td>${layer.name}</td>
      <td>${layer.geometry_type}</td>
      <td>${layer.feature_count}</td>
      <td>${layer.owner_detail ? layer.owner_detail.display_name : ""}</td>
      <td><span class="badge">${layer.my_permission}</span></td>
      <td class="table-actions">
        <button class="btn btn-sm" data-action="style" data-id="${layer.id}">Style</button>
        <button class="btn btn-sm" data-action="share" data-id="${layer.id}">Share</button>
        ${layer.my_permission === "owner" ? `
          <button class="btn btn-sm" data-action="rename" data-id="${layer.id}">Rename</button>
          <button class="btn btn-sm btn-danger" data-action="delete" data-id="${layer.id}">Delete</button>
        ` : ""}
      </td>
    </tr>
  `).join("");

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
document.getElementById("open-upload-modal").addEventListener("click", () => openModal("upload-modal"));

document.getElementById("upload-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const errorBox = document.getElementById("upload-error");
  errorBox.classList.add("hidden");
  const submitBtn = document.getElementById("upload-submit");
  submitBtn.disabled = true;
  submitBtn.textContent = "Uploading…";

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
    closeModal("upload-modal");
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
  openModal("rename-modal");
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
    closeModal("rename-modal");
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

function bindColorPair(textId, pickerId, fallback) {
  const text = document.getElementById(textId);
  const picker = document.getElementById(pickerId);
  picker.addEventListener("input", () => {
    text.value = picker.value;
  });
  text.addEventListener("input", () => {
    const hex = normalizeHexColor(text.value, "");
    if (hex) picker.value = hex;
  });
  text.addEventListener("blur", () => {
    setColorPair(textId, pickerId, text.value, fallback);
  });
}

function openStyleModal(layer) {
  document.getElementById("style-id").value = layer.id;
  const style = layer.style || {};
  setColorPair("style-fill-color", "style-fill-color-picker", style.color, "#0F2D53");
  setColorPair("style-stroke-color", "style-stroke-color-picker", style.strokeColor, "#0a2140");
  document.getElementById("style-stroke-width").value = style.strokeWidth ?? 1;
  document.getElementById("style-opacity").value = style.opacity ?? 0.6;

  const labelSelect = document.getElementById("label-field");
  const fields = (layer.attribute_schema || []).map((f) => f.name);
  labelSelect.innerHTML = `<option value="">(no labels)</option>` +
    fields.map((f) => `<option value="${f}">${f}</option>`).join("");

  const labelConfig = layer.label_config || {};
  labelSelect.value = labelConfig.field || "";
  setColorPair("label-color", "label-color-picker", labelConfig.color, "#0F2D53");
  document.getElementById("label-size").value = labelConfig.size || 12;

  const canEdit = layer.my_permission === "owner" || layer.my_permission === "edit";
  document.getElementById("style-form").querySelectorAll("input,select,button[type=submit]").forEach((el) => {
    el.disabled = !canEdit;
  });

  openModal("style-modal");
}

document.getElementById("style-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const id = document.getElementById("style-id").value;
  const payload = {
    style: {
      color: normalizeHexColor(document.getElementById("style-fill-color").value, "#0F2D53"),
      strokeColor: normalizeHexColor(document.getElementById("style-stroke-color").value, "#0a2140"),
      strokeWidth: parseFloat(document.getElementById("style-stroke-width").value || "1"),
      opacity: parseFloat(document.getElementById("style-opacity").value || "0.6"),
    },
    label_config: {
      field: document.getElementById("label-field").value,
      color: normalizeHexColor(document.getElementById("label-color").value, "#0F2D53"),
      size: parseInt(document.getElementById("label-size").value || "12", 10),
    },
  };
  const res = await Auth.apiFetch(`/api/layers/${id}/`, { method: "PATCH", body: payload });
  if (res.ok) {
    closeModal("style-modal");
    await loadLayers();
  }
});

// ---- Share (people + XYZ) ----
let SHARE_COPY_RESET = null;
let CURRENT_SHARE_LAYER = null;

function setShareTab(tab) {
  const peopleTab = document.getElementById("share-tab-people");
  const xyzTab = document.getElementById("share-tab-xyz");
  const peoplePanel = document.getElementById("share-panel-people");
  const xyzPanel = document.getElementById("share-panel-xyz");
  const isXyz = tab === "xyz";

  peopleTab.classList.toggle("is-active", !isXyz);
  xyzTab.classList.toggle("is-active", isXyz);
  peopleTab.setAttribute("aria-selected", String(!isXyz));
  xyzTab.setAttribute("aria-selected", String(isXyz));

  peoplePanel.classList.toggle("is-active", !isXyz);
  xyzPanel.classList.toggle("is-active", isXyz);
  if (isXyz) {
    peoplePanel.hidden = true;
    xyzPanel.hidden = false;
    xyzPanel.classList.add("is-entering");
    window.setTimeout(() => xyzPanel.classList.remove("is-entering"), 280);
  } else {
    xyzPanel.hidden = true;
    peoplePanel.hidden = false;
    peoplePanel.classList.add("is-entering");
    window.setTimeout(() => peoplePanel.classList.remove("is-entering"), 280);
  }
}

function fillXyzShareFields(layer) {
  const xyzUrl = layer.xyz_url || `${layer.tile_url}/{z}/{x}/{y}`;
  const sourceLayer = layer.source_layer || "";
  const geometry = layer.suggested_geometry || "line";

  const urlEl = document.getElementById("xyz-url");
  const sourceEl = document.getElementById("xyz-source-layer");
  const geomEl = document.getElementById("xyz-geometry");

  urlEl.textContent = "";
  sourceEl.textContent = "";
  geomEl.textContent = "";

  // Reveal text with a short staggered “live” reveal.
  window.requestAnimationFrame(() => {
    urlEl.textContent = xyzUrl;
    urlEl.classList.add("is-revealed");
    sourceEl.textContent = sourceLayer;
    sourceEl.classList.add("is-revealed");
    geomEl.textContent = geometry;
    geomEl.classList.add("is-revealed");
  });

  urlEl.dataset.copyText = xyzUrl;
  sourceEl.dataset.copyText = sourceLayer;
}

function openShareModal(layer) {
  CURRENT_SHARE_LAYER = layer;
  document.getElementById("share-layer-id").value = layer.id;
  document.getElementById("share-search").value = "";
  document.getElementById("share-results").innerHTML = "";
  document.getElementById("share-submit").disabled = true;
  SELECTED_SHARE_USER = null;

  const isOwner = layer.my_permission === "owner";
  document.getElementById("share-people-owner").classList.toggle("hidden", !isOwner);
  document.getElementById("share-people-viewer").classList.toggle("hidden", isOwner);

  document.querySelectorAll(".xyz-copy-btn.is-copied").forEach((btn) => {
    btn.classList.remove("is-copied");
  });
  document.getElementById("xyz-copy-status").textContent = "";
  document.getElementById("xyz-copy-status").classList.remove("is-visible");
  document.getElementById("xyz-url").classList.remove("is-revealed");
  document.getElementById("xyz-source-layer").classList.remove("is-revealed");
  document.getElementById("xyz-geometry").classList.remove("is-revealed");

  fillXyzShareFields(layer);
  if (isOwner) renderShareList(layer);
  setShareTab("people");
  openModal("share-modal");
}

function renderShareList(layer) {
  const list = document.getElementById("share-list");
  const shares = layer.shares || [];
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

async function copyShareValue(kind, button) {
  const layer = CURRENT_SHARE_LAYER;
  if (!layer) return;

  const text =
    kind === "source"
      ? (layer.source_layer || document.getElementById("xyz-source-layer").dataset.copyText || "")
      : (layer.xyz_url || document.getElementById("xyz-url").dataset.copyText || "");

  const status = document.getElementById("xyz-copy-status");
  clearTimeout(SHARE_COPY_RESET);

  try {
    await navigator.clipboard.writeText(text);
    document.querySelectorAll(".xyz-copy-btn.is-copied").forEach((btn) => {
      btn.classList.remove("is-copied");
    });
    button.classList.add("is-copied");
    status.textContent = kind === "source" ? "Source layer copied." : "XYZ link copied.";
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

document.querySelectorAll("#share-panel-xyz [data-copy-value]").forEach((btn) => {
  btn.addEventListener("click", () => copyShareValue(btn.dataset.copyValue, btn));
});

document.addEventListener("DOMContentLoaded", () => {
  bindColorPair("style-fill-color", "style-fill-color-picker", "#0F2D53");
  bindColorPair("style-stroke-color", "style-stroke-color-picker", "#0a2140");
  bindColorPair("label-color", "label-color-picker", "#0F2D53");
  loadLayers();
});
