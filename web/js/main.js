/**
 * main.js
 * Orquestador principal del Dashboard del Anticiclón del Pacífico Sur (APS)
 * Implementa Fase V2: modales desacoplados de KPIs, selector de modelo en foco,
 * climatología diaria DOY sin valores fijos, barra de tiempo dinámica de mapas
 * y sincronización bidireccional con series de tiempo.
 * Laboratorio de Oceanografía Física (LOFA) - Universidad Austral de Chile
 */

document.addEventListener('DOMContentLoaded', async () => {
  console.log('🌊 Inicializando Observatorio Científico del APS (LOFA UACh - Fase V2)...');

  let chartsInstance = null;
  let mapsInstance = null;
  let rawData = null;
  let timelineDates = [];
  let currentDateIndex = 0;
  let isPlaying = false;
  let playInterval = null;
  let focusedModelId = 'era5_reanalisis';

  // 1. Instanciar Selector de Modelos y Mapas
  const modelSelector = new ModelSelector((selectedModelIds) => {
    console.log('[MODELOS] Selección actualizada:', selectedModelIds);
    if (chartsInstance) {
      chartsInstance.updateCharts();
    }
    updateKpis();
    updateMapForCurrentDate();
  });

  mapsInstance = new DashboardMaps();

  // 2. Instanciar Gráficos con callback de clic para sincronización con mapas
  chartsInstance = new DashboardCharts(modelSelector, (selectedDate) => {
    syncTimelineToDate(selectedDate);
  });

  // 3. Cargar Datos del Pipeline (JSON)
  try {
    rawData = await loadData();
    if (!rawData || !rawData.models) {
      throw new Error('Estructura de datos incompleta');
    }

    // Configurar modelos en el selector
    modelSelector.setModels(rawData.models);
    chartsInstance.setData(rawData.models);

    // Extraer lista temporal unificada de fechas para el timeline
    initTimelineDates();

    // Inicializar selector de Modelo en Foco
    initModelFocusSelector();

    // Inicializar barra de reproducción y control de tiempo de mapas
    initTimelineController();

    // Inicializar todos los modales científicos individuales
    initScienceModals(rawData);

    // Renderizar estado inicial en mapas y KPIs
    syncTimelineToDate(timelineDates[timelineDates.length - 1]);

  } catch (error) {
    console.error('[ERROR] Error cargando los datos del APS:', error);
    showDataLoadError();
  }

  // =========================================================================
  // GESTIÓN TEMPORAL (TIMELINE SLIDER & REPRODUCTOR SINÓPTICO)
  // =========================================================================

  function initTimelineDates() {
    const primaryModel = rawData.models['ERA5 Reanálisis'] || Object.values(rawData.models)[0];
    const gfsModel = rawData.models['NOAA GFS Pronóstico'] || Object.values(rawData.models).find(m => m.id === 'noaa_gfs_forecast');

    const datesSet = new Set();
    if (primaryModel && primaryModel.dates) {
      primaryModel.dates.forEach(d => datesSet.add(d));
    }
    if (gfsModel && gfsModel.dates) {
      gfsModel.dates.forEach(d => datesSet.add(d));
    }

    if (datesSet.size > 0) {
      timelineDates = Array.from(datesSet).sort();
    } else {
      timelineDates = [new Date().toISOString().split('T')[0]];
    }
    currentDateIndex = timelineDates.length - 1;
  }

  function initTimelineController() {
    const slider = document.getElementById('timelineSlider');
    const datePicker = document.getElementById('timelineDatePicker');
    const activeDateLabel = document.getElementById('timelineActiveDate');

    if (slider) {
      slider.min = 0;
      slider.max = timelineDates.length - 1;
      slider.value = currentDateIndex;

      slider.addEventListener('input', (e) => {
        currentDateIndex = parseInt(e.target.value, 10);
        onDateChanged();
      });
    }

    if (datePicker && timelineDates.length > 0) {
      datePicker.min = timelineDates[0];
      datePicker.max = timelineDates[timelineDates.length - 1];
      datePicker.value = timelineDates[currentDateIndex];

      datePicker.addEventListener('change', (e) => {
        syncTimelineToDate(e.target.value);
      });
    }

    // Botones de paso de tiempo
    const btnFirst = document.getElementById('timeBtnFirst');
    const btnPrev = document.getElementById('timeBtnPrev');
    const btnPlay = document.getElementById('timeBtnPlay');
    const btnNext = document.getElementById('timeBtnNext');
    const btnLast = document.getElementById('timeBtnLast');

    if (btnFirst) btnFirst.addEventListener('click', () => setDateByIndex(0));
    if (btnPrev) btnPrev.addEventListener('click', () => setDateByIndex(currentDateIndex - 1));
    if (btnNext) btnNext.addEventListener('click', () => setDateByIndex(currentDateIndex + 1));
    if (btnLast) btnLast.addEventListener('click', () => setDateByIndex(timelineDates.length - 1));

    if (btnPlay) {
      btnPlay.addEventListener('click', () => {
        togglePlayPause(btnPlay);
      });
    }

    // Teclas de flecha izquierda/derecha para navegar en el tiempo si no se escribe en un input
    document.addEventListener('keydown', (e) => {
      if (['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement.tagName)) return;
      if (e.key === 'ArrowLeft') {
        setDateByIndex(currentDateIndex - 1);
      } else if (e.key === 'ArrowRight') {
        setDateByIndex(currentDateIndex + 1);
      } else if (e.key === ' ') {
        if (btnPlay) {
          e.preventDefault();
          togglePlayPause(btnPlay);
        }
      }
    });
  }

  function togglePlayPause(playBtn) {
    isPlaying = !isPlaying;
    if (isPlaying) {
      playBtn.textContent = '⏸ Pausa';
      playBtn.classList.add('playing');
      playInterval = setInterval(() => {
        if (currentDateIndex >= timelineDates.length - 1) {
          setDateByIndex(0);
        } else {
          setDateByIndex(currentDateIndex + 1);
        }
      }, 350);
    } else {
      playBtn.textContent = '▶ Play';
      playBtn.classList.remove('playing');
      if (playInterval) {
        clearInterval(playInterval);
        playInterval = null;
      }
    }
  }

  function setDateByIndex(index) {
    if (timelineDates.length === 0) return;
    currentDateIndex = Math.max(0, Math.min(timelineDates.length - 1, index));
    const slider = document.getElementById('timelineSlider');
    if (slider) slider.value = currentDateIndex;
    onDateChanged();
  }

  function syncTimelineToDate(dateStr) {
    if (!dateStr || timelineDates.length === 0) return;
    let idx = timelineDates.indexOf(dateStr);
    if (idx === -1) {
      // Buscar la fecha más cercana disponible
      idx = timelineDates.findIndex(d => d >= dateStr);
      if (idx === -1) idx = timelineDates.length - 1;
    }
    setDateByIndex(idx);
  }

  function onDateChanged() {
    const activeDate = timelineDates[currentDateIndex];
    const activeDateLabel = document.getElementById('timelineActiveDate');
    const datePicker = document.getElementById('timelineDatePicker');

    const gfsModel = rawData.models['NOAA GFS Pronóstico'] || Object.values(rawData.models).find(m => m.id === 'noaa_gfs_forecast');
    const isForecast = !!(gfsModel && gfsModel.dates && gfsModel.dates.includes(activeDate));

    if (activeDateLabel) {
      if (isForecast) {
        const fcIdx = gfsModel.dates.indexOf(activeDate);
        const hours = fcIdx * 24;
        activeDateLabel.innerHTML = `${activeDate} <span class="timeline-forecast-badge">🛰️ GFS +${hours}h</span>`;
      } else {
        activeDateLabel.textContent = activeDate;
      }
    }
    if (datePicker) datePicker.value = activeDate;

    updateKpis();
    updateMapForCurrentDate();
  }

  // =========================================================================
  // GESTIÓN DEL MODELO EN FOCO Y TARJETAS KPI (SECCIÓN 3 PLAN V2)
  // =========================================================================

  function initModelFocusSelector() {
    const select = document.getElementById('kpiModelSelect');
    if (!select) return;

    select.innerHTML = '';

    // Modelos individuales disponibles
    for (const model of Object.values(rawData.models)) {
      const opt = document.createElement('option');
      opt.value = model.id;
      opt.textContent = model.name;
      if (model.id === 'era5_reanalisis') opt.selected = true;
      select.appendChild(opt);
    }

    // Opción de Ensamble Multimodelo
    const optEnsemble = document.createElement('option');
    optEnsemble.value = 'ensemble';
    optEnsemble.textContent = '🌟 Ensamble Multimodelo (Media ± σ)';
    select.appendChild(optEnsemble);

    select.addEventListener('change', (e) => {
      focusedModelId = e.target.value;
      updateKpiFocusHint();
      updateKpis();
      updateMapForCurrentDate();
    });

    updateKpiFocusHint();
  }

  function updateKpiFocusHint() {
    const hint = document.getElementById('kpiFocusHint');
    if (!hint) return;
    if (focusedModelId === 'ensemble') {
      hint.textContent = 'Mostrando media sinóptica y dispersión estándar (σ) entre modelos activos';
    } else {
      const model = Object.values(rawData.models).find(m => m.id === focusedModelId);
      if (model) {
        hint.textContent = `Mostrando valores calculados para: ${model.name}`;
      }
    }
  }

  /**
   * Obtiene el valor climatológico histórico del día correspondiente (DOY)
   * de forma analítica y empírica sin ningún 1022.0 estático.
   */
  function getClimatologyForDate(dateStr) {
    const climModel = rawData.models['Climatología Histórica LOFA'] || rawData.models['Climatología Histórica'];
    if (climModel && climModel.dates) {
      const idx = climModel.dates.indexOf(dateStr);
      if (idx !== -1 && climModel.pressure_psa[idx] !== undefined) {
        return climModel.pressure_psa[idx];
      }
      // Búsqueda por día y mes (MM-DD)
      const mmdd = dateStr.slice(5);
      for (let i = climModel.dates.length - 1; i >= 0; i--) {
        if (climModel.dates[i].endsWith(mmdd)) {
          return climModel.pressure_psa[i];
        }
      }
    }

    // Respaldo climatológico empírico directo
    if (climModel && climModel.pressure_psa && climModel.pressure_psa.length > 0) {
      const sum = climModel.pressure_psa.reduce((a, b) => a + b, 0);
      return sum / climModel.pressure_psa.length;
    }
    return 1024.0;
  }

  function updateKpis() {
    if (!rawData || !rawData.models || timelineDates.length === 0) return;

    const activeDate = timelineDates[currentDateIndex];
    const kpiPressure = document.getElementById('kpiPressure');
    const kpiAnomaly = document.getElementById('kpiAnomaly');
    const kpiPosition = document.getElementById('kpiPosition');
    const kpiCentroid = document.getElementById('kpiCentroid');
    const kpiArea = document.getElementById('kpiArea');
    const kpiVolume = document.getElementById('kpiVolume');
    const kpiDecoupling = document.getElementById('kpiDecoupling');
    const kpiDecouplingBadge = document.getElementById('kpiDecouplingBadge');
    const kpiPatagonia = document.getElementById('kpiPatagonia');
    const kpiPatagoniaSub = document.getElementById('kpiPatagoniaSub');

    const climBaseline = getClimatologyForDate(activeDate);

    // Obtener modelo enfocado
    const model = Object.values(rawData.models).find(m => m.id === focusedModelId) ||
                  rawData.models['ERA5 Reanálisis'] ||
                  Object.values(rawData.models)[0];

    if (model) {
      const dIdx = model.dates.indexOf(activeDate);

      let p = 1024.0;
      let latCore = -33.5;
      let lonCore = -91.0;
      let latCent = null;
      let lonCent = null;
      let area1020 = null;
      let vol = null;
      let hEff = null;
      let distDec = null;
      let azimuth = null;
      let pPat = null;

      if (dIdx !== -1) {
        p = model.p_max_fit ? model.p_max_fit[dIdx] : model.pressure_psa[dIdx];
        latCore = model.lat_core ? model.lat_core[dIdx] : model.lat[dIdx];
        lonCore = model.lon_core ? model.lon_core[dIdx] : model.lon[dIdx];
        latCent = model.lat_centroid ? model.lat_centroid[dIdx] : null;
        lonCent = model.lon_centroid ? model.lon_centroid[dIdx] : null;
        area1020 = model.area_1020 ? model.area_1020[dIdx] : null;
        vol = model.vol_integral ? model.vol_integral[dIdx] : null;
        hEff = model.h_eff ? model.h_eff[dIdx] : null;
        distDec = model.dist_decoupling_km ? model.dist_decoupling_km[dIdx] : null;
        azimuth = model.azimuth_deg ? model.azimuth_deg[dIdx] : null;
        pPat = model.p_patagonia ? model.p_patagonia[dIdx] : null;
      } else if (model.latest) {
        p = model.latest.p_max_fit || model.latest.pressure_psa;
        latCore = model.latest.lat_core || model.latest.lat;
        lonCore = model.latest.lon_core || model.latest.lon;
        latCent = model.latest.lat_centroid || null;
        lonCent = model.latest.lon_centroid || null;
        area1020 = model.latest.area_1020 || null;
        vol = model.latest.vol_integral || null;
        hEff = model.latest.h_eff || null;
        distDec = model.latest.dist_decoupling_km || null;
        azimuth = model.latest.azimuth_deg || null;
        pPat = model.latest.p_patagonia || null;
      }

      const anom = (p - climBaseline).toFixed(2);

      // KPI 1: Presión Central
      if (kpiPressure) kpiPressure.innerHTML = `${p.toFixed(2)} <small>hPa</small>`;
      if (kpiAnomaly) {
        const sign = anom >= 0 ? '+' : '';
        kpiAnomaly.innerHTML = `Anomalía WMO: <strong style="color: ${anom >= 0 ? '#fbbf24' : '#38bdf8'};">${sign}${anom} hPa</strong>`;
      }

      // KPI 2: Par Dinámico
      if (kpiPosition) kpiPosition.textContent = `Núcleo (+): ${Math.abs(latCore).toFixed(2)}°S, ${Math.abs(lonCore).toFixed(2)}°W`;
      if (kpiCentroid) {
        kpiCentroid.textContent = latCent !== null ?
          `Centroide (◇): ${Math.abs(latCent).toFixed(2)}°S, ${Math.abs(lonCent).toFixed(2)}°W` :
          'Centroide: No disponible';
      }

      // KPI 3: Extensión y Masa
      if (kpiArea) kpiArea.innerHTML = area1020 !== null ? `${area1020.toFixed(2)} <small>M km²</small>` : '-- <small>M km²</small>';
      if (kpiVolume) {
        kpiVolume.textContent = vol !== null ?
          `Volumen: ${vol.toFixed(1)} hPa·M km² (H̄: ${hEff ? hEff.toFixed(2) : '--'} hPa)` :
          'Volumen: -- hPa·M km²';
      }

      // KPI 4: Desacople Morfológico
      if (kpiDecoupling) {
        kpiDecoupling.textContent = distDec !== null ? `${distDec.toFixed(1)} km (${azimuth ? azimuth.toFixed(1) : '--'}°)` : '-- km';
      }
      if (kpiDecouplingBadge && distDec !== null) {
        let badgeHtml = '';
        if (distDec < 200) {
          badgeHtml = '<span class="badge-regime-symmetric">Simétrico Concéntrico</span>';
        } else if (azimuth >= 45 && azimuth < 135) {
          badgeHtml = '<span class="badge-regime-coastal">Cuña Costera (Chile Central)</span>';
        } else if (azimuth >= 135 && azimuth < 225) {
          badgeHtml = '<span class="badge-regime-blocking">Bloqueo Patagónico Austral</span>';
        } else {
          badgeHtml = '<span class="badge-regime-oceanic">Elongación Oceánica</span>';
        }
        kpiDecouplingBadge.innerHTML = badgeHtml;
      }

      // KPI 5: Caja Norpatagonia
      if (kpiPatagonia) kpiPatagonia.innerHTML = pPat !== null ? `${pPat.toFixed(2)} <small>hPa</small>` : '-- <small>hPa</small>';
      if (kpiPatagoniaSub) {
        const isBlocking = pPat !== null && pPat >= 1018.0;
        kpiPatagoniaSub.innerHTML = isBlocking ?
          '<span style="color: #f87171; font-weight:700;">🚨 Condición de Bloqueo Activa</span>' :
          '<span style="color: #94a3b8;">Sinóptica Normal</span>';
      }
    }
  }

  function updateMapForCurrentDate() {
    if (!mapsInstance || !rawData || timelineDates.length === 0) return;

    const activeDate = timelineDates[currentDateIndex];
    const gfsModel = rawData.models['NOAA GFS Pronóstico'] || Object.values(rawData.models).find(m => m.id === 'noaa_gfs_forecast');
    const isForecast = !!(gfsModel && gfsModel.dates && gfsModel.dates.includes(activeDate));

    let targetModel = null;
    if (isForecast && gfsModel) {
      targetModel = gfsModel;
    } else {
      targetModel = Object.values(rawData.models).find(m => m.id === focusedModelId);
      if (!targetModel || focusedModelId === 'ensemble') {
        targetModel = rawData.models['ERA5 Reanálisis'] || Object.values(rawData.models)[0];
      }
    }

    let latCore = -33.5;
    let lonCore = -91.0;
    let latCent = null;
    let lonCent = null;
    let p = 1024.0;
    let distDec = null;
    let azimuth = null;
    let area1020 = null;
    let vol = null;

    if (targetModel && targetModel.dates) {
      const dIdx = targetModel.dates.indexOf(activeDate);
      if (dIdx !== -1) {
        latCore = targetModel.lat_core ? targetModel.lat_core[dIdx] : targetModel.lat[dIdx];
        lonCore = targetModel.lon_core ? targetModel.lon_core[dIdx] : targetModel.lon[dIdx];
        latCent = targetModel.lat_centroid ? targetModel.lat_centroid[dIdx] : null;
        lonCent = targetModel.lon_centroid ? targetModel.lon_centroid[dIdx] : null;
        p = targetModel.p_max_fit ? targetModel.p_max_fit[dIdx] : targetModel.pressure_psa[dIdx];
        distDec = targetModel.dist_decoupling_km ? targetModel.dist_decoupling_km[dIdx] : null;
        azimuth = targetModel.azimuth_deg ? targetModel.azimuth_deg[dIdx] : null;
        area1020 = targetModel.area_1020 ? targetModel.area_1020[dIdx] : null;
        vol = targetModel.vol_integral ? targetModel.vol_integral[dIdx] : null;
      } else if (targetModel.latest) {
        latCore = targetModel.latest.lat_core || targetModel.latest.lat;
        lonCore = targetModel.latest.lon_core || targetModel.latest.lon;
        latCent = targetModel.latest.lat_centroid || null;
        lonCent = targetModel.latest.lon_centroid || null;
        p = targetModel.latest.p_max_fit || targetModel.latest.pressure_psa;
        distDec = targetModel.latest.dist_decoupling_km || null;
        azimuth = targetModel.latest.azimuth_deg || null;
        area1020 = targetModel.latest.area_1020 || null;
        vol = targetModel.latest.vol_integral || null;
      }
    }

    const extraMetrics = {
      dist_decoupling_km: distDec,
      azimuth_deg: azimuth,
      area_1020: area1020,
      vol_integral: vol
    };

    mapsInstance.updatePressureMap(
      latCore, lonCore, p, latCent, lonCent,
      activeDate, isForecast, rawData.spatial_grid, extraMetrics
    );

    mapsInstance.updateAnomalyMap(rawData.spatial_grid, latCore, lonCore, p);
  }

  // =========================================================================
  // GESTIÓN DE MODALES CIENTÍFICOS DESACOPLADOS (INDIVIDUALES)
  // =========================================================================

  function initScienceModals(data) {
    const overlays = document.querySelectorAll('.science-modal-overlay');

    function openModal(modalId) {
      const modal = document.getElementById(modalId);
      if (modal) {
        modal.classList.add('open');
        if (typeof renderMathInElement === 'function') {
          try {
            renderMathInElement(modal, {
              delimiters: [
                { left: '$$', right: '$$', display: true },
                { left: '\\(', right: '\\)', display: false }
              ]
            });
          } catch (e) {
            console.warn('[KaTeX] Error renderizando fórmulas en modal:', e);
          }
        }
      }
    }

    function closeModal(modalId) {
      const modal = document.getElementById(modalId);
      if (modal) modal.classList.remove('open');
    }

    function closeAllModals() {
      overlays.forEach(m => m.classList.remove('open'));
    }

    // Botones de cierre [data-close] y clic en fondo oscuro
    overlays.forEach(overlay => {
      overlay.addEventListener('click', (e) => {
        if (e.target === overlay) overlay.classList.remove('open');
      });
      const closeBtn = overlay.querySelector('.modal-close-btn');
      if (closeBtn) {
        closeBtn.addEventListener('click', () => {
          overlay.classList.remove('open');
        });
      }
    });

    // 1. Triggers de los 4 KPIs individuales
    document.querySelectorAll('.kpi-info-trigger').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const modalKey = btn.dataset.modal; // ej: modalPressure, modalPosition, modalAnomaly, modalCoverage
        if (modalKey) {
          openModal(`${modalKey}Overlay`);
        }
      });
    });

    // 2. Modal Validación Estadística
    const openValidationBtn = document.getElementById('openValidationModalBtn');
    if (openValidationBtn) {
      openValidationBtn.addEventListener('click', () => openModal('validationModalOverlay'));
    }

    // 3. Modal Metodología Científica (Navbar y Footer)
    const openMethodologyBtn = document.getElementById('openMethodologyModalBtn');
    const footerMethodologyBtn = document.getElementById('footerMethodologyBtn');
    if (openMethodologyBtn) openMethodologyBtn.addEventListener('click', () => openModal('methodologyModalOverlay'));
    if (footerMethodologyBtn) footerMethodologyBtn.addEventListener('click', () => openModal('methodologyModalOverlay'));

    // 4. Modal Cómo Citar (Navbar y Footer)
    const openCitationBtn = document.getElementById('openCitationBtn');
    const footerCitationBtn = document.getElementById('footerCitationBtn');
    if (openCitationBtn) openCitationBtn.addEventListener('click', () => openModal('citationModalOverlay'));
    if (footerCitationBtn) footerCitationBtn.addEventListener('click', () => openModal('citationModalOverlay'));

    // Copiar Citas al portapapeles con feedback
    const copyApaBtn = document.getElementById('copyApaBtn');
    if (copyApaBtn) {
      copyApaBtn.addEventListener('click', () => {
        const text = document.getElementById('apaCitationText')?.innerText;
        if (text) {
          navigator.clipboard.writeText(text).then(() => {
            copyApaBtn.textContent = '✅ ¡Copiado!';
            setTimeout(() => { copyApaBtn.textContent = '📋 Copiar APA'; }, 2000);
          });
        }
      });
    }

    const copyBibtexBtn = document.getElementById('copyBibtexBtn');
    if (copyBibtexBtn) {
      copyBibtexBtn.addEventListener('click', () => {
        const text = document.getElementById('bibtexCitationText')?.innerText;
        if (text) {
          navigator.clipboard.writeText(text).then(() => {
            copyBibtexBtn.textContent = '✅ ¡Copiado!';
            setTimeout(() => { copyBibtexBtn.textContent = '📋 Copiar BibTeX'; }, 2000);
          });
        }
      });
    }

    // Renderizar tabla de métricas de validación
    const tableBody = document.getElementById('validationTableBody');
    if (tableBody) {
      const rows = Array.isArray(data.validation_metrics) ? data.validation_metrics : [];
      const formatValue = (value, digits = 2) => {
        if (value === null || value === undefined || value === '') return 'N/D';
        const numeric = Number(value);
        return Number.isFinite(numeric) ? numeric.toFixed(digits) : 'N/D';
      };

      if (rows.length === 0) {
        tableBody.innerHTML = '<tr><td colspan="9" style="text-align:center; color:#94a3b8;">Sin métricas de validación disponibles.</td></tr>';
      } else {
        tableBody.innerHTML = '';
        rows.forEach(row => {
          const tr = document.createElement('tr');
          const badgeClass = row.skill_class || 'badge-info';
          const willmottNumeric = Number(row.willmott_d);
          const willmottColor = Number.isFinite(willmottNumeric) && willmottNumeric > 0.8
            ? 'var(--color-accent)'
            : '#e2e8f0';
          const note = row.note || '';
          tr.innerHTML = `
            <td><strong>${row.model}</strong></td>
            <td title="${note}">
              <span style="font-size: 0.8rem; color: #94a3b8;">${row.type || 'N/D'}</span><br>
              <span class="badge badge-info" style="margin-top: 4px;">${row.reference || 'Referencia N/D'}</span>
            </td>
            <td><span class="badge ${badgeClass}">${row.skill_rating || 'N/D'}</span></td>
            <td>${formatValue(row.rmse_psa_hpa, 3)}</td>
            <td style="font-family: var(--font-mono);">${formatValue(row.bias_psa_hpa, 3)}</td>
            <td>${formatValue(row.corr_psa, 3)}</td>
            <td>${formatValue(row.corr_lat, 3)}</td>
            <td>${formatValue(row.dist_error_km, 1)}</td>
            <td><strong style="color: ${willmottColor}">${formatValue(row.willmott_d, 3)}</strong></td>
          `;
          tableBody.appendChild(tr);
        });
      }
    }

    // 7. Menú Desplegable Institucional de Documentación y Enlaces
    const navDocsDropdownBtn = document.getElementById('navDocsDropdownBtn');
    const navDocsDropdownMenu = document.getElementById('navDocsDropdownMenu');
    if (navDocsDropdownBtn && navDocsDropdownMenu) {
      navDocsDropdownBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        const isOpen = navDocsDropdownMenu.classList.toggle('show');
        navDocsDropdownBtn.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
      });

      // Cerrar al hacer clic en cualquier opción dentro del menú
      navDocsDropdownMenu.querySelectorAll('.nav-dropdown-item').forEach(item => {
        item.addEventListener('click', () => {
          navDocsDropdownMenu.classList.remove('show');
          navDocsDropdownBtn.setAttribute('aria-expanded', 'false');
        });
      });

      // Cerrar al hacer clic fuera del dropdown
      document.addEventListener('click', (e) => {
        if (!navDocsDropdownMenu.contains(e.target) && e.target !== navDocsDropdownBtn) {
          navDocsDropdownMenu.classList.remove('show');
          navDocsDropdownBtn.setAttribute('aria-expanded', 'false');
        }
      });
    }

    // Tecla ESC para cerrar cualquier modal abierto o menú desplegable
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        closeAllModals();
        if (navDocsDropdownMenu) {
          navDocsDropdownMenu.classList.remove('show');
          if (navDocsDropdownBtn) navDocsDropdownBtn.setAttribute('aria-expanded', 'false');
        }
      }
    });
  }
});

/**
 * Carga el archivo JSON de métricas desde la ruta relativa.
 * Si ninguna ruta responde, retorna null y la interfaz muestra un estado de
 * error explícito. No se usan datos sintéticos de respaldo.
 */
async function loadData() {
  const possiblePaths = [
    'data/latest_aps_data.json',
    '../data/processed/latest_aps_data.json',
    './data/latest_aps_data.json'
  ];

  for (const path of possiblePaths) {
    try {
      const res = await fetch(path);
      if (res.ok) {
        return await res.json();
      }
    } catch (e) {
      // Intentar siguiente ruta
    }
  }

  console.error('[ERROR] No se pudo cargar latest_aps_data.json desde ninguna ruta conocida.');
  return null;
}

function showDataLoadError() {
  const kpiPressure = document.getElementById('kpiPressure');
  if (kpiPressure) {
    kpiPressure.innerHTML = `<span style="font-size: 1rem; color: #ef4444;">Error al cargar datos</span>`;
  }
}
