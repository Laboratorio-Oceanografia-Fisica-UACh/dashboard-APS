/**
 * charts.js
 * Visualización de series de tiempo científicas con Plotly.js
 * Laboratorio de Oceanografía Física (LOFA) - UACh
 */

class DashboardCharts {
  constructor(modelSelector) {
    this.modelSelector = modelSelector;
    this.models = {};
    this.currentRange = '365';

    this.initControls();
  }

  initControls() {
    const chipButtons = document.querySelectorAll('.chart-controls .btn-chip');
    chipButtons.forEach((btn) => {
      btn.addEventListener('click', (e) => {
        const selectedRange = e.target.dataset.range;
        this.currentRange = selectedRange;

        // Sincronizar todos los grupos de botones de chips
        document.querySelectorAll('.chart-controls .btn-chip').forEach((b) => {
          b.classList.toggle('active', b.dataset.range === selectedRange);
        });

        this.updateCharts();
      });
    });

    window.addEventListener('resize', () => {
      Plotly.Plots.resize('positionChart');
      Plotly.Plots.resize('pressureChart');
    });
  }

  setData(modelsData) {
    this.models = modelsData;
    this.updateCharts();
  }

  filterDataByRange(dates, values) {
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
        name: `${model.name} (Latitud)`,
        line: { color: color, width: 2.0, shape: useSpline ? 'spline' : 'linear' },
        hovertemplate: '<b>%{x}</b><br>Latitud: %{y:.2f}°S<extra></extra>',
        yaxis: 'y1'
      });

      // Traza Longitud (línea punteada para distinguir)
      const lonData = this.filterDataByRange(model.dates, model.lon);
      traces.push({
        x: lonData.dates,
        y: lonData.values,
        mode: 'lines',
        name: `${model.name} (Longitud)`,
        line: { color: color, width: 1.6, dash: 'dot', shape: useSpline ? 'spline' : 'linear' },
        hovertemplate: '<b>%{x}</b><br>Longitud: %{y:.2f}°W<extra></extra>',
        yaxis: 'y2'
      });
    }

    const showSlider = this.currentRange === 'all' || this.currentRange === '1825';

    const layout = {
      paper_bgcolor: 'transparent',
      plot_bgcolor: 'rgba(9, 15, 30, 0.6)',
      font: { family: 'Outfit, sans-serif', color: '#94a3b8' },
      margin: { l: 50, r: 50, t: 30, b: showSlider ? 60 : 40 },
      showlegend: true,
      legend: {
        orientation: 'h',
        yanchor: 'bottom',
        y: 1.02,
        xanchor: 'right',
        x: 1,
        font: { size: 10 }
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

    const layout = {
      paper_bgcolor: 'transparent',
      plot_bgcolor: 'rgba(9, 15, 30, 0.6)',
      font: { family: 'Outfit, sans-serif', color: '#94a3b8' },
      margin: { l: 55, r: 25, t: 30, b: showSlider ? 60 : 40 },
      showlegend: true,
      legend: {
        orientation: 'h',
        yanchor: 'bottom',
        y: 1.02,
        xanchor: 'right',
        x: 1,
        font: { size: 11 }
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
}
