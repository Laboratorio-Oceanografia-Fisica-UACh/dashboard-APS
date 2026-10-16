/**
 * main.js
 * Orquestador principal del Dashboard del Anticiclón del Pacífico Sur (APS)
 * Laboratorio de Oceanografía Física (LOFA) - Universidad Austral de Chile
 */

document.addEventListener('DOMContentLoaded', async () => {
  console.log('🌊 Inicializando Dashboard Anticiclón del Pacífico Sur (LOFA UACh)...');

  // 1. Inicializar Módulos
  let chartsInstance = null;
  let mapsInstance = null;
  let rawData = null;

  const modelSelector = new ModelSelector((selectedModelIds) => {
    console.log('[MODELOS] Selección actualizada:', selectedModelIds);
    if (chartsInstance) {
      chartsInstance.updateCharts();
    }
    updateKpisWithSelection(selectedModelIds);
  });

  chartsInstance = new DashboardCharts(modelSelector);
  mapsInstance = new DashboardMaps();

  // 2. Cargar Datos del Pipeline (JSON)
  try {
    rawData = await loadData();
    if (!rawData || !rawData.models) {
      throw new Error('Estructura de datos incompleta');
    }

    // Configurar modelos en el selector
    modelSelector.setModels(rawData.models);
    chartsInstance.setData(rawData.models);

    // Obtener modelo primario (ej. ERA5 o el primero)
    const primaryModelKey = Object.keys(rawData.models)[0];
    const primaryModel = rawData.models[primaryModelKey];

    // Actualizar Mapas con el estado más reciente
    const latest = primaryModel.latest;
    mapsInstance.updatePressureMap(latest.lat, latest.lon, latest.pressure_psa);
    mapsInstance.updateAnomalyMap(latest.lat, latest.lon, rawData.spatial_grid);

    // Actualizar Tarjetas KPI
    updateKpis(primaryModel, rawData.metadata);

    // Inicializar modales científicos (Fundamentos Físicos y Validación)
    initScienceModals(rawData);

  } catch (error) {
    console.error('[ERROR] Error cargando los datos del APS:', error);
    showDataLoadError();
  }

  // Función para actualizar tarjetas KPI con el modelo en foco
  function updateKpis(model, metadata) {
    const latest = model.latest;
    
    const kpiPressure = document.getElementById('kpiPressure');
    const kpiPosition = document.getElementById('kpiPosition');
    const kpiAnomaly = document.getElementById('kpiAnomaly');
    const kpiDate = document.getElementById('kpiDate');
    const kpiModelFocus = document.getElementById('kpiModelFocus');

    if (kpiPressure) kpiPressure.innerHTML = `${latest.pressure_psa.toFixed(1)} <small>hPa</small>`;
    if (kpiPosition) kpiPosition.textContent = `${Math.abs(latest.lat).toFixed(1)}°S, ${Math.abs(latest.lon).toFixed(1)}°W`;
    
    // Cálculo de anomalía estimada en el centro
    const centerAnomaly = (latest.pressure_psa - 1022.0).toFixed(1);
    if (kpiAnomaly) {
      const sign = centerAnomaly > 0 ? '+' : '';
      kpiAnomaly.innerHTML = `${sign}${centerAnomaly} <small>hPa</small>`;
      kpiAnomaly.style.color = centerAnomaly >= 0 ? 'var(--color-gold)' : 'var(--color-primary)';
    }

    if (kpiDate && latest.date) {
      kpiDate.textContent = latest.date;
      const kpiDateSub = kpiDate.nextElementSibling;
      if (kpiDateSub && metadata && metadata.time_coverage) {
        kpiDateSub.textContent = `${metadata.time_coverage.start} al ${metadata.time_coverage.end} (${metadata.time_coverage.total_days.toLocaleString()} días)`;
      }
    }

    if (kpiModelFocus) {
      kpiModelFocus.textContent = `Modelo en foco: ${model.name}`;
    }
  }

  function updateKpisWithSelection(selectedModelIds) {
    if (!rawData || !rawData.models) return;
    
    // Tomar el primer modelo seleccionado
    const firstSelected = Object.values(rawData.models).find(m => selectedModelIds.includes(m.id));
    if (firstSelected) {
      updateKpis(firstSelected, rawData.metadata);
      const latest = firstSelected.latest;
      mapsInstance.updatePressureMap(latest.lat, latest.lon, latest.pressure_psa);
    }
  }

  function initScienceModals(data) {
    // 1. Modal Fundamentos Físicos
    const physicsOverlay = document.getElementById('physicsModalOverlay');
    const openPhysicsBtn = document.getElementById('openPhysicsModalBtn');
    const closePhysicsBtn = document.getElementById('closePhysicsModalBtn');

    function openPhysicsModal(targetTopicId = null) {
      physicsOverlay.classList.add('open');
      if (targetTopicId) {
        setTimeout(() => {
          const el = document.getElementById(`topic-${targetTopicId}`);
          if (el) {
            const modalBody = physicsOverlay.querySelector('.science-modal-body');
            if (modalBody) {
              const topPos = el.offsetTop - modalBody.offsetTop;
              modalBody.scrollTo({ top: Math.max(0, topPos - 10), behavior: 'smooth' });
            }
          }
        }, 100);
      }
    }

    function closePhysicsModal() {
      physicsOverlay.classList.remove('open');
    }

    if (openPhysicsBtn) openPhysicsBtn.addEventListener('click', () => openPhysicsModal());
    if (closePhysicsBtn) closePhysicsBtn.addEventListener('click', () => closePhysicsModal());
    physicsOverlay.addEventListener('click', (e) => {
      if (e.target === physicsOverlay) closePhysicsModal();
    });

    // Botones 'i' en cada tarjeta KPI
    document.querySelectorAll('.kpi-info-trigger').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const topic = btn.dataset.topic;
        openPhysicsModal(topic);
      });
    });

    // 2. Modal Validación Estadística
    const validationOverlay = document.getElementById('validationModalOverlay');
    const openValidationBtn = document.getElementById('openValidationModalBtn');
    const closeValidationBtn = document.getElementById('closeValidationModalBtn');
    const tableBody = document.getElementById('validationTableBody');

    function openValidationModal() {
      validationOverlay.classList.add('open');
    }

    function closeValidationModal() {
      validationOverlay.classList.remove('open');
    }

    if (openValidationBtn) openValidationBtn.addEventListener('click', () => openValidationModal());
    if (closeValidationBtn) closeValidationBtn.addEventListener('click', () => closeValidationModal());
    validationOverlay.addEventListener('click', (e) => {
      if (e.target === validationOverlay) closeValidationModal();
    });

    // Renderizar tabla de métricas si existen
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
        closePhysicsModal();
        closeValidationModal();
      }
    });
  }
});

/**
 * Carga el archivo JSON de métricas desde la ruta relativa.
 * Incluye fallback por si se abre directamente en navegador mediante file:// (CORS)
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

  console.warn('[AVISO] Fetch HTTP no disponible (ej. protocolo file://). Cargando datos de respaldo...');
  return getInlineFallbackData();
}

function showDataLoadError() {
  const kpiPressure = document.getElementById('kpiPressure');
  if (kpiPressure) {
    kpiPressure.innerHTML = `<span style="font-size: 1rem; color: #ef4444;">Error al cargar datos</span>`;
  }
}

/**
 * Datos de respaldo en memoria en caso de apertura offline o sin servidor web
 */
function getInlineFallbackData() {
  const today = new Date().toISOString().split('T')[0];
  return {
    metadata: {
      project: "Dashboard Anticiclón del Pacífico Sur",
      institution: "LOFA - UACh",
      last_updated: today
    },
    models: {
      "ERA5 Reanálisis": {
        id: "era5_reanalisis",
        name: "ERA5 Reanálisis",
        dates: [today],
        pressure_psa: [1025.4],
        lat: [-32.5],
        lon: [-92.1],
        latest: { date: today, pressure_psa: 1025.4, lat: -32.5, lon: -92.1 }
      }
    },
    spatial_grid: {
      lats: [-35, -32, -29],
      lons: [-100, -95, -90],
      current_anomaly: [[0.5, 1.2, 0.8], [1.1, 1.8, 1.3], [0.4, 0.9, 0.6]]
    }
  };
}
