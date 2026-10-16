/**
 * model_selector.js
 * Gestión del selector y comparador multimodelo (Drawer Toggleable)
 * Laboratorio de Oceanografía Física (LOFA) - UACh
 */

const MODEL_PALETTE = [
  '#00d2ff', // Cyan eléctrico (Modelo 1 - ERA5)
  '#f59e0b', // Ámbar / Dorado (Modelo 2 - GFS)
  '#10b981', // Esmeralda (Modelo 3 - LOFA-1)
  '#ec4899', // Rosa / Fucsia (Modelo 4)
  '#8b5cf6', // Violeta (Modelo 5)
  '#ef4444', // Rojo Coral (Modelo 6)
  '#3b82f6'  // Azul Real (Modelo 7)
];

class ModelSelector {
  constructor(onSelectionChange) {
    this.onSelectionChange = onSelectionChange;
    this.models = {};
    this.selectedIds = new Set();
    this.modelColors = {};

    // Elementos del DOM
    this.drawer = document.getElementById('modelDrawer');
    this.overlay = document.getElementById('drawerOverlay');
    this.toggleBtn = document.getElementById('toggleModelDrawerBtn');
    this.closeBtn = document.getElementById('closeDrawerBtn');
    this.listContainer = document.getElementById('modelsCheckboxList');
    this.countBadge = document.getElementById('selectedModelsCount');
    this.selectAllBtn = document.getElementById('selectAllModelsBtn');
    this.deselectAllBtn = document.getElementById('deselectAllModelsBtn');
    this.applyBtn = document.getElementById('applyModelsBtn');

    this.initEventListeners();
  }

  initEventListeners() {
    this.toggleBtn.addEventListener('click', () => this.openDrawer());
    this.closeBtn.addEventListener('click', () => this.closeDrawer());
    this.overlay.addEventListener('click', () => this.closeDrawer());

    this.selectAllBtn.addEventListener('click', () => this.selectAll());
    this.deselectAllBtn.addEventListener('click', () => this.deselectAll());
    this.applyBtn.addEventListener('click', () => {
      this.closeDrawer();
      if (this.onSelectionChange) {
        this.onSelectionChange(Array.from(this.selectedIds));
      }
    });

    // Escuchar tecla ESC para cerrar cajón
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && this.drawer.classList.contains('open')) {
        this.closeDrawer();
      }
    });
  }

  setModels(modelsData) {
    this.models = modelsData;
    this.selectedIds.clear();

    let colorIndex = 0;
    for (const [key, model] of Object.entries(this.models)) {
      this.selectedIds.add(model.id);
      this.modelColors[model.id] = MODEL_PALETTE[colorIndex % MODEL_PALETTE.length];
      colorIndex++;
    }

    this.renderChecklist();
    this.updateCountBadge();
  }

  openDrawer() {
    this.drawer.classList.add('open');
    this.overlay.classList.add('open');
  }

  closeDrawer() {
    this.drawer.classList.remove('open');
    this.overlay.classList.remove('open');
  }

  selectAll() {
    for (const model of Object.values(this.models)) {
      this.selectedIds.add(model.id);
    }
    this.updateChecklistUI();
    this.updateCountBadge();
  }

  deselectAll() {
    // Dejar al menos el primer modelo seleccionado para evitar gráficos vacíos
    const firstId = Object.values(this.models)[0]?.id;
    this.selectedIds.clear();
    if (firstId) {
      this.selectedIds.add(firstId);
    }
    this.updateChecklistUI();
    this.updateCountBadge();
  }

  toggleModel(modelId) {
    if (this.selectedIds.has(modelId)) {
      // Evitar deseleccionar todo
      if (this.selectedIds.size > 1) {
        this.selectedIds.delete(modelId);
      }
    } else {
      this.selectedIds.add(modelId);
    }
    this.updateChecklistUI();
    this.updateCountBadge();
  }

  updateCountBadge() {
    if (this.countBadge) {
      this.countBadge.textContent = this.selectedIds.size;
    }
  }

  renderChecklist() {
    this.listContainer.innerHTML = '';

    for (const model of Object.values(this.models)) {
      const isSelected = this.selectedIds.has(model.id);
      const color = this.modelColors[model.id];

      const item = document.createElement('div');
      item.className = `model-item ${isSelected ? 'selected' : ''}`;
      item.dataset.id = model.id;

      item.innerHTML = `
        <label class="model-label" for="chk_${model.id}">
          <span class="model-color-dot" style="color: ${color}; background-color: ${color};"></span>
          <span>${model.name}</span>
        </label>
        <input type="checkbox" id="chk_${model.id}" class="model-checkbox" ${isSelected ? 'checked' : ''}>
      `;

      item.addEventListener('click', (e) => {
        if (e.target.tagName !== 'INPUT') {
          const chk = item.querySelector('input');
          chk.checked = !chk.checked;
        }
        this.toggleModel(model.id);
      });

      this.listContainer.appendChild(item);
    }
  }

  updateChecklistUI() {
    const items = this.listContainer.querySelectorAll('.model-item');
    items.forEach((item) => {
      const id = item.dataset.id;
      const isSelected = this.selectedIds.has(id);
      const chk = item.querySelector('input');
      chk.checked = isSelected;
      item.classList.toggle('selected', isSelected);
    });
  }

  getSelectedModelIds() {
    return Array.from(this.selectedIds);
  }

  getModelColor(modelId) {
    return this.modelColors[modelId] || '#00b4d8';
  }
}
