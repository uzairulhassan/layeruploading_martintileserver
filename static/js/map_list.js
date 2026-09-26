let CURRENT_MAPS = [];
let SELECTED_SHARE_USER = null;

function openModal(id) { document.getElementById(id).classList.remove("hidden"); }
function closeModal(id) { document.getElementById(id).classList.add("hidden"); }
document.querySelectorAll("[data-close-modal]").forEach((btn) => {
  btn.addEventListener("click", () => closeModal(btn.dataset.closeModal));
});

function findMap(id) { return CURRENT_MAPS.find((m) => String(m.id) === String(id)); }

async function loadMaps() {
  const res = await Auth.apiFetch("/api/maps/");
  const data = await res.json();
  CURRENT_MAPS = data.results || data;
  renderMaps();
}

function renderMaps() {
  const tbody = document.getElementById("maps-tbody");
  if (!CURRENT_MAPS.length) {
    tbody.innerHTML = `<tr><td colspan="5"><div class="empty-state"><strong>No maps yet</strong>Create one to overlay your layers.</div></td></tr>`;
    return;
  }
  tbody.innerHTML = CURRENT_MAPS.map((map) => `
    <tr>
      <td><a href="/maps/${map.id}/">${map.name}</a></td>
      <td>${map.map_layers.length}</td>
      <td>${map.owner_detail.display_name}</td>
      <td><span class="badge">${map.my_permission}</span></td>
      <td class="table-actions">
        <a class="btn btn-sm" href="/maps/${map.id}/">Open</a>
        ${map.my_permission === "owner" ? `
          <button class="btn btn-sm" data-action="share" data-id="${map.id}">Share</button>
          <button class="btn btn-sm btn-danger" data-action="delete" data-id="${map.id}">Delete</button>
        ` : ""}
      </td>
    </tr>
  `).join("");

  tbody.querySelectorAll("button[data-action]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const map = findMap(btn.dataset.id);
      if (btn.dataset.action === "share") openShareModal(map);
      if (btn.dataset.action === "delete") deleteMap(map);
    });
  });
}

async function deleteMap(map) {
  if (!confirm(`Delete map "${map.name}"? This cannot be undone.`)) return;
  const res = await Auth.apiFetch(`/api/maps/${map.id}/`, { method: "DELETE" });
  if (res.ok || res.status === 204) await loadMaps();
}

function openShareModal(map) {
  document.getElementById("share-map-id").value = map.id;
  document.getElementById("share-search").value = "";
  document.getElementById("share-results").innerHTML = "";
  document.getElementById("share-submit").disabled = true;
  SELECTED_SHARE_USER = null;
  renderShareList(map);
  openModal("share-modal");
}

function renderShareList(map) {
  const list = document.getElementById("share-list");
  const shares = map.shares || [];
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
      const mapId = document.getElementById("share-map-id").value;
      await Auth.apiFetch(`/api/maps/${mapId}/unshare/`, {
        method: "POST",
        body: { user_id: btn.dataset.removeShare },
      });
      await loadMaps();
      renderShareList(findMap(mapId));
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
  const mapId = document.getElementById("share-map-id").value;
  const permission = document.getElementById("share-permission").value;
  await Auth.apiFetch(`/api/maps/${mapId}/share/`, {
    method: "POST",
    body: { shared_with: SELECTED_SHARE_USER.id, permission },
  });
  await loadMaps();
  renderShareList(findMap(mapId));
  document.getElementById("share-submit").disabled = true;
  SELECTED_SHARE_USER = null;
  document.getElementById("share-search").value = "";
});

function openCreateMapModal() {
  const error = document.getElementById("create-map-error");
  error.classList.add("hidden");
  error.textContent = "";
  document.getElementById("create-map-form").reset();
  openModal("create-map-modal");
  setTimeout(() => document.getElementById("new-map-name").focus(), 50);
}

document.getElementById("open-create-map-modal").addEventListener("click", openCreateMapModal);

document.getElementById("create-map-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const name = document.getElementById("new-map-name").value.trim();
  const error = document.getElementById("create-map-error");
  const submitBtn = document.getElementById("create-map-submit");
  error.classList.add("hidden");
  error.textContent = "";
  if (!name) {
    error.textContent = "Enter a map name.";
    error.classList.remove("hidden");
    return;
  }
  submitBtn.disabled = true;
  try {
    const res = await Auth.apiFetch("/api/maps/", {
      method: "POST",
      body: {
        name,
        basemap_style: "mapbox://styles/mapbox/streets-v12",
        center_lng: 0,
        center_lat: 0,
        zoom: 2,
      },
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      error.textContent = data.detail || data.name?.[0] || "Could not create map.";
      error.classList.remove("hidden");
      return;
    }
    const data = await res.json();
    window.location.href = `/maps/${data.id}/`;
  } catch (err) {
    console.error(err);
    error.textContent = "Could not create map.";
    error.classList.remove("hidden");
  } finally {
    submitBtn.disabled = false;
  }
});

document.addEventListener("DOMContentLoaded", () => {
  loadMaps();
  const params = new URLSearchParams(window.location.search);
  if (params.get("new") === "1") {
    openCreateMapModal();
    window.history.replaceState({}, "", "/maps/");
  }
});
