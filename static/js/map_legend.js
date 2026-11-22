/**
 * End-user legend for categorical colorBy / iconBy styles (any layer).
 */
(function (global) {
  function iconLabel(iconId) {
    const labels = global.GeoLayersIcons?.ICON_LABELS || {};
    return labels[iconId] || String(iconId || "").replace(/^gl-/, "");
  }

  function asObject(value) {
    return value && typeof value === "object" && !Array.isArray(value) ? value : {};
  }

  function normalizeHex(value, fallback) {
    const text = String(value || "").trim();
    if (/^#[0-9a-fA-F]{6}$/.test(text)) return text;
    return fallback || "#0F2D53";
  }

  /** Accept legacy string categories or `{icon, size}` objects from the style editor. */
  function iconIdFromCategory(raw, fallback) {
    if (raw && typeof raw === "object" && !Array.isArray(raw)) {
      raw = raw.icon;
    }
    const text = String(raw || "").trim();
    return text || fallback || "gl-poi";
  }

  function mergedStyle(mapLayer) {
    return {
      ...(mapLayer?.layer_detail?.style || {}),
      ...(mapLayer?.style_override || {}),
    };
  }

  function legendFromStyle(style, title) {
    const colorBy = asObject(style.colorBy);
    const marker = asObject(style.marker);
    const useIcons = String(marker.type || "circle").toLowerCase() === "icon";
    const iconBy = useIcons ? asObject(marker.iconBy) : {};
    const colorField = String(colorBy.field || "").trim();
    const iconField = String(iconBy.field || "").trim();
    if (!colorField && !iconField) return null;

    const colorCats = colorField ? asObject(colorBy.categories) : {};
    const iconCats = iconField ? asObject(iconBy.categories) : {};
    const defaultColor = normalizeHex(
      colorField ? colorBy.default : style.color,
      normalizeHex(style.color, "#0F2D53"),
    );
    const defaultIcon = iconIdFromCategory(
      iconField ? iconBy.default : marker.icon,
      iconIdFromCategory(marker.icon, "gl-poi"),
    );

    const makeItem = (key, color, iconId) => ({
      label: String(key),
      color: normalizeHex(color, defaultColor),
      icon: iconId || null,
      iconLabel: iconId ? iconLabel(iconId) : "",
    });

    if (colorField && iconField && colorField === iconField) {
      const keys = [...new Set([...Object.keys(colorCats), ...Object.keys(iconCats)])];
      const items = keys.map((key) =>
        makeItem(key, colorCats[key], iconIdFromCategory(iconCats[key], defaultIcon)),
      );
      if (!items.length) return null;
      return { title: String(title || "").trim(), field: colorField, items };
    }

    const sections = [];
    if (colorField && Object.keys(colorCats).length) {
      sections.push({
        title: String(title || "").trim(),
        field: colorField,
        items: Object.keys(colorCats).map((key) => makeItem(key, colorCats[key], null)),
      });
    }
    if (iconField && Object.keys(iconCats).length) {
      sections.push({
        title: String(title || "").trim(),
        field: iconField,
        items: Object.keys(iconCats).map((key) =>
          makeItem(key, defaultColor, iconIdFromCategory(iconCats[key], defaultIcon)),
        ),
      });
    }
    if (!sections.length) return null;
    if (sections.length === 1) return sections[0];
    return { title: String(title || "").trim(), field: "", sections };
  }

  function legendSectionsFromMapLayers(mapLayers) {
    const sections = [];
    [...(mapLayers || [])]
      .filter((ml) => ml.visible)
      .sort((a, b) => a.order - b.order)
      .forEach((ml) => {
        const legend = legendFromStyle(mergedStyle(ml), ml.layer_detail?.name || "");
        if (legend) sections.push(legend);
      });
    return sections;
  }

  function escapeHtml(text) {
    return String(text ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function itemRowsHtml(items) {
    return (items || [])
      .map((item) => {
        const swatch = `<span class="map-legend-swatch" style="background:${escapeHtml(item.color)}" aria-hidden="true"></span>`;
        const iconBit = item.iconLabel
          ? `<span class="map-legend-icon-label">${escapeHtml(item.iconLabel)}</span>`
          : "";
        return `<li class="map-legend-item">
          ${swatch}
          <span class="map-legend-item-text">
            <span class="map-legend-item-label">${escapeHtml(item.label)}</span>
            ${iconBit}
          </span>
        </li>`;
      })
      .join("");
  }

  function sectionHtml(section) {
    if (Array.isArray(section.sections) && section.sections.length) {
      return section.sections.map((sub) => sectionHtml(sub)).join("");
    }
    const title = escapeHtml(section.title || "Layer");
    const field = section.field ? `<p class="map-legend-field">${escapeHtml(section.field)}</p>` : "";
    return `<section class="map-legend-section">
      <h4 class="map-legend-section-title">${title}</h4>
      ${field}
      <ul class="map-legend-list">${itemRowsHtml(section.items)}</ul>
    </section>`;
  }

  function renderMapLegend(container, sections, { collapsed = false } = {}) {
    if (!container) return;
    if (!sections || !sections.length) {
      container.innerHTML = "";
      container.hidden = true;
      container.classList.add("is-empty");
      return;
    }
    container.hidden = false;
    container.classList.remove("is-empty");
    container.classList.toggle("is-collapsed", !!collapsed);
    container.innerHTML = `
      <div class="map-legend-card">
        <div class="map-legend-head">
          <h3 class="map-legend-title">Legend</h3>
          <button type="button" class="map-legend-toggle" aria-expanded="${collapsed ? "false" : "true"}" title="Toggle legend">
            ${collapsed ? "Show" : "Hide"}
          </button>
        </div>
        <div class="map-legend-body">${sections.map(sectionHtml).join("")}</div>
      </div>`;
    container.querySelector(".map-legend-toggle")?.addEventListener("click", () => {
      const next = !container.classList.contains("is-collapsed");
      renderMapLegend(container, sections, { collapsed: next });
    });
  }

  global.GeoLayersLegend = {
    legendSectionsFromMapLayers,
    renderMapLegend,
  };
})(typeof window !== "undefined" ? window : globalThis);
