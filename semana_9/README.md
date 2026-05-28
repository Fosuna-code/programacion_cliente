# Semana 9: Resiliencia del Cliente — Circuit Breaker y Tolerancia a Fallos
## Programación Distribuida del Lado del Cliente · LSC · UAN

Este módulo implementa un **ClienteRobusto** que incorpora el patrón **Circuit Breaker** (Disyuntor) en combinación con el **TokenManager** de la Semana 8. Su objetivo es evitar la saturación de servidores caídos o sobrecargados (thundering herd) mediante el principio de **Fail-Fast** (Fallo Rápido) e integrar degradación elegante de la UI en el panel EcoMarket.

---

## 🧠 Decisiones de Resiliencia y Diseño

### 1. Umbral de Fallos (`umbral_fallos = 5`)
- **Tipo de decisión:** Equilibrada.
- **Justificación:** Un umbral de 5 fallos es óptimo para entornos de producción interactivos como el panel de control de EcoMarket. Si configuráramos un umbral muy bajo (por ejemplo, 1 o 2), cualquier micro-corte temporal de red, fluctuación en el router Wi-Fi del operador o latencia momentánea abriría el circuito de inmediato, provocando falsos positivos y degradando innecesariamente la interfaz. Si fuera demasiado alto (por ejemplo, 15 o 20), el cliente continuaría bombardeando al servidor con timeouts largos (de 5 a 30s) durante minutos, empeorando el estado de un servidor en crisis y congelando la UI del operador. Con 5 fallos consecutivos, confirmamos una caída sostenida en menos de 10 segundos ante peticiones concurrentes o de polling rápido.

### 2. Timeout de Apertura (`timeout_apertura = 60.0` segundos)
- **Tipo de decisión:** Conservadora y protectora.
- **Justificación:** En nuestro escenario inmersivo, el servidor de inventarios tarda aproximadamente **45 segundos** en reiniciar su base de datos tras una caída. Un timeout de apertura de 60 segundos es excelente porque garantiza que el cliente permanecerá en estado **ABIERTO** y mantendrá cerradas las compuertas de red durante todo el proceso de recuperación del servidor. Si el timeout fuera demasiado corto (por ejemplo, 10 segundos), el circuito pasaría a **SEMIABIERTO** e intentaría llamadas de prueba repetidamente antes de que el servidor pudiera terminar de levantarse, extendiendo el tiempo de caída debido a la sobrecarga. 60 segundos da un respiro saludable a la infraestructura.

### 3. Clasificación de Errores
El disyuntor debe distinguir con precisión matemática qué errores representan una falla de la infraestructura del servidor de aquellos causados por errores del propio cliente:

| Escenario de Error | Código HTTP / Excepción | ¿Cuenta como Fallo del Servidor? | Razón de Diseño / Justificación |
|---|---|:---:|---|
| **Service Unavailable** | `503 Service Unavailable` | **SÍ** | El servidor está explícitamente sobrecargado o en mantenimiento. |
| **Timeout de Conexión** | `asyncio.TimeoutError` | **SÍ** | El servidor no responde en el tiempo límite; signo de congestión severa o caída. |
| **Internal Server Error** | `500 Internal Server Error` | **SÍ** | El servidor encontró una condición inesperada en su código o base de datos. |
| **Connection Refused** | `ConnectionRefusedError` | **SÍ** | El puerto del servidor está cerrado; el proceso del servidor no está corriendo. |
| **Unauthorized** | `401 Unauthorized` | **NO** | El token JWT es inválido o expiró. Es un error de credenciales del cliente, no del servidor. |
| **Not Found** | `404 Not Found` | **NO** | La ruta o recurso no existe. Error de URI en el cliente. |
| **Bad Request** | `400 Bad Request` | **NO** | El cuerpo o sintaxis de la petición del cliente es inválido. |
| **CircuitOpenError** | `CircuitOpenError` | **NO** | Es lanzado localmente por el breaker; computarlo como fallo inflaría el contador cíclicamente. |

---

## 🛡️ Evasión del Deadlock de Autenticación (Auth-Breaker Deadlock)

Uno de los mayores antipatrones al implementar resiliencia es aplicar el disyuntor a todas las llamadas del cliente sin distinción. Si las llamadas a `/api/auth/refresh` pasaran por el mismo disyuntor que envuelve a `/api/inventario`, se produciría un **deadlock silencioso e irrecuperable**:

1. El servidor de inventario falla 5 veces consecutivas y el disyuntor transiciona a **ABIERTO**.
2. El token de acceso expira en el cliente. El `TokenManager` intenta renovarlo haciendo una petición a `/api/auth/refresh`.
3. Al estar el disyuntor en estado **ABIERTO**, la petición de refresh es bloqueada localmente de inmediato y lanza `CircuitOpenError`.
4. El token nunca se renueva, por lo que las peticiones siempre fallan con 401. El disyuntor nunca puede probar si el servidor se recuperó porque todas las peticiones mueren localmente por falta de token válido. El sistema queda bloqueado indefinidamente.

### Nuestra Solución:
Hemos diseñado el flujo de `ClienteRobusto` de modo que el **TokenManager** realiza su renovación de token usando un cliente HTTP independiente que **no** está envuelto por el `CircuitBreaker` de negocio. De esta manera, el canal de autenticación permanece despejado y el token se puede renovar exitosamente incluso si las APIs de negocio están bajo disyuntor abierto.

---

## 📐 Invariantes del Sistema Implementados

1. **INV-A1 (Sin Auto-Inflado):** Lanzar un `CircuitOpenError` local nunca incrementa el contador de fallos. El contador solo registra errores reales de red o respuestas `5xx` del servidor remoto.
2. **INV-A2 (Aislamiento de Prueba):** En estado **SEMIABIERTO**, solo permitimos **una** petición de prueba simultánea. Si llegan peticiones concurrentes en este estado, la primera es enviada y las restantes son rebotadas inmediatamente con `CircuitOpenError` de forma instantánea sin esperar el resultado de la primera.
3. **INV-A3 (Inmunidad del Token):** Los errores `4xx` (y en particular el `401`) jamás incrementan el contador de fallos ni alteran el estado del disyuntor.
4. **INV-A4 (Responsabilidad Única):** La clase `CircuitBreaker` desconoce por completo la existencia de JWT, payloads o rutas específicas; solo gestiona flujos asíncronos y transiciones de estado genéricas.

---

## 🚫 Límites y Posibles Mejoras de la Implementación Actual

1. **Breaker Global vs. Por Endpoint (Bulkhead):** Actualmente usamos un único Circuit Breaker global para todas las APIs de negocio. Si `/api/inventario` falla y abre el circuito, también bloqueamos llamadas estables como `/api/precios`. En sistemas reales, implementamos un disyuntor independiente por cada grupo de endpoints o microservicios.
2. **Degradación con Caché SSE:** Cuando el circuito está abierto, el cliente podría servir datos en "modo degradado" leyendo el último estado almacenado localmente a través de la conexión SSE (recibida en la Semana 7), en lugar de retornar un error seco al operador de la UI.
3. **Jitter en el Timeout de Apertura:** Si múltiples instancias del cliente EcoMarket abren su circuito simultáneamente, todas esperarán exactamente 60 segundos y se coordinarán para saturar al servidor al segundo 60. Se podría agregar un "jitter" aleatorio (ej. ±10%) al timeout para mitigar este problema.
