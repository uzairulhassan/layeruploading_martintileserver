/* Shared share-modal helpers for layers list, maps list, and map builder. */
window.ShareUi = (function () {
  let copyResetTimer = null;
  let newLinkId = null;
  let newLinkClearTimer = null;

  const icons = {
    copy: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="8.5" y="8.5" width="10" height="12" rx="1.5" stroke="currentColor" stroke-width="1.7"/><path d="M15.5 8.5V6.2A1.7 1.7 0 0 0 13.8 4.5H6.2A1.7 1.7 0 0 0 4.5 6.2v7.6A1.7 1.7 0 0 0 6.2 15.5H8.5" stroke="currentColor" stroke-width="1.7"/></svg>`,
    trash: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 7.5h14M10 7.5V5.8A1.3 1.3 0 0 1 11.3 4.5h1.4A1.3 1.3 0 0 1 14 5.8V7.5M8.5 7.5v11.2A1.3 1.3 0 0 0 9.8 20h4.4a1.3 1.3 0 0 0 1.3-1.3V7.5" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
    users: `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="9" cy="8" r="3.1" stroke="currentColor" stroke-width="1.6"/><path d="M3.8 18.2c.7-2.7 2.8-4.2 5.2-4.2s4.5 1.5 5.2 4.2" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><circle cx="16.5" cy="9" r="2.4" stroke="currentColor" stroke-width="1.6"/><path d="M15.2 14.2c1.7.2 3.2 1.2 3.9 3.2" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><path d="M18.2 5.2v3.2M16.6 6.8h3.2" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>`,
    link: `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M10.2 13.8a4.2 4.2 0 0 1 0-5.9l2.1-2.1a4.2 4.2 0 0 1 5.9 5.9l-1 1" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><path d="M13.8 10.2a4.2 4.2 0 0 1 0 5.9l-2.1 2.1a4.2 4.2 0 1 1-5.9-5.9l1-1" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>`,
  };

  function setCount(id, count) {
    const el = document.getElementById(id);
    if (el) el.textContent = String(count || 0);
  }

  function setGenerateBusy(busy) {
    const btn = document.getElementById("external-create-btn");
    const panel = document.getElementById("external-create-panel");
    const label = btn?.querySelector(".share-generate-label");
    if (!btn) return;
    btn.disabled = !!busy;
    btn.classList.toggle("is-generating", !!busy);
    panel?.classList.toggle("is-generating", !!busy);
    if (label) label.textContent = busy ? "Generating..." : "Generate link";
  }

  function setTab(tab) {
    const peopleTab = document.getElementById("share-tab-people");
    const externalTab = document.getElementById("share-tab-external");
    const peoplePanel = document.getElementById("share-panel-people");
    const externalPanel = document.getElementById("share-panel-external");
    if (!peopleTab || !externalTab || !peoplePanel || !externalPanel) return;

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

  function getLinkType() {
    const selected = document.querySelector('input[name="external-link-type"]:checked');
    return selected?.value === "permanent" ? "permanent" : "expiring";
  }

  function syncExpiryControls() {
    const isPermanent = getLinkType() === "permanent";
    const expiryWrap = document.getElementById("external-expiry-wrap");
    const expiryInput = document.getElementById("external-expiry");
    const permanentHint = document.getElementById("external-permanent-hint");
    expiryWrap?.classList.toggle("is-hidden", isPermanent);
    permanentHint?.classList.toggle("is-hidden", !isPermanent);
    if (expiryInput) {
      expiryInput.required = !isPermanent;
      expiryInput.disabled = isPermanent;
      if (isPermanent) expiryInput.value = "";
    }
  }

  function resetCreateForm() {
    const expiring = document.querySelector('input[name="external-link-type"][value="expiring"]');
    if (expiring) expiring.checked = true;
    const expiryInput = document.getElementById("external-expiry");
    const ttlHint = document.getElementById("external-ttl-hint");
    const todayRiyadh = Auth.appCalendarYmd();
    const minDay = Auth.addAppCalendarDays(todayRiyadh, 1);
    const maxDays = Auth.shareLinkMaxTtlDays();
    const maxDay = Auth.addAppCalendarDays(todayRiyadh, maxDays);
    if (expiryInput) {
      expiryInput.min = minDay;
      expiryInput.max = maxDay;
      expiryInput.value = "";
    }
    if (ttlHint) {
      ttlHint.textContent = `Choose a date up to ${maxDays} days ahead.`;
    }
    syncExpiryControls();
  }

  function bindLinkTypeControls() {
    document.querySelectorAll('input[name="external-link-type"]').forEach((input) => {
      input.addEventListener("change", syncExpiryControls);
    });
  }

  function bindTabs() {
    document.querySelectorAll("[data-share-tab]").forEach((btn) => {
      btn.addEventListener("click", () => setTab(btn.dataset.shareTab));
    });
  }

  function isInactive(link) {
    return Boolean(link?.is_expired || link?.is_blocked);
  }

  function formatExpiryLabel(link) {
    if (link.never_expires || !link.expires_at) {
      return `<span class="external-pill external-pill-live"><span class="external-pill-dot" aria-hidden="true"></span>No expiry</span>`;
    }
    if (link.is_expired) {
      return `<span class="external-pill external-pill-expired"><span class="external-pill-dot" aria-hidden="true"></span>Expired ${Auth.formatAppDate(link.expires_at)}</span>`;
    }
    return `<span class="external-pill"><span class="external-pill-dot" aria-hidden="true"></span>Expires ${Auth.formatAppDate(link.expires_at)}</span>`;
  }

  function emptyState(iconHtml, message) {
    return `
      <li class="share-empty">
        <div class="share-empty-state">
          <span class="share-empty-icon">${iconHtml}</span>
          <span>${message}</span>
        </div>
      </li>`;
  }

  function linkCardHtml(link, { highlightId = null, stats = [] } = {}) {
    const inactive = isInactive(link);
    const isNew = highlightId && String(link.id) === String(highlightId);
    const shareUrl = Auth.escapeHtml(link.style_url);
    const copyDisabled = inactive
      ? `disabled title="${link.is_blocked ? "Blocked links cannot be copied" : "Expired links cannot be copied"}"`
      : `data-copy-link="${shareUrl}"`;
    const statsHtml = stats.length
      ? `<div class="external-stats" aria-label="Usage">${stats.map((stat) => `
          <div class="external-stat">
            <span class="external-stat-label">${Auth.escapeHtml(stat.label)}</span>
            <span class="external-stat-value">${stat.value}</span>
          </div>`).join("")}
        </div>`
      : "";

    return `
    <li class="external-link-card${inactive ? " is-inactive" : ""}${isNew ? " is-new" : ""}">
      <div class="external-link-top">
        <div class="external-link-badges">
          ${formatExpiryLabel(link)}
          ${link.is_blocked ? `<span class="external-pill external-pill-blocked"><span class="external-pill-dot" aria-hidden="true"></span>Blocked</span>` : ""}
          ${isNew ? `<span class="external-pill external-pill-live"><span class="external-pill-dot" aria-hidden="true"></span>Just created</span>` : ""}
        </div>
        <div class="external-link-actions">
          <button type="button" class="btn btn-sm btn-danger external-action-btn" data-revoke-link="${link.id}">${icons.trash}<span>Revoke</span></button>
        </div>
      </div>
      <div class="external-field">
        <span class="external-field-label">Share URL</span>
        <div class="external-url-tray">
          <input class="external-input" type="text" readonly value="${shareUrl}" aria-label="Share URL">
          <button type="button" class="btn btn-sm btn-primary external-action-btn" ${copyDisabled}>${icons.copy}<span>Copy</span></button>
        </div>
      </div>
      ${statsHtml}
    </li>`;
  }

  function clearNewLinkHighlightSoon() {
    clearTimeout(newLinkClearTimer);
    if (!newLinkId) return;
    newLinkClearTimer = window.setTimeout(() => {
      newLinkId = null;
    }, 2200);
  }

  function markNewLink(id) {
    newLinkId = id || null;
  }

  function resetNewLink() {
    clearTimeout(newLinkClearTimer);
    newLinkId = null;
  }

  function renderGroupedLinks(listEl, links, { statsForLink, onRevoke } = {}) {
    setCount("share-links-count", links.length);
    if (!links.length) {
      listEl.innerHTML = emptyState(icons.link, "No links yet. Generate your first one above.");
      return;
    }

    const active = links.filter((link) => !isInactive(link));
    const inactive = links.filter((link) => isInactive(link));
    const sections = [];
    const card = (link) => linkCardHtml(link, {
      highlightId: newLinkId,
      stats: typeof statsForLink === "function" ? statsForLink(link) : [],
    });

    if (active.length) {
      sections.push(`<li class="share-links-group-title" aria-hidden="true">Active</li>`);
      sections.push(...active.map(card));
    }
    if (inactive.length) {
      sections.push(`<li class="share-links-group-title" aria-hidden="true">Expired / blocked</li>`);
      sections.push(...inactive.map(card));
    }
    listEl.innerHTML = sections.join("");

    listEl.querySelectorAll("[data-copy-link]").forEach((btn) => {
      btn.addEventListener("click", () => copyWithFeedback(btn.dataset.copyLink, btn, "Share URL copied."));
    });
    listEl.querySelectorAll("[data-revoke-link]").forEach((btn) => {
      btn.addEventListener("click", () => onRevoke?.(btn.dataset.revokeLink));
    });
    clearNewLinkHighlightSoon();
  }

  function usageStats(link, { includeLayerCount = false } = {}) {
    const requests = Number(link.total_requests || 0).toLocaleString();
    const lastUsed = link.last_used_at ? Auth.formatAppDateTime(link.last_used_at) : "Never";
    const stats = [];
    if (includeLayerCount) {
      stats.push({ label: "Visible layers", value: String(Number(link.layer_count || 0)) });
    }
    stats.push(
      { label: "Tile requests", value: requests },
      { label: "Last used", value: Auth.escapeHtml(lastUsed) },
    );
    return stats;
  }

  async function buildCreateBody() {
    const isPermanent = getLinkType() === "permanent";
    if (isPermanent) return { expires_at: null };

    const expiryInput = document.getElementById("external-expiry");
    const expiryValue = expiryInput?.value;
    if (!expiryValue) {
      throw new Error("Choose an expiry date.");
    }
    const minDay = expiryInput?.min;
    const maxDay = expiryInput?.max;
    if ((minDay && expiryValue < minDay) || (maxDay && expiryValue > maxDay)) {
      throw new Error(`Expiry must be between ${minDay} and ${maxDay}.`);
    }
    return { expires_at: Auth.endOfAppDayIso(expiryValue) };
  }

  function copyText(text) {
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
      else reject(new Error("copy failed"));
    });
  }

  async function copyWithFeedback(text, button, successText) {
    clearTimeout(copyResetTimer);
    try {
      await copyText(text);
      document.querySelectorAll("#external-links-list .is-copied").forEach((btn) => {
        btn.classList.remove("is-copied");
      });
      button.classList.add("is-copied");
      copyResetTimer = window.setTimeout(() => {
        button.classList.remove("is-copied");
      }, 1800);
      Toast.success(successText || "Copied.");
    } catch {
      Toast.error("Copy failed. Select the text and copy manually.");
    }
  }

  function renderPeopleList(shares, { canRemove = true, onRemove } = {}) {
    const list = document.getElementById("share-list");
    if (!list) return;
    const rows = shares || [];
    setCount("share-people-count", rows.length);
    if (!rows.length) {
      list.innerHTML = emptyState(icons.users, "Not shared with anyone yet.");
      return;
    }
    list.innerHTML = rows.map((s) => Auth.renderSharePerson(s.shared_with_detail, {
      permission: s.permission,
      actionHtml: canRemove
        ? `<button type="button" class="btn btn-sm row-remove" data-remove-share="${s.shared_with_detail.id}">Remove</button>`
        : "",
    })).join("");
    list.querySelectorAll("[data-remove-share]").forEach((btn) => {
      btn.addEventListener("click", () => onRemove?.(btn.dataset.removeShare));
    });
  }

  function prepareOpen({ subtitleEl, subtitle }) {
    const search = document.getElementById("share-search");
    const results = document.getElementById("share-results");
    const submit = document.getElementById("share-submit");
    if (search) search.value = "";
    if (results) results.innerHTML = "";
    if (submit) submit.disabled = true;
    resetNewLink();
    setGenerateBusy(false);
    resetCreateForm();
    setTab("people");
    if (subtitleEl && subtitle) subtitleEl.textContent = subtitle;
  }

  async function loadShareLinks({ listUrl, includeLayerCount = false, onRevoke }) {
    const list = document.getElementById("external-links-list");
    if (!list) return;
    list.innerHTML = `<li class="share-empty">Loading...</li>`;
    const res = await Auth.apiFetch(listUrl);
    if (!res.ok) {
      list.innerHTML = `<li class="share-empty">Could not load share links.</li>`;
      return;
    }
    const links = await res.json();
    renderGroupedLinks(list, links, {
      statsForLink: (link) => usageStats(link, { includeLayerCount }),
      onRevoke,
    });
  }

  /**
   * Bind once-per-page share modal controls. Page scripts supply API paths and
   * people-list refresh; UI chrome lives here so maps/layers stay in sync.
   */
  function bindModal(cfg) {
    bindTabs();
    bindLinkTypeControls();

    let searchTimeout;
    let selectedUser = null;

    document.getElementById("share-search")?.addEventListener("input", (event) => {
      clearTimeout(searchTimeout);
      const query = event.target.value.trim();
      const box = document.getElementById("share-results");
      selectedUser = null;
      const submit = document.getElementById("share-submit");
      if (submit) submit.disabled = true;
      if (!query) {
        if (box) box.innerHTML = "";
        return;
      }
      searchTimeout = setTimeout(async () => {
        const res = await Auth.apiFetch(`/api/auth/users/?search=${encodeURIComponent(query)}`);
        const data = await res.json();
        const results = data.results || data;
        if (!box) return;
        if (!results.length) {
          box.innerHTML = `<p class="share-empty-inline muted">No users found.</p>`;
          return;
        }
        box.innerHTML = `<div class="share-results-list">${results.map((u) => Auth.renderShareHit(u)).join("")}</div>`;
        box.querySelectorAll("[data-user-id]").forEach((row) => {
          row.addEventListener("click", () => {
            selectedUser = results.find((u) => String(u.id) === row.dataset.userId);
            document.getElementById("share-search").value =
              selectedUser.display_name || selectedUser.username;
            box.innerHTML = "";
            if (submit) submit.disabled = false;
          });
        });
      }, 250);
    });

    document.getElementById("share-submit")?.addEventListener("click", async () => {
      if (!selectedUser) return;
      if (cfg.canManage && !cfg.canManage()) return;
      const resourceId = cfg.getResourceId?.();
      if (!resourceId) return;
      const btn = document.getElementById("share-submit");
      btn.disabled = true;
      try {
        const permission = document.getElementById("share-permission")?.value || "view";
        const res = await Auth.apiFetch(cfg.shareUrl(resourceId), {
          method: "POST",
          body: { shared_with: selectedUser.id, permission },
        });
        if (!res.ok) {
          throw new Error(await Toast.fromResponse(res, cfg.shareError || "Could not share."));
        }
        selectedUser = null;
        document.getElementById("share-search").value = "";
        btn.disabled = true;
        await cfg.afterPeopleChange?.();
        Toast.success(cfg.shareSuccess || "Shared.");
      } catch (err) {
        Toast.error(err.message || cfg.shareError || "Could not share.");
        btn.disabled = false;
      }
    });

    document.getElementById("external-create-btn")?.addEventListener("click", async () => {
      if (cfg.canManage && !cfg.canManage()) return;
      const resourceId = cfg.getResourceId?.();
      if (!resourceId) return;

      let body;
      try {
        body = await buildCreateBody();
      } catch (err) {
        Toast.error(err.message || "Could not generate the link.");
        return;
      }

      setGenerateBusy(true);
      try {
        const res = await Auth.apiFetch(cfg.shareLinksUrl(resourceId), {
          method: "POST",
          body,
        });
        if (!res.ok) {
          throw new Error(await Toast.fromResponse(res, "Could not generate the link."));
        }
        const created = await res.json().catch(() => null);
        markNewLink(created?.id || null);
        await new Promise((resolve) => window.setTimeout(resolve, 320));
        resetCreateForm();
        await loadShareLinks({
          listUrl: cfg.shareLinksUrl(resourceId),
          includeLayerCount: !!cfg.includeLayerCount,
          onRevoke: (linkId) => cfg.onRevoke?.(resourceId, linkId),
        });
        Toast.success("Share link ready.");
      } catch (err) {
        Toast.error(err.message || "Could not generate the link.");
      } finally {
        setGenerateBusy(false);
      }
    });

    document.getElementById("revoke-link-confirm")?.addEventListener("click", async () => {
      const resourceId = cfg.getRevokeResourceId?.() || cfg.getResourceId?.();
      const linkId = document.getElementById("revoke-link-id")?.value;
      if (!resourceId || !linkId) return;
      const btn = document.getElementById("revoke-link-confirm");
      btn.disabled = true;
      try {
        const res = await Auth.apiFetch(cfg.revokeUrl(resourceId, linkId), { method: "DELETE" });
        if (!res.ok && res.status !== 204) {
          throw new Error(await Toast.fromResponse(res, "Could not revoke link."));
        }
        Auth.closeModal("revoke-link-modal");
        await loadShareLinks({
          listUrl: cfg.shareLinksUrl(resourceId),
          includeLayerCount: !!cfg.includeLayerCount,
          onRevoke: (nextLinkId) => cfg.onRevoke?.(resourceId, nextLinkId),
        });
        Toast.success("Link revoked.");
      } catch (err) {
        Toast.error(err.message || "Could not revoke link.");
      } finally {
        btn.disabled = false;
      }
    });

    return {
      getSelectedUser: () => selectedUser,
      clearSelectedUser: () => {
        selectedUser = null;
      },
    };
  }

  return {
    icons,
    setCount,
    setGenerateBusy,
    setTab,
    resetCreateForm,
    emptyState,
    usageStats,
    renderPeopleList,
    prepareOpen,
    loadShareLinks,
    bindModal,
    resetNewLink,
  };
})();
