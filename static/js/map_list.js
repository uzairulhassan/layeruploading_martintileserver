let CURRENT_MAPS = [];
let MAP_FILTER = "all";
let MAP_SEARCH = "";

const MAP_ICONS = {
  map: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M9 4.5 3.5 6.5v13L9 17.5l6 2 5.5-2v-13L15 6.5 9 4.5Z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M9 4.5v13M15 6.5v13" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>',
  open: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M14 5h5v5" stroke="currentColor" stroke-width="1.7"/><path d="M10 14 19 5" stroke="currentColor" stroke-width="1.7"/><path d="M19 13v5a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5" stroke="currentColor" stroke-width="1.7"/></svg>',
  share: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="18" cy="5" r="2.4" stroke="currentColor" stroke-width="1.7"/><circle cx="6" cy="12" r="2.4" stroke="currentColor" stroke-width="1.7"/><circle cx="18" cy="19" r="2.4" stroke="currentColor" stroke-width="1.7"/><path d="M8.4 13.2l7.2 4.1M15.6 6.7l-7.2 4.1" stroke="currentColor" stroke-width="1.7"/></svg>',
  delete: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 7h14" stroke="currentColor" stroke-width="1.7"/><path d="M9 7V5h6v2" stroke="currentColor" stroke-width="1.7"/><path d="M8 7l1 12h6l1-12" stroke="currentColor" stroke-width="1.7"/></svg>',
  access: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="9" cy="9" r="2.6" stroke="currentColor" stroke-width="1.6"/><circle cx="16" cy="10.5" r="2.2" stroke="currentColor" stroke-width="1.6"/><path d="M4.8 18c1.1-2.3 2.9-3.5 5-3.5 1.2 0 2.2.3 3.1.9M13.8 15.8c1.5-.5 3-.3 4.4 1.2" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
};

function findMap(id) {
  return CURRENT_MAPS.find((m) => String(m.id) === String(id));
}

function permissionLabel(permission) {
  return String(permission || "").replace(/_/g, " ");
}

async function loadMaps() {
  try {
    const res = await Auth.apiFetch("/api/maps/?page_size=500");
    if (!res.ok) {
      throw new Error(await Toast.fromResponse(res, "Could not load maps."));
    }
    const data = await res.json();
    CURRENT_MAPS = data.results || data;
    renderMaps();
  } catch (err) {
    Toast.error(err.message || "Could not load maps.");
    CURRENT_MAPS = [];
    renderMaps();
  }
}

function filteredMaps() {
  let maps = CURRENT_MAPS;
  if (MAP_FILTER === "owned") {
    maps = maps.filter((map) => map.my_permission === "owner");
  } else if (MAP_FILTER === "shared") {
    maps = maps.filter((map) => map.my_permission !== "owner");
  }
  const q = MAP_SEARCH.trim().toLowerCase();
  if (q) {
    maps = maps.filter((map) => String(map.name || "").toLowerCase().includes(q));
  }
  return maps;
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

function actionButton(action, id, label, danger = false) {
  return `
    <button
      type="button"
      class="action-btn${danger ? " is-danger" : " is-accent"}"
      data-action="${action}"
      data-id="${id}"
      title="${label}"
      aria-label="${label}"
    >
      ${MAP_ICONS[action] || ""}
      <span>${label}</span>
    </button>
  `;
}

function actionLink(href, icon, label) {
  return `
    <a class="action-btn is-accent" href="${href}" title="${label}" aria-label="${label}">
      ${MAP_ICONS[icon] || ""}
      <span>${label}</span>
    </a>
  `;
}

function renderMaps() {
  const tbody = document.getElementById("maps-tbody");
  const maps = filteredMaps();
  if (!maps.length) {
    const empty = emptyStateMessage();
    const title = MAP_SEARCH.trim() ? "No matching maps" : empty.title;
    const body = MAP_SEARCH.trim() ? "Try a different search term." : empty.body;
    tbody.innerHTML = `<tr><td colspan="5"><div class="empty-state"><strong>${title}</strong>${body}</div></td></tr>`;
    return;
  }
  tbody.innerHTML = maps.map((map) => `
    <tr>
      <td>
        <a class="cell-entity cell-entity-link" href="/maps/${map.id}/">
          <span class="cell-icon tone-blue" aria-hidden="true">${MAP_ICONS.map}</span>
          <span class="cell-entity-name">${Auth.escapeHtml(map.name)}</span>
        </a>
      </td>
      <td><span class="cell-count">${map.map_layers.length}</span></td>
      <td>${Auth.escapeHtml(ownerLabel(map))}</td>
      <td>
        <span class="badge badge-access">
          <span class="badge-icon" aria-hidden="true">${MAP_ICONS.access}</span>
          ${Auth.escapeHtml(permissionLabel(map.my_permission))}
        </span>
      </td>
      <td class="table-actions">
        <div class="action-btn-row">
          ${actionLink(`/maps/${map.id}/`, "open", "Open")}
          ${map.my_permission === "owner" ? `
            ${actionButton("share", map.id, "Share")}
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

document.getElementById("maps-search")?.addEventListener("input", (event) => {
  MAP_SEARCH = event.target.value || "";
  renderMaps();
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
    if (!res.ok && res.status !== 204) {
      throw new Error(await Toast.fromResponse(res, "Could not delete map."));
    }
    Auth.closeModal("delete-modal");
    await loadMaps();
    Toast.success("Map deleted.");
  } catch (err) {
    Toast.error(err.message || "Could not delete map.");
  } finally {
    btn.disabled = false;
  }
});

function openRevokeLinkModal(mapId, linkId) {
  document.getElementById("revoke-link-map-id").value = mapId;
  document.getElementById("revoke-link-id").value = linkId;
  Auth.openModal("revoke-link-modal");
}

function renderShareList(map) {
  ShareUi.renderPeopleList(map?.shares || [], {
    onRemove: async (userId) => {
      const mapId = document.getElementById("share-map-id").value;
      try {
        const res = await Auth.apiFetch(`/api/maps/${mapId}/unshare/`, {
          method: "POST",
          body: { user_id: userId },
        });
        if (!res.ok) {
          throw new Error(await Toast.fromResponse(res, "Could not remove access."));
        }
        await loadMaps();
        renderShareList(findMap(mapId));
        Toast.success("Access removed.");
      } catch (err) {
        Toast.error(err.message || "Could not remove access.");
      }
    },
  });
}

function openShareModal(map) {
  if (map.my_permission !== "owner") {
    Toast.error("Only the map owner can share this map.");
    return;
  }
  document.getElementById("share-map-id").value = map.id;
  ShareUi.prepareOpen({
    subtitleEl: document.getElementById("share-map-sub"),
    subtitle: map.name
      ? `Sharing "${map.name}"`
      : "Share with GeoTrak Layers users or create an external link",
  });
  renderShareList(map);
  ShareUi.loadShareLinks({
    listUrl: `/api/maps/${map.id}/share-links/`,
    includeLayerCount: true,
    onRevoke: (linkId) => openRevokeLinkModal(map.id, linkId),
  });
  Auth.openModal("share-modal");
}

ShareUi.bindModal({
  includeLayerCount: true,
  getResourceId: () => document.getElementById("share-map-id")?.value,
  getRevokeResourceId: () => document.getElementById("revoke-link-map-id")?.value,
  shareUrl: (id) => `/api/maps/${id}/share/`,
  shareLinksUrl: (id) => `/api/maps/${id}/share-links/`,
  revokeUrl: (id, linkId) => `/api/maps/${id}/share-links/${linkId}/`,
  shareSuccess: "Map shared.",
  shareError: "Could not share map.",
  onRevoke: (mapId, linkId) => openRevokeLinkModal(mapId, linkId),
  afterPeopleChange: async () => {
    const mapId = document.getElementById("share-map-id").value;
    await loadMaps();
    renderShareList(findMap(mapId));
  },
});

function openCreateMapModal() {
  document.getElementById("create-map-form").reset();
  Auth.openModal("create-map-modal");
  setTimeout(() => document.getElementById("new-map-name").focus(), 50);
}

document.getElementById("open-create-map-modal").addEventListener("click", openCreateMapModal);

document.getElementById("create-map-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const name = document.getElementById("new-map-name").value.trim();
  const submitBtn = document.getElementById("create-map-submit");
  if (!name) {
    Toast.error("Enter a map name.");
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
      throw new Error(await Toast.fromResponse(res, "Could not create map."));
    }
    const data = await res.json();
    Toast.flash("Map created.");
    window.location.href = `/maps/${data.id}/`;
  } catch (err) {
    Toast.error(err.message || "Could not create map.");
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
