/**
 * Global toast notifications — theme-aware success / error / info messages.
 */
const Toast = (() => {
  const HOST_ID = "toast-host";
  const FLASH_KEY = "geolayers_toast_flash";
  const DEFAULT_DURATION = {
    success: 3200,
    error: 5200,
    info: 3600,
  };

  function host() {
    let el = document.getElementById(HOST_ID);
    if (el) return el;
    el = document.createElement("div");
    el.id = HOST_ID;
    el.className = "toast-host";
    el.setAttribute("aria-live", "polite");
    el.setAttribute("aria-relevant", "additions");
    document.body.appendChild(el);
    return el;
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function iconFor(type) {
    if (type === "success") {
      return `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 12.5 9.5 17 19 7.5" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
    }
    if (type === "error") {
      return `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 8v5.5M12 16.5h.01M12 3.5 21 20H3L12 3.5Z" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
    }
    return `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="8.25" stroke="currentColor" stroke-width="1.8"/><path d="M12 10.5V16M12 8h.01" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>`;
  }

  function show(message, type = "info", duration) {
    const text = String(message || "").trim();
    if (!text) return null;

    const kind = ["success", "error", "info"].includes(type) ? type : "info";
    const ms = typeof duration === "number" ? duration : DEFAULT_DURATION[kind];
    const el = document.createElement("div");
    el.className = `toast toast--${kind}`;
    el.setAttribute("role", kind === "error" ? "alert" : "status");
    el.innerHTML = `
      <span class="toast-icon">${iconFor(kind)}</span>
      <p class="toast-message">${escapeHtml(text)}</p>
      <button type="button" class="toast-close" aria-label="Dismiss">×</button>
    `;

    const remove = () => {
      if (el.dataset.leaving === "1") return;
      el.dataset.leaving = "1";
      el.classList.add("is-leaving");
      window.setTimeout(() => el.remove(), 220);
    };

    el.querySelector(".toast-close").addEventListener("click", remove);
    host().appendChild(el);
    requestAnimationFrame(() => el.classList.add("is-visible"));

    if (ms > 0) {
      window.setTimeout(remove, ms);
    }
    return el;
  }

  function success(message, duration) {
    return show(message, "success", duration);
  }

  function error(message, duration) {
    return show(message, "error", duration);
  }

  function info(message, duration) {
    return show(message, "info", duration);
  }

  /** Persist a toast across a full-page redirect (sessionStorage). */
  function flash(message, type = "success") {
    const text = String(message || "").trim();
    if (!text) return;
    try {
      sessionStorage.setItem(FLASH_KEY, JSON.stringify({ message: text, type }));
    } catch {
      /* ignore quota / private mode */
    }
  }

  function consumeFlash() {
    let raw = null;
    try {
      raw = sessionStorage.getItem(FLASH_KEY);
      if (raw) sessionStorage.removeItem(FLASH_KEY);
    } catch {
      return;
    }
    if (!raw) return;
    try {
      const data = JSON.parse(raw);
      if (data?.message) show(data.message, data.type || "info");
    } catch {
      /* ignore malformed */
    }
  }

  function fromApiBody(body, fallback = "Request failed.") {
    if (typeof Auth !== "undefined" && Auth.formatApiErrors) {
      return Auth.formatApiErrors(body, fallback);
    }
    if (body && typeof body.detail === "string") return body.detail;
    return fallback;
  }

  async function fromResponse(response, fallback = "Request failed.") {
    const body = await response.json().catch(() => ({}));
    return fromApiBody(body, fallback);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", consumeFlash);
  } else {
    consumeFlash();
  }

  return { show, success, error, info, flash, fromApiBody, fromResponse };
})();
