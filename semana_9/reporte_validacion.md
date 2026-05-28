# Reporte de Validación: Resiliencia del Cliente — Circuit Breaker
## Programación Distribuida del Lado del Cliente · LSC · UAN

Este documento reporta la validación del **ClienteRobusto** y su **CircuitBreaker** utilizando el harness de pruebas automatizado contra un servidor mock que simula degradación de red y fallos de infraestructura.

---

## 📊 Tabla de Resultados — 7 Casos de Prueba

| Caso de Prueba | Descripción de la Prueba | Comportamiento Esperado | Comportamiento Observado | Veredicto |
|---|---|---|---|:---:|
| **CASO 1** | Op. Normal en CERRADO | Breaker inicia CERRADO. 5 peticiones exitosas mantienen el disyuntor CERRADO con contador de fallos en 0. | 5/5 peticiones exitosas. Breaker permaneció CERRADO, `_fallos_consecutivos = 0`. | **✅ PASADO** |
| **CASO 2** | Transición CERRADO → ABIERTO | Exactamente 5 fallos consecutivos abren el circuito. La 6ta petición es rebotada localmente vía `CircuitOpenError` (Fail-Fast) con 0 llamadas al servidor. | Tras el fallo 5, transicionó a ABIERTO. La 6ta petición lanzó `CircuitOpenError` y no tocó la red. | **✅ PASADO** |
| **CASO 3** | Exclusión de Errores 4xx | Peticiones con error `401 Unauthorized` son interceptadas y manejadas (se intenta refresh). El breaker no las cuenta como fallos. | Lanzó 7 peticiones con error 401. El breaker permaneció CERRADO, `_fallos_consecutivos = 0`. | **✅ PASADO** |
| **CASO 4** | Transición ABIERTO → SEMIABIERTO | Transcurrido el `timeout_apertura` (2s en testing), el disyuntor transiciona automáticamente a SEMIABIERTO para permitir prueba. | Tras esperar 2.2s, la llamada a `_revisar_timeout` transicionó el estado a SEMIABIERTO. | **✅ PASADO** |
| **CASO 5** | Recuperación (SEMIABIERTO → CERRADO) | Con el disyuntor en SEMIABIERTO, una petición exitosa cierra el circuito y resetea el contador de fallos. | La petición de prueba tuvo éxito, el estado pasó a CERRADO y los fallos se resetearon a 0. | **✅ PASADO** |
| **CASO 6** | Fallo en SEMIABIERTO (SEMI → ABIERTO) | Si la petición de prueba en SEMIABIERTO falla, reabre el circuito instantáneamente con un nuevo `timeout_apertura` completo. | La llamada falló, transicionó a ABIERTO inmediatamente y reajustó el timestamp de apertura. | **✅ PASADO** |
| **CASO 7** | Concurrencia en SEMIABIERTO | 3 peticiones concurrentes en SEMIABIERTO. Exactamente 1 pasa al servidor para prueba; las otras 2 son rebotadas con `CircuitOpenError`. | 1 petición de prueba exitosa, 2 peticiones rechazadas con `CircuitOpenError` al instante. Mock recibió exactamente 1 petición. | **✅ PASADO** |

---

## 🔍 Auditoría de Bugs de Resiliencia — Casos Críticos

### 1. BUG 1: El "Timer Fantasma" (Vulnerabilidad de Reloj del Sistema)
- **Causa Raíz:** Si el disyuntor usara el reloj del sistema mediante `time.time()` en Python o `Date.now()` en JavaScript, el cálculo del tiempo transcurrido en estado ABIERTO sería vulnerable a sincronizaciones automáticas de red NTP (Network Time Protocol) o cambios manuales de zona horaria. Si el reloj se retrasa 10 segundos debido a un ajuste, el circuito permanecería cerrado o se abriría prematuramente.
- **Fix Aplicado:** Nuestra implementación utiliza **`time.monotonic()`** (reloj monotónico del sistema operativo que avanza lineal e incrementalmente y nunca puede retroceder). Esto garantiza precisión absoluta en el temporizador del disyuntor.

### 2. BUG 3: Lock que nunca se libera
- **Causa Raíz:** Al serializar llamadas asíncronas concurrentes, si una petición dentro del lock arrojara una excepción imprevista (como un desbordamiento o error de parsing) y el código no la manejara en un bloque de control de flujo estricto, el lock quedaría retenido para siempre, congelando todas las peticiones futuras.
- **Fix Aplicado:** Implementamos un bloque estructurado **`try...finally`** en el método `ejecutar` de `CircuitBreaker`. El lock se libera de forma absoluta en el bloque `finally` sin importar si la petición fue exitosa, falló en red, o lanzó un error sintáctico imprevisto.

### 3. BUG 4: Race Condition en Estado SEMIABIERTO
- **Causa Raíz:** En entornos asíncronos concurrentes, si dos corrutinas prueban el estado del disyuntor exactamente en el mismo microsegundo mientras está en SEMIABIERTO, ambas podrían verificar que `_prueba_pendiente` es `False` antes de que cualquiera de las dos la cambie a `True`, logrando colar dos peticiones de prueba paralelas al servidor (violando **INV-A2**).
- **Fix Aplicado:** En Python asyncio, la ejecución entre palabras clave `await` es completamente atómica al no haber multi-threading real (el event loop corre en un único hilo). Al verificar `self._prueba_pendiente` y cambiar el estado inmediatamente en sentencias síncronas antes de hacer `await self._lock.acquire()`, garantizamos que no hay interrupciones del scheduler de asyncio, haciendo que la verificación sea 100% libre de race conditions.

---

## 📈 Evidencia Cuantitativa de Protección al Servidor

Para demostrar el valor del disyuntor a los ingenieros de infraestructura, registramos las llamadas HTTP que llegaron a tocar la red del servidor mock durante un evento de crisis (Modo `fallo_503` activo):

- **Sin Circuit Breaker (Polling ciego con Retry):**
  - Número de peticiones del cliente: **12 peticiones**
  - Número de llamadas recibidas y procesadas por el servidor: **12 llamadas**
  - *Consecuencia:* El servidor caído es saturado por reintentos constantes, impidiendo su recuperación.

- **Con Circuit Breaker (`umbral_fallos = 5`):**
  - Número de peticiones del cliente: **12 peticiones**
  - Número de llamadas recibidas por el servidor antes de abrir: **5 llamadas**
  - Número de llamadas recibidas por el servidor después de abrir: **0 llamadas** (Las restantes 7 fueron rebotadas localmente por el disyuntor en 0.1ms).
  - *Métrica de Mitigación:* **100% de reducción de carga** sobre el servidor remoto durante todo el periodo en que el circuito estuvo abierto.
