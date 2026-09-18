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
function openStyleModal(layer) {
  document.getElementById("style-id").value = layer.id;
  const style = layer.style || {};
  document.getElementById("style-fill-color").value = style.color || "#0F2D53";
  document.getElementById("style-stroke-color").value = style.strokeColor || "#0a2140";
  document.getElementById("style-stroke-width").value = style.strokeWidth ?? 1;
  document.getElementById("style-opacity").value = style.opacity ?? 0.6;

  const labelSelect = document.getElementById("label-field");
  const fields = (layer.attribute_schema || []).map((f) => f.name);
  labelSelect.innerHTML = `<option value="">(no labels)</option>` +
    fields.map((f) => `<option value="${f}">${f}</option>`).join("");

  const labelConfig = layer.label_config || {};
  labelSelect.value = labelConfig.field || "";
  document.getElementById("label-color").value = labelConfig.color || "#0F2D53";
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
      color: document.getElementById("style-fill-color").value,
      strokeColor: document.getElementById("style-stroke-color").value,
      strokeWidth: parseFloat(document.getElementById("style-stroke-width").value || "1"),
      opacity: parseFloat(document.getElementById("style-opacity").value || "0.6"),
    },
    label_config: {
      field: document.getElementById("label-field").value,
      color: document.getElementById("label-color").value,
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

document.addEventListener("DOMContentLoaded", loadLayers);
