# Reto 7 — Checklist de Invariantes (7/7)

## INV-A1 — CB nunca accede a campos del payload JWT

**Estado:** ✅ Verificado

**Descripción:** El CircuitBreaker no importa, decodifica ni inspecciona claims del JWT (sub, exp, rol); trata excepciones HTTP opacamente.

**Evidencia:**
- Código: `circuit_breaker.py` — la clase `CircuitBreaker` no contiene referencias a JWT, decode, payload, sub, exp ni rol. El método `_es_fallo_servidor()` (línea 132) clasifica excepciones por tipo y status numérico sin inspeccionar tokens.
- Test: `test_circuit_breaker.py::test_inv_a1` (línea 76) — importa CB con token malformado `"no.es.jwt"`, ejecuta `cb.ejecutar()` y verifica que no lanza error de decodificación; además `assert not hasattr(cb, 'decode_payload')` y `assert not hasattr(cb, 'get_auth_header')`.
- Log: ver log generado

**Corrección aplicada (si aplica):** N/A

---

## INV-A2 — En SEMIABIERTO, exactamente una petición pasa; las demás reciben CircuitOpenError

**Estado:** ✅ Verificado

**Descripción:** Cuando el circuito está en SEMIABIERTO, un `asyncio.Lock()` garantiza que solo una petición de prueba se ejecuta; las concurrentes reciben `CircuitOpenError(0.0)` inmediato.

**Evidencia:**
- Código: `circuit_breaker.py:290-298` — `if self._lock.locked(): raise CircuitOpenError(0.0)` seguido de `await self._lock.acquire()`; solo la primera corutina adquiere el lock, las restantes se rechazan sin esperar.
- Test: `test_circuit_breaker.py::test_inv_a2` (línea 96) — abre el circuito con 2 fallos, espera timeout a SEMIABIERTO, lanza 3 peticiones concurrentes vía `asyncio.gather()`, verifica `exitos == 1` y `CircuitOpenError == 2`.
- Log: ver log generado

**Corrección aplicada (si aplica):** N/A

---

## INV-A3 — Al transicionar SEMIABIERTO → CERRADO, _fallos_consecutivos se resetea a 0

**Estado:** ✅ Verificado

**Descripción:** El método `_registrar_exito()` pone `_fallos_consecutivos = 0` antes de transicionar el estado, garantizando que el contador se limpia al cerrar.

**Evidencia:**
- Código: `circuit_breaker.py:211` — `self._fallos_consecutivos = 0` antes de la transición `SEMIABIERTO → CERRADO` en línea 214. Comentario de guardia en línea 219: `# INV-A3: _fallos_consecutivos ya se reseteó arriba.`
- Test: `test_circuit_breaker.py::test_inv_a3` (línea 137) — abre con 2 fallos, espera timeout a SEMIABIERTO, ejecuta petición exitosa, verifica `cb._fallos_consecutivos == 0` y `cb.estado == CERRADO`.
- Log: ver log generado

**Corrección aplicada (si aplica):** N/A

---

## INV-A4 — HTTP 401/403 no incrementan _fallos_consecutivos

**Estado:** ✅ Verificado

**Descripción:** Los errores 4xx (incluyendo 401 y 403) no son clasificados como fallos de servidor por `_es_fallo_servidor()`, por lo que el CB nunca los cuenta para abrir el circuito.

**Evidencia:**
- Código: `circuit_breaker.py:132-206` — `_es_fallo_servidor()` rechaza 4xx: el método verifica `status >= 500` (línea 181) y la regla general retorna `False` para cualquier status < 500. La lógica de `ejecutar()` (línea 312) solo llama `_registrar_fallo()` cuando `_es_fallo_servidor(e)` retorna `True`.
- Test: `test_circuit_breaker.py::test_inv_a4` (línea 166) — dispara `umbral + 5 = 8` peticiones 401, verifica `cb.estado == CERRADO` y `cb._fallos_consecutivos == 0`; repite con 403 con el mismo resultado.
- Log: ver log generado

**Corrección aplicada (si aplica):** N/A

---

## INV-B1 — TokenManager no tiene atributos del CircuitBreaker

**Estado:** ✅ Verificado

**Descripción:** La clase `TokenManager` es completamente independiente del CB: no contiene referencias a estado del circuito, umbral, ni modo de apertura.

**Evidencia:**
- Código: `token_manager.py:14-227` — los atributos de instancia son `_base_url`, `_access_token`, `_refresh_token`, `_session`, `_refresh_lock`, `_refresh_task`, `_margen_expiracion`; ninguno relacionado con CB. El docstring de clase (línea 27) declara explícitamente: `"No circuit-breaker attributes are stored (INV-B1)."`
- Test: `test_circuit_breaker.py::test_inv_b1` (línea 198) — itera `dir(tm)` buscando atributos que contengan 'circuit', 'breaker', '_open', '_closed'; verifica `not hasattr(tm, '_estado')` y `not hasattr(tm, '_breaker')`.
- Log: ver log generado

**Corrección aplicada (si aplica):** N/A

---

## INV-B2 — El token de acceso nunca aparece en logs, ni parcialmente

**Estado:** ✅ Verificado

**Descripción:** Ningún método de `TokenManager` registra el valor del token — solo fragmentos no reversibles como `"access_token refreshed successfully"`.

**Evidencia:**
- Código: `token_manager.py:66` — `logger.error("Failed to decode JWT payload: %s", exc)` loguea la excepción, no el token. `token_manager.py:121` — `logger.info("Refreshing access token via %s", url)` incluye solo la URL. `token_manager.py:133` — `logger.info("Access token refreshed successfully")` sin valor del token. `token_manager.py:172-173` — `store_tokens()` no loguea valores. El docstring en línea 41 declara: `"INV-B2: never log the raw token value"`.
- Test: `test_circuit_breaker.py::test_inv_b2` (línea 223) — inyecta un token conocido `"eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJvcDEiLCJyb2wiOiJ2aWV3ZXIiLCJleHAiOjk5OTk5OTk5OTl9.mock_sig"`, captura logs con `io.StringIO`, llama `get_auth_header()` y `decode_payload()`, verifica que ni el token completo ni fragmentos parciales aparecen en el log.
- Log: ver log generado

**Corrección aplicada (si aplica):** N/A

---

## INV-B3 — Con múltiples peticiones concurrentes expiradas, solo un refresh se ejecuta (patrón singleton)

**Estado:** ✅ Verificado

**Descripción:** `refresh_access_token()` implementa el patrón singleton con `asyncio.Lock()` + `asyncio.Task` compartido para deduplicar peticiones de refresh concurrentes.

**Evidencia:**
- Código: `token_manager.py:136-164` — `refresh_access_token()` adquiere `_refresh_lock` (línea 148), hace doble verificación (líneas 145 y 151), y si no hay task en vuelo crea uno compartido (línea 158). El await del task se hace fuera del lock (línea 164) para permitir que otros callers vean el task en vuelo y lo reutilicen.
- Test: `test_circuit_breaker.py::test_inv_b3` (línea 358) — crea `CountingRefreshTokenManager`, lanza 5 corutinas concurrentes con `asyncio.gather()`, verifica `tm.refresh_calls == 1`, que todas reciben el mismo token fresco y que el token resultante ya no expira.
- Log: `demo_resiliencia.log` o salida de `python test_circuit_breaker.py`: `INV-B3 PASADO: 5 corutinas compartieron 1 refresh real`.

**Corrección aplicada (si aplica):** Se reemplazó la prueba estructural por una prueba concurrente real con contador de refresh. El servidor mock conserva `/auth/token-count` para validación manual adicional, pero la certificación automática ya no depende de un servicio externo.
