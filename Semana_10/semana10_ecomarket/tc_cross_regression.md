# TC de Regresión Cruzada — Reto 8 (12 pts)

Caso de prueba que valida la interacción entre SSE, JWT y Circuit Breaker operando simultáneamente.

## TC-X1 — SSE activo + CB transiciona a ABIERTO → conexión SSE no se interrumpe

**Objetivo:** Verificar que la apertura del Circuit Breaker HTTP no interrumpe el stream SSE, porque SSE es un canal independiente que no pasa por `cb.ejecutar()` (ver `cliente_sse_multiplex.py:12-14`).

**Precondición:** Servidor mock corriendo en `localhost:3000`; cliente SSE conectado y recibiendo eventos; `ClienteRobusto` con CB en estado CERRADO.

**Pasos:**
1. Iniciar `servidor_mock.py` y obtener un JWT válido vía `POST /auth/login`.
2. Crear una instancia de `ClienteSSEMultiplex` con el `TokenManager` configurado y llamar a `conectar()`.
3. Registrar un handler para el evento `sistema` y verificar que se recibe al menos un evento (confirmación de conexión).
4. Crear un `ClienteRobusto` con `umbral_fallos=3` y `timeout_apertura=10.0`.
5. Cambiar el servidor a modo `fallo_503` vía `POST /admin/modo`.
6. Ejecutar 3 peticiones HTTP fallidas consecutivas a través de `cliente.get("/inventario")` para forzar la transición CERRADO → ABIERTO del CB.
7. Mientras el CB está ABIERTO, verificar que el cliente SSE sigue recibiendo eventos `sistema` (keep-alive `: ping`).
8. Verificar que `cliente_sse.estado == "CONECTADO"` y que `cliente_robusto.estado_circuito == EstadoCircuito.ABIERTO`.

**Evidencia esperada:**
```
[SSE] Recibido evento sistema: {"mensaje": "Conexion SSE establecida..."}
[CB]  Transición CERRADO → ABIERTO (umbral alcanzado: 3 fallos)
[SSE] Recibido evento sistema: keep-alive  ← SSE no se interrumpió
assert cliente_sse.estado == "CONECTADO"
assert cliente_robusto.estado_circuito == EstadoCircuito.ABIERTO
```

**Estado:** 📋 Protocolo manual

---

## TC-X2 — Token expira mientras CB está en SEMIABIERTO

**Objetivo:** Verificar que el refresh proactivo ocurre antes de la petición de prueba del estado SEMIABIERTO y que ese refresh no pasa por el CircuitBreaker principal.

**Precondición:** CB con `umbral_fallos=2` y `timeout_apertura=0.05`; token marcado como próximo a expirar; sesión HTTP fake con contador de peticiones.

**Pasos (automatizados en `test_circuit_breaker.py:378-416` y expuestos también en `test_tc_x2_refresh_semiaabierto.py`):**
1. Crear `ClienteRobusto` con `FakeExpiringTokenManager`, `FakeSession`, `max_retries=0` y CB de timeout corto.
2. Abrir el circuito con 2 fallos 503.
3. Esperar hasta SEMIABIERTO.
4. Ejecutar `cliente.get("/inventario")`.
5. Contar llamadas a `refresh_access_token()` y peticiones que llegan a la sesión fake.
6. Verificar el orden observable: `refresh` ocurre antes de `request`.

**Evidencia esperada:**
```
assert tm.refresh_calls == 1
assert cliente._session.requests == 1
assert eventos.index("refresh") < eventos.index("request")
assert Authorization == "Bearer token_fresco"
assert cb._fallos_consecutivos == 0
assert cb.estado == EstadoCircuito.CERRADO
```

**Estado:** ✅ Automatizado

---

## TC-X3 — Reconexión SSE con Last-Event-ID tras cierre del circuito

**Objetivo:** Verificar que al reconectar el stream SSE después de que el CB cierre, el cliente envía el header `Last-Event-ID` con el último ID recibido y el servidor reenvía los eventos almacenados con ID posterior.

**Precondición:** Servidor mock corriendo; cliente SSE ha recibido al menos un evento con campo `id`; el CB abrió y luego cerró (timeout expirado + petición de prueba exitosa).

**Pasos:**
1. Iniciar `servidor_mock.py` y hacer login.
2. Crear `ClienteSSEMultiplex` y conectar. Verificar recepción del evento inicial `(id: <timestamp>, event: sistema)`.
3. Registrar el valor de `cliente_sse.ultimo_id` (almacenado en `cliente_sse_multiplex.py:139`).
4. Forzar la desconexión del stream SSE (por ejemplo, cerrando la sesión o provocando un error de red temporal).
5. Esperar a que el CB abra y luego cierre (simular fallos 503 y luego recuperar el modo normal).
6. El cliente SSE reintenta automáticamente (`cliente_sse_multiplex.py:161-177`); verificar que el header `Last-Event-ID: <ultimo_id>` se incluye en la petición de reconexión (`cliente_sse_multiplex.py:184-185`).
7. Verificar que el servidor consulta su historial en memoria y emite eventos con `id > Last-Event-ID` (`servidor_mock.py:116-127`, `servidor_mock.py:315-317`).
8. Verificar que `cliente_sse._ultimo_id` no se reseteó a `None` durante la desconexión (`cliente_sse_multiplex.py:76`).

**Evidencia esperada:**
```
[SSE] Conectado — ultimo_id = 1717000000000
[CB]  Transición SEMIABIERTO → CERRADO
[SSE] Reconectando con Last-Event-ID: 1717000000000
[SRV] GET /api/alertas (SSE reconectado, Last-Event-ID: 1717000000000)
assert cliente_sse._ultimo_id == "1717000000000"  # No se reseteó
assert "Last-Event-ID" in headers_reconexion
```

**Estado:** 📋 Protocolo manual
