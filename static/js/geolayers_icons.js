/**
 * Built-in SDF point icons for GeoLayers (Mapbox GL / MapLibre).
 * White shapes on transparent canvas → tinted via paint `icon-color`.
 * Shapes stay bold so they remain readable at city-overview icon sizes.
 */
(function (global) {
  const SIZE = 64;
  // Ids/labels must stay aligned with apps/layers/share_style.GEOLAYERS_ICON_IDS.
  // ICON_OPTIONS is the client catalog for style pickers.
  const ICON_OPTIONS = [
    { id: "gl-poi", label: "Pin" },
    { id: "gl-station", label: "Station" },
    { id: "gl-underground", label: "Underground" },
    { id: "gl-elevated", label: "Elevated" },
    { id: "gl-bus", label: "Bus" },
    { id: "gl-metro", label: "Metro" },
    { id: "gl-square", label: "Square" },
    { id: "gl-triangle", label: "Triangle" },
    { id: "gl-diamond", label: "Diamond" },
  ];
  const ICON_IDS = ICON_OPTIONS.map((opt) => opt.id);

  function makeCanvas() {
    const canvas = document.createElement("canvas");
    canvas.width = SIZE;
    canvas.height = SIZE;
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, SIZE, SIZE);
    ctx.fillStyle = "#ffffff";
    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = 5;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    return { canvas, ctx };
  }

  function roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  function drawPin(ctx) {
    ctx.beginPath();
    ctx.arc(32, 26, 16, Math.PI * 0.18, Math.PI - Math.PI * 0.18, false);
    ctx.lineTo(32, 56);
    ctx.closePath();
    ctx.fill();
    ctx.globalCompositeOperation = "destination-out";
    ctx.beginPath();
    ctx.arc(32, 26, 6.5, 0, Math.PI * 2);
    ctx.fill();
    ctx.globalCompositeOperation = "source-over";
  }

  function drawStation(ctx) {
    ctx.beginPath();
    ctx.moveTo(32, 6);
    ctx.lineTo(54, 22);
    ctx.lineTo(54, 52);
    ctx.lineTo(10, 52);
    ctx.lineTo(10, 22);
    ctx.closePath();
    ctx.fill();
    ctx.globalCompositeOperation = "destination-out";
    roundRect(ctx, 24, 30, 16, 18, 2);
    ctx.fill();
    ctx.globalCompositeOperation = "source-over";
  }

  function drawUnderground(ctx) {
    ctx.beginPath();
    ctx.arc(32, 36, 20, Math.PI, 0, false);
    ctx.lineTo(52, 54);
    ctx.lineTo(12, 54);
    ctx.closePath();
    ctx.fill();
    ctx.globalCompositeOperation = "destination-out";
    roundRect(ctx, 24, 28, 16, 18, 2);
    ctx.fill();
    ctx.globalCompositeOperation = "source-over";
  }

  function drawElevated(ctx) {
    ctx.beginPath();
    ctx.moveTo(8, 30);
    ctx.lineTo(32, 8);
    ctx.lineTo(56, 30);
    ctx.closePath();
    ctx.fill();
    roundRect(ctx, 12, 28, 40, 22, 3);
    ctx.fill();
    ctx.fillRect(18, 50, 8, 8);
    ctx.fillRect(38, 50, 8, 8);
  }

  function drawBus(ctx) {
    roundRect(ctx, 10, 16, 44, 32, 8);
    ctx.fill();
    ctx.globalCompositeOperation = "destination-out";
    roundRect(ctx, 16, 22, 14, 12, 2);
    ctx.fill();
    roundRect(ctx, 34, 22, 14, 12, 2);
    ctx.fill();
    ctx.globalCompositeOperation = "source-over";
    ctx.beginPath();
    ctx.arc(20, 50, 6, 0, Math.PI * 2);
    ctx.arc(44, 50, 6, 0, Math.PI * 2);
    ctx.fill();
  }

  function drawMetro(ctx) {
    ctx.beginPath();
    ctx.moveTo(32, 8);
    ctx.lineTo(52, 18);
    ctx.lineTo(52, 44);
    ctx.lineTo(32, 54);
    ctx.lineTo(12, 44);
    ctx.lineTo(12, 18);
    ctx.closePath();
    ctx.fill();
    ctx.globalCompositeOperation = "destination-out";
    ctx.font = "bold 24px sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("M", 32, 32);
    ctx.globalCompositeOperation = "source-over";
  }

  function drawSquare(ctx) {
    roundRect(ctx, 12, 12, 40, 40, 8);
    ctx.fill();
  }

  function drawTriangle(ctx) {
    ctx.beginPath();
    ctx.moveTo(32, 8);
    ctx.lineTo(56, 52);
    ctx.lineTo(8, 52);
    ctx.closePath();
    ctx.fill();
  }

  function drawDiamond(ctx) {
    ctx.beginPath();
    ctx.moveTo(32, 6);
    ctx.lineTo(56, 32);
    ctx.lineTo(32, 58);
    ctx.lineTo(8, 32);
    ctx.closePath();
    ctx.fill();
  }

  const DRAWERS = {
    "gl-poi": drawPin,
    "gl-station": drawStation,
    "gl-underground": drawUnderground,
    "gl-elevated": drawElevated,
    "gl-bus": drawBus,
    "gl-metro": drawMetro,
    "gl-square": drawSquare,
    "gl-triangle": drawTriangle,
    "gl-diamond": drawDiamond,
  };

  function buildImageData(iconId) {
    const { canvas, ctx } = makeCanvas();
    const drawer = DRAWERS[iconId] || drawPin;
    drawer(ctx);
    return ctx.getImageData(0, 0, SIZE, SIZE);
  }

  /** Colored icon PNG for legends — same glyph as MapLibre SDF icons on the map. */
  function legendIconDataUrl(iconId, color) {
    const { canvas, ctx } = makeCanvas();
    const fill = /^#[0-9a-fA-F]{6}$/.test(String(color || "").trim())
      ? String(color).trim()
      : "#0F2D53";
    ctx.fillStyle = fill;
    ctx.strokeStyle = fill;
    const drawer = DRAWERS[iconId] || drawPin;
    drawer(ctx);
    return canvas.toDataURL("image/png");
  }

  function ensureGeoLayersIcons(map, iconIds) {
    if (!map || typeof map.addImage !== "function") return;
    // Empty array = nothing to register. Undefined = register the full set.
    const wanted = Array.isArray(iconIds) ? iconIds : ICON_IDS;
    if (!wanted.length) return;
    wanted.forEach((id) => {
      if (!ICON_IDS.includes(id)) return;
      if (map.hasImage?.(id)) return;
      try {
        map.addImage(id, buildImageData(id), { sdf: true });
      } catch (_err) {
        /* style reloads can race; ignore duplicate add */
      }
    });
  }

  global.GeoLayersIcons = {
    ICON_IDS,
    ICON_OPTIONS,
    ensureGeoLayersIcons,
    legendIconDataUrl,
  };
})(typeof window !== "undefined" ? window : globalThis);
