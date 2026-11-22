/**
 * GeoLayers theme system — single catalog for FOUC, persistence, and picker UI.
 * Load in <head> before main.css so data-theme / data-chrome apply before paint.
 */
(function (global) {
  const STORAGE_KEY = "geolayers_theme";
  const DEFAULT_THEME = "classic";

  /** @type {ReadonlyArray<{id:string,label:string,hint:string,swatch:[string,string],chrome:"light"|"dark"}>} */
  const THEMES = Object.freeze([
    {
      id: "classic",
      label: "Classic",
      hint: "Blue on soft white",
      swatch: ["#1d6ef5", "#f7f9fc"],
      chrome: "light",
    },
    {
      id: "mono",
      label: "Mono",
      hint: "Black & white",
      swatch: ["#141414", "#f6f6f6"],
      chrome: "light",
    },
    {
      id: "midnight",
      label: "Midnight",
      hint: "Dark professional",
      swatch: ["#0d1118", "#3b82f6"],
      chrome: "dark",
    },
    {
      id: "graphite",
      label: "Graphite",
      hint: "Cool charcoal light",
      swatch: ["#242a34", "#eceff3"],
      chrome: "light",
    },
  ]);

  const THEME_BY_ID = Object.freeze(
    Object.fromEntries(THEMES.map((theme) => [theme.id, theme]))
  );

  let animTimer = null;
  let documentBound = false;

  function isValid(id) {
    return Boolean(id && THEME_BY_ID[id]);
  }

  function resolveTheme(id) {
    return isValid(id) ? id : DEFAULT_THEME;
  }

  function readStored() {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (isValid(stored)) return stored;
    } catch (err) {
      /* private mode / blocked storage */
    }
    return null;
  }

  function getTheme() {
    return resolveTheme(
      readStored() || document.documentElement.getAttribute("data-theme")
    );
  }

  function applyToDocument(themeId, { animate = false } = {}) {
    const theme = resolveTheme(themeId);
    const meta = THEME_BY_ID[theme];
    const root = document.documentElement;

    if (animate) {
      root.classList.add("theme-animating");
      clearTimeout(animTimer);
      animTimer = setTimeout(() => root.classList.remove("theme-animating"), 320);
    }

    root.setAttribute("data-theme", theme);
    root.setAttribute("data-chrome", meta.chrome);

    document.querySelectorAll("[data-theme-option]").forEach((btn) => {
      const active = btn.getAttribute("data-theme-option") === theme;
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-checked", active ? "true" : "false");
    });

    return theme;
  }

  function persist(themeId) {
    try {
      localStorage.setItem(STORAGE_KEY, themeId);
    } catch (err) {
      /* ignore */
    }
  }

  function setTheme(id, { animate = true, persist: shouldPersist = true } = {}) {
    const theme = applyToDocument(id, { animate });
    if (shouldPersist) persist(theme);
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

  function closeAllPickers(exceptRoot) {
    document.querySelectorAll("[data-theme-picker]").forEach((rootEl) => {
      if (exceptRoot && rootEl === exceptRoot) return;
      const btn = rootEl.querySelector("[data-theme-trigger]");
      const menu = rootEl.querySelector("[data-theme-menu]");
      if (!btn || !menu) return;
      menu.classList.add("hidden");
      btn.setAttribute("aria-expanded", "false");
    });
  }

  function bindPicker(rootEl) {
    const btn = rootEl.querySelector("[data-theme-trigger]");
    const menu = rootEl.querySelector("[data-theme-menu]");
    const list = rootEl.querySelector("[data-theme-list]");
    if (!btn || !menu || !list || rootEl.dataset.themeBound === "1") return;

    rootEl.dataset.themeBound = "1";
    renderOptions(list);

    function setOpen(open) {
      if (open) closeAllPickers(rootEl);
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
  }

  function bindDocumentOnce() {
    if (documentBound) return;
    documentBound = true;

    document.addEventListener("click", (event) => {
      if (event.target.closest("[data-theme-picker]")) return;
      closeAllPickers();
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeAllPickers();
    });
  }

  function init() {
    persist(applyToDocument(getTheme(), { animate: false }));
    document.querySelectorAll("[data-theme-picker]").forEach(bindPicker);
    bindDocumentOnce();
  }

  // Apply stored theme immediately (before CSS paint).
  applyToDocument(getTheme(), { animate: false });

  const Theme = Object.freeze({
    THEMES,
    STORAGE_KEY,
    DEFAULT_THEME,
    getTheme,
    setTheme,
    init,
  });

  global.Theme = Theme;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})(window);
