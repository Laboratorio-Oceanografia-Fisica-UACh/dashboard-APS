/**
 * charts.js
 * Visualización de series de tiempo científicas multimodelo con Plotly.js
 * Resuelve el bug de compresión vertical de leyenda y soporta presets climáticos históricos
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

        // Resetear inputs de fechas y select de presets
        const presetSelect = document.getElementById('climatePresetsSelect');
        if (presetSelect) presetSelect.value = '';
        const fromInput = document.getElementById('chartDateFrom');
        const toInput = document.getElementById('chartDateTo');
        if (fromInput) fromInput.value = '';
        if (toInput) toInput.value = '';

        // Sincronizar todos los grupos de chips
        document.querySelectorAll('.chart-controls .btn-chip').forEach((b) => {
          b.classList.toggle('active', b.dataset.range === selectedRange);
        });

        this.updateCharts();
      });
    });

    // 2. Presets climáticos científicos preconfigurados
    const presetSelect = document.getElementById('climatePresetsSelect');
    if (presetSelect) {
      presetSelect.addEventListener('change', (e) => {
        const val = e.target.value;
        if (!val) return;

        const selectedOpt = presetSelect.options[presetSelect.selectedIndex];
        const isPending = selectedOpt && selectedOpt.dataset && selectedOpt.dataset.status === 'pending';

        if (isPending) {
          this.showScientificToast(
            `El evento <strong>${selectedOpt.textContent.trim()}</strong> está en proceso de ingesta histórica en segundo plano.<br><small style="color:#94a3b8;">La base activa actual cubre desde 1940 en adelante.</small>`
          );
        }

        // Desactivar chips rápidos
        document.querySelectorAll('.chart-controls .btn-chip').forEach((b) => b.classList.remove('active'));

        if (val === 'forecast') {
          // Activar modelo GFS y enfocar ventana temporal del pronóstico
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

        // Notificar fecha inicial del preset si hay callback
        if (this.onDateSelected && this.customStartDate) {
          this.onDateSelected(this.customStartDate);
        }
      });
    }

    // 3. Filtro por rango personalizado (Desde / Hasta)
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

    // 4. Redimensionamiento adaptativo en ventanas
    window.addEventListener('resize', () => {
      Plotly.Plots.resize('positionChart');
      Plotly.Plots.resize('pressureChart');
    });
  }

  setData(modelsData) {
    this.models = modelsData;
    this.updateCharts();
    this.attachClickEvents();
  }

  filterDataByRange(dates, values) {
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
    this.renderPositionChart();
    this.renderPressureChart();
  }

  renderPositionChart() {
    const selectedIds = this.modelSelector.getSelectedModelIds();
    const traces = [];

    for (const [key, model] of Object.entries(this.models)) {
      if (!selectedIds.includes(model.id)) continue;

      const color = this.modelSelector.getModelColor(model.id);

      // Traza Latitud
      const latData = this.filterDataByRange(model.dates, model.lat);
      const useSpline = latData.values.length <= 365;
      traces.push({
        x: latData.dates,
        y: latData.values,
        mode: 'lines',
        name: `${model.name} (Lat)`,
        line: { color: color, width: 2.0, shape: useSpline ? 'spline' : 'linear' },
        hovertemplate: '<b>%{x}</b><br>Latitud: %{y:.2f}°S<extra></extra>',
        yaxis: 'y1'
      });

      // Traza Longitud (línea discontinua)
      const lonData = this.filterDataByRange(model.dates, model.lon);
      traces.push({
        x: lonData.dates,
        y: lonData.values,
        mode: 'lines',
        name: `${model.name} (Lon)`,
        line: { color: color, width: 1.6, dash: 'dot', shape: useSpline ? 'spline' : 'linear' },
        hovertemplate: '<b>%{x}</b><br>Longitud: %{y:.2f}°W<extra></extra>',
        yaxis: 'y2'
      });
    }

    const showSlider = this.currentRange === 'all' || this.currentRange === '1825';

    // Layout con leyenda ubicada en el borde inferior con paginación limpia (Solución Bug de Achatamiento)
    const layout = {
      paper_bgcolor: 'transparent',
      plot_bgcolor: 'rgba(9, 15, 30, 0.6)',
      font: { family: 'Outfit, sans-serif', color: '#94a3b8' },
      margin: { l: 50, r: 50, t: 25, b: showSlider ? 95 : 65 },
      showlegend: true,
      legend: {
        orientation: 'h',
        yanchor: 'top',
        y: showSlider ? -0.32 : -0.22,
        xanchor: 'center',
        x: 0.5,
        font: { size: 10, color: '#cbd5e1' }
      },
      xaxis: {
        gridcolor: 'rgba(72, 110, 163, 0.15)',
        zerolinecolor: 'rgba(72, 110, 163, 0.25)',
        tickfont: { size: 10 },
        rangeslider: { visible: showSlider, thickness: 0.08, bgcolor: 'rgba(14, 22, 42, 0.5)' }
      },
      yaxis: {
        title: { text: 'Latitud (°S)', font: { size: 11, color: '#f1f5f9' } },
        gridcolor: 'rgba(72, 110, 163, 0.15)',
        zeroline: false,
        tickfont: { size: 10 }
      },
      yaxis2: {
        title: { text: 'Longitud (°W)', font: { size: 11, color: '#00d2ff' } },
        overlaying: 'y',
        side: 'right',
        showgrid: false,
        zeroline: false,
        tickfont: { size: 10 }
      },
      hovermode: 'x unified'
    };

    const config = { responsive: true, displayModeBar: false };
    Plotly.react('positionChart', traces, layout, config);
  }

  renderPressureChart() {
    const selectedIds = this.modelSelector.getSelectedModelIds();
    const traces = [];

    for (const [key, model] of Object.entries(this.models)) {
      if (!selectedIds.includes(model.id)) continue;

      const color = this.modelSelector.getModelColor(model.id);
      const pData = this.filterDataByRange(model.dates, model.pressure_psa);
      const useSpline = pData.values.length <= 365;

      traces.push({
        x: pData.dates,
        y: pData.values,
        mode: 'lines',
        name: model.name,
        line: { color: color, width: 2.2, shape: useSpline ? 'spline' : 'linear' },
        hovertemplate: '<b>%{x}</b><br>PSA: %{y:.1f} hPa<extra></extra>'
      });
    }

    const showSlider = this.currentRange === 'all' || this.currentRange === '1825';

    // Layout con leyenda ubicada en el borde inferior (Solución Bug de Achatamiento)
    const layout = {
      paper_bgcolor: 'transparent',
      plot_bgcolor: 'rgba(9, 15, 30, 0.6)',
      font: { family: 'Outfit, sans-serif', color: '#94a3b8' },
      margin: { l: 55, r: 25, t: 25, b: showSlider ? 95 : 65 },
      showlegend: true,
      legend: {
        orientation: 'h',
        yanchor: 'top',
        y: showSlider ? -0.32 : -0.22,
        xanchor: 'center',
        x: 0.5,
        font: { size: 10, color: '#cbd5e1' }
      },
      xaxis: {
        gridcolor: 'rgba(72, 110, 163, 0.15)',
        zerolinecolor: 'rgba(72, 110, 163, 0.25)',
        tickfont: { size: 10 },
        rangeslider: { visible: showSlider, thickness: 0.08, bgcolor: 'rgba(14, 22, 42, 0.5)' }
      },
      yaxis: {
        title: { text: 'Presión Central PSA (hPa)', font: { size: 11, color: '#f1f5f9' } },
        gridcolor: 'rgba(72, 110, 163, 0.15)',
        zeroline: false,
        tickfont: { size: 10 }
      },
      hovermode: 'x unified'
    };

    const config = { responsive: true, displayModeBar: false };
    Plotly.react('pressureChart', traces, layout, config);
  }

  attachClickEvents() {
    const bindPlotClick = (elementId) => {
      const el = document.getElementById(elementId);
      if (el && !el._hasClickBound) {
        el._hasClickBound = true;
        el.on('plotly_click', (data) => {
          if (data && data.points && data.points.length > 0) {
            const clickedDate = data.points[0].x;
            if (this.onDateSelected && clickedDate) {
              this.onDateSelected(clickedDate);
            }
          }
        });
      }
    };

    bindPlotClick('positionChart');
    bindPlotClick('pressureChart');
  }

  showScientificToast(message) {
    let toast = document.getElementById('scientificToast');
    if (!toast) {
      toast = document.createElement('div');
      toast.id = 'scientificToast';
      toast.style.cssText = 'position:fixed;bottom:24px;right:24px;background:#0b1329;border:1px solid #00d2ff;color:#f8fafc;padding:12px 20px;border-radius:8px;box-shadow:0 8px 30px rgba(0,0,0,0.85);z-index:9999;font-size:0.875rem;max-width:380px;line-height:1.45;transition:all 0.3s ease;pointer-events:none;opacity:0;transform:translateY(12px);';
      document.body.appendChild(toast);
    }
    toast.innerHTML = `📡 <strong>Aviso del Observatorio:</strong><br>${message}`;
    toast.style.opacity = '1';
    toast.style.transform = 'translateY(0)';
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(12px)';
    }, 4500);
  }
}
