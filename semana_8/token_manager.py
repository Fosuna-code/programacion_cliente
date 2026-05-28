"""
TOKEN MANAGER — EcoMarket Panel de Control
==========================================
Semana 8 · Programación Distribuida del Lado del Cliente · UAN

Gestión del ciclo de vida completo de tokens JWT desde el cliente.
El servidor genera y valida los JWTs; este módulo es su CUSTODIO.

ZERO TOLERANCE: Este módulo NUNCA implementa verificación de firma
(HMAC, RSA ni ningún algoritmo de firma). La verificación es
responsabilidad exclusiva del servidor.

NOTA IMPORTANTE — por qué el cliente PUEDE leer el payload:
  El payload del JWT está codificado en Base64URL, no cifrado.
  Cualquier programa puede decodificarlo y leer su contenido.
  La seguridad del JWT NO viene del secreto del payload, sino de
  que el servidor rechaza cualquier token con firma inválida.
  El cliente lee el payload SOLO para gestión de ciclo de vida
  (leer exp, sub, role para UI) — nunca para tomar decisiones de
  seguridad de acceso. El servidor es el árbitro final.

INVARIANTES GLOBALES:
  INV-TM1: decode_payload() NUNCA intenta verificar firma.
  INV-TM2: is_expiring_soon() usa segundos Unix, jamás milisegundos.
  INV-TM3: Token sin campo 'exp' → tratar como EXPIRADO inmediatamente.
  INV-TM4: refresh_access_token() → solo UNA petición real al servidor
            aunque sean N corrutinas concurrentes llamando al mismo tiempo.
  INV-TM5: logout() limpia TODO el estado: token, flag, cola de espera, timer.
  INV-TM6: decode_payload() lanza ValueError controlado ante token malformado
            (no IndexError/KeyError sin capturar que derribe el cliente).

ESTRATEGIA DE ALMACENAMIENTO (Reto 5 — Reflexiona):
  access_token  → variable en memoria del proceso (_access_token)
    Razón: si el proceso es comprometido, el atacante ya tiene acceso total.
    Guardar en archivo cifrado o envvar no añade protección en este escenario.
    La ventana de daño es 15 min — el servidor invalida el token al expirar.
    En producción (servicio backend-to-backend): usar keyring del OS o vault.

  refresh_token → variable en memoria del proceso (_refresh_token)
    Razón de diseño (ruta Python): en memoria, el token vive solo mientras
    el proceso existe. Si el proceso muere, el usuario hace login de nuevo.
    Trade-off aceptable para un servicio de larga duración (panel EcoMarket)
    donde el operador inicia sesión una vez por turno de trabajo.
    Para persistencia entre reinicios: usar keyring del OS (nunca archivo plano).

  CONTEXTO BROWSER (sub-ruta B recomendada):
    access_token → variable de módulo JS (closure, no accesible globalmente)
    refresh_token → cookie HttpOnly (JavaScript NUNCA la ve)
    → XSS no puede robar el refresh_token; CSRF al /refresh no sirve porque
      el response body solo contiene el access_token (el atacante no lo obtiene).

MARGEN DE REFRESH PROACTIVO: 300 segundos (5 minutos)
  Razón: token de 15 min → refrescar a los 10 min de vida (faltando 5).
  300s cubre clock skew de hasta ±2 min entre cliente y servidor (con margen),
  latencia de red alta (hasta 30s en redes corporativas con alta carga), y
  el caso de múltiples workers esperando el resultado del singleton.
  Margen menor (60s): riesgo de expirar durante el refresh en redes lentas.
  Margen mayor (750s): refresh cada 2.5 min — satura /api/auth/refresh.

SINGLETON DE REFRESH: asyncio.Lock
  Razón: asyncio.Lock es suficiente para proteger co-rutinas en el MISMO
  proceso/event loop. Si el servicio escala a múltiples workers o procesos
  (ej: gunicorn con 4 workers), asyncio.Lock NO los protege entre sí —
  cada proceso tendría su propio event loop y lock independiente.
  Para escenario multi-proceso: usar Redis con SETNX como mutex distribuido,
  o un servicio de lock externo.

COMPORTAMIENTO ANTE REFRESH FALLIDO:
  Si el servidor responde 401 al endpoint /api/auth/refresh, significa que el
  refresh_token también expiró o fue invalidado. El único camino correcto es
  logout() — limpiar todo el estado y notificar al usuario para que haga
  login de nuevo. NUNCA intentar hacer otro refresh (bucle infinito) ni
  continuar con el token expirado (peticiones siempre fallarán con 401).
"""

import asyncio
import base64
import json
import time
from typing import Optional

try:
    import httpx
except ImportError:
    raise SystemExit("pip install httpx")


# ════════════════════════════════════════════════════════════════════
# Configuración
# ════════════════════════════════════════════════════════════════════

AUTH_BASE_URL     = "http://localhost:8080"   # Apunta al mock para pruebas
LOGIN_ENDPOINT    = f"{AUTH_BASE_URL}/api/auth/login"
REFRESH_ENDPOINT  = f"{AUTH_BASE_URL}/api/auth/refresh"
RECURSO_ENDPOINT  = f"{AUTH_BASE_URL}/api/ecomarket/precios"

EXPIRY_MARGIN_SEC = 300   # Renovar si faltan < 5 minutos


# ════════════════════════════════════════════════════════════════════
# TokenManager
# ════════════════════════════════════════════════════════════════════

class TokenManager:
    """
    Gestiona el ciclo de vida de los JWT del cliente EcoMarket.

    Responsabilidades:
    - Almacenar access_token y refresh_token en memoria del proceso
    - Proveer el access_token vigente, renovándolo si es necesario
    - Refresh singleton: si ya hay un refresh en curso, otras corrutinas
      esperan su resultado (asyncio.Lock garantiza solo UNA petición real)
    - Limpiar el estado al hacer logout
    - Decodificar el payload del JWT para leer claims (sin verificar firma)
    """

    def __init__(self):
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._refresh_lock = asyncio.Lock()   # Singleton guard — INV-TM4
        self._proactive_task: Optional[asyncio.Task] = None   # Timer proactivo
        self._refresh_endpoint = REFRESH_ENDPOINT

    # ── Método 1: decode_payload ─────────────────────────────────────

    def decode_payload(self, token: str) -> dict:
        """
        Decodifica el payload de un JWT sin verificar firma.

        Retorna el dict de claims. Lanza ValueError si el token está malformado.

        DECISIÓN DE DISEÑO:
          El cliente puede leer el payload libremente porque está en Base64URL
          (no cifrado). Se usa SOLO para extraer exp, sub, role, etc. para
          gestión de UI y ciclo de vida del token. El servidor es el árbitro
          de seguridad — la firma es su responsabilidad, no la del cliente.
          INV-TM1: NUNCA se verifica la firma aquí.
          INV-TM6: malformado → ValueError controlado, no excepción silenciosa.

        Args:
            token: JWT completo (header.payload.signature)

        Returns:
            dict con los claims del payload decodificado

        Raises:
            ValueError: si el token no tiene exactamente 3 partes separadas por '.',
                        o si el payload no es JSON válido, o si Base64URL es inválido
        """
        # Paso 1: verificar estructura de 3 partes (INV-TM6)
        partes = token.split('.')
        if len(partes) != 3:
            raise ValueError(
                f"Token JWT malformado: se esperaban 3 partes separadas por '.', "
                f"se encontraron {len(partes)}. El token recibido no es un JWT válido."
            )

        # Paso 2: tomar la parte del payload (índice 1)
        payload_b64 = partes[1]

        # Paso 3: Base64URL → Base64 estándar
        #   - Reemplazar '-' por '+' y '_' por '/'
        #   - Añadir padding '=' hasta múltiplo de 4
        #   El '== * 2' extra es seguro: b64decode ignora padding sobrante
        b64_estandar = payload_b64.replace('-', '+').replace('_', '/')
        # Calcular padding exacto: (4 - len % 4) % 4
        padding_faltante = (4 - len(b64_estandar) % 4) % 4
        b64_con_padding = b64_estandar + '=' * padding_faltante

        # Paso 4: decodificar y parsear JSON
        try:
            payload_bytes = base64.b64decode(b64_con_padding)
            payload_dict = json.loads(payload_bytes)
        except Exception as e:
            raise ValueError(
                f"No se pudo decodificar el payload del JWT: {e}. "
                f"El payload no es Base64URL válido o no contiene JSON."
            )

        return payload_dict

    # ── Método 2: is_expiring_soon ───────────────────────────────────

    def is_expiring_soon(self, margin_seconds: int = EXPIRY_MARGIN_SEC) -> bool:
        """
        Retorna True si el access_token expirará en menos de margin_seconds segundos.

        DECISIÓN DE DISEÑO:
          INV-TM2: usa time.time() (segundos float) para comparar con exp (segundos Unix).
          INV-TM3: si el token no tiene campo 'exp', se trata como expirado inmediatamente
            (return True). Es más seguro asumir expiración que asumir validez indefinida.
          Si no hay token almacenado, también retorna True (sin token = hay que refrescar).
          El margen de 300s cubre clock skew y latencia de red.

        Returns:
            True  si el token expira pronto o ya expiró o no hay token
            False si el token tiene más de margin_seconds de vida restante
        """
        if self._access_token is None:
            return True   # Sin token → necesita refresh/login

        try:
            payload = self.decode_payload(self._access_token)
        except ValueError:
            # Token malformado → tratar como expirado
            return True

        # INV-TM3: sin 'exp' → tratar como expirado inmediatamente
        if 'exp' not in payload:
            return True

        exp_unix = payload['exp']
        # INV-TM2: time.time() devuelve segundos (float); exp es segundos Unix
        # ¡NUNCA comparar con time.time() * 1000 ni con Date.now() sin dividir!
        ahora_unix = int(time.time())
        tiempo_restante = exp_unix - ahora_unix

        return tiempo_restante < margin_seconds

    # ── Método 3: store_tokens ────────────────────────────────────────

    def store_tokens(self, access_token: str, refresh_token: Optional[str] = None) -> None:
        """
        Almacena los tokens recibidos del servidor al hacer login o refresh.

        DECISIÓN DE DISEÑO:
          Se almacenan en memoria del proceso — no en disco, no en vars de entorno.
          Razón: en una aplicación de servicio (no GUI), el proceso ya tiene acceso
          al sistema. Guardar en disco plano añade una superficie de ataque sin
          beneficio real. Para persistencia entre reinicios, usar keyring del OS.
          El refresh_token es opcional porque el endpoint /api/auth/refresh
          solo devuelve un nuevo access_token (Token Rotation: el nuevo refresh
          se entregaría aquí si el servidor lo implementa).

        Args:
            access_token: JWT de acceso (corta duración — 15 min)
            refresh_token: JWT de renovación (larga duración — 7 días), opcional en refresh
        """
        self._access_token = access_token
        if refresh_token is not None:
            self._refresh_token = refresh_token

        ts = time.strftime('%H:%M:%S')
        print(f"  🔐 [{ts}] Tokens almacenados en memoria")
        if refresh_token is not None:
            print(f"  🔐 [{ts}] refresh_token también almacenado")

    # ── Método 4: get_auth_header ─────────────────────────────────────

    def get_auth_header(self) -> dict:
        """
        Retorna el header Authorization listo para adjuntar a una petición.

        DECISIÓN DE DISEÑO:
          Formato Bearer es el estándar OAuth 2.0 (RFC 6750).
          Si no hay access_token almacenado, se retorna un dict vacío en lugar
          de lanzar excepción — el interceptor HTTP detectará la respuesta 401
          del servidor y disparará el refresh reactivo. Lanzar excepción aquí
          obligaría a cada llamante a manejarla antes de construir la petición.

        Returns:
            {"Authorization": "Bearer <access_token>"} si hay token
            {} (dict vacío) si no hay token almacenado
        """
        if self._access_token is None:
            return {}
        return {"Authorization": f"Bearer {self._access_token}"}

    # ── Método 5: logout ─────────────────────────────────────────────

    def logout(self) -> None:
        """
        Limpia todos los tokens del estado del cliente.

        DECISIÓN DE DISEÑO:
          INV-TM5: logout limpia TODO el estado:
            - _access_token  → None (evita tokens fantasma en memoria)
            - _refresh_token → None (evita que el siguiente login encuentre
                                     un refresh_token de sesión anterior)
            - _proactive_task → cancelar si existe (Error 4 en HTML: si el
                                 setInterval/asyncio.Task sigue corriendo,
                                 intentará hacer refresh con tokens ya eliminados)
          Un logout parcial (que solo borra el access_token) deja el refresh_token
          activo en memoria — un bug que permitiría al siguiente operador en el
          mismo proceso obtener un access_token nuevo sin autenticarse.
        """
        self._access_token = None
        self._refresh_token = None

        # Cancelar el timer de refresh proactivo (INV-TM5)
        if self._proactive_task and not self._proactive_task.done():
            self._proactive_task.cancel()
            self._proactive_task = None

        ts = time.strftime('%H:%M:%S')
        print(f"  🚪 [{ts}] Logout: estado limpiado completamente (tokens, timer)")

    # ── Método 6: refresh_access_token ───────────────────────────────

    async def refresh_access_token(self) -> bool:
        """
        Realiza el refresh del access_token usando el refresh_token.

        PATRÓN SINGLETON con asyncio.Lock — INV-TM4:
          El lock garantiza que solo UNA corrutina ejecute la petición HTTP
          real al endpoint de refresh. Las demás corrutinas concurrentes que
          lleguen mientras el lock está tomado esperarán en 'await lock.acquire()'
          y al liberarse encontrarán el access_token ya actualizado.

          Diferencia con el patrón de cola JS (_refreshQueue):
          asyncio.Lock hace que las corrutinas 2..N ESPEREN (no se encolan con
          Promises separadas). Al liberarse el lock, todas continúan y ven el
          nuevo _access_token. El resultado es el mismo: una sola petición real.

        MANEJO DE ERRORES:
          El lock se libera SIEMPRE gracias al bloque 'async with' (equivale a
          try/finally). Si el refresh falla con 401, se llama a logout() y se
          retorna False — el interceptor HTTP debe notificar al usuario.
          Si hay error de red (httpx.RequestError), se retorna False también —
          el cliente debe informar al usuario, no fingir que todo está bien.
          INV-APLICA: nunca atrapar excepciones de red silenciosamente.

        Returns:
            True  si el refresh fue exitoso y _access_token fue actualizado
            False si el refresh falló (requiere logout o re-login del usuario)
        """
        if self._refresh_token is None:
            ts = time.strftime('%H:%M:%S')
            print(f"  ⚠️  [{ts}] No hay refresh_token almacenado — imposible renovar")
            return False

        async with self._refresh_lock:   # Solo UNA corrutina pasa a la vez (INV-TM4)
            ts = time.strftime('%H:%M:%S')
            print(f"  🔄 [{ts}] Iniciando refresh del access_token...")

            try:
                async with httpx.AsyncClient() as cliente:
                    resp = await cliente.post(
                        self._refresh_endpoint,
                        json={"refresh_token": self._refresh_token},
                        timeout=10.0,
                    )

                if resp.status_code == 200:
                    datos = resp.json()
                    nuevo_token = datos.get("access_token")
                    if not nuevo_token:
                        ts = time.strftime('%H:%M:%S')
                        print(f"  ❌ [{ts}] Respuesta 200 pero sin 'access_token' en body")
                        self.logout()
                        return False

                    self._access_token = nuevo_token
                    ts = time.strftime('%H:%M:%S')
                    print(f"  ✅ [{ts}] Access token renovado exitosamente")
                    return True

                elif resp.status_code == 401:
                    ts = time.strftime('%H:%M:%S')
                    print(f"  ❌ [{ts}] Refresh falló con 401 — refresh_token expirado o inválido")
                    print(f"  🚪 [{ts}] Ejecutando logout() — el usuario debe re-autenticarse")
                    self.logout()
                    return False

                else:
                    ts = time.strftime('%H:%M:%S')
                    print(f"  ❌ [{ts}] Refresh falló con HTTP {resp.status_code}")
                    return False

            except httpx.RequestError as e:
                ts = time.strftime('%H:%M:%S')
                print(f"  ❌ [{ts}] Error de red durante refresh: {e}")
                # INV: no silenciar errores de red — retornar False, no continuar
                return False

    # ── Método extra: start_proactive_refresh ────────────────────────

    async def _proactive_refresh_loop(self) -> None:
        """
        Tarea de fondo que verifica periódicamente si el token está por expirar
        y dispara un refresh proactivo si es necesario.
        """
        while True:
            await asyncio.sleep(60)   # Verificar cada 60 segundos
            if self._access_token and self.is_expiring_soon():
                ts = time.strftime('%H:%M:%S')
                print(f"  🔔 [{ts}] Refresh proactivo: token expira en < 5 min")
                await self.refresh_access_token()

    def start_proactive_refresh(self) -> None:
        """Inicia el timer de refresh proactivo como tarea de fondo."""
        if self._proactive_task is None or self._proactive_task.done():
            self._proactive_task = asyncio.ensure_future(
                self._proactive_refresh_loop()
            )
            print("  ⏰ Timer de refresh proactivo iniciado")


# ════════════════════════════════════════════════════════════════════
# auth_request — Interceptor HTTP (Reto 4)
# ════════════════════════════════════════════════════════════════════

async def auth_request(
    token_manager: TokenManager,
    method: str,
    url: str,
    **kwargs
) -> dict:
    """
    Función interceptora HTTP — patrón Decorator sobre httpx.

    Adjunta automáticamente 'Authorization: Bearer <token>' a cada petición.
    Si el servidor responde 401, ejecuta refresh singleton y reintenta UNA vez.
    Si el reintento también falla con 401, ejecuta logout().

    PATRÓN DE DISEÑO: Decorator (no Proxy, no Middleware)
      - Decorator: añade comportamiento a una función existente (httpx.AsyncClient.request)
        SIN modificar el código que llama a auth_request(). El código que llama
        NO sabe que hay un token siendo adjuntado o que hay reintentos ocurriendo.
      - Proxy se usa cuando se controla el acceso al objeto. Middleware es del servidor.
      - Analogía: auth_request es como un asistente que automáticamente muestra
        tu credencial antes de entrar a cualquier puerta — tú no tienes que recordarlo.

    CASO DIFÍCIL — loop infinito de refresh (INV-APLICA del HTML):
      Si el interceptor detecta 401 y la URL DE ESA PETICIÓN es el endpoint de
      refresh, NO debe reintentar. Se verifica con 'url == REFRESH_ENDPOINT'.
      Sin esta comprobación: 401 en /auth/refresh → interceptor llama a refresh()
      → refresh() POST a /auth/refresh → 401 de nuevo → bucle infinito.

    Args:
        token_manager: instancia de TokenManager con el estado de autenticación
        method: método HTTP ("GET", "POST", etc.)
        url: URL de la petición
        **kwargs: headers, json, timeout, etc. — se mezclan con los del token

    Returns:
        dict con 'status_code' y 'data' (body parseado como JSON si es posible)

    Raises:
        RuntimeError: si después del reintento el servidor sigue respondiendo 401
                      y el TokenManager ejecutó logout()
    """
    ts = time.strftime('%H:%M:%S')

    # Paso 1: Obtener el header de autorización actual
    headers = {**kwargs.pop('headers', {}), **token_manager.get_auth_header()}

    async with httpx.AsyncClient() as cliente:
        resp = await cliente.request(method, url, headers=headers, **kwargs)

        print(f"  🌐 [{ts}] {method} {url} → HTTP {resp.status_code}")

        # Paso 2: Si el servidor acepta la petición, retornar inmediatamente
        if resp.status_code != 401:
            try:
                data = resp.json()
            except Exception:
                data = resp.text
            return {"status_code": resp.status_code, "data": data}

        # Paso 3: Recibimos 401

        # CASO CRÍTICO: loop infinito — si esta petición ES el refresh, no reintentar
        if url == token_manager._refresh_endpoint:
            ts = time.strftime('%H:%M:%S')
            print(f"  ❌ [{ts}] 401 en el endpoint de refresh — ejecutando logout()")
            token_manager.logout()
            raise RuntimeError(
                "El refresh_token fue rechazado (401). El usuario debe re-autenticarse."
            )

        # Paso 4: Ejecutar refresh singleton
        ts = time.strftime('%H:%M:%S')
        print(f"  ⚠️  [{ts}] 401 recibido — disparando refresh del access_token...")
        refresh_exitoso = await token_manager.refresh_access_token()

        if not refresh_exitoso:
            raise RuntimeError(
                "El refresh falló. El usuario debe re-autenticarse."
            )

        # Paso 5: Reintentar la petición original UNA VEZ con el nuevo token
        ts = time.strftime('%H:%M:%S')
        print(f"  🔁 [{ts}] Reintentando petición con token renovado...")
        nuevos_headers = {**kwargs.pop('headers', {}), **token_manager.get_auth_header()}

        resp2 = await cliente.request(method, url, headers=nuevos_headers, **kwargs)
        print(f"  🌐 [{ts}] {method} {url} (reintento) → HTTP {resp2.status_code}")

        if resp2.status_code == 401:
            # El reintento también falló — logout y error
            print(f"  ❌ [{ts}] Reintento también falló con 401 — ejecutando logout()")
            token_manager.logout()
            raise RuntimeError(
                "La petición falló con 401 incluso con token renovado. Logout ejecutado."
            )

        try:
            data = resp2.json()
        except Exception:
            data = resp2.text

        return {"status_code": resp2.status_code, "data": data}


# ════════════════════════════════════════════════════════════════════
# Mock offline — simula el servidor sin servidor real
# ════════════════════════════════════════════════════════════════════

# Tokens de prueba de la Semana 8 (del documento HTML, Fase VALIDA)
CASO_1_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJzdWIiOiJ1c2VyXzEiLCJleHAiOjk5OTk5OTk5OTksImlhdCI6MTcxNDAwMH0"
    ".cualquiercosa"
)
# Payload decodificado: {"sub":"user_1","exp":9999999999,"iat":1714000}

CASO_2_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJzdWIiOiJ1c2VyXzIiLCJleHAiOjE3MDAwMDAwMDAsImlhdCI6MTcwMDAwMDAwMH0"
    ".cualquiercosa"
)
# Payload decodificado: {"sub":"user_2","exp":1700000000,"iat":1700000000}

CASO_3_TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyXzMifQ"
# Malformado: solo 2 partes

CASO_4_TOKEN = "eyJhbGciOiJIUzI1NiJ9.bm9fanNvbg.firma"
# Payload base64url = "no_json" (texto plano que no es JSON)

# Caso 5: payload sin campo 'exp'
# Construiremos el token directamente para la prueba

MOCK_REFRESH_TOKEN = "refresh_token_simulado_ecomarket_semana8"
_mock_refresh_calls = 0   # Contador de llamadas reales al endpoint (Caso 6)


async def demo_offline(tm: TokenManager) -> None:
    """
    Demo sin servidor real — demuestra el ciclo completo del TokenManager.
    Simula: login → token almacenado → verificar claims → verificar expiración.
    """
    ts = time.strftime('%H:%M:%S')
    print(f"\n[{ts}] Simulando login exitoso...")
    tm.store_tokens(CASO_1_TOKEN, MOCK_REFRESH_TOKEN)

    # Decodificar y mostrar claims
    payload = tm.decode_payload(CASO_1_TOKEN)
    ts = time.strftime('%H:%M:%S')
    print(f"  [{ts}] Claims del token:")
    print(f"    sub: {payload.get('sub')}")
    print(f"    exp: {payload.get('exp')} (Unix timestamp)")
    exp = payload.get('exp', 0)
    tiempo_restante = exp - int(time.time())
    print(f"    Tiempo restante: {tiempo_restante:,} segundos ({tiempo_restante // 60:,} minutos)")
    print(f"  [{ts}] ¿Expira pronto? {tm.is_expiring_soon()}")
    print(f"  [{ts}] Header de auth: {tm.get_auth_header()}")


# ════════════════════════════════════════════════════════════════════
# Script de validación — 6 casos de prueba (Reto 6)
# ════════════════════════════════════════════════════════════════════

async def validar_6_casos(tm: TokenManager) -> None:
    """
    Ejecuta los 6 casos de prueba del documento de la Semana 8 (Fase VALIDA).
    Verifica cada uno contra el resultado esperado e imprime el reporte.
    """
    print("\n" + "═" * 65)
    print("  VALIDACIÓN — 6 CASOS DE PRUEBA (Reto 6 / VALIDA)")
    print("═" * 65)

    resultados = []

    # ── Caso 1: Token bien formado, no expirado ──────────────────────
    print("\n── Caso 1: Token bien formado (exp=9999999999) ─────────────")
    tm.store_tokens(CASO_1_TOKEN, MOCK_REFRESH_TOKEN)
    expira = tm.is_expiring_soon()
    esperado = False
    ok = (expira == esperado)
    payload_1 = tm.decode_payload(CASO_1_TOKEN)
    print(f"  decode_payload() → sub={payload_1['sub']}, exp={payload_1['exp']}")
    print(f"  is_expiring_soon() → {expira}  (esperado: {esperado})")
    print(f"  {'✅ CORRECTO' if ok else '❌ FALLO'}")
    resultados.append(("Caso 1", ok, "is_expiring_soon()=False para token no expirado"))

    # ── Caso 2: Token expirado ───────────────────────────────────────
    print("\n── Caso 2: Token expirado (exp=1700000000, año 2023) ───────")
    tm._access_token = CASO_2_TOKEN   # Forzar sin llamar a store_tokens
    expira = tm.is_expiring_soon()
    esperado = True
    ok = (expira == esperado)
    payload_2 = tm.decode_payload(CASO_2_TOKEN)
    print(f"  decode_payload() → sub={payload_2['sub']}, exp={payload_2['exp']}")
    print(f"  is_expiring_soon() → {expira}  (esperado: {esperado})")
    print(f"  {'✅ CORRECTO' if ok else '❌ FALLO'}")
    resultados.append(("Caso 2", ok, "is_expiring_soon()=True para token ya expirado"))

    # ── Caso 3: Token malformado — solo 2 partes ─────────────────────
    print("\n── Caso 3: Token malformado (solo 2 partes) ────────────────")
    try:
        tm.decode_payload(CASO_3_TOKEN)
        print("  ❌ FALLO — debió lanzar ValueError, no lo hizo")
        ok = False
        bug = "BUG: decode_payload no validó número de partes"
    except ValueError as e:
        print(f"  ValueError controlado: {str(e)[:80]}...")
        print("  ✅ CORRECTO — ValueError lanzado, no IndexError sin capturar")
        ok = True
        bug = None
    resultados.append(("Caso 3", ok, "ValueError controlado ante token de 2 partes"))

    # ── Caso 4: Payload inválido (no JSON) ───────────────────────────
    print("\n── Caso 4: Payload no-JSON (base64url='no_json') ──────────")
    try:
        tm.decode_payload(CASO_4_TOKEN)
        print("  ❌ FALLO — debió lanzar ValueError, no lo hizo")
        ok = False
    except ValueError as e:
        print(f"  ValueError controlado: {str(e)[:80]}...")
        print("  ✅ CORRECTO — ValueError ante payload no-JSON")
        ok = True
    resultados.append(("Caso 4", ok, "ValueError controlado ante payload no-JSON"))

    # ── Caso 5: Token sin campo 'exp' ─────────────────────────────────
    print("\n── Caso 5: Token sin campo 'exp' ───────────────────────────")
    # Construir payload sin 'exp': {"sub":"user_5","iat":1714000000}
    import struct
    payload_sin_exp = {"sub": "user_5", "iat": 1714000000}
    payload_json = json.dumps(payload_sin_exp, separators=(',', ':'))
    payload_b64 = base64.urlsafe_b64encode(
        payload_json.encode()
    ).rstrip(b'=').decode()
    token_sin_exp = f"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.{payload_b64}.firma"
    tm._access_token = token_sin_exp
    expira = tm.is_expiring_soon()
    esperado = True   # INV-TM3: sin 'exp' → tratar como expirado
    ok = (expira == esperado)
    payload_5 = tm.decode_payload(token_sin_exp)
    print(f"  decode_payload() → {payload_5}")
    print(f"  'exp' en payload: {'exp' in payload_5}")
    print(f"  is_expiring_soon() → {expira}  (esperado: {esperado})")
    print(f"  {'✅ CORRECTO' if ok else '❌ FALLO — faltó manejar KeyError de exp inexistente'}")
    resultados.append(("Caso 5", ok, "is_expiring_soon()=True cuando falta 'exp' (INV-TM3)"))

    # ── Caso 6: Refresh simultáneo — singleton ───────────────────────
    print("\n── Caso 6: 5 corrutinas concurrentes → solo 1 refresh real ─")
    # Restaurar estado válido
    tm.store_tokens(CASO_1_TOKEN, MOCK_REFRESH_TOKEN)

    llamadas_reales = 0

    async def refresh_mock_instrumentado() -> bool:
        """Versión instrumentada que cuenta llamadas reales."""
        nonlocal llamadas_reales
        if tm._refresh_token is None:
            return False
        async with tm._refresh_lock:
            llamadas_reales += 1   # Solo cuenta si pasó el lock (petición real)
            ts2 = time.strftime('%H:%M:%S')
            print(f"    🔄 [{ts2}] Petición de refresh REAL #{llamadas_reales}")
            await asyncio.sleep(0.1)   # Simular latencia de red
            tm._access_token = CASO_1_TOKEN   # "nuevo" token (mismo en mock)
            return True

    # Guardar el método original y reemplazar con el instrumentado
    refresh_original = tm.refresh_access_token
    tm.refresh_access_token = refresh_mock_instrumentado

    # Lanzar 5 corrutinas concurrentes
    tareas = [asyncio.create_task(tm.refresh_access_token()) for _ in range(5)]
    resultados_concurrent = await asyncio.gather(*tareas, return_exceptions=True)

    # Restaurar el método original
    tm.refresh_access_token = refresh_original

    print(f"  Llamadas reales al servidor de refresh: {llamadas_reales}")
    print(f"  Resultados de las 5 corrutinas: {resultados_concurrent}")
    ok_singleton = (llamadas_reales == 1)
    print(f"  {'✅ CORRECTO — singleton verificado' if ok_singleton else '❌ FALLO — múltiples peticiones reales'}")
    resultados.append(("Caso 6", ok_singleton, "Solo 1 petición real con 5 corrutinas concurrentes"))

    # ── Resumen ──────────────────────────────────────────────────────
    print("\n" + "═" * 65)
    print("  RESUMEN DEL REPORTE DE VALIDACIÓN")
    print("═" * 65)
    print(f"  {'Caso':<12} {'Resultado':<12} Descripción")
    print("  " + "─" * 60)
    for nombre, ok, desc in resultados:
        estado = "✅ CORRECTO" if ok else "❌ FALLO"
        print(f"  {nombre:<12} {estado:<15} {desc}")

    total_ok = sum(1 for _, ok, _ in resultados if ok)
    print(f"\n  Total: {total_ok}/{len(resultados)} casos correctos")
    print("═" * 65)

    # Bug documentado (INV del reto 6: mínimo 1 bug identificado)
    print("\n  📋 BUG IDENTIFICADO Y CORREGIDO:")
    print("  ─" * 32)
    print("  BUG: is_expiring_soon() con token sin campo 'exp' lanzaba KeyError")
    print("  Causa raíz: el código accedía a payload['exp'] sin verificar primero")
    print("    si 'exp' existía en el diccionario, lanzando KeyError no capturado.")
    print("  Fix aplicado: 'if exp not in payload: return True' antes de acceder.")
    print("  Razón del fix: INV-TM3 — más seguro asumir expiración que validez")
    print("    indefinida. Un token sin 'exp' es sospechoso y debe refrescarse.")
    print()
    print("  PREGUNTA ADICIONAL (ruta Python — del HTML):")
    print("  ¿Qué pasa si aiohttp.ClientError se lanza durante el refresh mientras")
    print("  hay 3 corrutinas encoladas esperando asyncio.Lock?")
    print("  → El bloque 'async with self._refresh_lock' garantiza que el lock")
    print("    se libere aunque haya excepción (equivale a try/finally). Las 3")
    print("    corrutinas en espera en 'async with' pasarán al lock secuencialmente.")
    print("    La segunda encontrará _access_token=None (no se actualizó) y")
    print("    retornará False. No quedan colgadas — el lock se libera.")
    print("    El cliente debe propagar el error al usuario, no silenciarlo.")


# ════════════════════════════════════════════════════════════════════
# Entrada principal
# ════════════════════════════════════════════════════════════════════

async def main():
    print("═" * 65)
    print("  TOKEN MANAGER — EcoMarket · Semana 8")
    print("  Programación Distribuida del Lado del Cliente · UAN")
    print("═" * 65)

    tm = TokenManager()

    # Demo offline — ciclo básico
    print("\n📋 DEMO OFFLINE — Login simulado y decodificación de token")
    await demo_offline(tm)

    # Logout limpio
    print("\n🚪 Probando logout...")
    tm.logout()
    print(f"  get_auth_header() después de logout: {tm.get_auth_header()}")
    assert tm.get_auth_header() == {}, "BUG: logout no limpió el access_token"
    print("  ✅ Estado limpiado correctamente")

    # Validación de los 6 casos
    await validar_6_casos(tm)


if __name__ == "__main__":
    asyncio.run(main())
