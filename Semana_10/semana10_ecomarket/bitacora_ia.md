# Bitácora de Uso de IA

## Entrada 1 — Singleton pattern para refresh_access_token con asyncio

**Prompt resumido:** ¿Cómo garantizar que múltiples corutinas concurrentes que llaman `refresh_access_token()` solo disparen una petición HTTP al endpoint `/auth/token`?

**Sugerencia de IA:** Usar el patrón Lock + shared Task: adquirir un `asyncio.Lock`, verificar si ya existe un `asyncio.Task` en vuelo para el refresh, y si existe, await el mismo Task. Esto evita requests duplicadas sin bloquear el event loop.

**Decisión del equipo:** Aceptada

**Justificación técnica:** El patrón Lock + shared Task (`token_manager.py:148-164`) asegura INV-B3 (singleton de refresh) sin necesidad de coordenadas externas. La doble verificación después de adquirir el lock cubre la race condition donde otro caller ya refrescó mientras esperábamos. La alternativa de usar `functools.lru_cache` asíncrono fue descartada porque no permite invalidar el cache cuando el token expira.

## Entrada 2 — Clasificación de errores 5xx vs 4xx en `_es_fallo_servidor`

**Prompt resumido:** ¿Qué errores deben contar como fallo del servidor para abrir el circuito, y cuáles deben dejarse pasar sin incrementar el contador?

**Sugerencia de IA:** Los 5xx, timeouts y errores de conexión sí cuentan; los 4xx (incluyendo 401/403) no, porque reflejan problemas del cliente, no del servidor. Verificar el atributo `.status` de la excepción y usar una lista de clases de excepciones de red conocidas.

**Decisión del equipo:** Aceptada

**Justificación técnica:** La implementación en `circuit_breaker.py:132-206` sigue esta clasificación. La distinción es crítica: si un 401 incrementara `_fallos_consecutivos`, un token expirado abriría el circuito falsamente (INV-A4), bloqueando también peticiones a endpoints que no requieren autenticación. La heurística de nombres de clase (`ServerConnectionError`, etc.) fue necesaria porque aiohttp lanza excepciones tipadas que no heredan de una base común manejable por `isinstance`.

## Entrada 3 — Estructura del test INV-A2 con asyncio.gather y return_exceptions

**Prompt resumido:** ¿Cómo probar que en SEMIABIERTO solo una petición pasa y las demás reciben CircuitOpenError inmediatamente, sin que el test falle por excepciones no capturadas?

**Sugerencia de IA:** Usar `asyncio.gather(*coros, return_exceptions=True)` para capturar todos los resultados sin que una excepción cancele las demás corutinas. Contar éxitos y `CircuitOpenError` por tipo.

**Decisión del equipo:** Aceptada

**Justificación técnica:** `return_exceptions=True` es esencial porque sin él, el primer `CircuitOpenError` cancelaría las corutinas restantes y el test nunca verificaría que exactamente 2 de 3 reciben el error. El lock en `circuit_breaker.py:295-298` usa `self._lock.locked()` + `self._lock.acquire()` sin ceder control entre ambas, lo cual funciona en asyncio single-threaded. El test en `test_circuit_breaker.py:114-130` reproduce exactamente este escenario con 3 peticiones concurrentes.

## Entrada 4 — Retry dentro o fuera del Circuit Breaker

**Prompt resumido:** ¿El retry con backoff exponencial debe estar dentro de `cb.ejecutar()` o fuera, en `ClienteRobusto._request_con_cb()`?

**Sugerencia de IA:** Las dos aproximaciones son válidas. Retry externo al CB permite que cada reintento pase por la decisión del breaker (abierto = no reintentar). Retry interno al CB reintentaría incluso cuando el circuito está abierto, lo cual contradice el fail-fast.

**Decisión del equipo:** Aceptada

**Justificación técnica:** Ubicamos el retry fuera del CB en `cliente_robusto.py:176-214`. Cada iteración resuelve primero el refresh proactivo fuera del breaker y luego llama a `cb.ejecutar()`, así que si el circuito está ABIERTO, el `CircuitOpenError` se propaga inmediatamente sin desperdiciar reintentos. Si el retry estuviera dentro del CB, el comportamiento de fail-fast se perdería y el cliente esperaría backoff innecesario. La decisión deja la responsabilidad del breaker como oráculo (¿paso o no paso?) y la responsabilidad del retry como estrategia (¿cuántas veces intento?).

## Entrada 5 — Desacoplar SSE del Circuit Breaker sin perder observabilidad

**Prompt resumido:** ¿Cómo hacer que la conexión SSE no pase por el CB (para que no se corte al abrirse el circuito) pero sin perder la capacidad de notificar a la UI?

**Sugerencia de IA:** Fachada `ClienteRobusto` que orquesta dos canales: el HTTP pasa por CB, el SSE conecta directamente. El SSE notifica al `ClienteRobusto` vía callback (`on_event_callback`) para actualizar su caché de fallback, y el `ClienteRobusto` notifica a la UI vía Observer pattern.

**Decisión del equipo:** Aceptada

**Justificación técnica:** La arquitectura final en `cliente_sse_multiplex.py:12-14` y `cliente_robusto.py:9-10` separa ambos canales. El SSE recibe eventos en tiempo real independientemente del estado del CB, y al mismo tiempo alimenta el caché de fallback (`cliente_robusto.py:238-246`) que se usa cuando el circuito está ABIERTO y las peticiones HTTP no pueden ejecutarse. Esto resuelve TC-X1: el stream SSE persiste aún con el circuito abierto, proporcionando datos en vivo que el `obtener_fallback()` expone a la UI.
