# Metodología de Cálculo y Dinámica Físico-Oceanográfica del Anticiclón del Pacífico Sur (APS / ASPS)
### Laboratorio de Oceanografía Física (LOFA) — Universidad Austral de Chile (UACh)
*Documento Técnico y Metodológico de Referencia para el Observatorio Multimodelo del APS*  
*Versión:* 5.3 (Noviembre 2026)  
*Director Científico:* Dr. José Garcés Vargas  
*Licencia:* GNU Affero General Public License v3 (AGPLv3)

---

## 1. Fundamentos Geofísicos y Oceanográficos del APS

El **Anticiclón del Pacífico Sur (APS)** (*South Pacific Subtropical Anticyclone, ASPS / SPH*) constituye la entidad barométrica motora fundamental de la circulación atmósfera-océano en el Pacífico Suroriental y a lo largo de las costas de Chile y Perú.

```
                              CELDA DE HADLEY
              Ecuador (0°)                       Subtrópico (30°S)
                   ▲                                     │
    Ascenso        │                                     ▼  Subsidencia Adiabática
    Convectivo     │                                  ┌─────┐
    Intertropical  │                                  │ APS │ (Núcleo Submalla + Centroide)
                   └──────────────────────────────────┤     │
                                                      └─────┘
                                                         │
                                                         ▼
                                            Campo de Sobrepresión Barométrica
                                       Masa Integrada (I_vol) y Área (A_1020)
                                                         │
                                                         ▼ Ondas de Rossby / Bloqueo
                                            DESACOPLE NÚCLEO–CENTROIDE (D_nc, θ)
                                            • D_nc < 300 km: Régimen Concéntrico Simétrico
                                            • θ ∈ [30°, 120°]: Cuña Costera / Compresión (Chile Central)
                                            • θ ∈ [120°, 210°]: Bloqueo Patagónico Austral (Norpatagonia)
```

### 1.1 Balance Dinámico y Subsidencia Subtropical
El APS es una componente de gran escala de la rama descendente de la **Celda de Hadley**. En torno a los $25^\circ\text{S} - 35^\circ\text{S}$, masas de aire secas provenientes de la alta troposfera descienden mediante subsidencia adiabática dinámica. Al comprimirse, la masa de aire se calienta adiabáticamente, originando una pronunciada **inversión térmica de subsidencia** entre los $600\text{ m}$ y $1200\text{ m}$ sobre el nivel del mar.

### 1.2 Balance Geostrófico
A escala sinóptica, las fuerzas dominantes en la atmósfera libre sobre el océano son la Fuerza del Gradiente Horizontal de Presión ($\vec{F}_P$) y la Aceleración Aparente de Coriolis ($\vec{F}_C$):
$$-\frac{1}{\rho_a} \nabla_h P - f \hat{k} \times \vec{V}_g = 0$$
Donde $f = 2\Omega \sin\phi < 0$ en el Hemisferio Sur, lo que imprime una circulación anticiclónica en sentido antihorario (levógiro).

---

## 2. Dominio Espacial y Fuentes de Datos

### 2.1 Dominio Geográfico Físico
Definido por el Dr. José Garcés Vargas para abarcar la celda de subsidencia y sus cuñas hacia el cono sur sin interferencia del frente polar antártico:
$$\Omega_{\text{track}} = \{ (\phi, \lambda) \mid -48.0^\circ\text{S} \le \phi \le -18.0^\circ\text{S}, \ -120.0^\circ\text{W} \le \lambda \le -70.0^\circ\text{W} \}$$

### 2.2 Caja de Monitoreo Norpatagonia
Para diagnosticar la intrusión de dorsales de bloqueo hacia los fiordos y canales chilenos:
$$\Omega_{\text{patagonia}} = \{ (\phi, \lambda) \mid -45.0^\circ\text{S} \le \phi \le -41.0^\circ\text{S}, \ -78.0^\circ\text{W} \le \lambda \le -72.0^\circ\text{W} \}$$

### 2.3 Climatología Normal Estándar OMM (1994–2023)
Se utiliza como línea base la normal climática internacional de 30 años recomendada por la Organización Meteorológica Mundial (OMM), correspondiente a la era satelital moderna de asimilación variacional 4D-Var en ERA5.

---

## 3. Formulación Matemática del Par Dinámico (V5.3)

### 3.1 Corrección Esférica: Elemento de Área Diferencial $dA(\phi)$
$$dA(\phi) = R_{\oplus}^2 \cdot \cos\left(\frac{\pi \phi}{180}\right) \cdot \left(\frac{\pi \Delta\phi}{180}\right) \cdot \left(\frac{\pi \Delta\lambda}{180}\right) \quad [\text{km}^2]$$
Con $R_{\oplus} = 6371.0088\text{ km}$ y $\Delta\phi = \Delta\lambda = 0.25^\circ$.

### 3.2 Ajuste Parabólico 2D Submalla (`fit_quadratic_2d`)
Para superar la limitación de nodos discretos de $0.25^\circ$ y resolver el vértice continuo:
$$P(x, y) = a x^2 + b y^2 + c x y + d x + e y + f$$
Ajustado por Mínimos Cuadrados Ordinarios en ventana $5 \times 5$ ($w=2$) centrada en el máximo discreto. En el vértice continuo $\nabla P = 0$:
$$\begin{pmatrix} 2a & c \\ c & 2b \end{pmatrix} \begin{pmatrix} x_{\text{opt}} \\ y_{\text{opt}} \end{pmatrix} = -\begin{pmatrix} d \\ e \end{pmatrix}$$

**Condiciones Físicas de Validación (Hessiano):**
1. $a < 0$, $b < 0$ (concavidad negativa).
2. $\det(H) = 4ab - c^2 > 10^{-4}$ (extremo cerrado estable).
3. $|x_{\text{opt}}| \le 0.35^\circ$, $|y_{\text{opt}}| \le 0.35^\circ$ (confinamiento submalla).
4. **Salvaguarda costera:** Si $(\phi_{\max}, \lambda_{\max})$ cae sobre la máscara continental Natural Earth 10m, se recurre al nodo discreto marino.

### 3.3 Extensión Areal ($A_{1020}$) y Masa Integrada ($I_{\text{vol}}$)
$$A_{1020} = \frac{1}{10^6} \sum_{\text{mar}, P \ge 1020} dA(\phi) \quad \left[10^6\text{ km}^2\right]$$
$$I_{\text{vol}} = \frac{1}{10^6} \sum_{\text{mar}} \max(P - 1020.0, \, 0.0) \cdot dA(\phi) \quad \left[\text{hPa} \cdot 10^6\text{ km}^2\right]$$
$$\bar{H}_{\text{eff}} = \frac{I_{\text{vol}}}{A_{1020}} \quad [\text{hPa}]$$

### 3.4 Centroide Barométrico Adaptativo ($\phi_c, \lambda_c$)
Resuelve la desaparición estacional de la isóbara de 1020 hPa en mayo:
$$P_{\text{ref}} = \begin{cases} 1020.0\text{ hPa} & \text{si } P_{\max} \ge 1020.0\text{ hPa} \\ P_{\max} - 4.0\text{ hPa} & \text{si } P_{\max} < 1020.0\text{ hPa} \end{cases}$$
$$\phi_c = \frac{\sum_{\text{mar}} \phi \cdot \max(P - P_{\text{ref}}, 0) \cdot dA}{\sum_{\text{mar}} \max(P - P_{\text{ref}}, 0) \cdot dA}, \quad \lambda_c = \frac{\sum_{\text{mar}} \lambda \cdot \max(P - P_{\text{ref}}, 0) \cdot dA}{\sum_{\text{mar}} \max(P - P_{\text{ref}}, 0) \cdot dA}$$

### 3.5 Vector de Desacople Físico ($D_{nc}$ y $\theta$)
* **Distancia Ortoédrica (Haversine):**
  $$D_{nc} = 2 R_{\oplus} \arcsin\left(\sqrt{\sin^2\left(\frac{\Delta\phi}{2}\right) + \cos\phi_{\max}\cos\phi_c \sin^2\left(\frac{\Delta\lambda}{2}\right)}\right) \quad [\text{km}]$$
* **Rumbo Náutico Esférico ($\theta$):**
  $$\theta = \left(\operatorname{atan2}(\sin\Delta\lambda \cos\phi_c, \, \cos\phi_{\max}\sin\phi_c - \sin\phi_{\max}\cos\phi_c \cos\Delta\lambda) \cdot \frac{180}{\pi} + 360\right) \pmod{360}$$

---

## 4. Supresión del Efecto Muro: Convolución Normalizada

Para evitar la contaminación de los gradientes marinos por valores ficticios en tierra firme:
$$P_{\text{smooth}}(\phi, \lambda) = \frac{G_\sigma * [P(\phi, \lambda) \cdot W(\phi, \lambda)]}{G_\sigma * W(\phi, \lambda) + \epsilon}$$
Donde $W(\phi, \lambda) = 1.0$ en mar abierto y $0.0$ en tierra firme, derivado de la máscara vectorial Natural Earth 10m (`ne_10m_land.shp`). Los valores sobre tierra se mantienen como `NaN` estricto.

---

## 5. Nota Metodológica: Exclusión del Índice de Bakun

En acuerdo con el Dr. José Garcés Vargas, el **Índice de Surgencia de Bakun ($UI$)** y las estimaciones de transporte de Ekman costero fueron **excluidos formalmente de esta versión del observatorio**.

**Motivación:**
El modelamiento riguroso de la surgencia costera requiere descomponer la Capa Límite Atmosférica Marina (CLAM), considerar el arrastre no lineal del Chorro Costero de Bajo Nivel (CLLJ) y contar con densidad oceanográfica in-situ ($\rho_w(S, T, p)$). Intentar derivar la surgencia a partir de gradientes isobáricos sinópticos generales introduce distorsiones de orden de magnitud. Se prioriza consolidar la física, morfología, masa y desacople del domo del APS antes de abordar cadenas tróficas acopladas.

---

## 6. Validación Estadística y Verificación de Pronóstico

Siguiendo normas internacionales de la OMM y S-RIP:
* Error Cuadrático Medio: $\text{RMSE} = \sqrt{\frac{1}{N}\sum (M_i - O_i)^2}$ [hPa].
* Sesgo Sistemático: $\text{BIAS} = \overline{M} - \overline{O}$ [hPa].
* Índice de Habilidad de Willmott: $d = 1 - \frac{\sum (M_i - O_i)^2}{\sum (|M_i - \overline{O}| + |O_i - \overline{O}|)^2}$.
* Error de posición geodésico: Distancia ortodrómica media por Gran Círculo en kilómetros.

---

## 6.1 Publicación de Campos 2D Reales por Fecha

El trazado de isóbaras del cliente (`web/js/maps.js`, método Marching Squares)
no modela el campo de presión: únicamente dibuja contornos sobre una rejilla
real ya publicada. Para que cualquier fecha del cronograma muestre isóbaras,
`pipeline/export_historical_grids.py` genera **un documento por día real**
presente en cada NetCDF de ERA5:

1. Se promedia la presión a nivel del mar a resolución diaria y se recorta al
   dominio físico del APS ($[-48^\circ\text{S}, -18^\circ\text{S}] \times
   [-120^\circ\text{W}, -70^\circ\text{W}]$).
2. La ventana operativa reciente (por defecto, los últimos 90 días disponibles)
   se publica a $0.5^\circ$ (61×101 celdas); el resto del histórico a $1.0^\circ$
   (31×51 celdas). No se interpola ni se rellena ninguna fecha ausente.
3. Cada documento se valida contra el contrato de `pipeline/grid_export.py` y
   se escribe de forma atómica, registrándose en
   `web/data/grids/manifest.json`. Un pase reducido posterior no degrada una
   rejilla completa ya publicada.

Esta estrategia garantiza que **toda isóbara visible provenga de datos
institucionales reales**, en concordancia con la directiva 2.3 de `AGENTS.md`.
Las rejillas se sirven bajo demanda desde `web/data/grids/`, sin incorporar
campos al payload principal ni introducir herramientas de compilación en `web/`.

---

## 7. Referencias Científicas Clave

1. **Garcés-Vargas, J., et al. (2026):** *Cinemática, Morfología 2D y Desacople Barométrico del Anticiclón del Pacífico Sur*. Laboratorio de Oceanografía Física (LOFA), Universidad Austral de Chile.
2. **Hersbach, H., et al. (2020):** *The ERA5 global reanalysis*. Quarterly Journal of the Royal Meteorological Society, 146(730), 1999–2049.
3. **Hoskins, B. J., et al. (1985):** *On the use and significance of isentropic potential vorticity maps*. Q. J. R. Meteorol. Soc., 111, 877–946.
4. **Peixoto, J. P., & Oort, A. H. (1992):** *Physics of Climate*. American Institute of Physics.
5. **Willmott, C. J. (1981):** *On the validation of models*. Physical Geography, 2(2), 184–194.
