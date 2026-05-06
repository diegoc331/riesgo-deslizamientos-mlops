# Pitch — Sistema Predictivo de Riesgo de Deslizamientos en Antioquia

**Presentación:** 7 minutos  
**Proyecto:** Ciencia de Datos II — Universidad de Medellín  
**Fecha:** Mayo 2026

---

## Minuto 1 — El Problema (con números reales)

### Gancho

> *"Entre 2019 y 2022, Antioquia registró 945 deslizamientos. 115 personas murieron. 56.353 fueron afectadas. Ninguno fue anticipado con un sistema de datos."*

### El problema hoy

- Las entidades de gestión del riesgo (DAGRD, DAPARD) operan **100% reactivo**
- No existe ningún sistema que les diga con días de anticipación *"esta semana es de alto riesgo"*
- Cuando el evento ocurre, ya es tarde para evacuar o pre-posicionar recursos

> **Fuente:** UNGRD — Emergencias Colombia 2019–2022 (`wwkg-r6te`)

---

## Minuto 2 — La Oportunidad en los Datos

### Hay una señal predecible

Antioquia tiene **dos temporadas claras** de deslizamientos:

```
Ene:  11  ██
Feb:  26  █████
Mar: 102  ████████████████████   ← temporada alta inicia
Abr: 111  ██████████████████████
May:  81  ████████████████
Jun: 153  ██████████████████████████████  ← pico máximo
Jul:  79  ███████████████
Ago:  99  ███████████████████
Sep:  81  ████████████████
Oct:  92  ██████████████████
Nov:  87  █████████████████
Dic:  23  ████
```

- La precipitación acumulada de los días anteriores tiene **correlación directa** con la ocurrencia de deslizamientos
- Los datos ya existen y son **públicos y gratuitos**: IDEAM (precipitación, sub-horaria) + UNGRD (eventos, diaria)

### La pregunta que respondemos

> *¿Puede la precipitación acumulada de los últimos 14 días predecir si la semana siguiente tendrá deslizamientos en Antioquia?*

---

## Minuto 3 — La Solución

### Modelo binario con anticipación de 7 días

```
Precipitación acumulada últimos 14 días  (IDEAM API)
+ Precipitación máxima de la semana
+ Días con lluvia intensa
+ Estacionalidad del mes (encoding cíclico)
        ↓
   Modelo de clasificación binaria
        ↓
   Probabilidad de evento  →  Umbral  →  ALERTA / SIN ALERTA
```

### Con 7 días el DAGRD puede

- Alertar comunidades en zonas de ladera
- Pre-posicionar maquinaria y equipos de rescate
- Restringir acceso a vías críticas
- Activar brigadas de monitoreo

---

## Minuto 4 — La Decisión del Umbral

### Dos errores posibles — costos muy distintos

| Error | Situación | Consecuencia |
|---|---|---|
| **Falso positivo** | Dijimos "hay riesgo" y no ocurrió | Preparación innecesaria — costo operativo |
| **Falso negativo** | Dijimos "sin riesgo" y sí ocurrió | **Vidas humanas + infraestructura** |

### El umbral es una decisión de negocio, no técnica

> *"El umbral se calibra maximizando Recall, porque el costo de no detectar un evento real es inaceptablemente alto versus el costo de una falsa alarma."*

El gestor del riesgo puede mover ese umbral según su capacidad operativa — eso convierte el modelo en una **herramienta de decisión**, no solo un clasificador.

---

---

## Minuto 5 — Cierre

### Lo que tenemos hoy

- Pipeline de datos completo (IDEAM + UNGRD, 2019–2022)
- 945 eventos reales de Antioquia como base de entrenamiento
- 4 modelos comparados con validación cruzada estratificada en MLflow
- Umbral calibrado por Recall — decisión de negocio, no técnica

### Lo que viene

- Migrar de mensual a **semanal** (los datos ya lo permiten)
- Validación retrospectiva: *¿cuántos de los 945 eventos habríamos anticipado?*
- Cuantificación económica: costo de preparación vs. costo de respuesta

### Frase de cierre

> *"Con datos que ya existen, gratuitos y públicos, podemos darle al DAGRD 7 días de ventaja. La diferencia entre reaccionar y anticipar puede ser la diferencia entre una evacuación y una tragedia."*

---

## Cobertura de la Rúbrica

| Criterio | Peso | Cubierto en |
|---|---|---|
| Descripción del problema | 20% | Minuto 1 — cifras reales UNGRD |
| Importancia del problema | 10% | Minuto 2 — estacionalidad + señal predecible |
| Diseño de la propuesta | 10% | Minuto 3 — flujo claro con anticipación de 7 días |
| Diferenciación | 5% | Minuto 4 — umbral como decisión de negocio |
| Tecnología utilizada | 10% | Minuto 3 — flujo de solución con fuentes de datos |
| Viabilidad técnica | 15% | Minuto 3 — datos públicos, anticipación demostrable |
| Generación de valor | 25% | Minuto 1 + 4 — cifras reales + argumento del umbral |
| Escalabilidad | 5% | Minuto 5 — roadmap en lo que viene |

---

## Fuentes de Datos

| Fuente | Dataset ID | Descripción |
|---|---|---|
| IDEAM | `s54a-sgyg` | Precipitación sensores automáticos (mm), sub-horaria |
| UNGRD | `wwkg-r6te` | Emergencias Colombia 2019–2022, nivel diario |

Acceso vía API Socrata: `https://www.datos.gov.co/resource/{dataset_id}.json`
