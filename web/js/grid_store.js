/**
 * grid_store.js
 * Carga diferida, validación y caché en memoria de campos 2D reales.
 * Contrato: un documento por model_id/fecha + manifiesto en data/grids/manifest.json.
 * Soporta documentos individuales y, a futuro, lotes mensuales con arreglo `grids`.
 * Laboratorio de Oceanografía Física (LOFA) - Universidad Austral de Chile (UACh)
 */

class GridStore {
  constructor(options = {}) {
    this.baseUrl = options.baseUrl || 'data/grids/';
    if (!this.baseUrl.endsWith('/')) this.baseUrl += '/';
    this.manifestUrl = `${this.baseUrl}manifest.json`;
    this.manifest = null;
    this.manifestPromise = null;
    this.cache = new Map();
    this.inflight = new Map();
    this.activeController = null;
  }

  async loadManifest() {
    if (this.manifest) return this.manifest;
    if (!this.manifestPromise) {
      this.manifestPromise = fetch(this.manifestUrl, { cache: 'no-store' })
        .then((response) => {
          if (!response.ok) {
            throw new Error(`Manifiesto 2D no disponible (${response.status})`);
          }
          return response.json();
        })
        .then((manifest) => {
          if (!manifest || typeof manifest !== 'object' ||
              !manifest.grids || typeof manifest.grids !== 'object') {
            throw new Error('Manifiesto 2D con estructura inválida');
          }
          this.manifest = manifest;
          return manifest;
        })
        .catch((error) => {
          this.manifestPromise = null;
          throw error;
        });
    }
    return this.manifestPromise;
  }

  static key(modelId, date) {
    return `${modelId}|${date}`;
  }

  async getGrid(modelId, date) {
    if (!modelId || !date) return null;
    const key = GridStore.key(modelId, date);
    if (this.cache.has(key)) return this.cache.get(key);

    const manifest = await this.loadManifest();
    const modelEntries = manifest.grids[modelId];
    const entry = modelEntries && modelEntries[date];
    if (!entry || !entry.file) return null;

    if (this.inflight.has(key)) return this.inflight.get(key);

    if (this.activeController) this.activeController.abort();
    const controller = new AbortController();
    this.activeController = controller;

    const promise = fetch(`${this.baseUrl}${entry.file}`, {
      signal: controller.signal,
      cache: 'no-cache'
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Campo 2D ${modelId}/${date} no disponible (${response.status})`);
        }
        return response.json();
      })
      .then((document) => {
        const grid = this.normalize(document, modelId, date);
        if (!grid) {
          throw new Error(`Campo 2D ${modelId}/${date} inválido`);
        }
        this.cache.set(key, grid);
        return grid;
      })
      .finally(() => {
        this.inflight.delete(key);
        if (this.activeController === controller) this.activeController = null;
      });

    this.inflight.set(key, promise);
    return promise;
  }

  /**
   * Normaliza un documento individual o un lote mensual futuro.
   * Rechaza cualquier rejilla cuyo model_id/date no coincida con lo solicitado.
   */
  normalize(document, modelId, date) {
    if (!document || typeof document !== 'object') return null;

    let source = document;
    if (Array.isArray(document.grids)) {
      source = document.grids.find((item) => (
        item && item.model_id === modelId && item.date === date
      ));
    }
    if (!source || typeof source !== 'object') return null;
    if (source.model_id !== modelId || source.date !== date) return null;

    const slp = source.slp || source.current_slp;
    const anomaly = source.anomaly || source.current_anomaly || null;
    if (!Array.isArray(source.lats) || !Array.isArray(source.lons)) return null;
    if (!Array.isArray(slp)) return null;

    const rows = source.lats.length;
    const cols = source.lons.length;
    if (rows < 2 || cols < 2 || slp.length !== rows) return null;

    for (const row of slp) {
      if (!Array.isArray(row) || row.length !== cols) return null;
    }
    if (anomaly !== null) {
      if (!Array.isArray(anomaly) || anomaly.length !== rows) return null;
      for (const row of anomaly) {
        if (!Array.isArray(row) || row.length !== cols) return null;
      }
    }

    return {
      model_id: modelId,
      date,
      forecast_hour: Number.isInteger(source.forecast_hour) ? source.forecast_hour : null,
      anomaly_reference: source.anomaly_reference || null,
      lats: source.lats,
      lons: source.lons,
      slp,
      anomaly
    };
  }

  clearActiveRequest() {
    if (this.activeController) {
      this.activeController.abort();
      this.activeController = null;
    }
  }
}