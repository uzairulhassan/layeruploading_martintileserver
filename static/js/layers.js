let CURRENT_LAYERS = [];
let SELECTED_SHARE_USER = null;
let LAYER_FILTER = "all";

async function loadLayers() {
  try {
    const res = await Auth.apiFetch("/api/layers/");
    if (!res.ok) {
      throw new Error(await Toast.fromResponse(res, "Could not load layers."));
    }
    const data = await res.json();
    CURRENT_LAYERS = data.results || data;
    renderLayers();
  } catch (err) {
    Toast.error(err.message || "Could not load layers.");
    CURRENT_LAYERS = [];
    renderLayers();
  }
}

function filteredLayers() {
  if (LAYER_FILTER === "owned") {
    return CURRENT_LAYERS.filter((layer) => layer.my_permission === "owner");
  }
  if (LAYER_FILTER === "shared") {
    return CURRENT_LAYERS.filter((layer) => layer.my_permission !== "owner");
  }
  return CURRENT_LAYERS;
}

function ownerLabel(layer) {
  if (layer.my_permission === "owner") return "You";
  return layer.owner_detail ? layer.owner_detail.display_name : "";
}

function descriptionLabel(layer) {
  const text = (layer.description || "").trim();
  return text || "—";
}

function emptyStateMessage() {
  if (LAYER_FILTER === "owned") {
    return { title: "No uploaded layers", body: "Upload a shapefile to add one." };
  }
  if (LAYER_FILTER === "shared") {
    return { title: "No shared layers", body: "Layers shared with you will appear here." };
  }
  return { title: "No layers yet", body: "Upload a shapefile to get started." };
}

function actionIcon(name) {
  const icons = {
    style: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20h4l10.5-10.5a2.1 2.1 0 0 0-3-3L5 17v3z"/><path d="M13.5 6.5l3 3"/></svg>',
    share: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="18" cy="5" r="2.5"/><circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="19" r="2.5"/><path d="M8.4 13.2l7.2 4.1M15.6 6.7l-7.2 4.1"/></svg>',
    rename: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20h16"/><path d="M8 16l9.2-9.2a1.8 1.8 0 0 0-2.5-2.5L5.5 13.5 4 20l6.5-1.5z"/></svg>',
    delete: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 7h14"/><path d="M9 7V5h6v2"/><path d="M8 7l1 12h6l1-12"/></svg>',
  };
  return icons[name] || "";
}

function actionButton(action, id, label, danger = false) {
  return `
    <button
      type="button"
      class="row-action${danger ? " is-danger" : ""}"
      data-action="${action}"
      data-id="${id}"
      title="${label}"
      aria-label="${label}"
    >
      ${actionIcon(action)}
      <span>${label}</span>
    </button>
  `;
}

function renderLayers() {
  const tbody = document.getElementById("layers-tbody");
  const layers = filteredLayers();
  if (!layers.length) {
    const empty = emptyStateMessage();
    tbody.innerHTML = `<tr><td colspan="7"><div class="empty-state"><strong>${empty.title}</strong>${empty.body}</div></td></tr>`;
    return;
  }
  tbody.innerHTML = layers.map((layer) => `
    <tr>
      <td>${layer.name}</td>
      <td class="table-desc">${descriptionLabel(layer)}</td>
      <td>${layer.geometry_type}</td>
      <td>${layer.feature_count}</td>
      <td>${ownerLabel(layer)}</td>
      <td><span class="badge">${layer.my_permission}</span></td>
      <td class="table-actions">
        <div class="row-actions">
          ${actionButton("style", layer.id, "Style")}
          ${actionButton("share", layer.id, "Share")}
          ${layer.my_permission === "owner" ? `
            ${actionButton("rename", layer.id, "Rename")}
            <span class="row-actions-sep" aria-hidden="true"></span>
            ${actionButton("delete", layer.id, "Delete", true)}
          ` : ""}
        </div>
      </td>
    </tr>
  `).join("");

  tbody.querySelectorAll("button[data-action]").forEach((btn) => {
    btn.addEventListener("click", () => handleRowAction(btn.dataset.action, btn.dataset.id));
  });
}

document.querySelectorAll("[data-layer-filter]").forEach((btn) => {
  btn.addEventListener("click", () => {
    LAYER_FILTER = btn.dataset.layerFilter;
    document.querySelectorAll("[data-layer-filter]").forEach((item) => {
      const active = item === btn;
      item.classList.toggle("is-active", active);
      item.setAttribute("aria-selected", active ? "true" : "false");
    });
    renderLayers();
  });
});

function findLayer(id) {
  return CURRENT_LAYERS.find((l) => String(l.id) === String(id));
}

function handleRowAction(action, id) {
  const layer = findLayer(id);
  if (action === "style") openStyleModal(layer);
  if (action === "rename") openRenameModal(layer);
  if (action === "share") openShareModal(layer);
  if (action === "delete") openDeleteModal(layer);
}

// ---- Upload ----
document.getElementById("open-upload-modal").addEventListener("click", () => Auth.openModal("upload-modal"));

document.getElementById("upload-form").addEventListener("submit", async (event) => {
  event.preventDefault();
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
      throw new Error(await Toast.fromResponse(res, "Could not upload layer."));
    }
    document.getElementById("upload-form").reset();
    Auth.closeModal("upload-modal");
    await loadLayers();
    Toast.success("Layer uploaded.");
  } catch (err) {
    Toast.error(err.message || "Could not upload layer.");
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
  try {
    const res = await Auth.apiFetch(`/api/layers/${id}/`, { method: "PATCH", body: payload });
    if (!res.ok) {
      throw new Error(await Toast.fromResponse(res, "Could not rename layer."));
    }
    Auth.closeModal("rename-modal");
    await loadLayers();
    Toast.success("Layer updated.");
  } catch (err) {
    Toast.error(err.message || "Could not rename layer.");
  }
});

// ---- Delete ----
function openDeleteModal(layer) {
  document.getElementById("delete-id").value = layer.id;
  document.getElementById("delete-layer-name").textContent = layer.name;
  Auth.openModal("delete-modal");
}

document.getElementById("delete-confirm").addEventListener("click", async () => {
  const id = document.getElementById("delete-id").value;
  const btn = document.getElementById("delete-confirm");
  btn.disabled = true;
  try {
    const res = await Auth.apiFetch(`/api/layers/${id}/`, { method: "DELETE" });
    if (!res.ok && res.status !== 204) {
      throw new Error(await Toast.fromResponse(res, "Could not delete layer."));
    }
    Auth.closeModal("delete-modal");
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
  labelSelect.innerHTML = `<option value="">No labels</option>` +
    fields.map((f) => `<option value="${f}">${f}</option>`).join("");

  const labelConfig = layer.label_config || {};
  labelSelect.value = labelConfig.field || "";
  setColorPair("label-color", "label-color-picker", labelConfig.color, "#0F2D53");
  document.getElementById("label-size").value = labelConfig.size || 12;

  const canEdit = layer.my_permission === "owner" || layer.my_permission === "edit";
  document.getElementById("style-form").querySelectorAll("input,select,button[type=submit]").forEach((el) => {
    el.disabled = !canEdit;
  });

  Auth.openModal("style-modal");
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
  if (!res.ok) {
    Toast.error(await Toast.fromResponse(res, "Could not save style."));
    return;
  }
  Auth.closeModal("style-modal");
  await loadLayers();
  Toast.success("Layer style saved.");
});

// ---- Share ----
let SHARE_COPY_RESET = null;
let CURRENT_SHARE_LAYER = null;

function setShareTab(tab) {
  const isXyz = tab === "xyz";
  const peopleTab = document.getElementById("share-tab-people");
  const xyzTab = document.getElementById("share-tab-xyz");
  const peoplePanel = document.getElementById("share-panel-people");
  const xyzPanel = document.getElementById("share-panel-xyz");
  const activePanel = isXyz ? xyzPanel : peoplePanel;

  peopleTab.classList.toggle("is-active", !isXyz);
  xyzTab.classList.toggle("is-active", isXyz);
  peopleTab.setAttribute("aria-selected", String(!isXyz));
  xyzTab.setAttribute("aria-selected", String(isXyz));
  peoplePanel.classList.toggle("is-active", !isXyz);
  xyzPanel.classList.toggle("is-active", isXyz);

  activePanel.classList.add("is-entering");
  window.setTimeout(() => activePanel.classList.remove("is-entering"), 280);
}

function fillXyzShareFields(layer) {
  const xyzUrl = layer.xyz_url || `${layer.tile_url}/{z}/{x}/{y}`;
  document.getElementById("xyz-url").textContent = xyzUrl;
  document.getElementById("xyz-source-layer").textContent = layer.source_layer || "";
  document.getElementById("xyz-geometry").textContent = layer.suggested_geometry || "line";
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

  fillXyzShareFields(layer);
  if (isOwner) renderShareList(layer);
  setShareTab("people");
  Auth.openModal("share-modal");
}

function renderShareList(layer) {
  const list = document.getElementById("share-list");
  const shares = layer.shares || [];
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
      const layerId = document.getElementById("share-layer-id").value;
      try {
        const res = await Auth.apiFetch(`/api/layers/${layerId}/unshare/`, {
          method: "POST",
          body: { user_id: btn.dataset.removeShare },
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
  const layerId = document.getElementById("share-layer-id").value;
  const permission = document.getElementById("share-permission").value;
  try {
    const res = await Auth.apiFetch(`/api/layers/${layerId}/share/`, {
      method: "POST",
      body: { shared_with: SELECTED_SHARE_USER.id, permission },
    });
    if (!res.ok) {
      throw new Error(await Toast.fromResponse(res, "Could not share layer."));
    }
    await loadLayers();
    renderShareList(findLayer(layerId));
    document.getElementById("share-submit").disabled = true;
    SELECTED_SHARE_USER = null;
    document.getElementById("share-search").value = "";
    Toast.success("Layer shared.");
  } catch (err) {
    Toast.error(err.message || "Could not share layer.");
  }
});

document.querySelectorAll("[data-share-tab]").forEach((btn) => {
  btn.addEventListener("click", () => setShareTab(btn.dataset.shareTab));
});

async function copyShareValue(kind, button) {
  const layer = CURRENT_SHARE_LAYER;
  if (!layer) return;

  const text =
    kind === "source"
      ? (layer.source_layer || "")
      : (layer.xyz_url || `${layer.tile_url}/{z}/{x}/{y}`);

  clearTimeout(SHARE_COPY_RESET);

  try {
    await copyTextToClipboard(text);
    document.querySelectorAll(".xyz-copy-btn.is-copied").forEach((btn) => {
      btn.classList.remove("is-copied");
    });
    button.classList.add("is-copied");
    Toast.success(kind === "source" ? "Source layer copied." : "Tile URL copied.");
    SHARE_COPY_RESET = window.setTimeout(() => {
      button.classList.remove("is-copied");
    }, 1800);
  } catch {
    Toast.error("Copy failed — select the text and copy manually.");
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

document.querySelectorAll("#share-panel-xyz [data-copy-value]").forEach((btn) => {
  btn.addEventListener("click", () => copyShareValue(btn.dataset.copyValue, btn));
});

document.addEventListener("DOMContentLoaded", () => {
  bindColorPair("style-fill-color", "style-fill-color-picker", "#0F2D53");
  bindColorPair("style-stroke-color", "style-stroke-color-picker", "#0a2140");
  bindColorPair("label-color", "label-color-picker", "#0F2D53");
  loadLayers();
});
