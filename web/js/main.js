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
    if (primaryModel && primaryModel.dates && primaryModel.dates.length > 0) {
      timelineDates = primaryModel.dates;
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

    if (activeDateLabel) activeDateLabel.textContent = activeDate;
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

    // Modelo estacional físico de respaldo (DOY):
    const dt = new Date(dateStr);
    const startYear = new Date(dt.getFullYear(), 0, 1);
    const doy = Math.floor((dt - startYear) / (24 * 3600 * 1000)) + 1;
    // Ciclo anual del APS en el Pacífico Suroriental: media 1023.2 hPa, pico estival en febrero
    return 1023.2 + 2.8 * Math.cos(2 * Math.PI * (doy - 45) / 365.25);
  }

  function updateKpis() {
    if (!rawData || !rawData.models || timelineDates.length === 0) return;

    const activeDate = timelineDates[currentDateIndex];
    const kpiPressure = document.getElementById('kpiPressure');
    const kpiPosition = document.getElementById('kpiPosition');
    const kpiAnomaly = document.getElementById('kpiAnomaly');
    const kpiDate = document.getElementById('kpiDate');
    const kpiModelFocus = document.getElementById('kpiModelFocus');
    const kpiAnomalySub = document.getElementById('kpiAnomalySub');
    const kpiDateSub = document.getElementById('kpiDateSub');

    const climBaseline = getClimatologyForDate(activeDate);

    if (focusedModelId === 'ensemble') {
      // Modo Ensamble Multimodelo: calcular media y dispersión inter-modelo
      const selectedIds = modelSelector.getSelectedModelIds();
      const pVals = [];
      const latVals = [];
      const lonVals = [];

      for (const model of Object.values(rawData.models)) {
        if (!selectedIds.includes(model.id)) continue;
        const dIdx = model.dates.indexOf(activeDate);
        if (dIdx !== -1) {
          pVals.push(model.pressure_psa[dIdx]);
          latVals.push(model.lat[dIdx]);
          lonVals.push(model.lon[dIdx]);
        }
      }

      if (pVals.length > 0) {
        const meanP = pVals.reduce((a, b) => a + b, 0) / pVals.length;
        const meanLat = latVals.reduce((a, b) => a + b, 0) / latVals.length;
        const meanLon = lonVals.reduce((a, b) => a + b, 0) / lonVals.length;

        // Desviación estándar barométrica
        const stdP = Math.sqrt(pVals.reduce((acc, v) => acc + Math.pow(v - meanP, 2), 0) / pVals.length);
        const anomaly = (meanP - climBaseline).toFixed(1);

        if (kpiPressure) kpiPressure.innerHTML = `${meanP.toFixed(1)} <small>± ${stdP.toFixed(1)} hPa</small>`;
        if (kpiPosition) kpiPosition.textContent = `${Math.abs(meanLat).toFixed(1)}°S, ${Math.abs(meanLon).toFixed(1)}°W`;
        if (kpiAnomaly) {
          const sign = anomaly > 0 ? '+' : '';
          kpiAnomaly.innerHTML = `${sign}${anomaly} <small>hPa</small>`;
          kpiAnomaly.style.color = anomaly >= 0 ? 'var(--color-gold)' : 'var(--color-accent)';
        }
        if (kpiModelFocus) kpiModelFocus.textContent = `Ensamble de ${pVals.length} modelos activos`;
      }
    } else {
      // Modelo Individual en Foco
      const model = Object.values(rawData.models).find(m => m.id === focusedModelId) || Object.values(rawData.models)[0];
      if (model) {
        let p = 1024.0;
        let lat = -33.0;
        let lon = -90.0;

        const dIdx = model.dates.indexOf(activeDate);
        if (dIdx !== -1) {
          p = model.pressure_psa[dIdx];
          lat = model.lat[dIdx];
          lon = model.lon[dIdx];
        } else if (model.latest) {
          p = model.latest.pressure_psa;
          lat = model.latest.lat;
          lon = model.latest.lon;
        }

        const anomaly = (p - climBaseline).toFixed(1);

        if (kpiPressure) kpiPressure.innerHTML = `${p.toFixed(1)} <small>hPa</small>`;
        if (kpiPosition) kpiPosition.textContent = `${Math.abs(lat).toFixed(1)}°S, ${Math.abs(lon).toFixed(1)}°W`;
        if (kpiAnomaly) {
          const sign = anomaly > 0 ? '+' : '';
          kpiAnomaly.innerHTML = `${sign}${anomaly} <small>hPa</small>`;
          kpiAnomaly.style.color = anomaly >= 0 ? 'var(--color-gold)' : 'var(--color-accent)';
        }
        if (kpiModelFocus) kpiModelFocus.textContent = `Modelo: ${model.name}`;
      }
    }

    if (kpiDate) kpiDate.textContent = activeDate;
    if (kpiAnomalySub) kpiAnomalySub.textContent = `Respecto a normal climática (${climBaseline.toFixed(1)} hPa)`;
    if (kpiDateSub && rawData.metadata && rawData.metadata.time_coverage) {
      kpiDateSub.textContent = `Registro: ${rawData.metadata.time_coverage.start} a ${rawData.metadata.time_coverage.end}`;
    }
  }

  function updateMapForCurrentDate() {
    if (!mapsInstance || !rawData || timelineDates.length === 0) return;

    const activeDate = timelineDates[currentDateIndex];
    let lat = -33.5;
    let lon = -91.0;
    let p = 1024.0;

    // Obtener coordenadas del modelo enfocado o ERA5
    let targetModel = Object.values(rawData.models).find(m => m.id === focusedModelId);
    if (!targetModel || focusedModelId === 'ensemble') {
      targetModel = rawData.models['ERA5 Reanálisis'] || Object.values(rawData.models)[0];
    }

    if (targetModel && targetModel.dates) {
      const dIdx = targetModel.dates.indexOf(activeDate);
      if (dIdx !== -1) {
        lat = targetModel.lat[dIdx];
        lon = targetModel.lon[dIdx];
        p = targetModel.pressure_psa[dIdx];
      } else if (targetModel.latest) {
        lat = targetModel.latest.lat;
        lon = targetModel.latest.lon;
        p = targetModel.latest.pressure_psa;
      }
    }

    mapsInstance.updatePressureMap(lat, lon, p, activeDate);
    mapsInstance.updateAnomalyMap(lat, lon, rawData.spatial_grid);
  }

  // =========================================================================
  // GESTIÓN DE MODALES CIENTÍFICOS DESACOPLADOS (INDIVIDUALES)
  // =========================================================================

  function initScienceModals(data) {
    const overlays = document.querySelectorAll('.science-modal-overlay');

    function openModal(modalId) {
      const modal = document.getElementById(modalId);
      if (modal) modal.classList.add('open');
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
    const openCitationBtn = document.getElementById('openCitationModalBtn');
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
    if (tableBody && data.validation_metrics) {
      tableBody.innerHTML = '';
      data.validation_metrics.forEach(row => {
        const tr = document.createElement('tr');
        const badgeClass = row.skill_class || (row.rmse_psa.includes('0.0') ? 'badge-primary' : 'badge-info');
        const isBest = row.rmse_psa.includes('0.0') || row.corr_psa === '1.000';
        tr.innerHTML = `
          <td><strong>${row.model}</strong></td>
          <td><span style="font-size: 0.8rem; color: #94a3b8;">${row.type}</span></td>
          <td><span class="badge ${badgeClass}">${row.skill_rating || 'Validado'}</span></td>
          <td style="${isBest ? 'color: var(--color-success); font-weight: 700;' : ''}">${row.rmse_psa}</td>
          <td style="font-family: var(--font-mono);">${row.bias_psa}</td>
          <td style="${row.corr_psa === '1.000' ? 'color: var(--color-success); font-weight: 700;' : ''}">${row.corr_psa}</td>
          <td>${row.corr_lat}</td>
          <td>${row.dist_error_km}</td>
          <td><strong style="color: ${parseFloat(row.willmott_d) > 0.8 ? 'var(--color-accent)' : '#e2e8f0'}">${row.willmott_d}</strong></td>
        `;
        tableBody.appendChild(tr);
      });
    }

    // Tecla ESC para cerrar cualquier modal abierto
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        closeAllModals();
      }
    });
  }
});

/**
 * Carga el archivo JSON de métricas desde la ruta relativa con fallback
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

  console.warn('[AVISO] Fetch HTTP no disponible. Cargando respaldo offline...');
  return getInlineFallbackData();
}

function showDataLoadError() {
  const kpiPressure = document.getElementById('kpiPressure');
  if (kpiPressure) {
    kpiPressure.innerHTML = `<span style="font-size: 1rem; color: #ef4444;">Error al cargar datos</span>`;
  }
}

/**
 * Datos de respaldo en caso de apertura offline sin servidor
 */
function getInlineFallbackData() {
  const today = new Date().toISOString().split('T')[0];
  return {
    metadata: {
      project: "Observatorio del Anticiclón del Pacífico Sur",
      institution: "LOFA - UACh",
      last_updated: today
    },
    models: {
      "ERA5 Reanálisis": {
        id: "era5_reanalisis",
        name: "ERA5 Reanálisis (ECMWF)",
        dates: [today],
        pressure_psa: [1025.4],
        lat: [-34.5],
        lon: [-92.1],
        latest: { date: today, pressure_psa: 1025.4, lat: -34.5, lon: -92.1 }
      }
    },
    spatial_grid: {
      lats: [-35, -32, -29],
      lons: [-100, -95, -90],
      current_anomaly: [[0.5, 1.2, 0.8], [1.1, 1.8, 1.3], [0.4, 0.9, 0.6]]
    }
  };
}
