# Contribución del Equipo

## Integrante 1

**Módulos responsables:**
- `circuit_breaker.py` — implementación completa (estados, _es_fallo_servidor, lock en SEMIABIERTO, callbacks de observabilidad)
- `test_circuit_breaker.py` — invariantes INV-A1 hasta INV-A4, INV-B1 hasta INV-B3, y TC-X2 automatizado
- `servidor_mock.py` — endpoints SSE con autenticación y soporte para Last-Event-ID

**Aportaciones destacables:**
- Implementó el lock `asyncio.Lock` en SEMIABIERTO que garantiza que exactamente una petición de prueba pase (`circuit_breaker.py:295-298`).
- Diseñó `_es_fallo_servidor()` con clasificación exhaustiva de errores de red y HTTP, incluyendo detección por nombre de clase para aiohttp (`circuit_breaker.py:132-206`).
- Implementó el soporte para Last-Event-ID en el endpoint `/api/alertas` del servidor mock (`servidor_mock.py:270-274`).

## Integrante 2

**Módulos responsables:**
- `token_manager.py` — singleton de refresh con asyncio.Lock + shared Task
- `cliente_sse_multiplex.py` — conexión SSE independiente con backoff exponencial y Last-Event-ID
- `cliente_robusto.py` — integración de capas CB + TM + HTTP + Observer

**Aportaciones destacables:**
- Implementó el patrón Lock + Task compartido en `refresh_access_token()` que satisface INV-B3 (`token_manager.py:136-164`).
- Diseñó `ClienteSSEMultiplex` como canal independiente del CB, con reconexión automática y preservación de `_ultimo_id` para TC-X3 (`cliente_sse_multiplex.py:76,184-185`).
- Integró el callback `on_event_callback` que alimenta el caché de fallback del `ClienteRobusto` (`cliente_robusto.py:83,223-231`).

---

## Conflicto técnico documentado

**Discusión:** ¿Dónde ubicar el retry con backoff exponencial — dentro de `CircuitBreaker.ejecutar()` o fuera, en `ClienteRobusto._request_con_cb()`?

**Postura A (Integrante 1):** Dentro del CB, porque es el componente que decide si se reintenta; centraliza la lógica de resiliencia.

**Postura B (Integrante 2):** Fuera del CB, porque si el circuito está ABIERTO, no se debe esperar backoff — se debe fallar de inmediato (fail-fast). El retry no tiene sentido cuando el breaker ya decidió no contactar al servidor.

**Resolución:** Se adoptó la postura B. El retry queda en `ClienteRobusto._request_con_cb()` (`cliente_robusto.py:176-214`). Cada iteración primero resuelve auth fuera del CB y luego llama a `cb.ejecutar()`, de modo que si el circuito está ABIERTO el `CircuitOpenError` se propaga inmediatamente al caller sin desperdiciar reintentos. Esto preserva la semántica de fail-fast del CB y mantiene la responsabilidad de cada componente: auth renueva credenciales, el CB decide si la petición de negocio se ejecuta y el retry decide cuántas veces se intenta.

---

## Declaración de defensa de decisiones arquitectónicas

Ambos miembros del equipo comprenden y pueden defender la decisión arquitectónica principal (ADR-001):

> **ADR-001: Excluir `/auth/token` del CircuitBreaker principal.** El CB protege exclusivamente las peticiones HTTP de negocio; el refresh de credenciales se ejecuta fuera de `cb.ejecutar()` mediante `_asegurar_token_vigente()` y `_refrescar_token_silencioso()`. Esta separación evita el Auth-Breaker Deadlock: si el circuito está ABIERTO, el cliente aún puede renovar credenciales antes de la petición de prueba en SEMIABIERTO.

- Integrante 1 defiende: por qué `_es_fallo_servidor()` no clasifica errores 4xx como fallos del servidor, y por qué el lock en SEMIABIERTO usa `locked()` + `acquire()` atómico en vez de `async with self._lock`.
- Integrante 2 defiende: por qué el singleton de refresh usa Lock + Task compartido en vez de `asyncio.Event` o variable booleana, y por qué `/auth/token` no debe pasar por el CB principal.
