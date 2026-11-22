/**
 * Renders map-builder legends from server-built ``map_layer.legend`` payloads
 * (same shape as ``geolayers:legend`` on share styles).
 */
(function (global) {
  function escapeHtml(text) {
    return String(text ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function legendSectionsFromMapLayers(mapLayers) {
    return [...(mapLayers || [])]
      .filter((ml) => ml.visible && ml.legend)
      .sort((a, b) => a.order - b.order)
      .map((ml) => ml.legend);
  }

  function iconImg(iconId, color, alt) {
    if (!iconId || !global.GeoLayersIcons?.legendIconDataUrl) return "";
    const src = escapeHtml(global.GeoLayersIcons.legendIconDataUrl(iconId, color));
    return `<img class="map-legend-swatch map-legend-swatch-icon" src="${src}" alt="${escapeHtml(alt || "icon")}" width="16" height="16">`;
  }

  function swatchHtml(item) {
    const color = escapeHtml(item.color || "#0F2D53");
    const kind = String(item.swatch || (item.icon ? "icon" : "fill")).toLowerCase();

    if (kind === "icon" && item.icon) {
      return iconImg(item.icon, item.color, item.label);
    }
    if (kind === "line") {
      return `<span class="map-legend-swatch map-legend-swatch-line" style="--swatch:${color}" aria-hidden="true"></span>`;
    }
    if (kind === "circle") {
      return `<span class="map-legend-swatch map-legend-swatch-circle" style="background:${color}" aria-hidden="true"></span>`;
    }
    return `<span class="map-legend-swatch" style="background:${color}" aria-hidden="true"></span>`;
  }

  function itemRowsHtml(items) {
    return (items || [])
      .map(
        (item) => `<li class="map-legend-item">
          ${swatchHtml(item)}
          <span class="map-legend-item-label">${escapeHtml(item.label)}</span>
        </li>`,
      )
      .join("");
  }

  function groupHtml(group) {
    if (!group?.items?.length) return "";
    const caption = group.caption || (group.field ? `By ${group.field}` : "");
    const captionHtml = caption
      ? `<p class="map-legend-field">${escapeHtml(caption)}</p>`
      : "";
    return `${captionHtml}<ul class="map-legend-list">${itemRowsHtml(group.items)}</ul>`;
  }

  function sectionHtml(section) {
    const titleHtml = section.title
      ? `<h4 class="map-legend-section-title">${escapeHtml(section.title)}</h4>`
      : "";
    if (Array.isArray(section.sections) && section.sections.length) {
      const groups = section.sections
        .map((sub) => `<div class="map-legend-group">${groupHtml(sub)}</div>`)
        .join("");
      return `<section class="map-legend-section">${titleHtml}${groups}</section>`;
    }
    return `<section class="map-legend-section">${titleHtml}${groupHtml(section)}</section>`;
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
      renderMapLegend(container, sections, {
        collapsed: !container.classList.contains("is-collapsed"),
      });
    });
  }

  global.GeoLayersLegend = {
    legendSectionsFromMapLayers,
    renderMapLegend,
  };
})(typeof window !== "undefined" ? window : globalThis);
