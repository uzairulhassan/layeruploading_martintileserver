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

document.addEventListener("DOMContentLoaded", loadMaps);
