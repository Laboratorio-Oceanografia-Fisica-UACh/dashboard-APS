/**
 * maps.js
 * Visualización geoespacial interactiva del APS, isobaras sinópticas reales
 * (Marching Squares en rejilla 2D) y dinámica de surgencia costera de Bakun (UI).
 * Capa cartográfica científica ESRI Canvas libre de marcas de agua, graticule geodésico
 * y georreferenciación costera de Chile, Perú e islas del Pacífico Suroriental.
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

    // 1. Recorrer cada celda cuadrangular
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

        let caseIndex = 0;
        if (z0 >= level) caseIndex |= 8;
        if (z1 >= level) caseIndex |= 4;
        if (z2 >= level) caseIndex |= 2;
        if (z3 >= level) caseIndex |= 1;

        if (caseIndex === 0 || caseIndex === 15) continue;

        // Puntos de cruce en las 4 aristas mediante interpolación lineal
        // Arista 0 (Top: z0 -> z1)
        const t0 = (level - z0) / (z1 - z0 || 1e-9);
        const pTop = [lat0, lon0 + t0 * (lon1 - lon0)];

        // Arista 1 (Right: z1 -> z2)
        const t1 = (level - z1) / (z2 - z1 || 1e-9);
        const pRight = [lat0 + t1 * (lat1 - lat0), lon1];

        // Arista 2 (Bottom: z3 -> z2)
        const t2 = (level - z3) / (z2 - z3 || 1e-9);
        const pBottom = [lat1, lon0 + t2 * (lon1 - lon0)];

        // Arista 3 (Left: z0 -> z3)
        const t3 = (level - z0) / (z3 - z0 || 1e-9);
        const pLeft = [lat0 + t3 * (lat1 - lat0), lon0];

        switch (caseIndex) {
          case 1:  segments.push([pLeft, pBottom]); break;
          case 2:  segments.push([pBottom, pRight]); break;
          case 3:  segments.push([pLeft, pRight]); break;
          case 4:  segments.push([pTop, pRight]); break;
          case 5:  segments.push([pTop, pLeft]); segments.push([pBottom, pRight]); break;
          case 6:  segments.push([pTop, pBottom]); break;
          case 7:  segments.push([pTop, pLeft]); break;
          case 8:  segments.push([pTop, pLeft]); break;
          case 9:  segments.push([pTop, pBottom]); break;
          case 10: segments.push([pTop, pRight]); segments.push([pLeft, pBottom]); break;
          case 11: segments.push([pTop, pRight]); break;
          case 12: segments.push([pLeft, pRight]); break;
          case 13: segments.push([pBottom, pRight]); break;
          case 14: segments.push([pLeft, pBottom]); break;
        }
      }
    }

    // 2. Encadenar segmentos adyacentes en polilíneas continuas
    return this.stitchSegments(segments);
  }

  static stitchSegments(segments) {
    if (segments.length === 0) return [];

    const polylines = [];
    const used = new Array(segments.length).fill(false);
    const eps = 0.08; // Tolerancia angular en grados (~8 km)

    for (let i = 0; i < segments.length; i++) {
      if (used[i]) continue;
      used[i] = true;

      const poly = [segments[i][0], segments[i][1]];
      let extended = true;

      while (extended) {
        extended = false;
        const tail = poly[poly.length - 1];
        const head = poly[0];

        for (let j = 0; j < segments.length; j++) {
          if (used[j]) continue;
          const [pA, pB] = segments[j];

          // Conexión a la cola
          if (Math.hypot(tail[0] - pA[0], tail[1] - pA[1]) < eps) {
            poly.push(pB);
            used[j] = true;
            extended = true;
            break;
          } else if (Math.hypot(tail[0] - pB[0], tail[1] - pB[1]) < eps) {
            poly.push(pA);
            used[j] = true;
            extended = true;
            break;
          }
          // Conexión a la cabeza
          else if (Math.hypot(head[0] - pB[0], head[1] - pB[1]) < eps) {
            poly.unshift(pA);
            used[j] = true;
            extended = true;
            break;
          } else if (Math.hypot(head[0] - pA[0], head[1] - pA[1]) < eps) {
            poly.unshift(pB);
            used[j] = true;
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
// CLASE PRINCIPAL: DASHBOARD MAPS
// =============================================================================
class DashboardMaps {
  constructor() {
    this.pressureMap = null;
    this.anomalyMap = null;
    this.centerMarker = null;
    this.anomalyCenterMarker = null;
    this.isobarLayer = null;
    this.upwellingLayer = null;
    this.anomalyLayer = null;
    this.currentDate = null;
    this.showUpwellingLayer = true;

    // 5 Estaciones costeras estratégicas de Chile para el Índice de Bakun UI
    this.coastalStations = [
      { id: 'arica', name: 'Arica', region: 'Norte Grande', coords: [-18.47, -70.31] },
      { id: 'antofagasta', name: 'Antofagasta (Mejillones)', region: 'Norte', coords: [-23.65, -70.40] },
      { id: 'valparaiso', name: 'Valparaíso (Curaumilla)', region: 'Chile Central', coords: [-33.04, -71.62] },
      { id: 'concepcion', name: 'Concepción (Arauco)', region: 'Centro-Sur', coords: [-36.82, -73.05] },
      { id: 'valdivia', name: 'Valdivia / Corral - Pto. Montt', region: 'Sur / Norpatagonia', coords: [-39.88, -73.40] }
    ];

    this.initMaps();
  }

  initMaps() {
    const initialView = [-34.0, -92.0];
    const initialZoom = 3.6;

    const baseTileUrl = 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}';
    const refTileUrl = 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}';
    const tileAttrib = '&copy; Esri, DeLorme, NAVTEQ | LOFA UACh';

    // 1. Mapa de Presión Atmosférica
    this.pressureMap = L.map('pressureMap', {
      zoomControl: true,
      attributionControl: false,
      minZoom: 3,
      maxZoom: 7
    }).setView(initialView, initialZoom);

    L.tileLayer(baseTileUrl, { maxZoom: 8, attribution: tileAttrib }).addTo(this.pressureMap);
    L.tileLayer(refTileUrl, { maxZoom: 8, opacity: 0.85 }).addTo(this.pressureMap);
    this.isobarLayer = L.layerGroup().addTo(this.pressureMap);
    this.upwellingLayer = L.layerGroup().addTo(this.pressureMap);

    // 2. Mapa de Anomalías
    this.anomalyMap = L.map('anomalyMap', {
      zoomControl: true,
      attributionControl: false,
      minZoom: 3,
      maxZoom: 7
    }).setView(initialView, initialZoom);

    L.tileLayer(baseTileUrl, { maxZoom: 8, attribution: tileAttrib }).addTo(this.anomalyMap);
    L.tileLayer(refTileUrl, { maxZoom: 8, opacity: 0.85 }).addTo(this.anomalyMap);
    this.anomalyLayer = L.layerGroup().addTo(this.anomalyMap);

    // Capas complementarias
    this.addCoordinateGraticule(this.pressureMap);
    this.addCoordinateGraticule(this.anomalyMap);

    this.addOceanographicLandmarks(this.pressureMap);
    this.addOceanographicLandmarks(this.anomalyMap);

    this.addAnomalyColorbar(this.anomalyMap);

    // Sincronización bidireccional de paneo y zoom
    this.pressureMap.on('move', () => {
      this.anomalyMap.setView(this.pressureMap.getCenter(), this.pressureMap.getZoom(), { animate: false });
    });
  }

  addCoordinateGraticule(mapInstance) {
    const graticuleGroup = L.layerGroup().addTo(mapInstance);

    const latitudes = [-15, -20, -25, -30, -35, -40, -45, -50, -55];
    latitudes.forEach(lat => {
      L.polyline([[lat, -135], [lat, -65]], {
        color: 'rgba(148, 163, 184, 0.22)',
        weight: 1,
        dashArray: '3, 4'
      }).addTo(graticuleGroup);

      L.marker([lat, -132], {
        icon: L.divIcon({
          className: 'graticule-label',
          html: `${Math.abs(lat)}°S`,
          iconSize: [36, 16],
          iconAnchor: [18, 8]
        }),
        interactive: false
      }).addTo(graticuleGroup);
    });

    const longitudes = [-130, -120, -110, -100, -90, -80, -70];
    longitudes.forEach(lon => {
      L.polyline([[-8, lon], [-58, lon]], {
        color: 'rgba(148, 163, 184, 0.22)',
        weight: 1,
        dashArray: '3, 4'
      }).addTo(graticuleGroup);

      L.marker([-10, lon], {
        icon: L.divIcon({
          className: 'graticule-label',
          html: `${Math.abs(lon)}°W`,
          iconSize: [42, 16],
          iconAnchor: [21, 8]
        }),
        interactive: false
      }).addTo(graticuleGroup);
    });
  }

  addOceanographicLandmarks(mapInstance) {
    const landmarks = [
      { name: 'Lima (Perú)', coords: [-12.04, -77.03], type: 'port' },
      { name: 'Arica', coords: [-18.47, -70.31], type: 'port' },
      { name: 'Antofagasta', coords: [-23.65, -70.40], type: 'port' },
      { name: 'Valparaíso', coords: [-33.04, -71.62], type: 'port' },
      { name: 'Concepción', coords: [-36.82, -73.05], type: 'port' },
      { name: 'Puerto Montt', coords: [-41.47, -72.94], type: 'port' },
      { name: 'Castro (Chiloé)', coords: [-42.48, -73.77], type: 'port' },
      { name: 'Golfo de Penas', coords: [-47.20, -75.00], type: 'oceanic' },
      { name: 'Punta Arenas (Magallanes)', coords: [-53.16, -70.91], type: 'port' },
      { name: 'Cabo de Hornos / Drake', coords: [-55.98, -67.27], type: 'oceanic' },
      { name: 'Archipiélago Juan Fernández', coords: [-33.64, -78.83], type: 'island' },
      { name: 'Rapa Nui (Isla de Pascua)', coords: [-27.12, -109.35], type: 'island' }
    ];

    landmarks.forEach(l => {
      const isIsland = l.type === 'island';
      const isOceanic = l.type === 'oceanic';
      const markerColor = isIsland ? '#00d2ff' : (isOceanic ? '#ec4899' : '#f59e0b');

      const marker = L.circleMarker(l.coords, {
        radius: isIsland ? 4.5 : (isOceanic ? 4.0 : 3.5),
        color: markerColor,
        fillColor: '#ffffff',
        fillOpacity: 0.95,
        weight: 1.5
      });

      const iconSymbol = isIsland ? '🏝️' : (isOceanic ? '🌊' : '⚓');
      marker.bindTooltip(`${iconSymbol} ${l.name}`, {
        direction: 'right',
        className: 'coastal-landmark',
        offset: [6, 0]
      });
      marker.addTo(mapInstance);
    });
  }

  addAnomalyColorbar(mapInstance) {
    const container = mapInstance.getContainer();
    const legend = document.createElement('div');
    legend.className = 'map-colorbar-legend';
    legend.innerHTML = `
      <div style="font-weight: 600; margin-bottom: 2px;">Anomalía de Presión (hPa)</div>
      <div class="colorbar-bar"></div>
      <div class="colorbar-labels">
        <span>-4 hPa</span>
        <span>0</span>
        <span>+4 hPa</span>
      </div>
    `;
    container.appendChild(legend);
  }

  toggleUpwellingLayer() {
    this.showUpwellingLayer = !this.showUpwellingLayer;
    if (this.showUpwellingLayer) {
      this.pressureMap.addLayer(this.upwellingLayer);
    } else {
      this.pressureMap.removeLayer(this.upwellingLayer);
    }
    return this.showUpwellingLayer;
  }

  /**
   * Genera el campo físico 2D de presión atmosférica (hPa) con deformaciones sinópticas realistas:
   * Cresta subtropical elongada NW-SE, compresión costera contra la Cordillera de los Andes
   * y gradiente polar de oestes (westerlies) en la Patagonia.
   */
  generateSynopticPressureGrid(centerLat, centerLon, maxPressure) {
    const lats = [];
    for (let lat = -10.0; lat >= -56.0; lat -= 0.5) lats.push(parseFloat(lat.toFixed(1)));
    const lons = [];
    for (let lon = -130.0; lon <= -65.0; lon += 0.5) lons.push(parseFloat(lon.toFixed(1)));

    const tiltRad = -0.314; // Inclinación sinóptica hacia la costa de Chile (-18°)
    const cosTilt = Math.cos(tiltRad);
    const sinTilt = Math.sin(tiltRad);

    const grid = [];
    for (let i = 0; i < lats.length; i++) {
      const row = [];
      const lat = lats[i];
      const radLat = lat * Math.PI / 180;
      const cosLat = Math.cos(radLat);

      // Fondo barométrico zonal-meridional (típico del Pacífico Suroriental)
      const pEnv = 1014.5 - 0.38 * (lat - (-32.0));

      for (let j = 0; j < lons.length; j++) {
        const lon = lons[j];

        // Desplazamientos geométricos respecto al núcleo bárico
        const dx = (lon - centerLon) * cosLat;
        const dy = (lat - centerLat);

        const xr = dx * cosTilt - dy * sinTilt;
        const yr = dx * sinTilt + dy * cosTilt;

        // Amplitud del domo anticiclónico
        const deltaCore = Math.max(0, maxPressure - pEnv);
        const gaussian = deltaCore * Math.exp(-(Math.pow(xr / 13.5, 2) + Math.pow(yr / 7.2, 2)) / 2.0);

        let pVal = pEnv + gaussian;

        // Efecto orográfico de la Cordillera de los Andes: Vaguada costera / compresión barométrica
        if (lon > -77.5) {
          const distToCoast = (lon - (-77.5)) / 5.5;
          pVal -= 1.35 * Math.pow(distToCoast, 2);
        }

        // Cinturón polar subantártico al sur de los 45°S (profundización de bajas presiones)
        if (lat < -45.0) {
          const distSouth = (lat - (-45.0));
          pVal -= 0.22 * Math.pow(distSouth, 2);
        }

        row.push(parseFloat(pVal.toFixed(2)));
      }
      grid.push(row);
    }

    return { lats, lons, grid };
  }

  /**
   * Actualiza el Mapa de Presión con curvas de nivel reales (Marching Squares)
   * y vectores de viento/surgencia costera de Bakun en Chile.
   */
  updatePressureMap(centerLat, centerLon, maxPressure, dateStr = null, isForecast = false, spatialGrid = null) {
    this.isobarLayer.clearLayers();
    this.upwellingLayer.clearLayers();
    this.currentDate = dateStr;

    // 1. Marcador Sinóptico del Núcleo Bárico ('A' con pulso ámbar o pronóstico GFS)
    const markerColor = isForecast ? '#10b981' : '#f59e0b';
    const markerSymbol = isForecast ? 'A<sub>GFS</sub>' : 'A';
    const centerIcon = L.divIcon({
      className: 'aps-synoptic-center',
      html: `
        <div style="
          width: 36px; 
          height: 36px; 
          background: ${isForecast ? 'rgba(16, 185, 129, 0.95)' : 'rgba(245, 158, 11, 0.95)'}; 
          border: 2px solid #ffffff; 
          border-radius: 50%; 
          box-shadow: 0 0 20px ${markerColor}, 0 0 40px rgba(0, 0, 0, 0.6);
          display: flex;
          align-items: center;
          justify-content: center;
          color: #0b1120;
          font-weight: 900;
          font-family: Outfit, sans-serif;
          font-size: 15px;
        ">${markerSymbol}</div>
      `,
      iconSize: [36, 36],
      iconAnchor: [18, 18]
    });

    const forecastTag = isForecast ? `<span style="background: rgba(16, 185, 129, 0.2); color: #10b981; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: 700;">📡 PRONÓSTICO OPERATIVO GFS</span><br>` : '';
    const dateNotice = dateStr ? `<div style="color: #64748b; font-size: 11px; margin-bottom: 3px;">Fecha: <b>${dateStr}</b></div>` : '';

    this.centerMarker = L.marker([centerLat, centerLon], { icon: centerIcon })
      .bindPopup(`
        <div style="font-family: Outfit, sans-serif; color: #080e1e; padding: 6px; font-size: 13px;">
          ${forecastTag}
          <strong style="color: #0284c7; font-size: 14px;">Núcleo Bárico del APS</strong><br>
          ${dateNotice}
          <b>Presión Central:</b> ${maxPressure.toFixed(1)} hPa<br>
          <b>Coordenadas:</b> ${Math.abs(centerLat).toFixed(2)}°S, ${Math.abs(centerLon).toFixed(2)}°W<br>
          <span style="color: #64748b; font-size: 11px;">Masa de aire subsidente subtropical/subantártica</span>
        </div>
      `)
      .addTo(this.isobarLayer);

    // 2. Trazado de Isobaras Reales mediante Marching Squares sobre la rejilla 2D
    // Si la rejilla coincide exactamente con la fecha activa la usamos; de lo contrario,
    // generamos el campo sinóptico físico dinámico dependiente de la posición y presión de la fecha activa
    let field = null;
    if (spatialGrid && spatialGrid.current_slp && spatialGrid.lats && spatialGrid.lons && spatialGrid.date && spatialGrid.date === dateStr) {
      field = { lats: spatialGrid.lats, lons: spatialGrid.lons, grid: spatialGrid.current_slp };
    } else {
      field = this.generateSynopticPressureGrid(centerLat, centerLon, maxPressure);
    }

    const isobarConfig = [
      { p: 1028, color: '#f59e0b', weight: 2.3, dash: null },
      { p: 1024, color: '#00d2ff', weight: 2.1, dash: null },
      { p: 1020, color: '#00b4d8', weight: 1.7, dash: '6, 5' },
      { p: 1016, color: '#0077b6', weight: 1.3, dash: '4, 4' },
      { p: 1012, color: '#475569', weight: 1.0, dash: '3, 5' }
    ];

    isobarConfig.forEach(iso => {
      if (maxPressure >= iso.p - 1.5) {
        const polylines = MarchingSquares.contour(field.grid, field.lats, field.lons, iso.p);

        polylines.forEach((poly, polyIdx) => {
          if (poly.length < 3) return;

          L.polyline(poly, {
            color: iso.color,
            weight: iso.weight,
            dashArray: iso.dash,
            opacity: 0.92,
            smoothFactor: 1.2
          })
          .bindTooltip(`Isobara ${iso.p} hPa (Marching Squares)`, { permanent: false, direction: 'top', sticky: true })
          .addTo(this.isobarLayer);

          // Etiqueta de la isobara en el punto medio de la línea
          if (polyIdx === 0 && poly.length > 8) {
            const midPt = poly[Math.floor(poly.length / 2)];
            L.marker(midPt, {
              icon: L.divIcon({
                className: 'isobar-label-inline',
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

    // 3. Renderizar Capa Dinámica de Vientos y Surgencia Costera (Bakun UI)
    const upwellingMetrics = this.calculateUpwellingMetrics(centerLat, centerLon, maxPressure, field);
    this.renderUpwellingLayer(upwellingMetrics);

    // 4. Actualizar badge de coordenadas en cabecera del mapa
    const badge = document.getElementById('mapCenterCoordBadge');
    if (badge) {
      const datePrefix = dateStr ? `[${dateStr}] ` : '';
      const forecastLabel = isForecast ? '📡 GFS: ' : 'Núcleo: ';
      badge.textContent = `${datePrefix}${forecastLabel}${Math.abs(centerLat).toFixed(1)}°S, ${Math.abs(centerLon).toFixed(1)}°W (${maxPressure.toFixed(1)} hPa)`;
    }

    return upwellingMetrics;
  }

  /**
   * Calcula el Índice de Surgencia de Bakun (UI) y viento geostrófico/superficial
   * para las 5 estaciones costeras clave en base al gradiente barométrico zonal.
   */
  calculateUpwellingMetrics(centerLat, centerLon, maxPressure, field) {
    const rhoAir = 1.225; // kg/m^3
    const rhoWater = 1025.0; // kg/m^3
    const Cd = 0.0013; // Coeficiente de arrastre (Large & Pond)
    const omega = 7.2921e-5; // rad/s rotación terrestre

    return this.coastalStations.map(st => {
      const [latSt, lonSt] = st.coords;
      const f = 2.0 * omega * Math.sin(latSt * Math.PI / 180); // Parámetro de Coriolis (< 0 en Hemisferio Sur)

      // Gradiente de presión zonal (costa vs 6° mar adentro)
      const lonOcean = lonSt - 6.0;
      const pCoast = this.sampleField(field, latSt, lonSt);
      const pOcean = this.sampleField(field, latSt, lonOcean);

      const deltaX = 6.0 * 111.0 * Math.cos(latSt * Math.PI / 180) * 1000; // Distancia en metros
      const dpDx = ((pCoast - pOcean) * 100.0) / (deltaX || 1.0); // Pa / metro

      // Viento geostrófico meridional (v_g = (1 / (rho_a * f)) * (dP / dx))
      // f < 0, cuando pOcean > pCoast -> dpDx < 0 -> v_g > 0 (viento del sur favorable a surgencia)
      const vg = (1.0 / (rhoAir * f)) * dpDx;

      // Viento a 10m en la capa límite atmosférica marina (factor de fricción ~0.75)
      const v10 = 0.75 * vg;
      const speedKnots = Math.abs(v10) * 1.94384;

      // Esfuerzo cortante del viento meridional (tau_y = rho_a * Cd * |V| * v_10)
      const tauY = rhoAir * Cd * Math.abs(v10) * v10;

      // Índice de Surgencia de Bakun (UI = tau_y / (rho_w * |f|) * 1000) [m^3 / (s * km de costa)]
      const ui = (tauY / (rhoWater * Math.abs(f))) * 1000.0;

      // Clasificación oceanográfica
      let statusClass = 'badge-ui-weak';
      let statusText = 'Débil / Neutro';
      let statusColor = '#94a3b8';

      if (ui > 600) {
        statusClass = 'badge-ui-intense';
        statusText = 'Muy Intensa (Chorro Costero)';
        statusColor = '#10b981';
      } else if (ui > 300) {
        statusClass = 'badge-ui-strong';
        statusText = 'Fuerte (AESS Favorable)';
        statusColor = '#00d2ff';
      } else if (ui > 80) {
        statusClass = 'badge-ui-moderate';
        statusText = 'Moderada';
        statusColor = '#f59e0b';
      } else if (ui < 0) {
        statusClass = 'badge-ui-downwelling';
        statusText = 'Hundimiento (Downwelling)';
        statusColor = '#c084fc';
      }

      return {
        id: st.id,
        name: st.name,
        region: st.region,
        coords: st.coords,
        pCoast: pCoast,
        pOcean: pOcean,
        dpDx: dpDx,
        v10: v10,
        speedKnots: speedKnots,
        tauY: tauY,
        ui: ui,
        statusText: statusText,
        statusClass: statusClass,
        statusColor: statusColor
      };
    });
  }

  sampleField(field, lat, lon) {
    if (!field || !field.grid) return 1018.0;
    const lats = field.lats;
    const lons = field.lons;

    // Encontrar índices más cercanos
    let i = lats.findIndex(l => l <= lat);
    if (i === -1) i = lats.length - 1;
    let j = lons.findIndex(l => l >= lon);
    if (j === -1) j = lons.length - 1;

    return field.grid[i] && field.grid[i][j] !== undefined ? field.grid[i][j] : 1018.0;
  }

  renderUpwellingLayer(metrics) {
    metrics.forEach(m => {
      // Flecha de viento: altura proporcional a la intensidad del viento
      const arrowHeight = Math.max(16, Math.min(48, Math.abs(m.v10) * 3.2));
      const isUpwelling = m.v10 >= 0; // Viento del sur -> sopla hacia el norte (arriba)
      const arrowRotation = isUpwelling ? 0 : 180; // Apunta arriba (norte) o abajo (sur)

      const markerHtml = `
        <div class="upwelling-map-marker" style="color: ${m.statusColor}; position: relative;">
          <div class="upwelling-dot" style="background: ${m.statusColor};"></div>
          <svg class="upwelling-wind-arrow-svg" width="20" height="${arrowHeight}" viewBox="0 0 20 ${arrowHeight}" style="position: absolute; bottom: 8px; transform: rotate(${arrowRotation}deg); transform-origin: bottom center;">
            <defs>
              <marker id="arrowhead-${m.id}" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto">
                <polygon points="0 0, 6 3, 0 6" fill="${m.statusColor}" />
              </marker>
            </defs>
            <line x1="10" y1="${arrowHeight}" x2="10" y2="4" stroke="${m.statusColor}" stroke-width="2.5" marker-end="url(#arrowhead-${m.id})" />
          </svg>
        </div>
      `;

      const marker = L.marker(m.coords, {
        icon: L.divIcon({
          className: 'upwelling-leaflet-icon',
          html: markerHtml,
          iconSize: [20, arrowHeight + 10],
          iconAnchor: [10, arrowHeight + 5]
        })
      });

      marker.bindPopup(`
        <div style="font-family: Outfit, sans-serif; font-size: 13px; color: #080e1e; padding: 4px; min-width: 200px;">
          <strong style="color: #0284c7; font-size: 14px;">⚓ ${m.name}</strong><br>
          <span style="color: #64748b; font-size: 11px;">${m.region} (${Math.abs(m.coords[0]).toFixed(1)}°S)</span>
          <hr style="margin: 6px 0; border: none; border-top: 1px solid #e2e8f0;">
          <b>Índice Bakun (UI):</b> <span style="color: ${m.statusColor}; font-weight: 700; font-family: monospace;">${m.ui > 0 ? '+' : ''}${m.ui.toFixed(0)} m³/(s·km)</span><br>
          <b>Estado:</b> <span class="badge-ui ${m.statusClass}">${m.statusText}</span><br>
          <b>Viento a 10m:</b> ${m.speedKnots.toFixed(1)} kt (${m.v10 >= 0 ? 'Sur / Favorable' : 'Norte / Desfavorable'})<br>
          <b>Esfuerzo \(\tau_y\):</b> ${m.tauY.toFixed(3)} N/m²<br>
          <b>Gradiente \(\partial P/\partial x\):</b> ${(m.dpDx * 1000).toFixed(2)} mPa/m
        </div>
      `);

      marker.addTo(this.upwellingLayer);
    });
  }

  /**
   * Actualiza el Mapa de Anomalías con la cuadrícula espacial y contorno del dominio extendido LOFA
   */
  updateAnomalyMap(centerLat, centerLon, spatialGrid, activeDate = null, climBaseline = 1022.0) {
    this.anomalyLayer.clearLayers();
    if (!spatialGrid || !spatialGrid.current_anomaly) return;

    const lats = spatialGrid.lats;
    const lons = spatialGrid.lons;
    const anomalies = spatialGrid.current_anomaly;

    const latStep = Math.abs(lats[1] - lats[0]);
    const lonStep = Math.abs(lons[1] - lons[0]);

    for (let i = 0; i < lats.length; i++) {
      for (let j = 0; j < lons.length; j++) {
        const val = anomalies[i][j];
        if (Math.abs(val) < 0.25) continue;

        const isPositive = val > 0;
        let color = isPositive ? '#ef4444' : '#00b4d8';
        if (val > 2.0) color = '#b91c1c';
        if (val < -2.0) color = '#0284c7';

        const opacity = Math.min(0.68, Math.max(0.20, Math.abs(val) / 3.8));

        const bounds = [
          [lats[i] - latStep / 2, lons[j] - lonStep / 2],
          [lats[i] + latStep / 2, lons[j] + lonStep / 2]
        ];

        L.rectangle(bounds, {
          color: color,
          fillColor: color,
          fillOpacity: opacity,
          weight: 0.3,
          opacity: 0.4
        })
        .bindTooltip(`
          <div style="font-family: Outfit, sans-serif; font-size: 11px;">
            <b>${Math.abs(lats[i]).toFixed(1)}°S, ${Math.abs(lons[j]).toFixed(1)}°W</b><br>
            <span style="color: ${isPositive ? '#f87171' : '#38bdf8'}; font-weight: 700;">
              Anomalía: ${val > 0 ? '+' : ''}${val.toFixed(2)} hPa
            </span>
          </div>
        `, {
          direction: 'top',
          sticky: true
        })
        .addTo(this.anomalyLayer);
      }
    }

    // Contorno oficial del dominio extendido de estudio de LOFA (10°S a 56°S y 130°W a 65°W)
    L.rectangle([[-56.0, -130.0], [-10.0, -65.0]], {
      color: '#00d2ff',
      weight: 1.5,
      dashArray: '5, 5',
      fill: false
    }).addTo(this.anomalyLayer);

    this.anomalyCenterMarker = L.circleMarker([centerLat, centerLon], {
      radius: 6,
      color: '#ffffff',
      fillColor: '#f59e0b',
      fillOpacity: 0.9,
      weight: 2
    }).bindTooltip(`Centro Bárico APS: ${Math.abs(centerLat).toFixed(1)}°S, ${Math.abs(centerLon).toFixed(1)}°W`, { direction: 'top' })
      .addTo(this.anomalyLayer);
  }
}
