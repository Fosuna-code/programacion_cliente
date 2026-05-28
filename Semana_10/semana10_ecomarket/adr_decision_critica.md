# ADR-001 — Excluir el endpoint /auth/token del CircuitBreaker principal

## Estado

Aceptado

## Contexto

El deadlock Auth-Breaker se produce así: (1) el servidor empieza a devolver 5xx en `/api/inventario`; (2) el CB acumula fallos consecutivos y transiciona a ABIERTO; (3) mientras tanto, el JWT de acceso expira; (4) el cliente necesita refrescar el token llamando a `/auth/token`; (5) si `/auth/token` también pasa por el CB, este bloquea la petición con `CircuitOpenError`; (6) sin token válido, todas las peticiones subsecuentes al API reciben 401; (7) nunca se rompe el ciclo — el sistema no puede ni operar ni recuperar credenciales. El circuito se cierra solo tras el timeout, pero el token sigue expirado, y la primera petición de prueba en SEMIABIERTO también fallará con 401 porque el refresh fue bloqueado.

## Decisión

Excluir las llamadas a `/auth/token` del CircuitBreaker principal. El refresh proactivo se ejecuta antes de `cb.ejecutar()` vía `_asegurar_token_vigente()`, y el refresh reactivo por 401 se ejecuta vía `_refrescar_token_silencioso()`; ambos caminos rompen la dependencia circular que produce el deadlock.

## Consecuencias

**Positivas:**
- El cliente siempre puede renovar credenciales aunque el circuito principal esté ABIERTO, rompiendo el deadlock Auth-Breaker y permitiendo que la petición de prueba en SEMIABIERTO porte un token válido.
- La separación de capas queda más clara: el CB protege el dominio de API de negocio, mientras auth opera en un dominio de infraestructura con contrato de disponibilidad distinto, consistente con el principio de bulkheading por endpoint.

**Negativas / costos honestos:**
- El endpoint de auth pierde la protección fail-fast del CB: si `/auth/token` está caído, cada intento de refresh ejecuta el timeout completo de la petición HTTP (5 s) antes de fallar, sin el mecanismo de rechazo inmediato que el CB brindaría.
- El cliente no tiene backoff para reintentos de auth: `_refrescar_token_silencioso()` (`cliente_robusto.py:227`) hace un solo intento y loguea el error sin colas de reintento, así que un auth server temporalmente inalcanzable produce degradación silenciosa hasta que el operador interviene.

## Escenario adverso

El servidor de auth sufre degradación parcial: responde, pero con latencia de 25–30 s por petición (no 5xx, solo lento). Sin un CB protegiendo `/auth/token`, cada invocación de `_refrescar_token_silencioso()` espera hasta el timeout de la sesión HTTP. Como `_asegurar_token_vigente()` se evalúa **antes** de cada intento protegido por el CB (`cliente_robusto.py:179`, `cliente_robusto.py:216-224`), si el token expira durante una ráfaga de tráfico, múltiples corutinas esperarán el mismo refresh singleton. El resultado: las peticiones a `/api/inventario` pueden quedar retenidas por auth aunque el API de negocio esté sano. El CB principal no puede mitigarlo porque auth está excluido. La degradación se propaga lateralmente hacia un dominio que sí funcionaba.

## Alternativas consideradas

1. **CB separado para auth:** Un segundo `CircuitBreaker` con umbral alto (e.g., 10 fallos) y timeout largo exclusivo para `/auth/token`. Protege contra el escenario adverso de latencia elevada en auth, pero añade complejidad de configuración y el riesgo de un segundo deadlock si ambos breakers se abren simultáneamente.
2. **CB prioritario con bypass selectivo:** Marcar ciertos endpoints como "críticos" que siempre se intentan (1 retry) incluso con el circuito ABIERTO. Más flexible pero viola la semántica del CB y puede enmascarar problemas de capacidad del servidor de auth.
3. **Fallback a token en cache sin refresh:** Si el refresh falla, operar con el token expirado y aceptar 401 del API. Esto solo posterga el problema — 401 sube al usuario sin recuperación.
