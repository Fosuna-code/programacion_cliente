# RetoIA_2 — Receptor de Alertas EcoMarket (Cliente SSE)
## Semana 6 · Programación Distribuida del Lado del Cliente · UAN

---

## Traza del flujo SSE (Reto 1)

```
t=0s   Cliente → GET /api/alertas
       Headers: Accept: text/event-stream, Cache-Control: no-cache
       (timeout de conexión: 30s)

t=0s   Servidor ← 200 OK
       Headers: Content-Type: text/event-stream
                Transfer-Encoding: chunked
       [Conexión TCP queda abierta — no se cierra]

t=2s   Servidor envía bytes al cliente:
       "id: 1\n"
       "event: precio-actualizado\n"
       "data: {\"producto\":\"A01\",\"precio\":47,\"moneda\":\"MXN\"}\n"
       "\n"    ← línea en blanco = MENSAJE COMPLETO
       Cliente: acumula líneas en buffer → detecta "\n" → crea EventoSSE
               actualiza _ultimo_id = "1"
               despacha handler manejar_precio_actualizado()

t=5s   Servidor envía:
       "id: 2\n"
       "event: stock-critico\n"
       "data: {\"producto\":\"B07\",\"stock\":1,\"umbral\":5}\n"
       "\n"
       Cliente: parsea → _ultimo_id = "2" → despacha manejar_stock_critico()

t=15s  Servidor envía comentario keep-alive:
       ": ping\n"
       Cliente: detecta línea que comienza con ':' → IGNORA como dato
                (el TCP lo procesa para evitar timeouts de red)

t=18s  Servidor envía:
       "id: 3\n"
       "event: precio-actualizado\n"
       "data: {\"producto\":\"A01\",\"precio\":45,\"moneda\":\"MXN\"}\n"
       "\n"
       Cliente: parsea → _ultimo_id = "3" → actualiza tabla

t=25s  ✗ CORTE DE RED — httpx lanza ConnectError o el stream termina
       Cliente: captura excepción, incrementa reintentos = 1

t=28s  Cliente espera retry_ms=3000ms (backoff exponencial para intento 1)
       retry = 3000 × 2^(1-1) = 3000ms

       Cliente → GET /api/alertas
       Headers: Accept: text/event-stream
                Last-Event-ID: 3    ← permite al servidor reanudar desde id=4
       Servidor puede reenviar eventos 4, 5, ... sin repetir los que ya llegaron
```

**Por qué SSE reduce peticiones vacías vs polling:**

Con polling en intervalo de 3s y 800 usuarios concurrentes, el servidor recibe
144,000 peticiones por minuto — la mayoría responden "sin cambios" (HTTP 304).
Con SSE, cada cliente mantiene 1 conexión TCP abierta y solo recibe bytes cuando
hay un cambio real. Para 2-3 cambios por hora, polling genera miles de peticiones
vacías; SSE genera exactamente 2-3 mensajes por hora por cliente.

---

## Instrucciones de ejecución

### 1. Instalar dependencia

```bash
pip install httpx
```

### 2. Ejecutar el cliente

```bash
# Usando el endpoint público de prueba (sse.dev/test)
python receptor_alertas.py
```

### 3. Probar con servidor propio

Levanta un servidor mínimo SSE con FastAPI:

```python
# servidor_sse_minimo.py
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import asyncio, json, time

app = FastAPI()

@app.get("/api/alertas")
async def alertas():
    async def generar():
        eventos = [
            {"id": 1, "event": "precio-actualizado",
             "data": json.dumps({"producto":"A01","precio":47,"moneda":"MXN"})},
            {"id": 2, "event": "stock-critico",
             "data": json.dumps({"producto":"B07","stock":1,"umbral":5})},
            {"id": 3, "event": "precio-actualizado",
             "data": json.dumps({"producto":"A01","precio":45,"moneda":"MXN"})},
        ]
        for ev in eventos:
            yield f"id: {ev['id']}\n"
            yield f"event: {ev['event']}\n"
            yield f"data: {ev['data']}\n\n"
            await asyncio.sleep(3)
        # Señal de fin de stream
        yield ": fin del stream\n\n"
    return StreamingResponse(generar(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"})
```

```bash
pip install fastapi uvicorn
uvicorn servidor_sse_minimo:app --port 8000
```

Luego cambia la URL en `receptor_alertas.py`:
```python
URL_SSE = "http://localhost:8000/api/alertas"
```

### 4. Probar reconexión

Levanta el servidor, ejecuta el cliente, y luego detén el servidor con Ctrl+C.
El cliente intentará reconectar hasta 5 veces con backoff exponencial:
```
Intento 1: espera 3s
Intento 2: espera 6s
Intento 3: espera 12s
Intento 4: espera 24s
Intento 5: espera 48s → detener
```

---

## Arquitectura del cliente

```
ReceptorAlertas
├── iniciar()          → bucle de reconexión con backoff exponencial
│   └── _consumir_stream()   → abre conexión HTTP + itera líneas
│       └── parsear_linea()  → acumula buffer → devuelve EventoSSE
│           └── _procesar_evento()  → despacha handler por tipo
├── detener()          → bandera _activo = False (sin tareas huérfanas)
└── _ultimo_id         → almacena id para Last-Event-ID en reconexión

Handlers registrados:
  "precio-actualizado" → manejar_precio_actualizado() → actualiza TablaPrecios
  "stock-critico"      → manejar_stock_critico()       → imprime alerta ⚠️
  (desconocido)        → log de advertencia + continúa
```

---

## Checklist de validación (Reto 4)

| Ítem | Descripción | Prueba |
|------|-------------|--------|
| ✅ | Buffer reseteado después de cada mensaje | 3 eventos seguidos → buffer limpio |
| ✅ | Timeout 30s en conexión inicial | Apuntar a servidor caído → falla en 30s |
| ✅ | Last-Event-ID en reconexión | Ver headers de segunda conexión en logs |
| ✅ | Máximo 5 reintentos con backoff | Servidor caído → se detiene en intento 5 |
| ✅ | Excepción en handler no cierra stream | raise en handler → log + continúa |
| ✅ | 204 No Content detiene reconexión | Servidor devuelve 204 → no reintentar |
| ✅ | Detención limpia con bandera | Ctrl+C → ninguna tarea activa |

---

## Archivos del proyecto

| Archivo | Descripción |
|---------|-------------|
| `receptor_alertas.py` | Cliente SSE principal (Ruta A — parseo manual) |
| `receptor_alertas_v2.py` | Cliente SSE + patrón Observer integrado (RetoIA_5) |
| `README.md` | Este archivo |
| `validacion.log` | Salida de terminal con evidencia de pruebas |
| `auditoria_sse.md` | Auditoría de código con errores (RetoIA_4) |

---

*Dr. Eligardo Cruz Sánchez · Universidad Autónoma de Nayarit · Semana 6 de 15*
