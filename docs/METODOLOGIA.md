# Metodología de Cálculo y Dinámica Físico-Oceanográfica del Anticiclón del Pacífico Sur (APS)
### Laboratorio de Oceanografía Física (LOFA) — Universidad Austral de Chile (UACh)
*Documento Técnico y Metodológico de Referencia para el Observatorio Multimodelo del APS*  
*Versión:* 3.0 (Revisión de Octubre 2026)  
*Licencia:* GNU Affero General Public License v3 (AGPLv3)

---

## 1. Fundamentos Geofísicos y Oceanográficos del APS

El **Anticiclón del Pacífico Sur (APS)** (*South Pacific Subtropical High, SPH*) constituye la entidad barotrópica y baroclínica motora fundamental de la circulación atmósfera-océano en el Pacífico Suroriental y el margen occidental de América del Sur.

```
                              CELDA DE HADLEY
              Ecuador (0°)                       Subtrópico (30°S)
                   ▲                                     │
    Ascenso        │                                     ▼  Subsidencia
    Convectivo     │                                  ┌─────┐
    Intertropical  │                                  │ APS │ (Núcleo de Alta Presión)
                   └──────────────────────────────────┤     │
                                                      └─────┘
                                                         │
                                                         ▼ Gradiente Barométrico Zonal
                                            Costas de Chile y Perú
                                            Vientos del Sur / SO (Alisios)
                                                         │
                                                         ▼ Fuerza de Coriolis (f < 0)
                                            Transporte de Ekman hacia el Oeste
                                                         │
                                                         ▼ Bombeo Vertical
                                            SURGENCIA COSTERA (AESS)
```

### 1.1 Balance Dinámico y Circulación Subtropical
El APS es una componente de gran escala de la rama descendente de la **Celda de Hadley**. En torno a los $25^\circ\text{S} - 35^\circ\text{S}$, masas de aire secas provenientes de la alta troposfera descienden mediante subsidencia adiabática dinámica. Al comprimirse, la masa de aire se calienta adiabáticamente, originando una pronunciada **inversión térmica de subsidencia** entre los $600\text{ m}$ y $1200\text{ m}$ sobre el nivel del mar. Esta inversión atrapa la humedad marina superficial formando los extensos mantos de estratocúmulos marinos subtropicales (*marine stratocumulus deck*) característicos del Pacífico Suroriental.

### 1.2 Balance Geostrófico en el Hemisferio Sur
A escala sinóptica, las fuerzas dominantes en la atmósfera libre sobre el océano son la Fuerza del Gradiente Horizontal de Presión ($\vec{F}_P$) y la Aceleración Aparente de Coriolis ($\vec{F}_C$):
$$-\frac{1}{\rho_a} \nabla_h P - f \hat{k} \times \vec{V}_g = 0$$

Desglosando en componentes zonales ($u_g$) y meridionales ($v_g$):
$$u_g = -\frac{1}{\rho_a f} \frac{\partial P}{\partial y}, \qquad v_g = \frac{1}{\rho_a f} \frac{\partial P}{\partial x}$$

Donde:
* $\rho_a \approx 1.225\text{ kg/m}^3$: Densidad media del aire a nivel del mar.
* $f = 2\Omega \sin\phi < 0$: Parámetro de Coriolis en el Hemisferio Sur ($\Omega = 7.2921 \times 10^{-5}\text{ rad/s}$, $\phi$ es la latitud negativa).
* Al ser $f < 0$, alrededor del núcleo central de alta presión ($\nabla P < 0$) la circulación geostrófica se orienta en **sentido antihorario (levógiro)**.

---

## 2. Dominio Espacial y Fuentes de Datos

### 2.1 Dominio Geográfico Homogéneo
Para evitar distorsiones en las métricas multidecadales y garantizar la captura completa del APS incluso en sus desplazamientos más extremos hacia el polo o el oeste, el observatorio utiliza dos dominios estandarizados:

1. **Caja Homogénea de Descarga y Almacenamiento:**
   $$\Omega_{\text{descarga}} = \{ (\phi, \lambda) \mid -56.0^\circ \le \phi \le -10.0^\circ, \ -130.0^\circ \le \lambda \le -65.0^\circ \}$$
   * Abarca desde el norte de Perú hasta el Paso Drake / Cabo de Hornos, y desde el Pacífico central hasta el borde continental oriental.

2. **Ventana de Búsqueda del Centro Bárico:**
   $$\Omega_{\text{track}} = \{ (\phi, \lambda) \mid -54.0^\circ \le \phi \le -18.0^\circ, \ -125.0^\circ \le \lambda \le -68.0^\circ \}$$

### 2.2 Reanálisis y Modelos Integrados
* **ERA5 (ECMWF):** Reanálisis atmosférico horario de 5ª generación, resolución horizontal nativa $0.25^\circ \times 0.25^\circ$. Variable procesada: `mean_sea_level_pressure` (`msl` en Pa). Representa el estándar de verdad para el cálculo climatológico y validación.
* **NOAA GFS (Global Forecast System):** Salidas operativas a 0.25° del ciclo $00\text{Z}$, procesadas a intervalos de $24\text{ h}$ hasta $+168\text{ h}$ (7 días). Variable: `prmsl` (Pressure Reduced to Mean Sea Level).
* **Modelos CMIP6 / Simulaciones LOFA:** Modelaciones numéricas regionales y proyecciones de cambio climático forzadas por el laboratorio.

---

## 3. Máscara Oceánica Estricta (Land-Sea Boundary Condition)

### 3.1 El Problema Físico de las Altas Presiones Continentales
Durante el invierno austral (junio a agosto), la superficie continental de la Patagonia argentina experimenta un enfriamiento radiativo extremo. Esto genera densas y frías **altas presiones térmicas continentales** sobre las mesetas de Santa Cruz y Chubut, y la reducción barométrica a nivel del mar sobre la Cordillera de los Andes produce valores locales que pueden superar los $1034\text{ hPa}$.

> [!CAUTION]
> Si no se impone una máscara oceánica real, una búsqueda simple de $\max(\text{MSLP})$ en un rectángulo geométrico selecciona erróneamente puntos sobre el continente argentino como el "núcleo del APS", falseando la climatología marina en más de 140 días históricos.

### 3.2 Formulación Matemática de la Línea Costera del Pacífico
Para garantizar que la identificación del centro sea **100% marina y subtropical**, se implementa una frontera analítica vectorial basada en la costa occidental de Sudamérica:

$$\lambda_{\text{costa}}(\phi) = \text{Interp}\left(\phi, \vec{\phi}_{\text{ref}}, \vec{\lambda}_{\text{ref}}\right)$$

Nodos de referencia oceanográfica fijados:
* $-10.0^\circ\text{S} \rightarrow -78.20^\circ\text{W}$ (Costa central de Perú)
* $-18.0^\circ\text{S} \rightarrow -71.20^\circ\text{W}$ (Arica)
* $-24.0^\circ\text{S} \rightarrow -70.40^\circ\text{W}$ (Antofagasta / Península de Mejillones)
* $-33.0^\circ\text{S} \rightarrow -71.65^\circ\text{W}$ (Valparaíso)
* $-37.0^\circ\text{S} \rightarrow -73.50^\circ\text{W}$ (Punta Lavapié / Golfo de Arauco)
* $-41.0^\circ\text{S} \rightarrow -73.80^\circ\text{W}$ (Canal de Chacao)
* $-46.5^\circ\text{S} \rightarrow -75.70^\circ\text{W}$ (Península de Taitao / Golfo de Penas)
* $-50.0^\circ\text{S} \rightarrow -75.40^\circ\text{W}$ (Archipiélago Reina Adelaida)
* $-54.0^\circ\text{S} \rightarrow -73.50^\circ\text{W}$ (Boca occidental del Estrecho de Magallanes)
* $-56.0^\circ\text{S} \rightarrow -68.50^\circ\text{W}$ (Cabo de Hornos / Drake)

### 3.3 Dominio Oceánico Válido
$$\Omega_{\text{mar}} = \left\{ (\phi, \lambda) \in \Omega_{\text{track}} \ \middle|\ \lambda < \lambda_{\text{costa}}(\phi) \right\}$$

Todo punto en tierra firme o cordillera ($\lambda \ge \lambda_{\text{costa}}(\phi)$) se enmascara con valor `NaN`:
$$\text{MSLP}_{\text{mar}}(\phi, \lambda, t) = \begin{cases} \text{MSLP}(\phi, \lambda, t) & \text{si } (\phi, \lambda) \in \Omega_{\text{mar}} \\ \text{NaN} & \text{en otro caso} \end{cases}$$

---

## 4. Algoritmo de Rastreo del Centro y Climatología Dinámica

### 4.1 Extracción Diaria del Centro Bárico
Para cada fecha $t$:
1. Se computa el promedio temporal diario a partir de los campos horarios:
   $$\overline{\text{SLP}}(\phi, \lambda, t) = \frac{1}{24} \sum_{h=0}^{23} \text{SLP}(\phi, \lambda, t, h)$$
2. Se aplica la máscara oceánica $\Omega_{\text{mar}}$.
3. Se identifica el máximo absoluto mediante optimización sobre el mallado 2D:
   $$\text{PSA}(t) = \max_{(\phi, \lambda) \in \Omega_{\text{mar}}} \left\{ \frac{\overline{\text{SLP}}(\phi, \lambda, t)}{100} \right\} \quad [\text{hPa}]$$
   $$(\phi_{\text{APS}}, \lambda_{\text{APS}})(t) = \arg\max_{(\phi, \lambda) \in \Omega_{\text{mar}}} \left\{ \overline{\text{SLP}}(\phi, \lambda, t) \right\}$$

### 4.2 Anomalía Climatológica Basada en el Día del Año (DOY)
El ciclo estacional del APS describe una migración latitudinal de $\sim 7^\circ$ y una oscilación barométrica de $\sim 4\text{ hPa}$. La anomalía diaria ($\Delta P$) no se calcula contra un escalar estático arbitrario (como los antiguos $1022.0\text{ hPa}$), sino respecto a la media climatológica del **Día del Año ($DOY \in [1, 366]$)** calculada sobre el período de referencia multidecadal:

$$\overline{\text{PSA}}_{\text{clim}}(d) = \frac{1}{Y} \sum_{y=1}^Y \text{PSA}(y, d)$$
$$\Delta P(t) = \text{PSA}(t) - \overline{\text{PSA}}_{\text{clim}}(\text{DOY}(t)) \quad [\text{hPa}]$$

* $\Delta P > +3.0\text{ hPa}$: Evento de Bloqueo o Intensa Dorsal Subtropical cálida.
* $\Delta P < -3.0\text{ hPa}$: Relajación barométrica severa o incursión de ciclones extratropicales.

---

## 5. Dinámica de Surgencia Costera (Índice de Bakun UI)

### 5.1 Acoplamiento Barométrico y Viento Costero
El gradiente horizontal de presión perpendicular a la costa entre el océano abierto (evaluado a $6^\circ$ de longitud mar adentro, $\approx 550\text{ a }650\text{ km}$) y la estación costera genera viento geostrófico paralelo al borde continental:

$$\frac{\partial P}{\partial x} \approx \frac{P_{\text{costa}} - P_{\text{océano}}}{\Delta x} \quad [\text{Pa/m}]$$
$$v_g = \frac{1}{\rho_a f} \frac{\partial P}{\partial x}$$

Dado que en el Pacífico Suroriental $P_{\text{océano}} > P_{\text{costa}}$ (por la presencia del APS en el mar y bajas térmicas sobre tierra), $\partial P/\partial x < 0$. Como $f < 0$, resulta $v_g > 0$, lo que corresponde a **vientos del sur** dirigidos hacia el ecuador.

### 5.2 Capa Límite Marina y Esfuerzo Cortante ($\tau_y$)
En la capa superficial de fricción (a $10\text{ m}$ sobre el nivel del mar), la fricción reduce la magnitud del viento geostrófico en aproximadamente un 25% y desvía ligeramente el flujo hacia la baja presión:
$$v_{10} = \gamma \cdot v_g \quad (\gamma \approx 0.75)$$

El esfuerzo cortante o tensión tangencial del viento sobre la superficie del agua ($\tau_y$) se modela mediante la formulación cuadrática aerodinámica de Large & Pond (1981):
$$\tau_y = \rho_a C_d |\vec{V}_{10}| v_{10} \quad [\text{N/m}^2]$$
Donde $C_d \approx 1.3 \times 10^{-3}$ es el coeficiente de arrastre adimensional para condiciones oceánicas estándar.

### 5.3 Transporte de Ekman y Formulación de Bakun (1973)
Por la aceleración de Coriolis, el transporte neto de masa de la capa superficial de Ekman ($M_{Ex}$) se dirige $90^\circ$ a la izquierda del viento en el Hemisferio Sur, es decir, mar adentro hacia el oeste:
$$M_{Ex} = \frac{\tau_y}{\rho_w |f|} \quad [\text{kg}/(\text{m}\cdot\text{s}) \text{ o } \text{m}^3/(\text{s}\cdot\text{m})]$$

El **Índice de Surgencia de Bakun ($UI$)** normaliza este volumen por cada kilómetro lineal de línea costera:
$$UI = \frac{\tau_y}{\rho_w |f|} \times 1000 \quad \left[\frac{\text{m}^3}{\text{s} \cdot \text{km de costa}}\right]$$

```
┌─────────────────┬───────────────────┬──────────────────────────────────────────┐
│ Rango UI        │ Clasificación     │ Efecto Ecológico y Oceanográfico         │
├─────────────────┼───────────────────┼──────────────────────────────────────────┤
│ UI > 600        │ Muy Intensa       │ Chorro Costero de Bajo Nivel (CLLJ)      │
│ 300 < UI ≤ 600  │ Fuerte            │ Ascenso vigoroso de AESS; floración      │
│ 80 < UI ≤ 300   │ Moderada          │ Bombeo continuo; fertilización fótica    │
│ 0 ≤ UI ≤ 80     │ Débil / Neutra    │ Mínima divergencia superficial           │
│ UI < 0          │ Hundimiento       │ Relajación o paso de tormenta polar      │
└─────────────────┴───────────────────┴──────────────────────────────────────────┘
```

---

## 6. Motor Cartográfico Marching Squares

Para sustituir las simplificaciones circulares o elípticas geométricas por contornos termodinámicamente continuos, el dashboard emplea una implementación nativa del algoritmo **Marching Squares**:

1. La rejilla 2D de presión $\text{SLP}(\phi_i, \lambda_j)$ se divide en celdas cuadriláteras elementales de $2 \times 2$ vértices.
2. Para cada isobara objetivo $C \in \{1012, 1016, 1020, 1024, 1028\}\text{ hPa}$, se genera un índice binario de 4 bits según si el valor de cada vértice es $\ge C$ (16 configuraciones topológicas).
3. Los puntos de cruce en los bordes de cada celda se determinan por interpolación lineal:
   $$x_{\text{iso}} = x_1 + (C - P_1) \frac{x_2 - x_1}{P_2 - P_1}$$
4. Los segmentos de línea interpolados se encadenan topológicamente formando polilíneas suaves que representan con precisión dorsales, vaguadas y el efecto de bloqueo contra la Cordillera de los Andes.

---

## 7. Métricas de Validación Estadística Inter-Modelo (Normas OMM / S-RIP)

Siguiendo los lineamientos internacionales del *SPARC Reanalysis Intercomparison Project (S-RIP)* y la Organización Meteorológica Mundial (OMM), cada modelo $M$ se valida cuantitativamente frente al reanálisis de referencia $O$ (ERA5):

### 7.1 Error Cuadrático Medio (RMSE)
Evalúa la magnitud cuadrática media del error en la intensidad del núcleo:
$$\text{RMSE} = \sqrt{\frac{1}{N} \sum_{i=1}^N \left( M_i - O_i \right)^2} \quad [\text{hPa}]$$

### 7.2 Sesgo Medio (BIAS)
Indica si el modelo sobrestima o subestima sistemáticamente la presión del APS:
$$\text{BIAS} = \frac{1}{N} \sum_{i=1}^N \left( M_i - O_i \right) = \overline{M} - \overline{O} \quad [\text{hPa}]$$

### 7.3 Correlación Lineal de Pearson ($r$)
Cuantifica la destreza del modelo en capturar la sincronía temporal de las fluctuaciones sinópticas:
$$r = \frac{\sum_{i=1}^N (M_i - \overline{M})(O_i - \overline{O})}{\sqrt{\sum_{i=1}^N (M_i - \overline{M})^2} \sqrt{\sum_{i=1}^N (O_i - \overline{O})^2}}$$

### 7.4 Distancia Ortodrómica por Gran Círculo (Fórmula de Haversine)
Mide el error espacial real en kilómetros entre el centro pronosticado/simulado $(\phi_M, \lambda_M)$ y el observado $(\phi_O, \lambda_O)$ sobre la esfera terrestre ($R = 6371.0\text{ km}$):

$$\Delta\phi = \phi_M - \phi_O, \qquad \Delta\lambda = \lambda_M - \lambda_O$$
$$a = \sin^2\left(\frac{\Delta\phi}{2}\right) + \cos(\phi_O) \cos(\phi_M) \sin^2\left(\frac{\Delta\lambda}{2}\right)$$
$$d_{\text{error}} = 2 R \arcsin\left(\sqrt{a}\right) \quad [\text{km}]$$

### 7.5 Índice de Habilidad de Willmott ($d$)
Medida adimensional estandarizada de concordancia ($d \in [0, 1]$) insensible a diferencias de escala:
$$d = 1 - \frac{\sum_{i=1}^N (M_i - O_i)^2}{\sum_{i=1}^N \left( |M_i - \overline{O}| + |O_i - \overline{O}| \right)^2}$$
Un valor $d > 0.85$ denota excelente habilidad predictiva sinóptica.

---

## 8. Reproducibilidad y Descarga de Datos

El observatorio garantiza la ciencia abierta y la reproducibilidad total:
* **Series Multimodelo Consolidadas:** Disponibles en formato CSV compatible con R, Python (Pandas) y MATLAB en `web/data/aps_multimodel_metrics_lofa.csv`.
* **Código Fuente:** Repositorio oficial público alojado en GitHub:  
  [https://github.com/Laboratorio-Oceanografia-Fisica-UACh/dashboard-APS](https://github.com/Laboratorio-Oceanografia-Fisica-UACh/dashboard-APS).
* **Contacto Científico:** Laboratorio de Oceanografía Física (LOFA), Universidad Austral de Chile, Valdivia, Chile.
