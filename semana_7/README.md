# Semana 7 — ClienteSSEMultiplex · Panel de Control EcoMarket
## Programación Distribuida del Lado del Cliente · UAN

---

## Reto 1 — Decisiones de diseño entendidas antes de codificar

### 1. ¿Por qué una conexión multiplexada y no tres separadas?

HTTP/1.1 limita a **6 conexiones simultáneas por origen** en el navegador. Cada
conexión SSE es persistente — nunca se libera mientras el cliente esté activo.
Con tres módulos (precios, inventario, pedidos) ya ocupamos 3 de las 6 ranuras.
Añade el `fetch()` de autenticación, uno para cargar datos históricos, y ya
quedan 1 o 2 ranuras para las operaciones normales del panel.

Con **una sola conexión multiplexada** hacia `/api/ecomarket/eventos?modulos=...`,
el pool tiene 5 ranuras libres para todo lo demás. El costo: el EventRouter
en el cliente debe despachar por tipo — pero eso es lógica en memoria, no red.

### 2. ¿Qué hace el cliente ante un tipo de evento que no conoce?

Lo ignora **silenciosamente** — sin lanzar excepción, sin cerrar la conexión.
El EventRouter simplemente verifica si hay handlers registrados para ese tipo;
si no los hay, hace `return`. Esto permite al servidor agregar nuevos tipos de
eventos sin forzar actualizaciones del cliente. Es el principio de tolerancia
hacia extensiones desconocidas (robustez en protocolos).

### 3. ¿Qué diferencia hay entre "el servidor filtra por módulo" y "el cliente enruta por tipo"?

- **Filtrado del servidor**: el servidor lee el query param `?modulos=precios,inventario`
  y solo envía eventos de esos módulos. Si añadimos el módulo `devoluciones`,
  necesitamos reconectar con la nueva URL — eso requiere cambio en el **cliente**.
- **Routing del cliente**: el EventRouter despacha eventos según el campo `event:`
  a los handlers registrados. Si registramos un nuevo handler para `devoluciones`,
  no necesitamos reconectar (si el servidor ya envía esos eventos). El cambio
  es solo en el **cliente**, sin tocar la conexión.

El cambio que requiere código del cliente: **agregar módulo** → cambiar URL → reconectar.

### 4. ¿Qué pasa si se llama a `iniciar()` cuando la conexión ya está activa?

La máquina de estados verifica `self.estado != "DESCONECTADO"` al inicio de
`iniciar()`. Si el estado es "CONECTADO" o "RECONECTANDO", `iniciar()` imprime
una advertencia y retorna sin abrir ninguna conexión adicional. Esto previene el
race condition más común: dos streams leyendo en paralelo generan eventos duplicados.

### Síntesis correctiva sobre el análisis del cliente

La multiplexación SSE reduce la presión sobre el pool de conexiones HTTP/1.1
del **cliente** — eso es una decisión de arquitectura del código del cliente.
Cualquier afirmación sobre "el servidor escala mejor" o "reduce carga de CPU del
backend" está **fuera del alcance del análisis del cliente** y no debe aparecer
en el docstring de decisiones. Las métricas relevantes son: ranuras del pool
usadas, latencia de detección de fallo (timeout), y tiempo total de reconexión
con backoff (1+2+4+8+16 = 31s acumulados).

---

## Archivos del proyecto

| Archivo | Descripción |
|---------|-------------|
| [`cliente_sse_multiplex.py`](./cliente_sse_multiplex.py) | ClienteSSEMultiplex completo con EventRouter, 4 handlers, demo de 10 eventos y auditoría de 4 escenarios |
| [`README.md`](./README.md) | Este archivo — decisiones de diseño y documentación |
| [`validacion.log`](./validacion.log) | Salida de la demo + auditoría de los 4 escenarios de fallo |
| [`event_router_prioritizado.py`](./event_router_prioritizado.py) | Reto 5 — EventRouter con prioridades (avanzado) |

---

## Cómo ejecutar

```bash
# Instalar dependencias
pip install httpx

# Ejecutar demo offline (sin servidor real)
python cliente_sse_multiplex.py

# Redirigir salida a log
python cliente_sse_multiplex.py > validacion.log 2>&1
```

---

## Máquina de estados del ClienteSSEMultiplex

```
DESCONECTADO ──iniciar()──► CONECTANDO ──conexión OK──► CONECTADO
      ▲                                                       │
      │                                                  error red
      │                      RECONECTANDO ◄──────────────────┘
      │                           │
      └──────────max reintentos───┘  o  detener()
```

---

## Invariantes del sistema

| Invariante | Descripción |
|---|---|
| INV-A1 | `router.despachar()` nunca recibe `tipo=None`. Default: `"message"` |
| INV-A2 | Toda conexión HTTP tiene timeout explícito (`connect=30s`) |
| INV-A3 | Excepción en handler no cierra el stream ni afecta otros handlers |
| INV-A4 | `ultimo_id` NO se resetea en reconexión automática |
| INV-V1 | Datos malformados (no JSON) → log + continúa la conexión |
| INV-V2 | `Last-Event-ID` nunca se pierde en reconexión automática |
| INV-V3 | `iniciar()` con conexión activa → warning, no segunda conexión |

---

## Reto 5 — EventRouterPrioritizado (avanzado)

Ver [`event_router_prioritizado.py`](./event_router_prioritizado.py).

**Decisión de diseño: Decorador (wrapper) en lugar de herencia**

Se eligió el patrón **decorador** (wrapper) sobre la herencia porque:
1. `EventRouter` ya está dado y no debe modificarse — la herencia requeriría
   conocer los internos de la clase padre para sobreescribir correctamente.
2. Un decorador envuelve la interfaz original sin cambiarla: el código existente
   que usa `EventRouter` directamente sigue funcionando sin modificaciones.
3. El decorador puede añadirse o retirarse en tiempo de ejecución — no está
   acoplado a la jerarquía de clases.
4. La prioridad es una preocupación transversal (cross-cutting concern), no una
   especialización de EventRouter.

---

*Dr. Eligardo Cruz Sánchez · Universidad Autónoma de Nayarit · Semana 7 de 15*
