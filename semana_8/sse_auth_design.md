# Reto 7 — Diseño de Integración SSE + Auth · Semana 8 (Avanzado)
## Programación Distribuida del Lado del Cliente · UAN

---

## El problema

El `ClienteSSEMultiplex` de Semana 7 abre una conexión HTTP persistente a
`/api/ecomarket/eventos`. El `TokenManager` de Semana 8 gestiona un `access_token`
de **15 minutos de duración**. ¿Qué pasa cuando el token expira mientras la
conexión SSE sigue activa?

El servidor puede comportarse de dos formas:
- **Opción A**: Ignorar la expiración y seguir enviando eventos (sin re-autenticación)
- **Opción B**: Cerrar la conexión cuando detecta que el token expiró (401 o evento especial)

---

## 1. Análisis de Opciones A vs B — perspectiva del cliente

### Opción A: El servidor ignora la expiración

**Ventaja para el cliente**: sin lógica adicional — la conexión nunca se interrumpe.

**Vulnerabilidad**: si el token fue revocado (ej: el operador fue desactivado en el
sistema de RRHH), el servidor debería rechazarlo pero no lo hace. La conexión SSE
quedaría "fantasma": activa pero para un usuario que ya no tiene acceso. El operador
seguiría viendo datos del panel que ya no debería ver.

**Postura del equipo de seguridad**: inaceptable en producción. Una sesión que no
respeta la revocación del token es un agujero de seguridad — aunque conveniente
para el cliente.

**Postura del cliente (simplicidad)**: preferible — cero interrupciones para el operador.

### Opción B: El servidor cierra en expiración

**Ventaja de seguridad**: el servidor detecta el token expirado o revocado y cierra
la conexión con un evento especial o un 401. El cliente SABE que debe renovar.

**Complejidad para el cliente**: debe:
1. Distinguir un cierre por expiración de un cierre por error de red (¿cómo?)
2. Renovar el token antes de reconectar
3. Reconectar con el nuevo token automáticamente

**Postura del equipo de seguridad**: preferible — garantiza que las sesiones respetan
el ciclo de vida del token.

**Conclusión**: Para EcoMarket (panel con datos comerciales sensibles), se elige
**Opción B** desde el diseño, pero se implementa **refresh proactivo** en el cliente
para que la reconexión sea casi instantánea y el operador apenas note la interrupción
(duración ~2 segundos para refresh + reconexión).

---

## 2. Mecanismo de paso del token al abrir la conexión SSE

### Ruta Browser (JavaScript con EventSource nativo)

**Problema crítico**: el `EventSource` de los navegadores **no soporta headers personalizados**.
No existe forma de añadir `Authorization: Bearer <token>` a la petición de `EventSource`.

Las tres opciones disponibles:

| Opción | Mecanismo | Ventaja | Riesgo |
|---|---|---|---|
| A | `?token=eyJ...` en la URL | Simple, funciona en todos los navegadores | El token queda en **logs del servidor**, historial del navegador y headers `Referer`. Anti-patrón documentado. |
| B | Cookie HttpOnly enviada automáticamente | El navegador la adjunta sin código JS | Requiere `SameSite=Strict` + CSRF protection en el endpoint SSE |
| C | Header `Authorization` (no disponible) | Estándar OAuth 2.0 | **No implementable** con EventSource nativo |

**Elección para ruta Browser**: **Cookie HttpOnly (Opción B)**.
El `access_token` viaja en una cookie `HttpOnly; SameSite=Strict; Secure`, emitida
por el servidor después del login. El navegador la adjunta automáticamente a la
petición GET de la conexión SSE. El JavaScript nunca la lee ni la envía manualmente.

Alternativa cuando no hay cookies (app móvil, Electron): usar `fetch()` con
`ReadableStream` en lugar de `EventSource` nativo — `fetch()` sí soporta headers:
```js
const resp = await fetch('/api/ecomarket/eventos', {
  headers: { 'Authorization': `Bearer ${tokenManager.getAccessToken()}` }
});
// Leer el stream con resp.body.getReader()
```

### Ruta Python (httpx async streaming)

En Python no hay la restricción de `EventSource`. La implementación de Semana 7
usa `httpx.AsyncClient().stream()`, que sí admite el header `Authorization`.

```python
headers = {
    "Accept": "text/event-stream",
    "Authorization": f"Bearer {token_manager.get_auth_header()['Authorization'].split()[1]}"
}
async with httpx.AsyncClient().stream("GET", url, headers=headers) as resp:
    ...
```

---

## 3. Diseño del cliente — flujo de reconexión autenticada (Opción B)

El servidor cierra la conexión SSE cuando el token expira. El cliente lo detecta
y reconecta con un token renovado. El `ClienteSSEMultiplex` de Semana 7 ya tiene
un mecanismo de reconexión con backoff — la integración agrega un paso de refresh
antes del reintento.

### Flujo en pseudocódigo

```
FUNCIÓN iniciar_con_auth(token_manager, modulos):

  MIENTRAS no parar:
    token = token_manager.get_auth_header()
    SI token está vacío:
      LANZAR RuntimeError("No autenticado — hacer login primero")

    # Incluir token al abrir la conexión SSE
    headers = {
      "Accept": "text/event-stream",
      "Authorization": token["Authorization"]
    }

    INTENTAR:
      CONECTAR a /api/ecomarket/eventos?modulos=precios,inventario,pedidos
        CON headers = headers
        CON timeout = 30s

      LEER stream línea por línea:
        PARA cada línea en stream:
          SI línea == "":
            procesar_evento(evento_parcial)
          SINO:
            parsear_linea(linea, evento_parcial)

    CAPTURAR HTTP 401:
      # El servidor cerró porque el token expiró
      # ¿Cómo distinguir de un error de red?
      #   → HTTP 401 es explícito; un error de red lanza ConnectError, no HTTP 401
      IMPRIMIR "Token expirado durante conexión SSE — iniciando refresh"

      refresh_ok = ESPERAR token_manager.refresh_access_token()
      SI no refresh_ok:
        IMPRIMIR "Refresh falló — el operador debe re-autenticarse"
        PARAR
      SINO:
        IMPRIMIR "Token renovado — reconectando SSE con nuevo token"
        # Volver al inicio del MIENTRAS sin espera (no backoff — no es error de red)
        CONTINUAR

    CAPTURAR ConnectError, TimeoutError:
      # Error de red — usar backoff exponencial (lógica de Semana 7)
      reintentos += 1
      espera = min(1 * 2^(reintentos-1), 60)
      ESPERAR espera segundos
      CONTINUAR

  RETORNAR "Conexión SSE detenida limpiamente"
```

### ¿Cómo distinguir "cerró por expiración" de "cerró por error de red"?

| Causa | Señal que recibe el cliente | Acción |
|---|---|---|
| Token expirado | HTTP `401 Unauthorized` (respuesta del servidor) | Refresh + reconectar inmediatamente |
| Error de red | `httpx.ConnectError` / `httpx.TimeoutException` | Backoff exponencial + reconectar |
| Servidor caído | `httpx.ConnectError` | Backoff exponencial + alertar |
| Stream terminó normalmente | Fin del stream sin excepción (HTTP 200 completado) | Reconectar o detener según configuración |

El cliente distingue porque:
- HTTP 401 → `resp.raise_for_status()` lanza `httpx.HTTPStatusError` con `status_code=401`
- Error de red → lanza `httpx.ConnectError` (sin código HTTP)

### Integración con ClienteSSEMultiplex de Semana 7

El cambio mínimo al código de Semana 7 es en el método `_conectar()`:

```python
async def _conectar(self, token_manager: TokenManager) -> None:
    url = self.construir_url()
    headers = {
        "Accept": "text/event-stream",
        "Cache-Control": "no-cache",
        **token_manager.get_auth_header(),   # ← ÚNICA LÍNEA NUEVA
    }
    if self.ultimo_id:
        headers["Last-Event-ID"] = self.ultimo_id

    async with httpx.AsyncClient() as cliente:
        async with cliente.stream("GET", url, headers=headers, timeout=...) as resp:
            if resp.status_code == 401:
                raise httpx.HTTPStatusError("401 — token expirado", ...)
            resp.raise_for_status()
            await self._leer_stream(resp)
```

Y en `iniciar()`, capturar el 401 específicamente para hacer refresh antes de reconectar:

```python
except httpx.HTTPStatusError as e:
    if e.response.status_code == 401:
        # Token expirado — refresh sin backoff
        ok = await token_manager.refresh_access_token()
        if not ok:
            print("Refresh falló — detener SSE")
            break
        # Continuar el loop → reconectar con nuevo token
    else:
        # Otro error HTTP — backoff normal
        ...
```

---

## 4. Consideraciones de seguridad al pasar el token

### Problema del query parameter (`?token=eyJ...`)

Si por limitaciones técnicas el equipo decide usar el query parameter para la
conexión SSE (por ejemplo, al usar `EventSource` nativo sin migrar a `fetch()` streaming):

- El token completo (15 minutos de validez) queda en:
  - Logs del servidor (Nginx, Apache, etc.) por defecto
  - Historial del navegador
  - Headers `Referer` si hay recursos de terceros en la página
  
**Mitigación parcial**: usar tokens de vida muy corta (1–2 minutos) específicos
para la conexión SSE, distintos del access_token general. El endpoint SSE acepta
solo este token especial. Si se filtra, solo da acceso durante 1–2 minutos y solo
al endpoint de eventos, no a los endpoints REST de la API.

### Solución recomendada para producción

La solución más robusta combina:
1. **Cookie HttpOnly** para el token de larga duración (refresh_token)
2. **fetch() streaming** (en lugar de EventSource nativo) para el SSE en browser,
   que sí permite headers personalizados con `Authorization: Bearer`
3. **Refresh proactivo** en el TokenManager para que el token sea renovado antes
   de expirar, evitando la reconexión visible

---

## 5. Trade-offs resumidos

| Decisión | Elegido | Alternativa | Razón del rechazo |
|---|---|---|---|
| Opción servidor | B (cierra en expiración) | A (ignora) | Seguridad > conveniencia para datos comerciales |
| Paso del token en Python | Header `Authorization` | Query param | Query param → token en logs del servidor |
| Paso del token en Browser | Cookie HttpOnly | Query param con EventSource | Query param es anti-patrón documentado |
| Refresh ante 401 en SSE | Sin backoff (reconexión inmediata) | Backoff exponencial | 401 no es error de red — el token ya está listo |
| Distinción 401 vs ConnectError | `HTTPStatusError.status_code` | Flag booleano externo | El código HTTP es la señal más directa y precisa |

---

*Dr. Eligardo Cruz Sánchez · Universidad Autónoma de Nayarit · Semana 8 de 15*
