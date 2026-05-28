# Semana 8 — TokenManager · Autenticación JWT desde el Cliente
## Programación Distribuida del Lado del Cliente · UAN

---

## Reto 2 — COMPRENDE: Decisiones de diseño antes de codificar

### 1. ¿Qué puede leer el cliente del JWT y por qué?

El payload del JWT está en **Base64URL** — no cifrado. Cualquier programa puede
decodificarlo. El cliente lee el payload para:
- Extraer `exp` → calcular cuándo expira y disparar refresh proactivo
- Extraer `sub`, `email`, `role` → mostrar nombre de usuario y ajustar la UI

Lo que el cliente **nunca hace**: verificar la firma. La seguridad del JWT viene
de que el **servidor rechaza cualquier token con firma inválida** — no de que el
payload sea secreto. El servidor es el árbitro final.

**Zero Tolerance (de la guía del curso):** implementar HMAC, RSA u otro algoritmo
de firma en el cliente invalida el entregable completo — es una decisión de
arquitectura incorrecta, no un error de código.

### 2. ¿Qué pasa cuando el token expira mientras el panel está activo?

Sin TokenManager: el operador recibe un 401 silencioso y la UI se congela o
muestra un error críptico. El usuario no sabe qué pasó.

Con TokenManager:
- **Refresh proactivo**: a los 10 minutos (faltando 5), el cliente detecta
  `is_expiring_soon()=True` y renueva el token *antes* de que expire.
  El operador nunca nota interrupciones.
- **Refresh reactivo**: si el proactivo falla (clock skew, red lenta), el
  interceptor HTTP detecta el 401 del servidor, dispara `refresh_access_token()`
  y reintenta la petición original automáticamente — transparente para el código
  que usa la API.

### 3. ¿Por qué el refresh debe ser "singleton"?

El problema: si hay 5 peticiones concurrentes al panel (precios, stock, pedidos,
heartbeat, fetch de historial) y el token expira, **todas recibirán 401 al mismo
tiempo**. Sin protección, dispararán 5 llamadas a `/api/auth/refresh` simultáneas.

Muchos servidores implementan **Token Rotation**: el primer uso del refresh_token
lo invalida y emite uno nuevo. Las 4 peticiones restantes fallarán con 401 (el
refresh_token que intentan usar ya fue invalidado por la primera) — forzando un
logout no deseado.

La solución es `asyncio.Lock`: la primera corrutina que llegue al lock lo toma
y hace la petición real. Las otras 4 esperan en `async with self._refresh_lock`.
Al liberarse el lock, encuentran el `_access_token` ya actualizado — sin hacer
una petición adicional.

### 4. ¿Dónde guardar los tokens?

| Token | Dónde | Razón |
|---|---|---|
| `access_token` | Memoria del proceso (`_access_token`) | Ventana de daño: 15 min. Si el proceso muere, el usuario re-autentica. |
| `refresh_token` | Memoria del proceso (`_refresh_token`) | Para persistencia: keyring del OS. Nunca archivo plano. |

**Ruta Browser** (referencia):
- `access_token` → variable de módulo JS (closure) — no en `localStorage`
- `refresh_token` → cookie `HttpOnly + SameSite=Strict` — JavaScript nunca la ve

**Por qué no `localStorage` para el refresh_token**: un script malicioso (XSS)
puede ejecutar `localStorage.getItem('refresh_token')` en una línea y robar un
token de 7 días de vida. Con cookie `HttpOnly`, el script no puede leerla.

### 5. Máquina de estados del TokenManager

```
SIN_TOKEN → (login exitoso) → AUTENTICADO
AUTENTICADO → (exp - now < 5 min) → RENOVANDO (proactivo)
AUTENTICADO → (recibe 401) → RENOVANDO (reactivo)
RENOVANDO → (refresh OK) → AUTENTICADO
RENOVANDO → (refresh 401) → SIN_TOKEN (logout)
AUTENTICADO → (logout()) → SIN_TOKEN
```

---

## Archivos del proyecto

| Archivo | Reto | Descripción |
|---|---|---|
| [token_manager.py](./token_manager.py) | 3 + 4 + 6 | TokenManager completo + interceptor auth_request + 6 casos de prueba |
| [README.md](./README.md) | 2 | Este archivo — decisiones de diseño y documentación |
| [sse_auth_design.md](./sse_auth_design.md) | 7 | Diseño de integración SSE + Auth (avanzado) |

---

## Cómo ejecutar

```bash
# Instalar dependencias
pip install httpx

# Demo offline (sin servidor real) + validación de 6 casos
python token_manager.py
```

---

## Invariantes del sistema

| Invariante | Descripción |
|---|---|
| INV-TM1 | `decode_payload()` NUNCA verifica firma (Zero Tolerance) |
| INV-TM2 | `is_expiring_soon()` usa segundos Unix — nunca milisegundos |
| INV-TM3 | Token sin `exp` → tratarlo como expirado inmediatamente |
| INV-TM4 | `refresh_access_token()` → solo 1 petición real (asyncio.Lock) |
| INV-TM5 | `logout()` limpia TODO: token, flag, cola, timer proactivo |
| INV-TM6 | Token malformado → ValueError controlado, no IndexError sin capturar |

---

*Dr. Eligardo Cruz Sánchez · Universidad Autónoma de Nayarit · Semana 8 de 15*
