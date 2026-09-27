/**
 * App-wide theme preferences.
 * Persists selection in localStorage and applies data-theme on <html>.
 */
const Theme = (() => {
  const STORAGE_KEY = "geolayers_theme";
  const DEFAULT_THEME = "classic";
  const THEMES = [
    { id: "classic", label: "Classic", hint: "Navy on soft white", swatch: ["#0f2d53", "#f4f6f9"] },
    { id: "mono", label: "Mono", hint: "Black & white", swatch: ["#141414", "#f6f6f6"] },
    { id: "midnight", label: "Midnight", hint: "Dark professional", swatch: ["#0d1118", "#3b82f6"] },
    { id: "graphite", label: "Graphite", hint: "Charcoal & gray", swatch: ["#242a34", "#eceff3"] },
  ];

  let animTimer = null;

  function isValid(id) {
    return THEMES.some((theme) => theme.id === id);
  }

  function getTheme() {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored && isValid(stored)) return stored;
    } catch (err) {
      /* ignore */
    }
    const attr = document.documentElement.getAttribute("data-theme");
    return isValid(attr) ? attr : DEFAULT_THEME;
  }

  function setTheme(id, { animate = true } = {}) {
    const theme = isValid(id) ? id : DEFAULT_THEME;
    const root = document.documentElement;
    if (animate) {
      root.classList.add("theme-animating");
      clearTimeout(animTimer);
      animTimer = setTimeout(() => root.classList.remove("theme-animating"), 300);
    }
    root.setAttribute("data-theme", theme);
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch (err) {
      /* ignore */
    }
    document.querySelectorAll("[data-theme-option]").forEach((btn) => {
      const active = btn.getAttribute("data-theme-option") === theme;
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-checked", active ? "true" : "false");
    });
    return theme;
  }

  function renderOptions(container) {
    const current = getTheme();
    container.innerHTML = THEMES.map((theme) => {
      const active = theme.id === current;
      return `
        <button
          type="button"
          class="theme-option${active ? " is-active" : ""}"
          role="menuitemradio"
          data-theme-option="${theme.id}"
          aria-checked="${active ? "true" : "false"}"
        >
          <span class="theme-swatch" aria-hidden="true">
            <span style="background:${theme.swatch[0]}"></span>
            <span style="background:${theme.swatch[1]}"></span>
          </span>
          <span class="theme-option-copy">
            <span class="theme-option-label">${theme.label}</span>
            <span class="theme-option-hint">${theme.hint}</span>
          </span>
        </button>
      `;
    }).join("");
  }

  function bindPicker(rootEl) {
    const btn = rootEl.querySelector("[data-theme-trigger]");
    const menu = rootEl.querySelector("[data-theme-menu]");
    const list = rootEl.querySelector("[data-theme-list]");
    if (!btn || !menu || !list) return;

    renderOptions(list);

    function setOpen(open) {
      menu.classList.toggle("hidden", !open);
      btn.setAttribute("aria-expanded", open ? "true" : "false");
    }

    btn.addEventListener("click", (event) => {
      event.stopPropagation();
      setOpen(menu.classList.contains("hidden"));
    });

    list.addEventListener("click", (event) => {
      const option = event.target.closest("[data-theme-option]");
      if (!option) return;
      setTheme(option.getAttribute("data-theme-option"));
      setOpen(false);
    });

    document.addEventListener("click", (event) => {
      if (menu.classList.contains("hidden") || rootEl.contains(event.target)) return;
      setOpen(false);
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") setOpen(false);
    });
  }

  function init() {
    setTheme(getTheme(), { animate: false });
    document.querySelectorAll("[data-theme-picker]").forEach(bindPicker);
  }

  return { init };
})();

document.addEventListener("DOMContentLoaded", () => Theme.init());
