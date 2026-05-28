"""
RECEPTOR ALERTAS ECOMARKET — Decisiones de arquitectura (cliente)
RetoIA_3 · Fase REFLEXIONA · Semana 6 · Programación Distribuida del Lado del Cliente · UAN
==============================================================================================

Trade-off SSE vs Polling — Análisis de los 4 escenarios:

══════════════════════════════════════════════════════════════════════
ESCENARIO A: 10,000 usuarios concurrentes, precios cambian 2-3 veces/hora
══════════════════════════════════════════════════════════════════════
Decisión: SSE ✅

Justificación técnica (desde el cliente):
- Con polling cada 5s y 10,000 clientes: 10,000 × 12 peticiones/min = 120,000 req/min.
  Cada petición abre una conexión TCP nueva, envía headers (~500 bytes), espera respuesta.
  Si los precios cambian 2-3 veces/hora = ~0.04 cambios/min, la tasa de peticiones vacías
  (HTTP 304) es del 99.97%. El cliente envía 120,000 peticiones para recibir ~0.04 datos útiles.
- Con SSE: 10,000 conexiones TCP persistentes. El cliente no envía ningún byte adicional
  después de la conexión inicial. Solo recibe datos cuando hay un cambio real.
  Ahorro del cliente: elimina 119,997 peticiones vacías por minuto.
- Limitación HTTP/1.1: bajo HTTP/1.1, el navegador limita 6 conexiones TCP por dominio.
  Con 10,000 usuarios en múltiples pestañas, esto es una restricción real.
  Solución: HTTP/2 (multiplexación, elimina el límite de 6).

══════════════════════════════════════════════════════════════════════
ESCENARIO B: Inventario que actualiza stock cada 1s, servidor legacy (solo REST)
══════════════════════════════════════════════════════════════════════
Decisión: Polling obligatorio ⚠️

Justificación técnica:
- SSE requiere que el SERVIDOR soporte streaming (Transfer-Encoding: chunked +
  Content-Type: text/event-stream). Un servidor REST clásico cierra la conexión
  después de cada respuesta JSON — no puede mantenerla abierta para enviar eventos.
- El cliente no puede "forzar" SSE si el servidor no lo soporta.
- Con intervalo de 1s y 1 cliente: 60 peticiones/min. Si los datos cambian cada 1s,
  la tasa de peticiones vacías es prácticamente 0 (los datos siempre son frescos).
  En este escenario, polling con interval=1s es equivalente en eficiencia a SSE.
- Costo de la opción: el cliente administra el ciclo (while activo:), el timeout
  por petición y la detención limpia — exactamente como en el Examen 1.

══════════════════════════════════════════════════════════════════════
ESCENARIO C: Cliente móvil con 3G, interrupciones cada 20-30s
══════════════════════════════════════════════════════════════════════
Decisión: SSE con backoff cuidadoso ✅ (con matices)

Justificación técnica:
- Con polling cada 3s en 3G: cada petición incurre en latencia de round-trip de
  300-800ms en 3G. Si la red se interrumpe, el polling genera un timeout por
  petición, lo recupera y sigue — el manejo de errores es por petición individual.
- Con SSE: una sola conexión persistente. Cuando la red se cae, el cliente espera
  retry_ms y reconecta con Last-Event-ID — sin perder eventos intermedios.
  Ventaja clave: SSE garantiza que los eventos emitidos durante la desconexión
  se reenvíen al reconectar (si el servidor conserva historial).
- Matiz importante: en redes muy inestables (interrupciones cada 20-30s), el
  cliente SSE puede entrar en un ciclo de reconexión frecuente. El backoff
  exponencial (3s → 6s → 12s → 24s → 48s) evita tormenta de reconexiones.
- Si las interrupciones son más frecuentes que el retry_ms, polling podría ser
  más robusto porque cada petición es independiente — no depende del estado de
  una conexión persistente previa.

══════════════════════════════════════════════════════════════════════
ESCENARIO D: Panel necesita recibir alertas Y enviar filtros dinámicos
══════════════════════════════════════════════════════════════════════
Decisión: WebSocket (Semana 11) ✅

Justificación técnica:
- SSE es UNIDIRECCIONAL: servidor → cliente. El cliente no puede enviar datos
  por la misma conexión SSE. Para enviar filtros ("solo alertas de Electrónica"),
  necesitaría una petición HTTP separada (POST) mientras mantiene la conexión SSE.
  Esto es técnicamente posible pero arquitectónicamente incómodo: el estado del
  servidor debe correlacionar la sesión SSE con la petición POST de filtros.
- WebSocket es BIDIRECCIONAL sobre una sola conexión. El cliente puede enviar
  {"accion":"filtrar","categoria":"Electronica"} mientras recibe alertas en tiempo
  real por el mismo canal.
- Costo: WebSocket requiere upgrade de protocolo (HTTP → WS), el cliente debe
  implementar reconexión manualmente (no hay Last-Event-ID nativo), y el servidor
  necesita un handler de WebSocket, no solo de HTTP streaming.
- Cuándo NO usar WebSocket en lugar de SSE: si el único requisito es recibir datos
  del servidor, SSE es más simple, compatible con proxies HTTP estándar, y tiene
  reconexión automática. WebSocket se justifica solo cuando el cliente necesita
  enviar datos frecuentes al servidor en tiempo real.

══════════════════════════════════════════════════════════════════════
Resumen de la decisión
══════════════════════════════════════════════════════════════════════
La elección SSE vs polling NO es simplemente "SSE es más moderno". Depende de:
  1. ¿El servidor soporta streaming? Si no → polling obligatorio.
  2. ¿Cuál es la frecuencia de cambio de datos? Si cambios son < 1/min → SSE ahorra
     la mayor cantidad de peticiones vacías.
  3. ¿El cliente necesita enviar datos en tiempo real? Si sí → WebSocket.
  4. ¿Hay restricciones de red? HTTP/1.1 limita 6 conexiones SSE por dominio.
"""

# Este archivo forma parte de la evidencia del RetoIA_3 (Fase REFLEXIONA).
# El docstring de arriba es el entregable requerido: trade-off de arquitectura
# documentado con datos concretos para los 4 escenarios del Reto 3.

print("RetoIA_3 — Trade-off docstring cargado correctamente.")
print("Ver el docstring del módulo para el análisis completo.")
print(__doc__)
