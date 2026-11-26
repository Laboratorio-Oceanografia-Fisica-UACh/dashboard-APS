/**
 * maps.js
 * Visualización geoespacial interactiva del Anticiclón del Pacífico Sur (APS / ASPS)
 * Implementa Par Dinámico V5.3 (LOFA - UACh):
 * - Núcleo Continuo Submalla 2D (+) y Centroide Barométrico Adaptativo (◇).
 * - Vector Geodésico de Desacople Físico (Distancia D_nc y Rumbo Náutico θ).
 * - Trazado de Isobaras Reales (Marching Squares 2D) con Isóbara 1020 hPa destacada.
 * - Delimitación Cartográfica de la Caja Norpatagonia (Monitoreo de Bloqueos).
 * - Libre al 100% de cálculos y capas de surgencia de Bakun.
 * Dominio espacial extendido LOFA: 10°S a 56°S, 130°W a 65°W
 * Laboratorio de Oceanografía Física (LOFA) - UACh
 */

// =============================================================================
// MOTOR DE CONTORNEO SINÓPTICO: MARCHING SQUARES 2D
// =============================================================================
class MarchingSquares {
  /**
   * Genera polilíneas continuas de contorno para un nivel escalar en una cuadrícula 2D
   * @param {number[][]} grid - Matriz 2D de valores escalares [filas = lats, cols = lons]
   * @param {number[]} lats - Vector de latitudes ordenadas
   * @param {number[]} lons - Vector de longitudes ordenadas
   * @param {number} level - Valor de la isobara a contornear (ej. 1016, 1020, 1024 hPa)
   * @returns {number[][][]} Lista de polilíneas continuas [[ [lat, lon], [lat, lon], ... ], ...]
   */
  static contour(grid, lats, lons, level) {
    const rows = lats.length;
    const cols = lons.length;
    const segments = [];

    // Recorrer cada celda cuadrangular
    for (let i = 0; i < rows - 1; i++) {
      const lat0 = lats[i];
      const lat1 = lats[i + 1];

      for (let j = 0; j < cols - 1; j++) {
        const lon0 = lons[j];
        const lon1 = lons[j + 1];

        const z0 = grid[i][j];         // Top-Left
        const z1 = grid[i][j + 1];     // Top-Right
        const z2 = grid[i + 1][j + 1]; // Bottom-Right
        const z3 = grid[i + 1][j];     // Bottom-Left

        if (z0 === null || z1 === null || z2 === null || z3 === null ||
            isNaN(z0) || isNaN(z1) || isNaN(z2) || isNaN(z3)) {
          continue;
        }

        // Determinar índice binario de estado (0 a 15)
        let cellIndex = 0;
        if (z0 >= level) cellIndex |= 8;
        if (z1 >= level) cellIndex |= 4;
        if (z2 >= level) cellIndex |= 2;
        if (z3 >= level) cellIndex |= 1;

        if (cellIndex === 0 || cellIndex === 15) continue;

        // Interpolaciones lineales en los 4 bordes de la celda
        const t = (valA, valB) => {
          const denom = valB - valA;
          return Math.abs(denom) < 1e-6 ? 0.5 : (level - valA) / denom;
        };

        const top = [lat0, lon0 + t(z0, z1) * (lon1 - lon0)];
        const right = [lat0 + t(z1, z2) * (lat1 - lat0), lon1];
        const bottom = [lat1, lon0 + t(z3, z2) * (lon1 - lon0)];
        const left = [lat0 + t(z0, z3) * (lat1 - lat0), lon0];

        switch (cellIndex) {
          case 1: case 14: segments.push([left, bottom]); break;
          case 2: case 13: segments.push([bottom, right]); break;
          case 3: case 12: segments.push([left, right]); break;
          case 4: case 11: segments.push([top, right]); break;
          case 5:
            segments.push([left, top]);
            segments.push([bottom, right]);
            break;
          case 6: case 9: segments.push([top, bottom]); break;
          case 7: case 8: segments.push([left, top]); break;
          case 10:
            segments.push([top, right]);
            segments.push([left, bottom]);
            break;
        }
      }
    }

    return this.stitchSegments(segments);
  }

  /**
   * Conecta segmentos aislados en polilíneas continuas cerradas o abiertas
   */
  static stitchSegments(segments) {
    if (segments.length === 0) return [];

    const tolerance = 0.05;
    const polylines = [];
    const used = new Uint8Array(segments.length);

    for (let i = 0; i < segments.length; i++) {
      if (used[i]) continue;

      const poly = [segments[i][0], segments[i][1]];
      used[i] = 1;
      let extended = true;

      while (extended) {
        extended = false;
        const tail = poly[poly.length - 1];
        const head = poly[0];

        for (let j = 0; j < segments.length; j++) {
          if (used[j]) continue;
          const seg = segments[j];

          if (Math.hypot(tail[0] - seg[0][0], tail[1] - seg[0][1]) < tolerance) {
            poly.push(seg[1]);
            used[j] = 1;
            extended = true;
            break;
          } else if (Math.hypot(tail[0] - seg[1][0], tail[1] - seg[1][1]) < tolerance) {
            poly.push(seg[0]);
            used[j] = 1;
            extended = true;
            break;
          } else if (Math.hypot(head[0] - seg[1][0], head[1] - seg[1][1]) < tolerance) {
            poly.unshift(seg[0]);
            used[j] = 1;
            extended = true;
            break;
          } else if (Math.hypot(head[0] - seg[0][0], head[1] - seg[0][1]) < tolerance) {
            poly.unshift(seg[1]);
            used[j] = 1;
            extended = true;
            break;
          }
        }
      }

      if (poly.length >= 2) {
        polylines.push(poly);
      }
    }

    return polylines;
  }
}

// =============================================================================
// CLASE PRINCIPAL: DASHBOARD MAPS (PAR DINÁMICO V5.3)
// =============================================================================
class DashboardMaps {
  constructor() {
    this.pressureMap = null;
    this.anomalyMap = null;

    // Capas dinámicas
    this.isobarLayer = null;
    this.coreMarker = null;
    this.centroidMarker = null;
    this.decouplingLine = null;
    this.patagoniaBoxLayer = null;
    this.anomalyLayer = null;

    this.currentDate = null;
    this.currentModelId = null;
    this.pressureGridNotice = null;
    this.anomalyGridNotice = null;

    this.initMaps();
  }

  initMaps() {
    const defaultCenter = [-34.5, -95.0];
    const defaultZoom = 4;
    const minZoom = 3;
    const maxZoom = 9;

    const baseTileUrl = 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}';
    const tileOptions = {
      attribution: 'Esri, HERE, Garmin, © OpenStreetMap',
      subdomains: ['server', 'services'],
      minZoom,
      maxZoom
    };

    // 1. Inicializar Mapa 1: Presión e Isobaras
    this.pressureMap = L.map('pressureMap', {
      center: defaultCenter,
      zoom: defaultZoom,
      minZoom,
      maxZoom,
      zoomControl: true,
      preferCanvas: true
    });

    L.tileLayer(baseTileUrl, tileOptions).addTo(this.pressureMap);
    this.isobarLayer = L.layerGroup().addTo(this.pressureMap);
    this.patagoniaBoxLayer = L.layerGroup().addTo(this.pressureMap);
    this.pressureGridNotice = this.createGridNotice(this.pressureMap);

    // 2. Inicializar Mapa 2: Campo de Anomalías de Presión
    this.anomalyMap = L.map('anomalyMap', {
      center: defaultCenter,
      zoom: defaultZoom,
      minZoom,
      maxZoom,
      zoomControl: true,
      preferCanvas: true
    });

    L.tileLayer(baseTileUrl, tileOptions).addTo(this.anomalyMap);
    this.anomalyLayer = L.layerGroup().addTo(this.anomalyMap);
    this.anomalyGridNotice = this.createGridNotice(this.anomalyMap);

    // 3. Sincronizar encuadre y zoom bidireccional entre ambos mapas
    this.pressureMap.on('move', () => {
      this.anomalyMap.setView(this.pressureMap.getCenter(), this.pressureMap.getZoom(), { animate: false });
    });
    this.anomalyMap.on('move', () => {
      this.pressureMap.setView(this.anomalyMap.getCenter(), this.anomalyMap.getZoom(), { animate: false });
    });

    // 4. Agregar Graticule Geodésico y Referencias Costeras
    this.addGraticule(this.pressureMap);
    this.addGraticule(this.anomalyMap);
    this.addGeographicReferences(this.pressureMap);
    this.addGeographicReferences(this.anomalyMap);

    // 5. Renderizar Polígono Fijo de la Caja Norpatagonia
    this.renderPatagoniaBox();
  }

  createGridNotice(mapInstance) {
    const notice = L.control({ position: 'bottomleft' });
    notice.onAdd = () => {
      const div = L.DomUtil.create('div', 'map-grid-notice');
      div.textContent = 'Campo 2D no disponible para esta fecha/modelo';
      div.hidden = true;
      return div;
    };
    notice.addTo(mapInstance);
    return notice;
  }

  setGridNotice(control, visible) {
    if (!control) return;
    const container = control.getContainer();
    if (container) container.hidden = !visible;
  }

  isValidGrid(spatialGrid, dateStr, modelId) {
    if (!spatialGrid || !modelId || !dateStr) return false;
    if (spatialGrid.model_id !== modelId) return false;
    if (spatialGrid.date !== dateStr) return false;
    if (!Array.isArray(spatialGrid.lats) || !Array.isArray(spatialGrid.lons)) return false;
    if (!Array.isArray(spatialGrid.slp)) return false;
    return spatialGrid.lats.length >= 2 && spatialGrid.lons.length >= 2;
  }

  addGraticule(mapInstance) {
    const graticuleStyle = {
      color: 'rgba(255, 255, 255, 0.08)',
      weight: 1,
      dashArray: '3, 4',
      interactive: false
    };

    const lats = [-20, -30, -40, -50];
    const lons = [-70, -80, -90, -100, -110, -120];

    lats.forEach(lat => {
      L.polyline([[lat, -130], [lat, -65]], graticuleStyle).addTo(mapInstance);
      L.marker([lat, -125], {
        icon: L.divIcon({
          className: 'graticule-label',
          html: `${Math.abs(lat)}°S`,
          iconSize: [36, 12],
          iconAnchor: [18, 6]
        }),
        interactive: false
      }).addTo(mapInstance);
    });

    lons.forEach(lon => {
      L.polyline([[-10, lon], [-56, lon]], graticuleStyle).addTo(mapInstance);
      L.marker([-14, lon], {
        icon: L.divIcon({
          className: 'graticule-label',
          html: `${Math.abs(lon)}°W`,
          iconSize: [36, 12],
          iconAnchor: [18, 6]
        }),
        interactive: false
      }).addTo(mapInstance);
    });
  }

  addGeographicReferences(mapInstance) {
    const refPoints = [
      { name: 'Valparaíso', lat: -33.04, lon: -71.62 },
      { name: 'Antofagasta', lat: -23.65, lon: -70.40 },
      { name: 'Pto. Montt', lat: -41.47, lon: -72.94 },
      { name: 'Punta Arenas', lat: -53.16, lon: -70.91 },
      { name: 'I. de Pascua', lat: -27.11, lon: -109.35 },
      { name: 'I. Robinson Crusoe', lat: -33.64, lon: -78.83 }
    ];

    refPoints.forEach(p => {
      L.circleMarker([p.lat, p.lon], {
        radius: 3.5,
        color: '#60a5fa',
        fillColor: '#38bdf8',
        fillOpacity: 0.8,
        weight: 1.5,
        interactive: true
      })
      .bindTooltip(`📍 ${p.name}`, { permanent: false, direction: 'right', className: 'ref-point-tooltip' })
      .addTo(mapInstance);
    });
  }

  renderPatagoniaBox() {
    this.patagoniaBoxLayer.clearLayers();
    // Caja Norpatagonia: [-45°S, -41°S] x [-78°W, -72°W]
    const bounds = [[-45.0, -78.0], [-41.0, -72.0]];
    L.rectangle(bounds, {
      color: '#c084fc',
      weight: 1.8,
      dashArray: '5, 5',
      fillColor: '#a855f7',
      fillOpacity: 0.08
    })
    .bindTooltip(`<b>Caja Norpatagonia</b><br>[-45°S a -41°S, -78°W a -72°W]<br><small>Monitoreo de Bloqueos y Cuñas en Fiordos</small>`, {
      sticky: true,
      direction: 'top'
    })
    .addTo(this.patagoniaBoxLayer);
  }

  /**
   * Actualiza el Mapa de Presión con el Par Dinámico V5.3:
   * Núcleo Submalla (+), Centroide Adaptativo (◇), vector de desacople e isobara 1020 destacada.
   */
  updatePressureMap(coreLat, coreLon, maxPressure, centLat = null, centLon = null, dateStr = null, isForecast = false, spatialGrid = null, extraMetrics = {}, modelId = null) {
    this.isobarLayer.clearLayers();
    this.currentDate = dateStr;
    this.currentModelId = modelId;

    const cLat = Number.isFinite(centLat) ? centLat : coreLat;
    const cLon = Number.isFinite(centLon) ? centLon : coreLon;
    const hasCore = Number.isFinite(coreLat) &&
                    Number.isFinite(coreLon) &&
                    Number.isFinite(maxPressure);
    const hasCentroid = Number.isFinite(cLat) && Number.isFinite(cLon);

    // Etiquetas compartidas por ambos marcadores del Par Dinámico.
    // Deben declararse en el ámbito de la función: usarlas dentro de los
    // bloques if (hasCore) / if (hasCentroid) provocaba un ReferenceError
    // que abortaba el trazado de isóbaras y del mapa de anomalías.
    const forecastTag = isForecast ? `<span style="background: rgba(16, 185, 129, 0.2); color: #10b981; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: 700;">📡 PRONÓSTICO GFS</span><br>` : '';
    const dateNotice = dateStr ? `<div style="color: #64748b; font-size: 11px; margin-bottom: 3px;">Fecha: <b>${dateStr}</b></div>` : '';

    // 1. Vector Geodésico de Desacople Físico (Línea discontinua Núcleo - Centroide)
    const distKm = extraMetrics.dist_decoupling_km !== undefined ? extraMetrics.dist_decoupling_km : null;
    const azimuth = extraMetrics.azimuth_deg !== undefined ? extraMetrics.azimuth_deg : null;

    if (hasCore && hasCentroid &&
        (Math.abs(coreLat - cLat) > 0.05 || Math.abs(coreLon - cLon) > 0.05)) {
      const decouplingLine = L.polyline([[coreLat, coreLon], [cLat, cLon]], {
        color: '#f43f5e',
        weight: 2.5,
        dashArray: '6, 6',
        opacity: 0.95
      });

      let regimeLabel = 'Simetría Concéntrica';
      if (distKm && distKm >= 300) {
        if (azimuth >= 30 && azimuth < 120) regimeLabel = 'Cuña Costera (Chile Central)';
        else if (azimuth >= 120 && azimuth < 210) regimeLabel = 'Bloqueo Patagónico Austral';
        else regimeLabel = 'Elongación Oceánica';
      }

      decouplingLine.bindTooltip(`
        <b>Vector de Desacople Morfológico:</b><br>
        Distancia D<sub>nc</sub>: <b>${distKm ? distKm.toFixed(1) : '--'} km</b><br>
        Rumbo: <b>${azimuth ? azimuth.toFixed(1) : '--'}°</b><br>
        Régimen: <span style="color:#f43f5e; font-weight:700;">${regimeLabel}</span>
      `, { sticky: true, direction: 'top' });

      decouplingLine.addTo(this.isobarLayer);
    }

    // 2. Marcador 1: Núcleo Barométrico Continuo Submalla (+)
    if (hasCore) {
    const coreIcon = L.divIcon({
      className: 'aps-core-icon',
      html: `<div class="aps-core-marker" title="Núcleo Continuo (Submalla 2D)">+</div>`,
      iconSize: [22, 22],
      iconAnchor: [11, 11]
    });

    this.coreMarker = L.marker([coreLat, coreLon], { icon: coreIcon })
      .bindPopup(`
        <div style="font-family: Outfit, sans-serif; color: #080e1e; padding: 6px; font-size: 13px;">
          ${forecastTag}
          <strong style="color: #d97706; font-size: 14px;">Núcleo Barométrico Submalla (+)</strong><br>
          ${dateNotice}
          <b>Presión Máxima (P<sub>max</sub>):</b> ${maxPressure.toFixed(2)} hPa<br>
          <b>Vértice Continuo:</b> ${Math.abs(coreLat).toFixed(2)}°S, ${Math.abs(coreLon).toFixed(2)}°W<br>
          <span style="color: #64748b; font-size: 11px;">Cima continua calculada vía gradiente ∇P = 0 en ventana 5x5</span>
        </div>
      `)
      .addTo(this.isobarLayer);
    }

    // 3. Marcador 2: Centroide de Masa Barométrica Adaptativo (◇)
    if (hasCentroid) {
    const centroidIcon = L.divIcon({
      className: 'aps-centroid-icon',
      html: `<div class="aps-centroid-marker" title="Centroide de Masa (Adaptativo)"><span>◇</span></div>`,
      iconSize: [18, 18],
      iconAnchor: [9, 9]
    });

    this.centroidMarker = L.marker([cLat, cLon], { icon: centroidIcon })
      .bindPopup(`
        <div style="font-family: Outfit, sans-serif; color: #080e1e; padding: 6px; font-size: 13px;">
          <strong style="color: #0891b2; font-size: 14px;">Centroide Barométrico Adaptativo (◇)</strong><br>
          ${dateNotice}
          <b>Centro de Masa:</b> ${Math.abs(cLat).toFixed(2)}°S, ${Math.abs(cLon).toFixed(2)}°W<br>
          <b>Extensión A<sub>1020</sub>:</b> ${extraMetrics.area_1020 !== undefined ? extraMetrics.area_1020.toFixed(2) : '--'} M km²<br>
          <b>Volumen I<sub>vol</sub>:</b> ${extraMetrics.vol_integral !== undefined ? extraMetrics.vol_integral.toFixed(1) : '--'} hPa·M km²<br>
          <span style="color: #64748b; font-size: 11px;">Centro ponderado por sobrepresión con umbral adaptativo flotante</span>
        </div>
      `)
      .addTo(this.isobarLayer);
    }

    // 4. Trazado de Isobaras con Marching Squares 2D sobre campo real.
    // Sin coincidencia exacta model_id/date no se dibuja ninguna isóbara.
    const hasValidGrid = this.isValidGrid(spatialGrid, dateStr, modelId);
    const field = hasValidGrid
      ? { lats: spatialGrid.lats, lons: spatialGrid.lons, grid: spatialGrid.slp }
      : null;
    this.setGridNotice(this.pressureGridNotice, !hasValidGrid);

    const isobarConfig = [
      { p: 1028, color: '#f59e0b', weight: 2.4, dash: null, highlight: false },
      { p: 1024, color: '#00d2ff', weight: 2.0, dash: null, highlight: false },
      { p: 1020, color: '#f59e0b', weight: 3.2, dash: null, highlight: true }, // ISÓBARA CRÍTICA DESTACADA
      { p: 1016, color: '#0077b6', weight: 1.4, dash: '5, 4', highlight: false },
      { p: 1012, color: '#475569', weight: 1.1, dash: '3, 4', highlight: false }
    ];

    isobarConfig.forEach(iso => {
      if (!field || !Number.isFinite(maxPressure)) return;
      if (maxPressure >= iso.p - 1.5) {
        const polylines = MarchingSquares.contour(field.grid, field.lats, field.lons, iso.p);

        polylines.forEach((poly, polyIdx) => {
          if (poly.length < 3) return;

          const polylineObj = L.polyline(poly, {
            color: iso.color,
            weight: iso.weight,
            dashArray: iso.dash,
            opacity: iso.highlight ? 0.98 : 0.88,
            smoothFactor: 1.2
          });

          const tooltipText = iso.highlight ?
            `⭐ <b>Isóbara Crítica de 1020 hPa</b> (Límite del Domo Barométrico)` :
            `Isobara ${iso.p} hPa (Marching Squares)`;

          polylineObj.bindTooltip(tooltipText, { permanent: false, direction: 'top', sticky: true });
          polylineObj.addTo(this.isobarLayer);

          if (polyIdx === 0 && poly.length > 8) {
            const midPt = poly[Math.floor(poly.length / 2)];
            L.marker(midPt, {
              icon: L.divIcon({
                className: iso.highlight ? 'isobar-label-inline highlighted-1020' : 'isobar-label-inline',
                html: `${iso.p}`,
                iconSize: [28, 14],
                iconAnchor: [14, 7]
              }),
              interactive: false
            }).addTo(this.isobarLayer);
          }
        });
      }
    });

    // 5. Actualizar badge de coordenadas en cabecera del mapa
    const badge = document.getElementById('mapCenterCoordBadge');
    if (badge) {
      const datePrefix = dateStr ? `[${dateStr}] ` : '';
      const forecastLabel = isForecast ? '📡 GFS: ' : 'Par Dinámico: ';
      if (hasCore && hasCentroid) {
        badge.textContent = `${datePrefix}${forecastLabel}Núcleo ${Math.abs(coreLat).toFixed(1)}°S, ${Math.abs(coreLon).toFixed(1)}°W | Cent: ${Math.abs(cLat).toFixed(1)}°S, ${Math.abs(cLon).toFixed(1)}°W`;
      } else {
        badge.textContent = `${datePrefix}${forecastLabel}N/D`;
      }
    }
  }

  /**
   * Actualiza el Mapa de Anomalías Superficiales
   */
  updateAnomalyMap(spatialGrid, centerLat, centerLon, maxPressure, dateStr = null, modelId = null) {
    this.anomalyLayer.clearLayers();

    const hasValidGrid = this.isValidGrid(spatialGrid, dateStr, modelId);
    const hasAnomaly = hasValidGrid && Array.isArray(spatialGrid.anomaly);
    this.setGridNotice(this.anomalyGridNotice, !hasAnomaly);

    if (hasAnomaly) {
      const lats = spatialGrid.lats;
      const lons = spatialGrid.lons;
      const anomGrid = spatialGrid.anomaly;

      const levels = [-6, -4, -2, 2, 4, 6];
      levels.forEach(lvl => {
        const isPos = lvl > 0;
        const color = isPos ? (lvl >= 4 ? '#ef4444' : '#f97316') : (lvl <= -4 ? '#3b82f6' : '#06b6d4');
        const polylines = MarchingSquares.contour(anomGrid, lats, lons, lvl);

        polylines.forEach(poly => {
          if (poly.length < 3) return;
          L.polyline(poly, {
            color: color,
            weight: 1.8,
            dashArray: isPos ? null : '4, 4',
            opacity: 0.85
          })
          .bindTooltip(`Anomalía ${lvl > 0 ? '+' : ''}${lvl} hPa`, { sticky: true })
          .addTo(this.anomalyLayer);
        });
      });
    }

    // Marcador de referencia del centro solo con métricas finitas.
    if (Number.isFinite(centerLat) &&
        Number.isFinite(centerLon) &&
        Number.isFinite(maxPressure)) {
      L.circleMarker([centerLat, centerLon], {
        radius: 6,
        color: '#ffffff',
        fillColor: '#f59e0b',
        fillOpacity: 0.9,
        weight: 2
      })
      .bindTooltip(`Centro APS: ${maxPressure.toFixed(1)} hPa`)
      .addTo(this.anomalyLayer);
    }
  }
}
