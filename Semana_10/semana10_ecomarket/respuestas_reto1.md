# Reto 1 — Mapa de Responsabilidades

## Fragmento A → ReceptorAlertas
Implementamos el parseo a nivel de bytes del stream SSE — decodifica el chunk, extrae campos `data:` y mantiene `_ultimo_id` para reconexión. Es la única capa que toca el protocolo SSE directamente (`cliente_sse_multiplex.py:105-134`, `_procesar_evento` en línea 136).

## Fragmento B → EventRouter (ClienteSSEMultiplex)
Decidimos separar el despacho del transporte: `despachar()` implementa el patrón Dispatcher con un diccionario de handlers, sin conocer el protocolo de transporte subyacente (`cliente_sse_multiplex.py:48-55`).

## Fragmento C → TokenManager
Implementamos la decodificación del payload JWT separando partes del token, restaurando padding Base64URL y parseando el JSON — responsabilidad exclusiva del TM para inspeccionar el contenido del token (`token_manager.py:47-57`).

## Fragmento D → CircuitBreaker
Decidimos modelar la transición `ABIERTO → SEMIABIERTO` basada en timeout y lanzar `CircuitOpenError` cuando el circuito sigue abierto — lógica de estados que pertenece exclusivamente al CB (`circuit_breaker.py:117-130` para la transición, `circuit_breaker.py:282-288` para el error).

## Fragmento E → ClienteRobusto
Implementamos la orquestación sin duplicar: verifica expiración vía `is_expiring_soon()` antes del CB, construye el header de autorización dentro de la petición y delega la ejecución de negocio al CB, sin reimplementar ni gestión de tokens ni máquina de estados (`cliente_robusto.py:176-180`, `cliente_robusto.py:216-224`).
