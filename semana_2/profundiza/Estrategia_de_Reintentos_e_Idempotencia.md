# Estrategia de Reintentos e Idempotencia

Esta documentación define cuándo es seguro reintentar una petición HTTP fallida y cuándo no, basándose en los principios de idempotencia estudiados en la **Semana 1 (Arquitectura Cliente-Servidor)**.

## Introducción

En sistemas distribuidos, las fallas son inevitables. Un simple "parpadeo" en la red puede causar que una petición falle. Los **reintentos (retries)** son un mecanismo fundamental para hacer que nuestro cliente sea resiliente, pero aplicarlos ciegamente puede ser peligroso (e.g., duplicar una compra).

## Regla de Oro (Semana 1)

Como vimos en los fundamentos del Modelo AETL:

> - **4xx (Error Cliente)** → **NO reintentar**. El problema es de la petición (e.g., datos inválidos, sin permisos). Reintentar lo mismo dará el mismo error.
> - **5xx (Error Servidor)** → **SÍ reintentar**. El servidor falló temporalmente. Un reintento podría tener éxito.
> - **2xx (Éxito)** → Procesar el resultado.

## ¿Cuándo es Seguro Reintentar?

Es seguro reintentar cuando la operación es **Idempotente** o cuando el fallo ocurrió antes de llegar al servidor (errores de conexión).

### 1. Errores de Red / Conexión
Si el cliente no pudo conectar con el servidor (Timeout, Connection Refused), **es seguro reintentar** porque la petición nunca fue procesada.

### 2. Códigos de Estado 5xx (Server Errors)
- `500 Internal Server Error`
- `502 Bad Gateway`
- `503 Service Unavailable`
- `504 Gateway Timeout`

Estos errores sugieren problemas transitorios. Se recomienda usar una estrategia de **Exponential Backoff** (esperar tiempos crecientes: 1s, 2s, 4s...) para no saturar al servidor.

### 3. Métodos Idempotentes
Un método es **idempotente** si hacer la misma petición múltiples veces tiene el mismo efecto que hacerla una sola vez. Matemáticamente: $f(f(x)) = f(x)$.

| Método | ¿Idempotente? | ¿Seguro reintentar? | Razón |
| :--- | :--- | :--- | :--- |
| **GET** | ✅ Sí | ✅ **SÍ** | Solo lee datos. No cambia el estado del servidor. |
| **PUT** | ✅ Sí | ✅ **SÍ** | Reemplaza el recurso completo. Si envías lo mismo 2 veces, el resultado final es el mismo. |
| **DELETE** | ✅ Sí | ✅ **SÍ** | Borrar algo que ya está borrado (en el 2do intento) suele dar 404 o 200, pero el estado final es "recurso eliminado". |
| **HEAD** | ✅ Sí | ✅ **SÍ** | Igual que GET pero sin cuerpo. |
| **OPTIONS** | ✅ Sí | ✅ **SÍ** | Pide información sobre la comunicación. |

---

## ¿Cuándo NO es Seguro Reintentar?

No se debe reintentar automáticamente si la operación no es idempotente o si el error indica que la petición es inválida.

### 1. Códigos de Estado 4xx (Client Errors)
- `400 Bad Request`: Tu JSON está mal formado o faltan datos.
- `401 Unauthorized`: Tus credenciales están mal.
- `403 Forbidden`: No tienes permiso.
- `404 Not Found`: El recurso no existe.
- **Excepción**: `429 Too Many Requests` (Rate Limiting) a veces permite reintentos si se respeta el header `Retry-After`.

### 2. Métodos NO Idempotentes (POST, PATCH)

| Método | ¿Idempotente? | ¿Seguro reintentar? | Riesgo |
| :--- | :--- | :--- | :--- |
| **POST** | ❌ No | ⚠️ **NO** (generalmente) | **Duplicación**. Si el primer intento cobró la tarjeta pero la respuesta se perdió por red, el segundo intento cobrará de nuevo. |
| **PATCH** | ❌ No | ⚠️ **NO** | Modificación parcial. Si la operación es "aumentar precio en +10", reintentar subiría el precio +20. |

### ¿Cómo reintentar POST de forma segura?
Para hacer seguro el reintento de un POST, se necesitan **Idempotency Keys** (un ID único por petición que el servidor usa para identificar duplicados). Si el servidor no soporta esto, **no reintentes POST automáticamente**.

## Referencia a Semana 1

En el material de la Semana 1 (*Arquitectura Cliente-Servidor y Fundamentos HTTP*), sección **"¿Por qué importa la idempotencia?"**, se establece:

> "Si una petición falla y no sabes si llegó al servidor, ¿puedes reintentarla con seguridad? Con métodos idempotentes (GET, PUT, DELETE), sí. Con POST, podrías crear duplicados. Esta distinción es fundamental para implementar patrones de resiliencia en tus clientes."
