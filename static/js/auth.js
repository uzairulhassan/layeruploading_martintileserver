/**
 * JWT auth helper: stores the access/refresh token pair issued at login,
 * attaches the access token to API calls, and transparently refreshes it
 * once on a 401 before retrying the original request.
 *
 * Also provides registration helpers (username availability + sign-up POST)
 * used by the signup / onetime pages.
 */
const Auth = (() => {
  const ACCESS_KEY = "geolayers_access_token";
  const REFRESH_KEY = "geolayers_refresh_token";

  function getAccessToken() {
    return localStorage.getItem(ACCESS_KEY);
  }

  function getRefreshToken() {
    return localStorage.getItem(REFRESH_KEY);
  }

  function setTokens({ access, refresh }) {
    if (access) localStorage.setItem(ACCESS_KEY, access);
    if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
  }

  function clearTokens() {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  }

  function getCookie(name) {
    const match = document.cookie.match(new RegExp(`(^|;\\s*)${name}=([^;]*)`));
    return match ? decodeURIComponent(match[2]) : null;
  }

  function formatApiErrors(body) {
    if (!body || typeof body !== "object") return "Request failed.";
    if (body.detail) {
      return typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    }
    const parts = [];
    for (const [key, value] of Object.entries(body)) {
      if (key === "errors") continue;
      const msg = Array.isArray(value) ? value.join(" ") : String(value);
      parts.push(key === "non_field_errors" ? msg : `${key}: ${msg}`);
    }
    return parts.join(" ") || "Request failed.";
  }

  async function login(username, password) {
    const response = await fetch("/api/auth/login/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || "Invalid username/email or password.");
    }
    const data = await response.json();
    setTokens({ access: data.access, refresh: data.refresh });
    return data.user;
  }

  async function register(endpoint, payload) {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(formatApiErrors(body));
    }
    setTokens({ access: body.access, refresh: body.refresh });
    return body.user;
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

  function bindUsernameCheck(inputEl, statusEl, onChange) {
    let timer = null;
    let latestRequest = 0;
    let available = false;

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
      setStatus("Checking availability…", "pending");
      try {
        const response = await fetch(
          `/api/auth/username-available/?username=${encodeURIComponent(username)}`,
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
          available ? "Username is available." : "Username is already taken.",
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
      clearTimeout(timer);
      check(inputEl.value.trim());
    });

    notify();
    return { isAvailable: () => available };
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

  async function refreshAccessToken() {
    const refresh = getRefreshToken();
    if (!refresh) throw new Error("No refresh token available.");

    const response = await fetch("/api/auth/token/refresh/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh }),
    });
    if (!response.ok) {
      clearTokens();
      throw new Error("Session expired.");
    }
    const data = await response.json();
    setTokens({ access: data.access, refresh: data.refresh });
    return data.access;
  }

  async function logout() {
    const refresh = getRefreshToken();
    try {
      await fetch("/api/auth/logout/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${getAccessToken()}`,
        },
        body: JSON.stringify({ refresh }),
      });
    } catch (err) {
      // Best effort — still clear local state and end the Django session below.
    }
    clearTokens();
    window.location.href = "/logout/";
  }

  /**
   * fetch() wrapper that attaches the JWT access token and retries once
   * after a silent refresh if the server responds 401.
   */
  async function apiFetch(url, options = {}, _retried = false) {
    const headers = new Headers(options.headers || {});
    const accessToken = getAccessToken();
    if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);

    const isBodyPlainObject =
      options.body && !(options.body instanceof FormData) && typeof options.body === "object";
    if (isBodyPlainObject) {
      headers.set("Content-Type", "application/json");
      options = { ...options, body: JSON.stringify(options.body) };
    }

    if (["POST", "PUT", "PATCH", "DELETE"].includes((options.method || "GET").toUpperCase())) {
      headers.set("X-CSRFToken", getCookie("csrftoken") || "");
    }

    const response = await fetch(url, { ...options, headers });

    if (response.status === 401 && !_retried && getRefreshToken()) {
      try {
        await refreshAccessToken();
        return apiFetch(url, options, true);
      } catch (err) {
        clearTokens();
        window.location.href = "/logout/";
        throw err;
      }
    }

    return response;
  }

  return { login, logout, register, bindUsernameCheck, bindPasswordCheck, evaluatePassword, apiFetch };
})();

document.addEventListener("DOMContentLoaded", () => {
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
      !profileMenu.classList.contains("hidden")
      && !profileMenu.contains(event.target)
      && !profileBtn.contains(event.target)
    ) {
      setMenuOpen(false);
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") setMenuOpen(false);
  });
});
