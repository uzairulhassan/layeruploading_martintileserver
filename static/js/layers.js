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
  document.getElementById("xyz-owner-only").classList.toggle("hidden", !isOwner);
  document.getElementById("xyz-viewer-note").classList.toggle("hidden", isOwner);

  document.getElementById("xyz-copy-status").textContent = "";
  document.getElementById("xyz-copy-status").classList.remove("is-visible");
  document.getElementById("xyz-create-error").classList.add("hidden");

  const expiryInput = document.getElementById("xyz-expiry");
  const tomorrow = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
  expiryInput.min = tomorrow;
  expiryInput.value = "";

  if (isOwner) renderShareList(layer);
  if (isOwner) loadShareLinks(layer.id);
  setShareTab("people");
  openModal("share-modal");
}

// ---- XYZ share links (expiring, revocable) ----
async function loadShareLinks(layerId) {
  const list = document.getElementById("xyz-links-list");
  list.innerHTML = `<li class="muted">Loading…</li>`;
  const res = await Auth.apiFetch(`/api/layers/${layerId}/share-links/`);
  if (!res.ok) {
    list.innerHTML = `<li class="muted">Could not load share links.</li>`;
    return;
  }
  const links = await res.json();
  renderShareLinks(layerId, links);
}

function formatExpiry(isoString) {
  const date = new Date(isoString);
  return date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function formatUsage(link) {
  if (!link.total_requests) return "never used";
  const last = link.last_used_at ? `, last used ${formatExpiry(link.last_used_at)}` : "";
  return `${link.total_requests.toLocaleString()} tile requests (${link.requests_last_30_days.toLocaleString()} in 30 days)${last}`;
}

function renderShareLinks(layerId, links) {
  const list = document.getElementById("xyz-links-list");
  if (!links.length) {
    list.innerHTML = `<li class="muted">No active share links yet.</li>`;
    return;
  }
  list.innerHTML = links.map((link) => `
    <li data-link-id="${link.id}">
      <div style="flex:1; min-width:0;">
        <code class="xyz-chip" style="display:block; margin-bottom:0.3rem;">${link.xyz_url}</code>
        <span class="muted" style="font-size:0.78rem;">
          ${link.is_expired ? "Expired" : "Expires"} ${formatExpiry(link.expires_at)}
          ${link.is_blocked ? " &middot; blocked by admin" : ""}
          &middot; ${formatUsage(link)}
        </span>
      </div>
      <div style="display:flex; gap:0.4rem; flex:0 0 auto;">
        <button type="button" class="btn btn-sm" data-copy-link="${link.xyz_url}">Copy</button>
        <button type="button" class="btn btn-sm btn-danger" data-revoke-link="${link.id}">Revoke</button>
      </div>
    </li>
  `).join("");

  list.querySelectorAll("[data-copy-link]").forEach((btn) => {
    btn.addEventListener("click", () => copyToClipboardWithFeedback(btn.dataset.copyLink, btn, "Link copied."));
  });
  list.querySelectorAll("[data-revoke-link]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm("Revoke this share link? Anyone using it will immediately lose access.")) return;
      await Auth.apiFetch(`/api/layers/${layerId}/share-links/${btn.dataset.revokeLink}/`, { method: "DELETE" });
      await loadShareLinks(layerId);
    });
  });
}

document.getElementById("xyz-create-btn").addEventListener("click", async () => {
  const layer = CURRENT_SHARE_LAYER;
  if (!layer) return;
  const errorBox = document.getElementById("xyz-create-error");
  errorBox.classList.add("hidden");

  const expiryValue = document.getElementById("xyz-expiry").value;
  if (!expiryValue) {
    errorBox.textContent = "Pick an expiry date.";
    errorBox.classList.remove("hidden");
    return;
  }
  // End-of-day in the browser's local time, sent as an absolute instant.
  const expiresAt = new Date(`${expiryValue}T23:59:59`);

  const btn = document.getElementById("xyz-create-btn");
  btn.disabled = true;
  try {
    const res = await Auth.apiFetch(`/api/layers/${layer.id}/share-links/`, {
      method: "POST",
      body: { expires_at: expiresAt.toISOString() },
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.expires_at?.[0] || body.detail || "Could not create the link.");
    }
    document.getElementById("xyz-expiry").value = "";
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

async function copyToClipboardWithFeedback(text, button, successText) {
  const status = document.getElementById("xyz-copy-status");
  clearTimeout(SHARE_COPY_RESET);

  try {
    await copyTextToClipboard(text);
    document.querySelectorAll("#xyz-links-list .is-copied").forEach((btn) => btn.classList.remove("is-copied"));
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
