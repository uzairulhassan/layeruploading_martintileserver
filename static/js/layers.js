let CURRENT_LAYERS = [];
let SELECTED_SHARE_USER = null;

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
  if (res.ok) {
    Auth.closeModal("style-modal");
    await loadLayers();
  }
});

// ---- Share (people + External Share) ----
let SHARE_COPY_RESET = null;
let CURRENT_SHARE_LAYER = null;

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

function syncExternalExpiryControls() {
  const noExpiry = document.getElementById("external-no-expiry").checked;
  const expiryInput = document.getElementById("external-expiry");
  expiryInput.disabled = noExpiry;
  expiryInput.required = !noExpiry;
  if (noExpiry) {
    expiryInput.value = "";
  }
}

function openShareModal(layer) {
  CURRENT_SHARE_LAYER = layer;
  document.getElementById("share-layer-id").value = layer.id;
  document.getElementById("share-layer-sub").textContent =
    `Sharing “${layer.name}” with teammates or via an external tile link.`;
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
  document.getElementById("external-create-error").classList.add("hidden");

  const expiryInput = document.getElementById("external-expiry");
  const tomorrow = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
  expiryInput.min = tomorrow;
  expiryInput.value = "";
  document.getElementById("external-no-expiry").checked = false;
  syncExternalExpiryControls();

  if (isOwner) renderShareList(layer);
  if (isOwner) loadShareLinks(layer.id);
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

function formatExpiryLabel(link) {
  if (link.never_expires || !link.expires_at) {
    return `<span class="external-pill external-pill-live">No expiry</span>`;
  }
  if (link.is_expired) {
    return `<span class="external-pill external-pill-expired">Expired ${formatExpiry(link.expires_at)}</span>`;
  }
  return `<span class="external-pill">Expires ${formatExpiry(link.expires_at)}</span>`;
}

function renderShareLinks(layerId, links) {
  const list = document.getElementById("external-links-list");
  if (!links.length) {
    list.innerHTML = `<li class="share-empty">No active external share links yet.</li>`;
    return;
  }
  list.innerHTML = links.map((link) => {
    const geometryLabel = simplifyGeometryLabel(link.geometry_type, link.suggested_geometry);
    const requests = Number(link.total_requests || 0).toLocaleString();
    const lastUsed = link.last_used_at ? formatExpiry(link.last_used_at) : "Never";
    return `
    <li class="external-link-card" data-link-id="${link.id}">
      <div class="external-link-top">
        <div class="external-link-badges">
          ${formatExpiryLabel(link)}
          ${link.is_blocked ? `<span class="external-pill external-pill-blocked">Blocked</span>` : ""}
        </div>
        <div class="external-link-actions">
          <button type="button" class="btn btn-sm" data-copy-link="${Auth.escapeHtml(link.xyz_url)}">Copy URL</button>
          <button type="button" class="btn btn-sm btn-danger" data-revoke-link="${link.id}">Revoke</button>
        </div>
      </div>

      <div class="external-field">
        <span class="external-field-label">Tile URL</span>
        <code class="external-chip">${Auth.escapeHtml(link.xyz_url)}</code>
      </div>

      <div class="external-meta-grid">
        <div class="external-field">
          <span class="external-field-label">Source layer</span>
          <div class="external-chip-row">
            <code class="external-chip">${Auth.escapeHtml(link.source_layer)}</code>
            <button type="button" class="btn btn-sm" data-copy-source="${Auth.escapeHtml(link.source_layer)}">Copy</button>
          </div>
        </div>
        <div class="external-field">
          <span class="external-field-label">Geometry</span>
          <span class="external-geom-value">${Auth.escapeHtml(geometryLabel)}</span>
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

document.getElementById("external-no-expiry").addEventListener("change", syncExternalExpiryControls);

document.getElementById("external-create-btn").addEventListener("click", async () => {
  const layer = CURRENT_SHARE_LAYER;
  if (!layer) return;
  const errorBox = document.getElementById("external-create-error");
  errorBox.classList.add("hidden");

  const noExpiry = document.getElementById("external-no-expiry").checked;
  const expiryValue = document.getElementById("external-expiry").value;
  let body = { expires_at: null };

  if (!noExpiry) {
    if (!expiryValue) {
      errorBox.textContent = "Pick an expiry date, or enable No expiry.";
      errorBox.classList.remove("hidden");
      return;
    }
    // End-of-day in the browser's local time, sent as an absolute instant.
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
      throw new Error(errBody.expires_at?.[0] || errBody.detail || "Could not create the link.");
    }
    document.getElementById("external-expiry").value = "";
    document.getElementById("external-no-expiry").checked = false;
    syncExternalExpiryControls();
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
    list.innerHTML = `<li class="share-empty">Not shared with anyone yet.</li>`;
    return;
  }
  list.innerHTML = shares.map((s) => `
    <li class="share-person-row">
      <span>${s.shared_with_detail.display_name} — ${s.permission}</span>
      <button class="btn btn-link" data-remove-share="${s.shared_with_detail.id}">Remove</button>
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
  bindColorPair("style-fill-color", "style-fill-color-picker", "#0F2D53");
  bindColorPair("style-stroke-color", "style-stroke-color-picker", "#0a2140");
  bindColorPair("label-color", "label-color-picker", "#0F2D53");
  loadLayers();
});
