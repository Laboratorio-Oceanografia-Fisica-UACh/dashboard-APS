/**
 * maps.js
 * Visualización geoespacial interactiva del APS y anomalías con Leaflet.js
 * Capa cartográfica científica libre de marcas de agua, con rejilla de coordenadas (Graticule)
 * y georreferenciación costera de Chile, Perú e islas del Pacífico Sur.
 * Laboratorio de Oceanografía Física (LOFA) - UACh
 */

class DashboardMaps {
  constructor() {
    this.pressureMap = null;
    this.anomalyMap = null;
    this.centerMarker = null;
    this.isobarLayer = null;
    this.anomalyLayer = null;

    this.initMaps();
  }

  initMaps() {
    // Vista inicial centrada en el Pacífico Suroriental y la costa chilena
    const initialView = [-32.0, -88.0];
    const initialZoom = 3.6;

    // Servidor de teselas cartográficas ESRI Dark Gray Canvas (Cero marcas de agua, libre y de alta definición)
    const baseTileUrl = 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}';
    const refTileUrl = 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}';
    const tileAttrib = '&copy; Esri, DeLorme, NAVTEQ | LOFA UACh';

    // 1. Inicializar Mapa de Presión Atmosférica
    this.pressureMap = L.map('pressureMap', {
      zoomControl: true,
      attributionControl: false,
      minZoom: 3,
      maxZoom: 7
    }).setView(initialView, initialZoom);

    L.tileLayer(baseTileUrl, { maxZoom: 8, attribution: tileAttrib }).addTo(this.pressureMap);
    L.tileLayer(refTileUrl, { maxZoom: 8, opacity: 0.85 }).addTo(this.pressureMap);
    this.isobarLayer = L.layerGroup().addTo(this.pressureMap);

    // 2. Inicializar Mapa de Anomalías
    this.anomalyMap = L.map('anomalyMap', {
      zoomControl: true,
      attributionControl: false,
      minZoom: 3,
      maxZoom: 7
    }).setView(initialView, initialZoom);

    L.tileLayer(baseTileUrl, { maxZoom: 8, attribution: tileAttrib }).addTo(this.anomalyMap);
    L.tileLayer(refTileUrl, { maxZoom: 8, opacity: 0.85 }).addTo(this.anomalyMap);
    this.anomalyLayer = L.layerGroup().addTo(this.anomalyMap);

    // Agregar Rejilla Geográfica de Coordenadas (Graticule) a ambos mapas
    this.addCoordinateGraticule(this.pressureMap);
    this.addCoordinateGraticule(this.anomalyMap);

    // Agregar Referencias Costeras e Islas Oceánicas
    this.addOceanographicLandmarks(this.pressureMap);
    this.addOceanographicLandmarks(this.anomalyMap);

    // Agregar Leyenda Colorbar al Mapa de Anomalías
    this.addAnomalyColorbar(this.anomalyMap);

    // Sincronizar paneo y zoom entre mapas
    this.pressureMap.on('move', () => {
      this.anomalyMap.setView(this.pressureMap.getCenter(), this.pressureMap.getZoom(), { animate: false });
    });
  }

  /**
   * Dibuja líneas de meridianos y paralelos con etiquetas visibles
   */
  addCoordinateGraticule(mapInstance) {
    const graticuleGroup = L.layerGroup().addTo(mapInstance);

    // Paralelos (Latitudes de 10°S a 50°S cada 5°)
    const latitudes = [-15, -20, -25, -30, -35, -40, -45, -50];
    latitudes.forEach(lat => {
      L.polyline([[lat, -135], [lat, -65]], {
        color: 'rgba(148, 163, 184, 0.25)',
        weight: 1,
        dashArray: '3, 4'
      }).addTo(graticuleGroup);

      // Etiqueta fija en el borde oeste
      L.marker([lat, -125], {
        icon: L.divIcon({
          className: 'graticule-label',
          html: `${Math.abs(lat)}°S`,
          iconSize: [36, 16],
          iconAnchor: [18, 8]
        }),
        interactive: false
      }).addTo(graticuleGroup);
    });

    // Meridianos (Longitudes de 120°W a 70°W cada 10°)
    const longitudes = [-120, -110, -100, -90, -80, -70];
    longitudes.forEach(lon => {
      L.polyline([[-8, lon], [-52, lon]], {
        color: 'rgba(148, 163, 184, 0.25)',
        weight: 1,
        dashArray: '3, 4'
      }).addTo(graticuleGroup);

      // Etiqueta fija en el borde norte
      L.marker([-11, lon], {
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

  /**
   * Puntos de referencia geográfica, puertos costeros e islas oceánicas
   */
  addOceanographicLandmarks(mapInstance) {
    const landmarks = [
      { name: 'Lima (Perú)', coords: [-12.04, -77.03], type: 'port' },
      { name: 'Arica', coords: [-18.47, -70.31], type: 'port' },
      { name: 'Antofagasta', coords: [-23.65, -70.40], type: 'port' },
      { name: 'Valparaíso', coords: [-33.04, -71.62], type: 'port' },
      { name: 'Concepción', coords: [-36.82, -73.05], type: 'port' },
      { name: 'Puerto Montt', coords: [-41.47, -72.94], type: 'port' },
      { name: 'Archipiélago Juan Fernández', coords: [-33.64, -78.83], type: 'island' },
      { name: 'Rapa Nui (Isla de Pascua)', coords: [-27.12, -109.35], type: 'island' }
    ];

    landmarks.forEach(l => {
      const isIsland = l.type === 'island';
      const marker = L.circleMarker(l.coords, {
        radius: isIsland ? 4.5 : 3.5,
        color: isIsland ? '#00d2ff' : '#f59e0b',
        fillColor: '#ffffff',
        fillOpacity: 0.95,
        weight: 1.5
      });
      marker.bindTooltip(`${isIsland ? '🏝️' : '⚓'} ${l.name}`, {
        direction: 'right',
        className: 'coastal-landmark',
        offset: [6, 0]
      });
      marker.addTo(mapInstance);
    });
  }

  /**
   * Añade la barra de escala cromática (Colorbar) al mapa de anomalías
   */
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

  updatePressureMap(centerLat, centerLon, maxPressure) {
    this.isobarLayer.clearLayers();

    // Marcador Sinóptico del Núcleo Bárico del Anticiclón (Símbolo 'A' con pulso ámbar)
    const centerIcon = L.divIcon({
      className: 'aps-synoptic-center',
      html: `
        <div style="
          width: 32px; 
          height: 32px; 
          background: rgba(245, 158, 11, 0.95); 
          border: 2px solid #ffffff; 
          border-radius: 50%; 
          box-shadow: 0 0 20px #f59e0b, 0 0 40px rgba(245, 158, 11, 0.5);
          display: flex;
          align-items: center;
          justify-content: center;
          color: #0b1120;
          font-weight: 900;
          font-family: Outfit, sans-serif;
          font-size: 16px;
        ">A</div>
      `,
      iconSize: [32, 32],
      iconAnchor: [16, 16]
    });

    this.centerMarker = L.marker([centerLat, centerLon], { icon: centerIcon })
      .bindPopup(`
        <div style="font-family: Outfit, sans-serif; color: #080e1e; padding: 6px; font-size: 13px;">
          <strong style="color: #0284c7; font-size: 14px;">Núcleo Bárico del APS</strong><br>
          <b>Presión Central:</b> ${maxPressure} hPa<br>
          <b>Coordenadas:</b> ${Math.abs(centerLat).toFixed(2)}°S, ${Math.abs(centerLon).toFixed(2)}°W<br>
          <span style="color: #64748b; font-size: 11px;">Masa de aire subsidente subtropical</span>
        </div>
      `)
      .addTo(this.isobarLayer);

    // Isobaras sinópticas realistas (1028, 1024, 1020, 1016, 1012 hPa) con elipses meridionales
    const isobarLevels = [
      { p: 1028, rLat: 3.2, rLon: 5.5, color: '#f59e0b', weight: 2.2, dash: 'solid' },
      { p: 1024, rLat: 6.8, rLon: 11.5, color: '#00d2ff', weight: 2.0, dash: 'solid' },
      { p: 1020, rLat: 11.0, rLon: 18.0, color: '#00b4d8', weight: 1.6, dash: '5, 5' },
      { p: 1016, rLat: 15.5, rLon: 25.0, color: '#0077b6', weight: 1.2, dash: '4, 4' },
      { p: 1012, rLat: 20.0, rLon: 32.0, color: '#475569', weight: 1.0, dash: '3, 5' }
    ];

    isobarLevels.forEach(iso => {
      if (maxPressure >= iso.p - 1.2) {
        // Generar puntos para elipse meteorológica realista orientada NW-SE
        const points = [];
        const numPoints = 64;
        const tiltRad = -0.22; // Inclinación sinóptica hacia la costa de Chile central
        
        for (let i = 0; i <= numPoints; i++) {
          const theta = (i / numPoints) * 2 * Math.PI;
          const x0 = iso.rLon * Math.cos(theta);
          const y0 = iso.rLat * Math.sin(theta);
          
          const x = x0 * Math.cos(tiltRad) - y0 * Math.sin(tiltRad);
          const y = x0 * Math.sin(tiltRad) + y0 * Math.cos(tiltRad);
          
          points.push([centerLat + y, centerLon + x]);
        }

        L.polyline(points, {
          color: iso.color,
          weight: iso.weight,
          dashArray: iso.dash,
          opacity: 0.9
        })
        .bindTooltip(`Isobara ${iso.p} hPa`, { permanent: false, direction: 'top', sticky: true })
        .addTo(this.isobarLayer);

        // Etiqueta de la isobara en el flanco oceánico
        const labelLat = centerLat + iso.rLat * Math.sin(Math.PI * 0.75);
        const labelLon = centerLon - iso.rLon * Math.cos(Math.PI * 0.75);
        L.marker([labelLat, labelLon], {
          icon: L.divIcon({
            className: 'graticule-label',
            html: `${iso.p}`,
            iconSize: [32, 14],
            iconAnchor: [16, 7]
          }),
          interactive: false
        }).addTo(this.isobarLayer);
      }
    });

    const badge = document.getElementById('mapCenterCoordBadge');
    if (badge) {
      badge.textContent = `Núcleo: ${Math.abs(centerLat).toFixed(1)}°S, ${Math.abs(centerLon).toFixed(1)}°W (${maxPressure} hPa)`;
    }
  }

  updateAnomalyMap(centerLat, centerLon, spatialGrid) {
    this.anomalyLayer.clearLayers();
    if (!spatialGrid || !spatialGrid.current_anomaly) return;

    const lats = spatialGrid.lats;
    const lons = spatialGrid.lons;
    const anomalies = spatialGrid.current_anomaly;

    // Dibujar celdas oceánicas de anomalía discretas y legibles
    const latStep = Math.abs(lats[1] - lats[0]);
    const lonStep = Math.abs(lons[1] - lons[0]);

    for (let i = 0; i < lats.length; i++) {
      for (let j = 0; j < lons.length; j++) {
        const val = anomalies[i][j];
        if (Math.abs(val) < 0.25) continue; // Descartar neutros para legibilidad

        // Mapear color: gradiente suave de azul a rojo según valor
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

    // Contorno del dominio de estudio del APS
    L.rectangle([[-48.0, -120.0], [-10.0, -70.0]], {
      color: '#00d2ff',
      weight: 1.5,
      dashArray: '5, 5',
      fill: false
    }).addTo(this.anomalyLayer);
  }
}
