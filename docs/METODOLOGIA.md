# Metodología de Cálculo y Definiciones Físicas del Anticiclón del Pacífico Sur (APS)
### Laboratorio de Oceanografía Física (LOFA) — Universidad Austral de Chile

---

## 1. Definición Oceanográfica y Meteorológica

El **Anticiclón del Pacífico Sur (APS)** (o *South Pacific High / SPH*) es un centro de alta presión semipermanente subtropical localizado en el Océano Pacífico Suroriental. Forma parte de la rama descendente de la Celda de Hadley y es el principal motor del gradiente de presión que genera los vientos alisios del sureste a lo largo de las costas de Chile y Perú.

### Relevancia Oceanográfica:
- **Surgencia Costera (*Upwelling*):** El viento superficial paralelo a la costa genera transporte de Ekman hacia el océano abierto, provocando el ascenso de aguas subsuperficiales frías, ricas en nutrientes, que sostienen uno de los ecosistemas marinos más productivos del planeta (el Gran Ecosistema Marino de la Corriente de Humboldt).
- **Variabilidad Estacional:**
  - En **verano austral** (DJF), el APS se intensifica y migra hacia el sur (aprox. 35°S–38°S), extendiendo los vientos favorables a la surgencia hacia el centro-sur de Chile.
  - En **invierno austral** (JJA), el APS se debilita y migra hacia el norte (aprox. 25°S–30°S), permitiendo el paso de sistemas frontales de latitudes medias hacia la zona central y sur de Chile.

---

## 2. Dominio Espacial y Variables

### 2.1. Dominio de Detección
Para aislar el núcleo del APS de otras estructuras de alta presión transitorias (ej. anticiclones migratorios polares) se delimita la siguiente región de estudio:
- **Latitud:** $10^\circ \text{S}$ a $48^\circ \text{S}$
- **Longitud:** $120^\circ \text{W}$ a $70^\circ \text{W}$

### 2.2. Variable Principal
- **Presión a Nivel del Mar (*Sea Level Pressure*, SLP o MSLP):**
  - Unidades estándar: Hectopascales ($\text{hPa}$) o milibares ($\text{mbar}$). En archivos NetCDF frecuentemente se almacena en Pascales ($\text{Pa}$), por lo que se aplica el factor de conversión:
    $$\text{SLP}_{\text{hPa}} = \frac{\text{SLP}_{\text{Pa}}}{100}$$

---

## 3. Algoritmo de Identificación del Centro del APS

Para cada paso temporal $t$ de un modelo dado $m$:

### Paso 1: Suavizado Espacial (Opcional pero recomendado)
Para evitar que fluctuaciones locales de pequeña escala o ruido numérico del modelo falseen la posición del núcleo bárico, se aplica un suavizado espacial gaussiano o promedio móvil 2D sobre la matriz de presión:
$$\widetilde{\text{SLP}}(\phi, \lambda) = \mathcal{G}_\sigma * \text{SLP}(\phi, \lambda)$$
donde $\sigma$ típicamente equivale a $1.0^\circ - 1.5^\circ$ de resolución espacial.

### Paso 2: Localización del Máximo de Presión
La intensidad máxima y las coordenadas del centro se determinan como:
$$\text{PSA}_{max}(t) = \max_{(\phi, \lambda) \in \Omega} \widetilde{\text{SLP}}(\phi, \lambda, t)$$
$$(\phi_{APS}, \lambda_{APS}) = \arg\max_{(\phi, \lambda) \in \Omega} \widetilde{\text{SLP}}(\phi, \lambda, t)$$

Donde:
- $\text{PSA}_{max}$: Intensidad de la Presión Superficial Atmosférica central (hPa).
- $\phi_{APS}$: Latitud del centro (grados Sur).
- $\lambda_{APS}$: Longitud del centro (grados Oeste).

---

## 4. Cálculo de Anomalías

Las anomalías espaciales y temporales se calculan restando el ciclo estacional de referencia (climatología base):
$$\text{Anomalía}(\phi, \lambda, t) = \text{SLP}(\phi, \lambda, t) - \overline{\text{SLP}}_{\text{clim}}(\phi, \lambda, \text{mes}(t))$$

### Período Climatológico Estándar:
Se utiliza la normal climática internacional de 30 años recomendada por la OMM (**1991–2020**) obtenida a partir del reanálisis **ERA5** de Copernicus ECMWF.

---

## 5. Modelos Considerados en la Plataforma

La plataforma permite la ingestión y comparación de diversos productos:
1. **ERA5 (ECMWF):** Reanálisis atmosférico global de 5ª generación. Resolución nativa $0.25^\circ \times 0.25^\circ$. Modelo base de referencia histórica.
2. **NCEP/NCAR o NCEP-DOE R2:** Reanálisis de la NOAA. Útil para contrastes inter-reanálisis de largo plazo.
3. **GFS (NOAA):** Modelo de pronóstico operativo global. Permite extender el monitoreo a escala de pronóstico a 7–10 días.
4. **Simulaciones Regionales LOFA (ej. WRF / CROCO / ROMS):** Salidas de alta resolución modeladas por los investigadores y tesistas del laboratorio.
