"""
cliente_robusto.py — ClienteRobusto para EcoMarket (Semana 10: Grand Deploy)
=============================================================================

Arquitectura de capas (de afuera hacia adentro):
  ClienteRobusto
    ├── CircuitBreaker  (decide: ejecutar o no?)
    ├── TokenManager    (gestiona JWT, adjunta Bearer)
    ├── ClienteSSEMultiplex (conexion SSE independiente, TC-X1/TC-X3)
    └── aiohttp.ClientSession  (transporte HTTP real)

Orden de aplicacion de capas:
  1. ClienteRobusto recibe la peticion del UI/operador
  2. TokenManager adjunta el header Authorization: Bearer <token>
     2a. Si is_expiring_soon(): refresh_access_token() PRIMERO (TC-X2)
  3. CircuitBreaker decide si la peticion se ejecuta o se rechaza (CircuitOpenError)
  4. Se ejecuta la peticion HTTP
  5. Si 401: TokenManager intenta refresh (sin pasar por el mismo breaker)
  6. El resultado vuelve al ClienteRobusto que notifica al UI via Observer

DECISIONES DE DISENO:
  - Las peticiones de autenticacion (/auth/token) NO pasan por el CircuitBreaker
    principal para evitar el deadlock Auth-Breaker.
  - Retry con backoff exponencial: maximo 3 reintentos con delay 1s, 2s, 4s.
    El CircuitBreaker decide si el retry tiene permitido ejecutarse.
  - SSE es un canal INDEPENDIENTE: no pasa por el CB (TC-X1/TC-X3).
  - Notificacion a la UI mediante patron Observer (callbacks registrables).
  - INV-A1: ClienteRobusto no decodifica JWT ni verifica roles.
  - INV-B1: TokenManager no tiene atributos del circuit breaker.
  - INV-B2: El token nunca aparece en logs, ni parcialmente.
"""

import asyncio
import json
import logging
import time
from typing import Callable, Optional

import aiohttp

from circuit_breaker import CircuitBreaker, CircuitOpenError, EstadoCircuito
from token_manager import TokenManager

logger = logging.getLogger(__name__)

BASE_URL = "http://localhost:3000/api"
TIMEOUT_PETICION = 5.0
MAX_RETRIES = 3
ESPERA_INICIAL = 1.0


class EstadoUI:
    CONECTADO = "conectado"
    DEGRADADO = "degradado"
    DESCONECTADO = "desconectado"


class ClienteRobusto:
    """
    Cliente robusto que integra CircuitBreaker + TokenManager + HTTP + Observer.
    """

    def __init__(
        self,
        token_manager: Optional[TokenManager] = None,
        umbral_fallos: int = 5,
        timeout_apertura: float = 10.0,
        base_url: str = BASE_URL,
        max_retries: int = MAX_RETRIES,
        espera_inicial: float = ESPERA_INICIAL,
    ):
        self._base_url = base_url.rstrip("/")
        self._tm = token_manager or TokenManager(base_url=base_url.replace("/api", ""))
        self._cb = CircuitBreaker(
            umbral_fallos=umbral_fallos,
            timeout_apertura=timeout_apertura,
            nombre="EcoMarketAPI"
        )
        self._session: Optional[aiohttp.ClientSession] = None
        self._estado_ui = EstadoUI.CONECTADO
        self._observadores: list[Callable] = []
        self._cache_sse: dict = {}
        self._max_retries = max_retries
        self._espera_inicial = espera_inicial

        self._cb.on_circuit_open = lambda: self._notificar(
            EstadoUI.DEGRADADO,
            "Circuito ABIERTO - servicio no disponible",
            {"circuito_abierto": True}
        )
        self._cb.on_circuit_close = lambda: self._notificar(
            EstadoUI.CONECTADO,
            "Circuito CERRADO - conexion restablecida",
            {"circuito_abierto": False}
        )

    def suscribir_estado(self, fn: Callable):
        self._observadores.append(fn)

    def desuscribir_estado(self, fn: Callable):
        if fn in self._observadores:
            self._observadores.remove(fn)

    def _notificar(self, estado: str, mensaje: str, datos: Optional[dict] = None):
        self._estado_ui = estado
        for fn in self._observadores:
            try:
                fn(estado, mensaje, datos or {})
            except Exception as e:
                logger.error("Observer fallo: %s", e)

    def _url(self, path: str) -> str:
        return f"{self._base_url}/{path.lstrip('/')}"

    async def _session_actual(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=TIMEOUT_PETICION)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def cerrar(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def get(self, path: str, **kwargs):
        return await self._request_con_cb("GET", path, **kwargs)

    async def post(self, path: str, **kwargs):
        return await self._request_con_cb("POST", path, **kwargs)

    async def put(self, path: str, **kwargs):
        return await self._request_con_cb("PUT", path, **kwargs)

    async def patch(self, path: str, **kwargs):
        return await self._request_con_cb("PATCH", path, **kwargs)

    async def delete(self, path: str, **kwargs):
        return await self._request_con_cb("DELETE", path, **kwargs)

    async def _request_con_cb(self, method: str, path: str, **kwargs):
        """
        Ejecuta una peticion HTTP pasando por el Circuit Breaker.
        Incluye retry con backoff exponencial controlado por el breaker.
        """
        headers_base = dict(kwargs.pop("headers", {}) or {})

        async def _hacer_peticion():
            session = await self._session_actual()
            url = self._url(path)
            headers = dict(headers_base)

            headers.update(self._tm.get_auth_header())

            async with session.request(method, url, headers=headers, **kwargs) as resp:
                if resp.status >= 500:
                    text = await resp.text()
                    raise aiohttp.ClientResponseError(
                        resp.request_info, resp.history,
                        status=resp.status, message=text, headers=resp.headers
                    )
                if resp.status == 401:
                    await self._refrescar_token_silencioso()
                    headers.update(self._tm.get_auth_header())
                    async with session.request(method, url, headers=headers, **kwargs) as resp2:
                        if resp2.status == 401:
                            raise Exception("Token invalido despues de refresh")
                        return await resp2.json()
                if resp.status >= 400:
                    text = await resp.text()
                    raise aiohttp.ClientResponseError(
                        resp.request_info, resp.history,
                        status=resp.status, message=text, headers=resp.headers
                    )
                return await resp.json()

        ultimo_error = None
        for intento in range(self._max_retries + 1):
            try:
                await self._asegurar_token_vigente()
                resultado = await self._cb.ejecutar(_hacer_peticion)
                if self._estado_ui != EstadoUI.CONECTADO:
                    self._notificar(EstadoUI.CONECTADO, "Conexion restablecida")
                return resultado
            except CircuitOpenError as e:
                self._notificar(
                    EstadoUI.DEGRADADO,
                    f"Servicio no disponible. Reintenta en {e.tiempo_restante:.1f}s",
                    {"tiempo_restante": e.tiempo_restante, "circuito_abierto": True}
                )
                raise
            except aiohttp.ClientResponseError as e:
                if 400 <= e.status < 500:
                    raise
                ultimo_error = e
                if intento < self._max_retries:
                    espera = self._espera_inicial * (2 ** intento)
                    logger.warning("Reintento %d/%d en %.1fs | status=%s", intento + 1, self._max_retries, espera, e.status)
                    await asyncio.sleep(espera)
                else:
                    break
            except (asyncio.TimeoutError, aiohttp.ClientConnectionError) as e:
                ultimo_error = e
                if intento < self._max_retries:
                    espera = self._espera_inicial * (2 ** intento)
                    logger.warning("Reintento %d/%d en %.1fs | error=%s", intento + 1, self._max_retries, espera, type(e).__name__)
                    await asyncio.sleep(espera)
                else:
                    break
            except Exception:
                raise

        if ultimo_error:
            raise ultimo_error
        raise Exception("Peticion fallo despues de todos los reintentos")

    async def _asegurar_token_vigente(self) -> bool:
        """
        Ejecuta el refresh proactivo antes de entrar al CircuitBreaker.

        Esta es la parte crítica de ADR-001: /auth/token no debe quedar
        bloqueado por el estado ABIERTO/SEMIABIERTO del breaker principal.
        """
        if self._tm.access_token and self._tm.is_expiring_soon():
            return await self._refrescar_token_silencioso()
        return True

    async def _refrescar_token_silencioso(self) -> bool:
        """
        Renueva el token directamente, SIN pasar por el CircuitBreaker.
        Evita el deadlock Auth-Breaker.
        """
        try:
            await self._tm.refresh_access_token()
            logger.info("Token refrescado exitosamente (sin pasar por CB)")
            return True
        except Exception as e:
            logger.error("Error refrescando token: %s", type(e).__name__)
            return False

    def actualizar_cache_sse(self, datos: dict):
        """Recibe datos del ClienteSSEMultiplex para usar como fallback."""
        self._cache_sse.update(datos)

    def obtener_fallback(self) -> Optional[dict]:
        """Retorna datos del cache SSE cuando el circuito esta abierto."""
        if self._cache_sse:
            return {"__fallback__": True, "__origen__": "cache_sse", **self._cache_sse}
        return None

    @property
    def estado_circuito(self) -> EstadoCircuito:
        return self._cb.estado

    @property
    def esta_degradado(self) -> bool:
        return self._estado_ui == EstadoUI.DEGRADADO

    @property
    def token_manager(self) -> TokenManager:
        return self._tm

    @property
    def circuit_breaker(self) -> CircuitBreaker:
        return self._cb


# ═════════════════════════════════════════════════════════════
# DEMO DE RESILIENCIA
# ═════════════════════════════════════════════════════════════

def _demo_notificador(estado, mensaje, datos):
    emoji = {"conectado": "🟢", "degradado": "🟡", "desconectado": "🔴"}.get(estado, "⚪")
    print(f"  [UI] {emoji} {estado.upper()} — {mensaje}")
    if datos:
        print(f"       datos={json.dumps(datos, indent=2, default=str)}")


async def demo_resiliencia():
    """
    Script de demostracion que ejecuta la secuencia completa:
      1. Login exitoso -> Token almacenado en TM
      2. Modo normal -> 3 peticiones exitosas
      3. Activa modo fallo_503 -> observa el circuito abrirse
      4. Espera timeout -> observa el estado Semiabierto
      5. Restaura modo normal -> observa la recuperacion
    """
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)

    print("=" * 60)
    print("EcoMarket — Demo de Resiliencia (Grand Deploy)")
    print("=" * 60)

    tm = TokenManager(base_url="http://localhost:3000")
    cliente = ClienteRobusto(token_manager=tm, umbral_fallos=3, timeout_apertura=5.0)
    cliente.suscribir_estado(_demo_notificador)

    # Helper para cambiar modo del servidor
    async def cambiar_modo(modo: str):
        session = await cliente._session_actual()
        async with session.post("http://localhost:3000/admin/modo", json={"modo": modo}) as resp:
            data = await resp.json()
            print(f"  [ADMIN] Modo servidor -> {data['modo']}")

    async def reset_contador():
        session = await cliente._session_actual()
        async with session.post("http://localhost:3000/admin/reset") as resp:
            return await resp.json()

    # FASE 0: Login
    print("\nFASE 0: Login")
    print("-" * 40)
    login_data = await tm.login(username="op1", rol="viewer")
    payload = tm.decode_payload(tm.access_token)
    print(f"  [LOGIN] Token almacenado · rol={payload.get('rol')} · sub={payload.get('sub')}")

    # FASE 1: Operacion normal
    print("\nFASE 1: Operacion Normal (3 peticiones exitosas)")
    print("-" * 40)
    await cambiar_modo("normal")
    await reset_contador()

    for i in range(1, 4):
        try:
            resp = await cliente.get("/inventario")
            cb = cliente.circuit_breaker
            print(f"  [HTTP #{i}] 200 · productos={resp.get('productos')} · CB: {cb.estado.name} (fallos={cb._fallos_consecutivos})")
        except Exception as e:
            print(f"  [HTTP #{i}] fallo — {type(e).__name__}: {e}")

    # FASE 2: Fallo sostenido
    print("\nFASE 2: Fallo Sostenido (modo 503)")
    print("-" * 40)
    await cambiar_modo("fallo_503")

    for i in range(1, 7):
        try:
            resp = await cliente.get("/inventario")
            print(f"  [HTTP #{i+3}] 200 · productos={resp.get('productos')}")
        except CircuitOpenError as e:
            print(f"  [BREAKER] Fail fast — CircuitOpenError (sin tocar el servidor)")
            print(f"  [UI] banner=Servidor temporalmente no disponible · action=disable_checkout")
        except Exception as e:
            cb = cliente.circuit_breaker
            print(f"  [HTTP #{i+3}] 503 · CB: {cb.estado.name} (fallos={cb._fallos_consecutivos})")

    # FASE 3: Esperar timeout -> Semiabierto
    print("\nFASE 3: Esperando timeout de apertura (5s)...")
    print("-" * 40)
    print(f"  [BREAKER] Timeout {cliente.circuit_breaker.timeout_apertura}s -> SEMIABIERTO")
    await asyncio.sleep(cliente.circuit_breaker.timeout_apertura + 0.5)
    print(f"  Estado del circuito: {cliente.estado_circuito.name}")

    # FASE 4: Recuperacion
    print("\nFASE 4: Recuperacion (restaurar modo normal)")
    print("-" * 40)
    await cambiar_modo("normal")

    try:
        resp = await cliente.get("/inventario")
        cb = cliente.circuit_breaker
        print(f"  [HTTP #10] 200 · productos={resp.get('productos')} · CB: {cb.estado.name} (fallos={cb._fallos_consecutivos})")
        print(f"  [UI] banner=oculto · action=enable_checkout")
    except Exception as e:
        print(f"  [HTTP #10] fallo — {type(e).__name__}: {e}")

    print(f"  Estado final: circuito={cliente.estado_circuito.name} · token_valido={not tm.is_expiring_soon()}")

    await cliente.cerrar()
    await tm.close()
    print("\n" + "=" * 60)
    print("Demo finalizado.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(demo_resiliencia())
