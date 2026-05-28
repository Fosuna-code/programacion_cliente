# Reto 3 — Autopsia de ClienteRobusto

## Bug A — CircuitBreaker decodifica JWT y verifica roles

**Síntoma observable:** Los operadores con rol `viewer` reciben un `PermissionError` al hacer GET a `/api/inventario`, aunque el endpoint debería permitirles consultar.

**Causa raíz:** `CircuitBreaker.ejecutar()` decodifica el payload del JWT y evalúa `payload.get('rol')`, asumiendo una responsabilidad de autorización que no le corresponde. El breaker debe decidir *si* se ejecuta la petición según el historial de fallos, no *quién* puede ejecutarla.

**Corrección aplicada:** Se eliminó el parámetro `token_manager` y todo el bloque de decodificación/verificación de roles dentro de `ejecutar()`. El método ahora recibe solo `fn` (`circuit_breaker.py:261`). La decodificación del JWT permanece en `TokenManager.decode_payload()` (`token_manager.py:39-67`), que es la capa autorizada para inspeccionar el contenido del token.

**Principio violado:** SRP (Single Responsibility Principle) e invariante INV-A1 — el CircuitBreaker viola su responsabilidad única al asumir lógica de autorización que corresponde al servidor o a una capa de permisos separada.

## Bug B — Fuga de token en logs de producción

**Síntoma observable:** En los logs de producción aparecen fragmentos del token de acceso como `Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6...`.

**Causa raíz:** El bloque `except` de `get_inventario()` registra `headers['Authorization'][:40]` en el log, filtrando los primeros 40 caracteres del header de autenticación. Aunque el fragmento no sea el token completo, expone suficiente información para facilitar ataques.

**Corrección aplicada:** En `cliente_robusto.py:187-209`, el manejo de errores solo registra el código de estado HTTP (`status=%s`, línea 193) y el tipo de excepción (`error=%s`, línea 201), nunca el header `Authorization`. En `token_manager.py:66`, el logging de errores de decode usa `logger.error("Failed to decode JWT payload: %s", exc)`, reportando solo la excepción sin incluir el token.

**Principio violado:** Information Hiding e invariante INV-B2 — las credenciales de autenticación no deben aparecer en logs, ni siquiera parcialmente; un fragmento de token ya es suficiente comprometimiento de seguridad.

## Bug C — Contador de fallos no se reinicia al cerrar el circuito

**Síntoma observable:** Después de que el servidor se recupera y el circuito transiciona SEMIABIERTO→CERRADO, los fallos se siguen acumulando desde el valor previo en vez de empezar desde cero, lo que provoca que el circuito se abra de nuevo con menos fallos de los esperados.

**Causa raíz:** El método `_on_exito()` cambia el estado a `CERRADO` pero omite resetear `self._fallos` a 0. Al conservar el contador previo, el siguiente ciclo de fallos alcanza el umbral prematuremente.

**Corrección aplicada:** En `circuit_breaker.py:211`, `_registrar_exito()` ejecuta `self._fallos_consecutivos = 0` *antes* de transicionar el estado a `CERRADO` (línea 214). Esto garantiza que la invariante se cumple: cuando el circuito está `CERRADO`, el contador de fallos consecutivos es siempre 0.

**Principio violado:** Invariante INV-A3 — el estado `CERRADO` exige `_fallos_consecutivos == 0` como postcondición; sin el reseteo, la máquina de estados queda en un estado corrupto que viola el contrato de la transición.