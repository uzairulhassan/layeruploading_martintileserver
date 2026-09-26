let CURRENT_MAPS = [];
let SELECTED_SHARE_USER = null;
let MAP_FILTER = "all";

function findMap(id) {
  return CURRENT_MAPS.find((m) => String(m.id) === String(id));
}

async function loadMaps() {
  const res = await Auth.apiFetch("/api/maps/");
  const data = await res.json();
  CURRENT_MAPS = data.results || data;
  renderMaps();
}

function filteredMaps() {
  if (MAP_FILTER === "owned") {
    return CURRENT_MAPS.filter((map) => map.my_permission === "owner");
  }
  if (MAP_FILTER === "shared") {
    return CURRENT_MAPS.filter((map) => map.my_permission !== "owner");
  }
  return CURRENT_MAPS;
}

function ownerLabel(map) {
  if (map.my_permission === "owner") return "You";
  return map.owner_detail ? map.owner_detail.display_name : "";
}

function emptyStateMessage() {
  if (MAP_FILTER === "owned") {
    return { title: "No created maps", body: "Create a map to get started." };
  }
  if (MAP_FILTER === "shared") {
    return { title: "No shared maps", body: "Maps shared with you will appear here." };
  }
  return { title: "No maps yet", body: "Create one to overlay your layers." };
}

function actionIcon(name) {
  const icons = {
    open: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 5h5v5"/><path d="M10 14L19 5"/><path d="M19 13v5a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5"/></svg>',
    share: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="18" cy="5" r="2.5"/><circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="19" r="2.5"/><path d="M8.4 13.2l7.2 4.1M15.6 6.7l-7.2 4.1"/></svg>',
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

function actionLink(href, icon, label) {
  return `
    <a class="row-action" href="${href}" title="${label}" aria-label="${label}">
      ${actionIcon(icon)}
      <span>${label}</span>
    </a>
  `;
}

function renderMaps() {
  const tbody = document.getElementById("maps-tbody");
  const maps = filteredMaps();
  if (!maps.length) {
    const empty = emptyStateMessage();
    tbody.innerHTML = `<tr><td colspan="5"><div class="empty-state"><strong>${empty.title}</strong>${empty.body}</div></td></tr>`;
    return;
  }
  tbody.innerHTML = maps.map((map) => `
    <tr>
      <td><a href="/maps/${map.id}/">${map.name}</a></td>
      <td>${map.map_layers.length}</td>
      <td>${ownerLabel(map)}</td>
      <td><span class="badge">${map.my_permission}</span></td>
      <td class="table-actions">
        <div class="row-actions">
          ${actionLink(`/maps/${map.id}/`, "open", "Open")}
          ${map.my_permission === "owner" ? `
            ${actionButton("share", map.id, "Share")}
            <span class="row-actions-sep" aria-hidden="true"></span>
            ${actionButton("delete", map.id, "Delete", true)}
          ` : ""}
        </div>
      </td>
    </tr>
  `).join("");

  tbody.querySelectorAll("button[data-action]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const map = findMap(btn.dataset.id);
      if (btn.dataset.action === "share") openShareModal(map);
      if (btn.dataset.action === "delete") openDeleteModal(map);
    });
  });
}

document.querySelectorAll("[data-map-filter]").forEach((btn) => {
  btn.addEventListener("click", () => {
    MAP_FILTER = btn.dataset.mapFilter;
    document.querySelectorAll("[data-map-filter]").forEach((item) => {
      const active = item === btn;
      item.classList.toggle("is-active", active);
      item.setAttribute("aria-selected", active ? "true" : "false");
    });
    renderMaps();
  });
});

function openDeleteModal(map) {
  document.getElementById("delete-id").value = map.id;
  document.getElementById("delete-map-name").textContent = map.name;
  Auth.openModal("delete-modal");
}

document.getElementById("delete-confirm").addEventListener("click", async () => {
  const id = document.getElementById("delete-id").value;
  const btn = document.getElementById("delete-confirm");
  btn.disabled = true;
  try {
    const res = await Auth.apiFetch(`/api/maps/${id}/`, { method: "DELETE" });
    if (res.ok || res.status === 204) {
      Auth.closeModal("delete-modal");
      await loadMaps();
    }
  } finally {
    btn.disabled = false;
  }
});

function openShareModal(map) {
  document.getElementById("share-map-id").value = map.id;
  document.getElementById("share-search").value = "";
  document.getElementById("share-results").innerHTML = "";
  document.getElementById("share-submit").disabled = true;
  SELECTED_SHARE_USER = null;
  renderShareList(map);
  Auth.openModal("share-modal");
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
  Auth.openModal("create-map-modal");
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
