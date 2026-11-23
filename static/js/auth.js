/** First-party auth: session cookie + CSRF. Login is session-only (no JWT storage). */
const Auth = (() => {
  // Saudi Arabia (Riyadh) — fixed UTC+3, no DST. Used for every user-facing datetime.
  const RIYADH_OFFSET = "+03:00";

  function appTimeZone() {
    return window.GeoLayersConfig?.timeZone || "Asia/Riyadh";
  }

  function shareLinkMaxTtlDays() {
    const raw = Number(window.GeoLayersConfig?.shareLinkMaxTtlDays);
    return Number.isFinite(raw) && raw > 0 ? Math.floor(raw) : 365;
  }

  function formatAppDate(isoString, options = {}) {
    if (!isoString) return "";
    try {
      return new Intl.DateTimeFormat("en-GB", {
        timeZone: appTimeZone(),
        year: "numeric",
        month: "short",
        day: "numeric",
        ...options,
      }).format(new Date(isoString));
    } catch {
      return String(isoString);
    }
  }

  function formatAppDateTime(isoString) {
    return formatAppDate(isoString, {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  }

  /** Calendar YYYY-MM-DD in the app timezone (Riyadh). */
  function appCalendarYmd(fromDate = new Date()) {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: appTimeZone(),
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(fromDate);
    const get = (type) => parts.find((p) => p.type === type)?.value || "01";
    return `${get("year")}-${get("month")}-${get("day")}`;
  }

  function addAppCalendarDays(ymd, days) {
    const base = new Date(`${ymd}T12:00:00${RIYADH_OFFSET}`);
    base.setTime(base.getTime() + Number(days || 0) * 86400000);
    return appCalendarYmd(base);
  }

  /** End of the given Riyadh calendar day as UTC ISO (for share-link expiry). */
  function endOfAppDayIso(ymd) {
    return new Date(`${ymd}T23:59:59${RIYADH_OFFSET}`).toISOString();
  }

  function sharePermissionLabel(permission) {
    if (permission === "edit") return "Can edit style & labels";
    if (permission === "view") return "View only";
    return String(permission || "").replace(/_/g, " ");
  }

  function getCookie(name) {
    const match = document.cookie.match(new RegExp(`(^|;\\s*)${name}=([^;]*)`));
    return match ? decodeURIComponent(match[2]) : null;
  }

  /**
   * Human-readable message from an API error body.
   * Prefers the standardized {code, message, errors, request_id} contract.
   * Never surfaces raw 5xx / INTERNAL_ERROR payloads beyond a generic message + ref.
   *
   * @param {object} body
   * @param {string} [fallback]
   * @param {{ status?: number }} [options]
   */
  function formatApiErrors(body, fallback = "Request failed.", options = {}) {
    if (!body || typeof body !== "object") return fallback;

    const status = Number(options.status) || 0;
    const code = typeof body.code === "string" ? body.code : "";
    const requestId = typeof body.request_id === "string" ? body.request_id.trim() : "";

    if (code === "INTERNAL_ERROR" || status >= 500) {
      let msg = "Something went wrong. Please try again.";
      if (requestId) msg = `${msg} (Ref: ${requestId})`;
      return msg;
    }

    if (body.errors && typeof body.errors === "object") {
      const parts = [];
      for (const [key, value] of Object.entries(body.errors)) {
        const msg = Array.isArray(value) ? value.join(" ") : String(value);
        parts.push(key === "non_field_errors" ? msg : `${key}: ${msg}`);
      }
      if (parts.length) return parts.join(" ");
    }

    if (typeof body.message === "string" && body.message.trim()) {
      return body.message.trim();
    }

    if (typeof body.detail === "string" && body.detail.trim()) {
      return body.detail.trim();
    }
    if (body.detail != null && typeof body.detail !== "string") {
      return JSON.stringify(body.detail);
    }
    return fallback;
  }

  async function login(username, password) {
    const response = await fetch("/api/auth/login/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ username, password }),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      const opts = { status: response.status };
      if (response.status === 429) {
        throw new Error(
          formatApiErrors(body, "Too many sign-in attempts. Please try again later.", opts)
        );
      }
      throw new Error(formatApiErrors(body, "Invalid username/email or password.", opts));
    }
    const data = await response.json();
    return data.user;
  }

  async function register(endpoint, payload) {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(payload),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const opts = { status: response.status };
      if (response.status === 429) {
        throw new Error(
          formatApiErrors(body, "Too many registration attempts. Please try again later.", opts)
        );
      }
      throw new Error(formatApiErrors(body, "Request failed.", opts));
    }
    return body;
  }

  function evaluatePassword(password) {
    const rules = {
      length: password.length >= 8,
      letter: /[A-Za-z]/.test(password),
      digit: /\d/.test(password),
      special: /[^A-Za-z0-9]/.test(password),
    };
    const score = Object.values(rules).filter(Boolean).length;
    let label = "";
    let level = "";
    if (!password) {
      label = "";
      level = "";
    } else if (score <= 1) {
      label = "Weak";
      level = "weak";
    } else if (score === 2) {
      label = "Fair";
      level = "fair";
    } else if (score === 3) {
      label = "Good";
      level = "good";
    } else {
      label = "Strong";
      level = "strong";
    }
    return {
      rules,
      score,
      label,
      level,
      valid: score === 4,
    };
  }

  function bindUsernameCheck(inputEl, statusEl, onChange, options = {}) {
    let timer = null;
    let latestRequest = 0;
    let available = false;
    let currentUsername = String(options.currentUsername || "").trim().toLowerCase();
    const availableMessage = options.availableMessage || "Username is available.";
    const takenMessage = options.takenMessage || "Username is already taken.";
    const currentMessage = options.currentMessage || availableMessage;

    function setStatus(text, state) {
      statusEl.textContent = text;
      statusEl.className = "field-hint" + (state ? ` is-${state}` : "");
    }

    function notify() {
      if (typeof onChange === "function") onChange();
    }

    async function check(username) {
      const requestId = ++latestRequest;
      if (!username) {
        available = false;
        setStatus("", "");
        notify();
        return;
      }
      if (currentUsername && username.toLowerCase() === currentUsername) {
        available = true;
        setStatus(currentMessage, "ok");
        notify();
        return;
      }
      setStatus("Checking availability…", "pending");
      try {
        const response = await fetch(
          `/api/auth/username-available/?username=${encodeURIComponent(username)}`,
          { credentials: "same-origin" },
        );
        const body = await response.json().catch(() => ({}));
        if (requestId !== latestRequest) return;

        if (!response.ok) {
          available = false;
          const err = body.errors?.username
            ? (Array.isArray(body.errors.username) ? body.errors.username[0] : body.errors.username)
            : "Invalid username.";
          setStatus(err, "error");
          notify();
          return;
        }

        available = Boolean(body.available);
        setStatus(
          available ? availableMessage : takenMessage,
          available ? "ok" : "error",
        );
        notify();
      } catch (err) {
        if (requestId !== latestRequest) return;
        available = false;
        setStatus("Could not check username.", "error");
        notify();
      }
    }

    inputEl.addEventListener("input", () => {
      if (inputEl.readOnly || inputEl.disabled) return;
      available = false;
      notify();
      clearTimeout(timer);
      if (!inputEl.value.trim()) {
        setStatus("", "");
        return;
      }
      timer = setTimeout(() => check(inputEl.value.trim()), 350);
    });

    inputEl.addEventListener("blur", () => {
      if (inputEl.readOnly || inputEl.disabled) return;
      clearTimeout(timer);
      check(inputEl.value.trim());
    });

    notify();
    return {
      isAvailable: () => available,
      setCurrentUsername(value) {
        currentUsername = String(value || "").trim().toLowerCase();
      },
    };
  }

  function bindPasswordCheck(passwordEl, confirmEl, onChange) {
    const strengthEl = document.getElementById("password-strength");
    const strengthBar = strengthEl ? strengthEl.querySelector(".password-strength-bar") : null;
    const strengthLabel = strengthEl ? strengthEl.querySelector(".password-strength-label") : null;
    const rulesEl = document.getElementById("password-rules");
    const matchEl = document.getElementById("password-match");
    let valid = false;
    let matches = false;

    function notify() {
      if (typeof onChange === "function") onChange();
    }

    function render() {
      const password = passwordEl.value;
      const confirm = confirmEl.value;
      const result = evaluatePassword(password);
      valid = result.valid;
      matches = Boolean(password) && password === confirm;

      if (strengthEl) {
        if (!password) {
          strengthEl.hidden = true;
          strengthEl.dataset.level = "";
          if (strengthLabel) strengthLabel.textContent = "";
        } else {
          strengthEl.hidden = false;
          strengthEl.dataset.level = result.level;
          if (strengthLabel) {
            strengthLabel.textContent = `Strength: ${result.label}`;
          }
        }
      }

      if (strengthBar) {
        strengthBar.style.width = password ? `${(result.score / 4) * 100}%` : "0%";
      }

      if (rulesEl) {
        rulesEl.querySelectorAll("[data-rule]").forEach((item) => {
          const key = item.getAttribute("data-rule");
          const ok = Boolean(result.rules[key]);
          item.classList.toggle("is-met", ok);
          item.classList.toggle("is-unmet", Boolean(password) && !ok);
        });
      }

      if (matchEl) {
        if (!confirm) {
          matchEl.textContent = "";
          matchEl.className = "field-hint";
        } else if (matches) {
          matchEl.textContent = "Passwords match.";
          matchEl.className = "field-hint is-ok";
        } else {
          matchEl.textContent = "Passwords do not match.";
          matchEl.className = "field-hint is-error";
        }
      }

      notify();
    }

    passwordEl.addEventListener("input", render);
    confirmEl.addEventListener("input", render);
    render();

    return {
      isValid: () => valid,
      matchesConfirm: () => matches,
    };
  }

  async function logout() {
    try {
      await fetch("/api/auth/logout/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCookie("csrftoken") || "",
        },
        credentials: "same-origin",
        body: "{}",
      });
    } catch (err) {
      // Best effort — still leave the app.
    }
    window.location.href = "/login/";
  }

  /** Session cookie + CSRF on mutating requests. */
  async function apiFetch(url, options = {}) {
    const headers = new Headers(options.headers || {});

    const isBodyPlainObject =
      options.body && !(options.body instanceof FormData) && typeof options.body === "object";
    if (isBodyPlainObject) {
      headers.set("Content-Type", "application/json");
      options = { ...options, body: JSON.stringify(options.body) };
    }

    if (["POST", "PUT", "PATCH", "DELETE"].includes((options.method || "GET").toUpperCase())) {
      headers.set("X-CSRFToken", getCookie("csrftoken") || "");
    }

    const response = await fetch(url, {
      ...options,
      headers,
      credentials: "same-origin",
    });

    if (response.status === 401) {
      const next = `${window.location.pathname}${window.location.search}`;
      const loginUrl = next && next !== "/"
        ? `/login/?next=${encodeURIComponent(next)}`
        : "/login/";
      window.location.href = loginUrl;
      throw new Error("Session expired.");
    }

    return response;
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function userInitials(user) {
    const source = String(user?.display_name || user?.username || "?").trim();
    const parts = source.split(/[\s._-]+/).filter(Boolean);
    if (parts.length >= 2) {
      return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
    }
    return source.slice(0, 2).toUpperCase();
  }

  function avatarMarkup(user, className = "person-avatar") {
    const url = user?.avatar_url;
    if (url) {
      return `<span class="${className} has-image" aria-hidden="true"><img src="${escapeHtml(url)}" alt=""></span>`;
    }
    return `<span class="${className}" aria-hidden="true">${escapeHtml(userInitials(user))}</span>`;
  }

  function syncHeaderAvatar(user) {
    const el = document.getElementById("header-avatar");
    if (!el || !user) return;
    if (user.avatar_url) {
      el.classList.add("has-image");
      el.innerHTML = `<img src="${escapeHtml(user.avatar_url)}" alt="">`;
    } else {
      el.classList.remove("has-image");
      el.textContent = userInitials(user);
    }
  }

  function personMeta(user) {
    // Directory payloads omit email; show @username when it differs from display name.
    const display = String(user?.display_name || "").trim();
    const username = String(user?.username || "").trim();
    if (username && display && display !== username) {
      return `<span class="person-username">@${escapeHtml(username)}</span>`;
    }
    return "";
  }

  function renderShareHit(user) {
    const meta = personMeta(user);
    return `
      <button type="button" class="person-row share-hit" data-user-id="${escapeHtml(user.id)}">
        ${avatarMarkup(user)}
        <span class="person-copy">
          <span class="person-name">${escapeHtml(user.display_name || user.username)}</span>
          ${meta ? `<span class="person-meta">${meta}</span>` : ""}
        </span>
      </button>
    `;
  }

  function renderSharePerson(user, { permission = "", actionHtml = "" } = {}) {
    const perm = permission
      ? `<span class="person-perm">${escapeHtml(sharePermissionLabel(permission))}</span>`
      : "";
    const meta = personMeta(user);
    return `
      <li class="person-row">
        ${avatarMarkup(user)}
        <span class="person-copy">
          <span class="person-name">${escapeHtml(user.display_name || user.username)}${perm}</span>
          ${meta ? `<span class="person-meta">${meta}</span>` : ""}
        </span>
        ${actionHtml}
      </li>
    `;
  }

  function openModal(id) {
    const el = document.getElementById(id);
    if (el) el.classList.remove("hidden");
  }

  function closeModal(id) {
    const el = document.getElementById(id);
    if (el) el.classList.add("hidden");
  }

  function bindModalClosers() {
    document.querySelectorAll("[data-close-modal]").forEach((btn) => {
      btn.addEventListener("click", () => closeModal(btn.dataset.closeModal));
    });
  }

  return {
    login,
    logout,
    register,
    bindUsernameCheck,
    bindPasswordCheck,
    apiFetch,
    escapeHtml,
    formatApiErrors,
    openModal,
    closeModal,
    bindModalClosers,
    renderShareHit,
    renderSharePerson,
    sharePermissionLabel,
    syncHeaderAvatar,
    appTimeZone,
    shareLinkMaxTtlDays,
    formatAppDate,
    formatAppDateTime,
    appCalendarYmd,
    addAppCalendarDays,
    endOfAppDayIso,
  };
})();

document.addEventListener("DOMContentLoaded", () => {
  Auth.bindModalClosers();

  const logoutBtn = document.getElementById("logout-btn");
  if (logoutBtn) logoutBtn.addEventListener("click", () => Auth.logout());

  const profileBtn = document.getElementById("profile-menu-btn");
  const profileMenu = document.getElementById("profile-menu");
  if (!profileBtn || !profileMenu) return;

  function setMenuOpen(open) {
    profileMenu.classList.toggle("hidden", !open);
    profileBtn.setAttribute("aria-expanded", open ? "true" : "false");
  }

  profileBtn.addEventListener("click", (event) => {
    event.stopPropagation();
    setMenuOpen(profileMenu.classList.contains("hidden"));
  });

  document.addEventListener("click", (event) => {
    if (
      profileMenu.classList.contains("hidden")
      || profileMenu.contains(event.target)
      || profileBtn.contains(event.target)
    ) {
      return;
    }
    setMenuOpen(false);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") setMenuOpen(false);
  });
});
