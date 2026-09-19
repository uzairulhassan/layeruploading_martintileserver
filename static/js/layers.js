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
        <button class="btn btn-sm" data-action="xyz" data-id="${layer.id}">XYZ link</button>
        <button class="btn btn-sm" data-action="style" data-id="${layer.id}">Style</button>
        ${layer.my_permission === "owner" ? `
          <button class="btn btn-sm" data-action="rename" data-id="${layer.id}">Rename</button>
          <button class="btn btn-sm" data-action="share" data-id="${layer.id}">Share</button>
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
  if (action === "xyz") openXyzModal(layer);
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

// ---- Share ----
function openShareModal(layer) {
  document.getElementById("share-layer-id").value = layer.id;
  document.getElementById("share-search").value = "";
  document.getElementById("share-results").innerHTML = "";
  document.getElementById("share-submit").disabled = true;
  SELECTED_SHARE_USER = null;
  renderShareList(layer);
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

// ---- XYZ shareable link ----
function buildGeotrakPackage(layer) {
  return {
    geotrakLayer: true,
    name: layer.name || "",
    type: "vector",
    url: layer.xyz_url || `${layer.tile_url}/{z}/{x}/{y}`,
    sourceLayer: layer.source_layer || "",
    geometry: layer.suggested_geometry || "line",
  };
}

function openXyzModal(layer) {
  const pkg = buildGeotrakPackage(layer);
  document.getElementById("xyz-layer-id").value = layer.id;
  document.getElementById("xyz-url").value = pkg.url;
  document.getElementById("xyz-source-layer").value = pkg.sourceLayer;
  document.getElementById("xyz-geometry").value = pkg.geometry;
  document.getElementById("xyz-package").value = JSON.stringify(pkg, null, 2);
  const status = document.getElementById("xyz-copy-status");
  status.classList.add("hidden");
  status.textContent = "";
  openModal("xyz-modal");
}

async function copyFieldValue(targetId) {
  const el = document.getElementById(targetId);
  const text = el.value;
  const status = document.getElementById("xyz-copy-status");
  try {
    await navigator.clipboard.writeText(text);
    status.textContent = "Copied to clipboard.";
    status.classList.remove("hidden");
  } catch {
    el.focus();
    el.select?.();
    status.textContent = "Could not copy automatically — select the text and copy manually.";
    status.classList.remove("hidden");
  }
}

document.querySelectorAll("#xyz-modal [data-copy-target]").forEach((btn) => {
  btn.addEventListener("click", () => copyFieldValue(btn.dataset.copyTarget));
});

document.getElementById("copy-xyz-all").addEventListener("click", () => {
  copyFieldValue("xyz-package");
});

document.addEventListener("DOMContentLoaded", () => {
  bindColorPair("style-fill-color", "style-fill-color-picker", "#0F2D53");
  bindColorPair("style-stroke-color", "style-stroke-color-picker", "#0a2140");
  bindColorPair("label-color", "label-color-picker", "#0F2D53");
  loadLayers();
});
