# RetoIA_3 — Trade-off Docstring: SSE vs Polling vs WebSocket
## Semana 6 · Fase REFLEXIONA · Programación Distribuida del Lado del Cliente · UAN

---

## Análisis de los 4 Escenarios

### Escenario A: 10,000 usuarios concurrentes, precios cambian 2-3 veces/hora
**Decisión: SSE** ✅

**Preguntas difíciles que debo responder:**
1. *¿Cuántas peticiones TCP genera polling vs SSE con 10,000 usuarios y interval=5s?*
   - Polling: 10,000 × 12 peticiones/min = **120,000 req/min**
   - SSE: 10,000 conexiones persistentes, **0 peticiones adicionales**
2. *Si los precios cambian 2-3 veces/hora, ¿cuál es la tasa de peticiones vacías con polling?*
   - 120,000 req/min × 60 min = 7,200,000 peticiones/hora
   - Peticiones con datos reales: 2-3
   - Tasa de vacías: **99.99%** (la mayoría dice "sin cambios")
3. *¿Por qué el límite de 6 conexiones HTTP/1.1 afecta la decisión de SSE en el cliente?*
   - Bajo HTTP/1.1, el navegador permite solo 6 conexiones TCP simultáneas al mismo dominio.
   - Con 6 pestañas del panel EcoMarket, la 7ª petición (o petición REST normal) queda
     en estado `pending` indefinidamente — bloqueada sin error visible.
   - **Solución**: HTTP/2 multiplexación, o agrupar todos los eventos en un solo stream SSE.

---

### Escenario B: Inventario legacy, solo REST, actualización cada 1s
**Decisión: Polling obligatorio** ⚠️

**Justificación técnica:**
- SSE requiere que el servidor mantenga la conexión HTTP abierta con
  `Transfer-Encoding: chunked`. Un servidor REST clásico cierra la conexión
  tras cada respuesta — no puede hacer streaming.
- El cliente no puede forzar SSE si el servidor no lo soporta.
- Con cambios cada 1s y polling cada 1s: tasa de peticiones vacías ≈ 0.
  En este escenario, polling es tan eficiente como SSE (cada petición tiene datos frescos).
- **Costo real**: el cliente gestiona el ciclo `while activo:`, timeout por petición,
  y detención limpia — como en el Examen 1.

---

### Escenario C: Cliente móvil 3G, interrupciones cada 20-30s
**Decisión: SSE con backoff cuidadoso** ✅ (con matices)

**Análisis desde el cliente:**
- **A favor de SSE**: Last-Event-ID garantiza que eventos emitidos durante la
  desconexión se reenvíen al reconectar (si el servidor conserva historial).
  Con polling, los eventos emitidos durante el downtime se pierden para siempre.
- **Riesgo SSE en 3G**: interrupciones cada 20-30s generan un ciclo de reconexión
  frecuente. Sin backoff exponencial, esto crea una *tormenta de reconexiones*
  que agrava la congestión de red.
- **Backoff del cliente implementado**:
  ```
  Intento 1: espera 3s  (retry_ms × 2^0)
  Intento 2: espera 6s  (retry_ms × 2^1)
  Intento 3: espera 12s (retry_ms × 2^2)
  Intento 4: espera 24s (retry_ms × 2^3)
  Intento 5: espera 48s (retry_ms × 2^4) → detener
  ```
- **Cuándo polling sería mejor**: si el servidor no conserva historial de eventos,
  Last-Event-ID no sirve, y polling puede ser más predecible en redes muy inestables.

---

### Escenario D: Panel necesita recibir alertas Y enviar filtros dinámicos
**Decisión: WebSocket (Semana 11)** ✅

**Por qué SSE no es suficiente:**
- SSE es **unidireccional** (servidor → cliente). Para enviar filtros al servidor,
  el cliente necesitaría peticiones HTTP adicionales (POST), lo que crea correlación
  compleja de estado entre la sesión SSE y las peticiones REST.
- **WebSocket** permite enviar `{"accion":"filtrar","categoria":"Electronica"}` y
  recibir alertas por la **misma conexión bidireccional**.
- **Cuándo NO usar WebSocket**: si el único requisito es recibir datos del servidor,
  SSE es más simple, compatible con proxies HTTP estándar, y tiene reconexión
  automática nativa con Last-Event-ID.

---

## Tabla Resumen

| Factor de Decisión | Polling | SSE | WebSocket |
|---|---|---|---|
| Servidor legacy (REST) | ✅ | ❌ | ❌ |
| Cambios poco frecuentes (2-3/hora) | ❌ ineficiente | ✅ | ✅ |
| Red inestable con recuperación | ✅ | ✅ con backoff | ⚠️ manual |
| Comunicación bidireccional | ❌ | ❌ | ✅ |
| HTTP/1.1 (límite 6 conexiones) | ✅ | ⚠️ límite slot | n/a |
| HTTP/2 (multiplexación) | ✅ | ✅ excelente | requiere negociación |

---

## Regla práctica derivada del análisis

> **"SSE es la mejor opción cuando: el servidor soporta streaming, el flujo es
> unidireccional, y la frecuencia de cambio de datos es menor que el intervalo
> de polling. No es porque 'sea más moderno', sino porque elimina peticiones vacías
> de manera medible."**

---

*Autor: Fosuna · RetoIA_3 · Semana 6 · Dr. Eligardo Cruz Sánchez · UAN*
