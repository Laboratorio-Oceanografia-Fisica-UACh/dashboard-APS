/**
 * charts.js
 * Visualización de series de tiempo científicas multimodelo y Diagrama de Fase 2D con Plotly.js
 * Implementa V5.3 (LOFA - UACh):
 * - Diagrama de Fase Espacial 2D (Longitud vs. Latitud) con cuadrantes de régimen sinóptico.
 * - Series temporales del Par Dinámico (Núcleo submalla y Centroide adaptativo).
 * - Gráfico de Morfología y Contenido Energético (Área A1020 y Masa Integrada I_vol).
 * - Gráfico de Diagnóstico de Bloqueos (Desacople D_nc y Presión Caja Norpatagonia).
 * - Soporta Presets Climáticos Documentados y selección de rangos temporales.
 * Laboratorio de Oceanografía Física (LOFA) - UACh
 */

class DashboardCharts {
  constructor(modelSelector, onDateSelected = null) {
    this.modelSelector = modelSelector;
    this.onDateSelected = onDateSelected;
    this.models = {};
    this.currentRange = '365';
    this.customStartDate = null;
    this.customEndDate = null;
    this.activeTab = 'phase'; // 'phase', 'timeseries', 'morphology', 'decoupling'

    this.initControls();
  }

  initControls() {
    // 1. Chips de intervalo temporal rápido
    const chipButtons = document.querySelectorAll('.chart-controls .btn-chip');
    chipButtons.forEach((btn) => {
      btn.addEventListener('click', (e) => {
        const selectedRange = e.target.dataset.range;
        this.currentRange = selectedRange;
        this.customStartDate = null;
        this.customEndDate = null;

        const presetSelect = document.getElementById('climatePresetsSelect');
        if (presetSelect) presetSelect.value = '';
        const fromInput = document.getElementById('chartDateFrom');
        const toInput = document.getElementById('chartDateTo');
        if (fromInput) fromInput.value = '';
        if (toInput) toInput.value = '';

        document.querySelectorAll('.chart-controls .btn-chip').forEach((b) => {
          b.classList.toggle('active', b.dataset.range === selectedRange);
        });

        this.updateCharts();
      });
    });

    // 2. Presets climáticos científicos
    const presetSelect = document.getElementById('climatePresetsSelect');
    if (presetSelect) {
      presetSelect.addEventListener('change', (e) => {
        const val = e.target.value;
        if (!val) return;

        const selectedOpt = presetSelect.options[presetSelect.selectedIndex];
        const isPending = selectedOpt && selectedOpt.dataset && selectedOpt.dataset.status === 'pending';

        if (isPending) {
          this.showScientificToast(
            `El evento <strong>${selectedOpt.textContent.trim()}</strong> está en proceso de ingesta histórica en segundo plano.<br><small style="color:#94a3b8;">La base activa actual cubre desde 1994 en adelante.</small>`
          );
        }

        document.querySelectorAll('.chart-controls .btn-chip').forEach((b) => b.classList.remove('active'));

        if (val === 'forecast') {
          const gfsModel = Object.values(this.models).find(m => m.id === 'noaa_gfs_forecast');
          if (gfsModel && gfsModel.dates && gfsModel.dates.length > 0) {
            this.modelSelector.selectedModelIds.add('noaa_gfs_forecast');
            this.customStartDate = gfsModel.dates[0];
            this.customEndDate = gfsModel.dates[gfsModel.dates.length - 1];
            this.currentRange = 'custom';
            const fromInput = document.getElementById('chartDateFrom');
            const toInput = document.getElementById('chartDateTo');
            if (fromInput) fromInput.value = this.customStartDate;
            if (toInput) toInput.value = this.customEndDate;
          } else {
            this.currentRange = '14';
            this.customStartDate = null;
            this.customEndDate = null;
          }
        } else {
          const [start, end] = val.split(':');
          this.customStartDate = start;
          this.customEndDate = end;
          this.currentRange = 'custom';

          const fromInput = document.getElementById('chartDateFrom');
          const toInput = document.getElementById('chartDateTo');
          if (fromInput) fromInput.value = start;
          if (toInput) toInput.value = end;
        }

        this.updateCharts();

        if (this.onDateSelected && this.customStartDate) {
          this.onDateSelected(this.customStartDate);
        }
      });
    }

    // 3. Filtro por rango personalizado
    const applyRangeBtn = document.getElementById('applyCustomDateRangeBtn');
    if (applyRangeBtn) {
      applyRangeBtn.addEventListener('click', () => {
        const fromInput = document.getElementById('chartDateFrom');
        const toInput = document.getElementById('chartDateTo');
        if (fromInput && toInput && fromInput.value && toInput.value) {
          this.customStartDate = fromInput.value;
          this.customEndDate = toInput.value;
          this.currentRange = 'custom';

          document.querySelectorAll('.chart-controls .btn-chip').forEach((b) => b.classList.remove('active'));
          this.updateCharts();

          if (this.onDateSelected) {
            this.onDateSelected(this.customStartDate);
          }
        }
      });
    }

    // 4. Redimensionamiento adaptativo
    window.addEventListener('resize', () => {
      ['phaseSpaceChart', 'positionChart', 'pressureChart', 'morphologyChart', 'decouplingChart'].forEach(id => {
        const el = document.getElementById(id);
        if (el && el.data) Plotly.Plots.resize(id);
      });
    });
  }

  setData(modelsData) {
    this.models = modelsData;
    this.updateCharts();
    this.attachClickEvents();
  }

  filterDataByRange(dates, values) {
    if (!dates || !values) return { dates: [], values: [] };

    if (this.currentRange === 'custom' && this.customStartDate && this.customEndDate) {
      const filteredDates = [];
      const filteredValues = [];
      for (let i = 0; i < dates.length; i++) {
        const d = dates[i];
        if (d >= this.customStartDate && d <= this.customEndDate) {
          filteredDates.push(d);
          filteredValues.push(values[i]);
        }
      }
      return { dates: filteredDates, values: filteredValues };
    }

    if (this.currentRange === 'all') {
      return { dates, values };
    }

    const days = parseInt(this.currentRange, 10);
    const sliceIndex = Math.max(0, dates.length - days);
    return {
      dates: dates.slice(sliceIndex),
      values: values.slice(sliceIndex)
    };
  }

  updateCharts() {
    this.renderPhaseSpaceChart();
    this.renderPositionChart();
    this.renderPressureChart();
    this.renderMorphologyChart();
    this.renderDecouplingChart();
  }

  /**
   * 1. Diagrama de Fase Espacial 2D: Longitud vs. Latitud (LOFA - UACh)
   */
  renderPhaseSpaceChart() {
    const el = document.getElementById('phaseSpaceChart');
    if (!el) return;

    const traces = [];
    const era5 = this.models['ERA5 Reanálisis'] || Object.values(this.models)[0];
    if (!era5) return;

    const filteredDates = this.filterDataByRange(era5.dates, era5.dates).dates;
    if (filteredDates.length === 0) return;

    const sliceIdx = era5.dates.indexOf(filteredDates[0]);
    const endIdx = era5.dates.indexOf(filteredDates[filteredDates.length - 1]) + 1;

    const coreLats = (era5.lat_core || era5.lat).slice(sliceIdx, endIdx);
    const coreLons = (era5.lon_core || era5.lon).slice(sliceIdx, endIdx);
    const centLats = (era5.lat_centroid || era5.lat).slice(sliceIdx, endIdx);
    const centLons = (era5.lon_centroid || era5.lon).slice(sliceIdx, endIdx);
    const pVals = (era5.p_max_fit || era5.pressure_psa).slice(sliceIdx, endIdx);

    // Traza Núcleo (+)
    traces.push({
      x: coreLons,
      y: coreLats,
      mode: 'lines+markers',
      name: 'Núcleo Barométrico (+)',
      marker: {
        size: 7,
        color: '#fbbf24',
        symbol: 'circle',
        line: { color: '#000', width: 1 }
      },
      line: { color: '#fbbf24', width: 2.2, shape: 'spline' },
      text: filteredDates.map((d, i) => `${d}<br>P_max: ${pVals[i]} hPa`),
      hovertemplate: '<b>Núcleo (+)</b><br>Fecha: %{text}<br>Lon: %{x:.2f}°W<br>Lat: %{y:.2f}°S<extra></extra>'
    });

    // Traza Centroide (◇)
    traces.push({
      x: centLons,
      y: centLats,
      mode: 'lines+markers',
      name: 'Centroide de Masa (◇)',
      marker: {
        size: 7,
        color: '#06b6d4',
        symbol: 'diamond',
        line: { color: '#fff', width: 1 }
      },
      line: { color: '#06b6d4', width: 1.8, dash: 'dot', shape: 'spline' },
      text: filteredDates,
      hovertemplate: '<b>Centroide (◇)</b><br>Fecha: %{text}<br>Lon: %{x:.2f}°W<br>Lat: %{y:.2f}°S<extra></extra>'
    });

    // Punto más reciente destacado
    if (coreLats.length > 0) {
      traces.push({
        x: [coreLons[coreLons.length - 1]],
        y: [coreLats[coreLats.length - 1]],
        mode: 'markers',
        name: 'Núcleo Activo',
        marker: { size: 14, color: '#f59e0b', symbol: 'star', line: { color: '#fff', width: 1.5 } },
        showlegend: false,
        hoverinfo: 'skip'
      });
      traces.push({
        x: [centLons[centLons.length - 1]],
        y: [centLats[centLats.length - 1]],
        mode: 'markers',
        name: 'Centroide Activo',
        marker: { size: 12, color: '#06b6d4', symbol: 'diamond', line: { color: '#fff', width: 2 } },
        showlegend: false,
        hoverinfo: 'skip'
      });
    }

    const layout = {
      title: false,
      paper_bgcolor: 'transparent',
      plot_bgcolor: 'rgba(11, 17, 32, 0.65)',
      font: { family: 'Outfit, sans-serif', color: '#cbd5e1' },
      margin: { l: 55, r: 25, t: 30, b: 50 },
      xaxis: {
        title: 'Longitud (°W)',
        color: '#94a3b8',
        gridcolor: 'rgba(255, 255, 255, 0.06)',
        range: [-120.0, -70.0],
        zeroline: false
      },
      yaxis: {
        title: 'Latitud (°S)',
        color: '#94a3b8',
        gridcolor: 'rgba(255, 255, 255, 0.06)',
        range: [-48.0, -18.0],
        zeroline: false
      },
      legend: {
        orientation: 'h',
        x: 0.0,
        y: 1.15,
        font: { size: 11 }
      },
      annotations: [
        {
          x: -110, y: -22,
          text: '<b>Retracción Oceánica</b>',
          showarrow: false,
          font: { size: 10, color: 'rgba(96, 165, 250, 0.5)' }
        },
        {
          x: -78, y: -22,
          text: '<b>Cuña Costera (Chile Central)</b>',
          showarrow: false,
          font: { size: 10, color: 'rgba(251, 191, 36, 0.6)' }
        },
        {
          x: -78, y: -45,
          text: '<b>Bloqueo Patagónico Austral</b>',
          showarrow: false,
          font: { size: 10, color: 'rgba(248, 113, 113, 0.6)' }
        },
        {
          x: -105, y: -38,
          text: '<b>Simetría Estival Típica</b>',
          showarrow: false,
          font: { size: 10, color: 'rgba(52, 211, 153, 0.5)' }
        }
      ]
    };

    Plotly.react('phaseSpaceChart', traces, layout, { responsive: true, displayModeBar: false });
  }

  /**
   * 2. Serie Temporal: Posición Latitud y Longitud del Par Dinámico
   */
  renderPositionChart() {
    const el = document.getElementById('positionChart');
    if (!el) return;

    const selectedIds = this.modelSelector.getSelectedModelIds();
    const traces = [];

    for (const [key, model] of Object.entries(this.models)) {
      if (!selectedIds.includes(model.id)) continue;

      const color = this.modelSelector.getModelColor(model.id);
      const latCoreVals = model.lat_core || model.lat;
      const lonCoreVals = model.lon_core || model.lon;
      const latCentVals = model.lat_centroid || model.lat;
      const lonCentVals = model.lon_centroid || model.lon;

      const latData = this.filterDataByRange(model.dates, latCoreVals);
      const lonData = this.filterDataByRange(model.dates, lonCoreVals);
      const latCentData = this.filterDataByRange(model.dates, latCentVals);

      traces.push({
        x: latData.dates,
        y: latData.values,
        mode: 'lines',
        name: `${model.name} (Núcleo Lat)`,
        line: { color: color, width: 2.0 },
        hovertemplate: '<b>%{x}</b><br>Núcleo Lat: %{y:.2f}°S<extra></extra>',
        yaxis: 'y1'
      });

      if (model.lat_centroid) {
        traces.push({
          x: latCentData.dates,
          y: latCentData.values,
          mode: 'lines',
          name: `${model.name} (Cent. Lat)`,
          line: { color: color, width: 1.4, dash: 'dot' },
          hovertemplate: '<b>%{x}</b><br>Cent. Lat: %{y:.2f}°S<extra></extra>',
          yaxis: 'y1'
        });
      }

      traces.push({
        x: lonData.dates,
        y: lonData.values,
        mode: 'lines',
        name: `${model.name} (Núcleo Lon)`,
        line: { color: color, width: 1.6, dash: 'dash' },
        hovertemplate: '<b>%{x}</b><br>Núcleo Lon: %{y:.2f}°W<extra></extra>',
        yaxis: 'y2'
      });
    }

    const layout = {
      title: false,
      paper_bgcolor: 'transparent',
      plot_bgcolor: 'rgba(11, 17, 32, 0.65)',
      font: { family: 'Outfit, sans-serif', color: '#cbd5e1' },
      margin: { l: 55, r: 55, t: 25, b: 40 },
      xaxis: {
        color: '#94a3b8',
        gridcolor: 'rgba(255, 255, 255, 0.06)'
      },
      yaxis: {
        title: 'Latitud (°S)',
        color: '#fbbf24',
        gridcolor: 'rgba(255, 255, 255, 0.06)',
        autorange: 'reversed'
      },
      yaxis2: {
        title: 'Longitud (°W)',
        color: '#38bdf8',
        overlaying: 'y',
        side: 'right',
        gridcolor: 'transparent',
        autorange: 'reversed'
      },
      legend: {
        orientation: 'h',
        x: 0.0,
        y: 1.15,
        font: { size: 10 }
      }
    };

    Plotly.react('positionChart', traces, layout, { responsive: true, displayModeBar: false });
  }

  /**
   * 3. Serie Temporal: Intensidad Central P_max (hPa) y Espesor Efectivo H_eff
   */
  renderPressureChart() {
    const el = document.getElementById('pressureChart');
    if (!el) return;

    const selectedIds = this.modelSelector.getSelectedModelIds();
    const traces = [];

    for (const [key, model] of Object.entries(this.models)) {
      if (!selectedIds.includes(model.id)) continue;

      const color = this.modelSelector.getModelColor(model.id);
      const pVals = model.p_max_fit || model.pressure_psa;
      const hVals = model.h_eff || [];

      const pData = this.filterDataByRange(model.dates, pVals);
      traces.push({
        x: pData.dates,
        y: pData.values,
        mode: 'lines',
        name: `${model.name} (P_max)`,
        line: { color: color, width: 2.2 },
        hovertemplate: '<b>%{x}</b><br>P_max: %{y:.2f} hPa<extra></extra>',
        yaxis: 'y1'
      });

      if (hVals.length > 0) {
        const hData = this.filterDataByRange(model.dates, hVals);
        traces.push({
          x: hData.dates,
          y: hData.values,
          mode: 'lines',
          name: `${model.name} (Espesor H̄)`,
          line: { color: color, width: 1.2, dash: 'dot' },
          hovertemplate: '<b>%{x}</b><br>Espesor H̄: %{y:.2f} hPa<extra></extra>',
          yaxis: 'y2'
        });
      }
    }

    const layout = {
      title: false,
      paper_bgcolor: 'transparent',
      plot_bgcolor: 'rgba(11, 17, 32, 0.65)',
      font: { family: 'Outfit, sans-serif', color: '#cbd5e1' },
      margin: { l: 55, r: 55, t: 25, b: 40 },
      xaxis: {
        color: '#94a3b8',
        gridcolor: 'rgba(255, 255, 255, 0.06)'
      },
      yaxis: {
        title: 'Presión Máxima (hPa)',
        color: '#f59e0b',
        gridcolor: 'rgba(255, 255, 255, 0.06)'
      },
      yaxis2: {
        title: 'Espesor Efectivo H̄ (hPa)',
        color: '#34d399',
        overlaying: 'y',
        side: 'right',
        gridcolor: 'transparent'
      },
      legend: {
        orientation: 'h',
        x: 0.0,
        y: 1.15,
        font: { size: 10 }
      }
    };

    Plotly.react('pressureChart', traces, layout, { responsive: true, displayModeBar: false });
  }

  /**
   * 4. Serie Temporal: Extensión Areal A_1020 y Masa Integrada I_vol
   */
  renderMorphologyChart() {
    const el = document.getElementById('morphologyChart');
    if (!el) return;

    const era5 = this.models['ERA5 Reanálisis'] || Object.values(this.models)[0];
    if (!era5 || !era5.area_1020) return;

    const aData = this.filterDataByRange(era5.dates, era5.area_1020);
    const vData = this.filterDataByRange(era5.dates, era5.vol_integral);

    const traces = [
      {
        x: aData.dates,
        y: aData.values,
        mode: 'lines',
        name: 'Área A₁₀₂₀ (10⁶ km²)',
        line: { color: '#38bdf8', width: 2.2 },
        fill: 'tozeroy',
        fillcolor: 'rgba(56, 189, 248, 0.1)',
        hovertemplate: '<b>%{x}</b><br>Área A₁₀₂₀: %{y:.2f} M km²<extra></extra>',
        yaxis: 'y1'
      },
      {
        x: vData.dates,
        y: vData.values,
        mode: 'lines',
        name: 'Masa/Volumen I_vol (hPa·10⁶ km²)',
        line: { color: '#a855f7', width: 2.0, dash: 'dash' },
        hovertemplate: '<b>%{x}</b><br>Masa I_vol: %{y:.1f} hPa·M km²<extra></extra>',
        yaxis: 'y2'
      }
    ];

    const layout = {
      title: false,
      paper_bgcolor: 'transparent',
      plot_bgcolor: 'rgba(11, 17, 32, 0.65)',
      font: { family: 'Outfit, sans-serif', color: '#cbd5e1' },
      margin: { l: 55, r: 55, t: 25, b: 40 },
      xaxis: { color: '#94a3b8', gridcolor: 'rgba(255, 255, 255, 0.06)' },
      yaxis: { title: 'Área A₁₀₂₀ (10⁶ km²)', color: '#38bdf8', gridcolor: 'rgba(255, 255, 255, 0.06)' },
      yaxis2: { title: 'Masa I_vol (hPa·10⁶ km²)', color: '#a855f7', overlaying: 'y', side: 'right', gridcolor: 'transparent' },
      legend: { orientation: 'h', x: 0.0, y: 1.15, font: { size: 10 } }
    };

    Plotly.react('morphologyChart', traces, layout, { responsive: true, displayModeBar: false });
  }

  /**
   * 5. Serie Temporal: Desacople D_nc (km) y Presión en Caja Norpatagonia (hPa)
   */
  renderDecouplingChart() {
    const el = document.getElementById('decouplingChart');
    if (!el) return;

    const era5 = this.models['ERA5 Reanálisis'] || Object.values(this.models)[0];
    if (!era5 || !era5.dist_decoupling_km) return;

    const dData = this.filterDataByRange(era5.dates, era5.dist_decoupling_km);
    const pPatData = this.filterDataByRange(era5.dates, era5.p_patagonia);

    const traces = [
      {
        x: dData.dates,
        y: dData.values,
        mode: 'lines',
        name: 'Desacople D_nc (km)',
        line: { color: '#f43f5e', width: 2.0 },
        hovertemplate: '<b>%{x}</b><br>Desacople D_nc: %{y:.1f} km<extra></extra>',
        yaxis: 'y1'
      },
      {
        x: pPatData.dates,
        y: pPatData.values,
        mode: 'lines',
        name: 'Presión Norpatagonia (hPa)',
        line: { color: '#c084fc', width: 1.8, dash: 'dot' },
        hovertemplate: '<b>%{x}</b><br>Presión Norpatagonia: %{y:.2f} hPa<extra></extra>',
        yaxis: 'y2'
      }
    ];

    const layout = {
      title: false,
      paper_bgcolor: 'transparent',
      plot_bgcolor: 'rgba(11, 17, 32, 0.65)',
      font: { family: 'Outfit, sans-serif', color: '#cbd5e1' },
      margin: { l: 55, r: 55, t: 25, b: 40 },
      xaxis: { color: '#94a3b8', gridcolor: 'rgba(255, 255, 255, 0.06)' },
      yaxis: { title: 'Desacople D_nc (km)', color: '#f43f5e', gridcolor: 'rgba(255, 255, 255, 0.06)' },
      yaxis2: { title: 'Presión Norpatagonia (hPa)', color: '#c084fc', overlaying: 'y', side: 'right', gridcolor: 'transparent' },
      legend: { orientation: 'h', x: 0.0, y: 1.15, font: { size: 10 } }
    };

    Plotly.react('decouplingChart', traces, layout, { responsive: true, displayModeBar: false });
  }

  attachClickEvents() {
    ['positionChart', 'pressureChart', 'phaseSpaceChart', 'morphologyChart', 'decouplingChart'].forEach(chartId => {
      const el = document.getElementById(chartId);
      if (el) {
        el.on('plotly_click', (data) => {
          if (data && data.points && data.points.length > 0) {
            const pt = data.points[0];
            const clickedDate = pt.x;
            if (clickedDate && typeof clickedDate === 'string' && clickedDate.includes('-') && this.onDateSelected) {
              this.onDateSelected(clickedDate);
            }
          }
        });
      }
    });
  }

  showScientificToast(message) {
    let toast = document.getElementById('scientificToast');
    if (!toast) {
      toast = document.createElement('div');
      toast.id = 'scientificToast';
      toast.style.cssText = `
        position: fixed;
        bottom: 24px;
        right: 24px;
        background: rgba(15, 23, 42, 0.95);
        border: 1px solid rgba(2, 132, 199, 0.4);
        color: #f1f5f9;
        padding: 12px 18px;
        border-radius: 8px;
        box-shadow: 0 10px 25px rgba(0,0,0,0.5);
        font-family: Outfit, sans-serif;
        font-size: 13px;
        z-index: 9999;
        transition: opacity 0.3s ease;
      `;
      document.body.appendChild(toast);
    }
    toast.innerHTML = message;
    toast.style.opacity = '1';
    clearTimeout(this._toastTimeout);
    this._toastTimeout = setTimeout(() => {
      if (toast) toast.style.opacity = '0';
    }, 4500);
  }
}
