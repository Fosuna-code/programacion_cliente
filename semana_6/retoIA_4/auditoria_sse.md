# Auditoría SSE — RetoIA_4 · Semana 6
## Fase VALIDA · Programación Distribuida del Lado del Cliente · UAN

---

## Los 6 invariantes que un cliente SSE robusto NO debe romper

Antes de auditar, estos son los invariantes del cliente:

1. **Buffer reseteado completamente** después de cada mensaje completo
2. **Timeout de 30s configurado** en la conexión inicial (no `None`)
3. **Last-Event-ID enviado** en headers al reconectar
4. **Máximo 5 intentos de reconexión** con backoff exponencial (no flat retry)
5. **Excepción en handler no cierra el stream** — solo loguear y continuar
6. **204 No Content detiene la reconexión** permanentemente (no solo incrementa contador)

---

## Los 4 Errores Encontrados

### 🐛 Error #1 — Last-Event-ID nunca se envía en reconexión

**Ubicación**: método `_consumir_stream()`, sección de headers

**Código con error:**
```python
headers = {
    "Accept": "text/event-stream",
}
# _ultimo_id se guarda en self._ultimo_id pero NUNCA se incluye en headers
```

**Código corregido:**
```python
headers = {
    "Accept": "text/event-stream",
    "Cache-Control": "no-cache",
}
if self._ultimo_id is not None:
    headers["Last-Event-ID"] = self._ultimo_id
```

**Invariante violado**: #3 (Last-Event-ID en reconexión)

**¿Cómo falla en producción?**
El servidor usa `Last-Event-ID` para saber desde qué punto reanudar el stream.
Sin él, después de una desconexión, el servidor envía todos los eventos desde el
principio — o solo los futuros, dependiendo de su implementación. El cliente puede
perder eventos emitidos durante la desconexión o recibir duplicados.

**Evidencia de manifestación:**
```
[SIMULACIÓN — servidor con historial de 5 eventos]
Primera conexión:
  [15:30:01] Evento id=1 | tipo=precio-actualizado
  [15:30:04] Evento id=2 | tipo=stock-critico
  [15:30:07] Evento id=3 | tipo=precio-actualizado
  ✗ CORTE DE RED

Reconexión (con el código buggy):
  Headers enviados: {"Accept": "text/event-stream"}  ← SIN Last-Event-ID
  Servidor NO sabe desde dónde reanudar
  [15:30:11] Evento id=1 | tipo=precio-actualizado  ← DUPLICADO desde el inicio
  [15:30:11] Evento id=2 | tipo=stock-critico       ← DUPLICADO
  [15:30:11] Evento id=3 | tipo=precio-actualizado  ← DUPLICADO

  Los eventos 4 y 5 emitidos durante el downtime se PERDIERON porque
  el servidor no pudo identificar qué eventos ya había recibido el cliente.

Reconexión (con código corregido):
  Headers enviados: {"Accept": "...", "Last-Event-ID": "3"}
  [15:30:11] Evento id=4 | tipo=nuevo-pedido    ← reanuda desde id=4
  [15:30:11] Evento id=5 | tipo=stock-critico   ← sin pérdida
```

---

### 🐛 Error #2 — Timeout de conexión es `None` (sin límite)

**Ubicación**: `_consumir_stream()`, configuración de `httpx.Timeout`

**Código con error:**
```python
timeout = httpx.Timeout(
    connect=None,  # BUG: sin timeout de conexión
    read=None,
    write=10.0,
    pool=5.0,
)
```

**Código corregido:**
```python
timeout = httpx.Timeout(
    connect=30.0,   # INVARIANTE: timeout de 30s en la conexión inicial
    read=None,      # lectura sin límite (stream abierto)
    write=10.0,
    pool=5.0,
)
```

**Invariante violado**: #2 (Timeout de 30s en conexión inicial)

**¿Cómo falla en producción?**
Si el servidor está caído o la red es muy lenta, el cliente intenta conectar
indefinidamente sin timeout. El programa cuelga para siempre en la llamada
`cliente.stream(...)`. El operador no puede determinar si el cliente está
esperando datos o si está colgado en la conexión inicial.

En producción con 800 clientes, esto significa que una caída del servidor
hace que todos los procesos clientes queden colgados — consumiendo recursos
(descriptores de archivo, memoria de socket) sin posibilidad de recuperación
automática, hasta que el proceso se mate manualmente.

**Evidencia de manifestación:**
```
# Apuntar a un servidor que no responde (puerto bloqueado):
$ python receptor_con_errores.py
🔌 Conectando a http://192.168.1.100:8000/api/alertas ...
[cursor parpadeando... sin salida durante 3 minutos]
[el proceso NO falla — está colgado esperando conectar]

# Con el código corregido (connect=30.0):
🔌 Conectando a http://192.168.1.100:8000/api/alertas ...
⏱  Timeout de 30.0s alcanzado. Intento 1/5
⏳ Esperando 3.0s antes de reconectar...
[el cliente falla en 30s y procede con reconexión/backoff]
```

---

### 🐛 Error #3 — 204 No Content no detiene el ciclo de reconexión

**Ubicación**: método `iniciar()`, bloque `except httpx.HTTPStatusError`

**Código con error:**
```python
except httpx.HTTPStatusError as e:
    if e.response.status_code == 204:
        print("204 No Content — fin del stream.")
        reintentos += 1  # BUG: solo incrementa el contador, NO detiene el ciclo
        # El ciclo while self._activo: sigue ejecutándose
        # Después de 5 reintentos con 204, se detiene — pero debería detenerse inmediatamente
```

**Código corregido:**
```python
except httpx.HTTPStatusError as e:
    if e.response.status_code == 204:
        print("✅ Servidor envió 204 No Content — fin del stream. No se reconecta.")
        self._activo = False  # CORRECCIÓN: detener inmediatamente
        return
    reintentos += 1
    print(f"❌ Error HTTP {e.response.status_code}. Intento {reintentos}/{self.max_reintentos}")
```

**Invariante violado**: #6 (204 No Content detiene reconexión permanentemente)

**¿Cómo falla en producción?**
El código 204 es la señal del servidor de que el stream terminó intencionalmente —
no es un error temporal, sino una terminación limpia. Por ejemplo: "el evento de
cierre de mercado fue enviado, no hay más alertas hoy". Si el cliente reconecta
5 veces más antes de detenerse, genera carga innecesaria en el servidor y demora
la detención del programa.

**Evidencia de manifestación:**
```
# Servidor que responde 204 después del primer evento:
[15:30:01] Evento id=1 | tipo=precio-actualizado  ← evento normal
[15:30:05] 204 No Content — fin del stream.
⏳ Esperando 3.0s antes de reconectar...   ← BUG: debería parar aquí

🔌 Conectando... (intento 1/5)
[15:30:08] 204 No Content — fin del stream.
⏳ Esperando 6.0s antes de reconectar...   ← BUG: 5 reintentos innecesarios

[... 3 intentos más con backoff creciente ...]
🚫 Máximo de reintentos alcanzado. Deteniendo.   ← se detuvo 5 intentos tarde

# Con código corregido:
[15:30:01] Evento id=1 | tipo=precio-actualizado
[15:30:05] ✅ Servidor envió 204 No Content — fin del stream. No se reconecta.
🏁 ReceptorAlertas detenido limpiamente.   ← parada inmediata
```

---

### 🐛 Error #4 — Backoff de reconexión es constante (no exponencial)

**Ubicación**: método `iniciar()`, cálculo de tiempo de espera

**Código con error:**
```python
espera = self.retry_ms / 1000  # BUG: siempre 3s, sin backoff exponencial
await asyncio.sleep(espera)
```

**Código corregido:**
```python
# Backoff exponencial: retry_ms × 2^(reintentos-1), cap en 60s
espera_ms = min(self.retry_ms * (2 ** (reintentos - 1)), 60_000)
espera_s = espera_ms / 1000
print(f"⏳ Esperando {espera_s:.1f}s antes de reconectar (backoff exponencial)...")
await asyncio.sleep(espera_s)
```

**Invariante violado**: #4 (reconexión con backoff exponencial)

**¿Cómo falla en producción?**
Sin backoff exponencial, si el servidor cae, todos los clientes intentan reconectar
cada 3 segundos simultáneamente. Con 800 clientes, esto genera **800 peticiones cada
3 segundos** — una tormenta de reconexiones que puede impedir que el servidor se recupere.

El backoff exponencial (3s → 6s → 12s → 24s → 48s) distribuye los reintentos en el
tiempo, dando al servidor espacio para recuperarse. Este patrón se llama
*Exponential Backoff with Jitter* en sistemas distribuidos.

**Evidencia de manifestación:**
```
# Con código buggy (servidor caído):
⏳ Esperando 3.0s antes de reconectar...   # intento 1
⏳ Esperando 3.0s antes de reconectar...   # intento 2
⏳ Esperando 3.0s antes de reconectar...   # intento 3
⏳ Esperando 3.0s antes de reconectar...   # intento 4
⏳ Esperando 3.0s antes de reconectar...   # intento 5
[todos los intentos con el mismo intervalo → tormenta de reconexiones]

# Con código corregido (backoff exponencial):
⏳ Esperando 3.0s antes de reconectar...    # intento 1: 3000ms × 2^0 = 3s
⏳ Esperando 6.0s antes de reconectar...    # intento 2: 3000ms × 2^1 = 6s
⏳ Esperando 12.0s antes de reconectar...   # intento 3: 3000ms × 2^2 = 12s
⏳ Esperando 24.0s antes de reconectar...   # intento 4: 3000ms × 2^3 = 24s
⏳ Esperando 48.0s antes de reconectar...   # intento 5: 3000ms × 2^4 = 48s
🚫 Se alcanzó el límite de 5 reintentos.   → carga total en el servidor: mucho menor
```

---

## Resumen de auditoría

| # | Error | Invariante violado | Falla en producción |
|---|-------|-------------------|---------------------|
| 1 | Last-Event-ID no se envía | #3 Last-Event-ID en reconexión | Pérdida/duplicación de eventos |
| 2 | `connect=None` sin timeout | #2 Timeout de 30s | Cliente cuelga indefinidamente |
| 3 | 204 no detiene el ciclo | #6 204 detiene reconexión | 5 reintentos innecesarios |
| 4 | Backoff constante (no exponencial) | #4 Backoff exponencial | Tormenta de reconexiones |

---

## Código corregido (versión limpia)

Ver [`../../retoIA_2/receptor_alertas.py`](../../retoIA_2/receptor_alertas.py) para la
implementación completa con todos los invariantes respetados.

Los 4 errores encontrados son exactamente las brechas más frecuentes del examen anterior:
- ⚠ Timeout no configurado → Error #2
- ⚠ Detención sucia del ciclo async → Error #3
- ⚠ 5xx reintentado sin backoff → Error #4
- ⚠ Last-Event-ID perdido en reconexión → Error #1

---

*Autor: Fosuna · RetoIA_4 · Semana 6 · Dr. Eligardo Cruz Sánchez · UAN*
