/**
 * JWT auth helper: stores the access/refresh token pair issued at login,
 * attaches the access token to API calls, and transparently refreshes it
 * once on a 401 before retrying the original request.
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

  async function login(username, password) {
    const response = await fetch("/api/auth/login/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || "Invalid username or password.");
    }
    const data = await response.json();
    setTokens({ access: data.access, refresh: data.refresh });
    return data.user;
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

  return { login, logout, apiFetch };
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
