"""
cliente_sse_multiplex.py — Cliente SSE real para EcoMarket (Semana 10)
=====================================================================
Conecta a http://localhost:3000/api/alertas vía SSE con:
  - Autenticación Bearer vía TokenManager
  - Soporte Last-Event-ID para reconexión (TC-X3)
  - Reconexión automática con backoff exponencial (máx 5 reintentos)
  - Parsing completo de campos SSE: id, event, data, retry, comentarios
  - EventRouter heredado de Semana 7 (handlers dict)
  - Integración con ClienteRobusto para actualización de caché SSE

DECISIONES DE DISEÑO:
  - SSE es un canal INDEPENDIENTE del CircuitBreaker (TC-X1, TC-X3).
    No pasa por cb.ejecutar(); el retry es propio del cliente SSE.
  - Al recibir 401 en el handshake SSE se refresca el token y se reintenta
    UNA vez dentro del mismo ciclo de conexión.
  - ultimo_id se preserva en self._ultimo_id para enviarlo como
    Last-Event-ID en reconexiones subsiguientes.
  - Se usa aiohttp.ClientSession con streaming real (resp.content.readline).
"""

import asyncio
import json
import logging

import aiohttp

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════
# EventRouter (de Semana 7)
# ═════════════════════════════════════════════════════════════

class EventRouter:
    def __init__(self):
        self.handlers = {}

    def registrar(self, tipo, fn):
        if tipo not in self.handlers:
            self.handlers[tipo] = []
        self.handlers[tipo].append(fn)

    def desregistrar(self, tipo, fn):
        if tipo in self.handlers and fn in self.handlers[tipo]:
            self.handlers[tipo].remove(fn)

    def despachar(self, tipo, datos):
        if tipo not in self.handlers:
            return
        for fn in self.handlers[tipo]:
            try:
                fn(datos)
            except Exception as e:
                logger.error("Handler para '%s' fallo: %s", tipo, e)


# ═════════════════════════════════════════════════════════════
# ClienteSSEMultiplex
# ═════════════════════════════════════════════════════════════

class ClienteSSEMultiplex:
    """
    Decisiones de diseno:
    - SSE connection is independent of CircuitBreaker (TC-X1/TC-X3)
    - On reconnection, sends Last-Event-ID header
    - Uses TokenManager for auth, refreshes token if 401 on SSE connect
    - Exponential backoff with max 5 retries
    - Notifies cliente_robusto cache on events via callback
    """

    def __init__(self, base_url, token_manager, on_event_callback=None):
        self._base_url = base_url.rstrip("/")
        self._tm = token_manager
        self._router = EventRouter()
        self._ultimo_id = None  # Preserved across reconnections (TC-X3)
        self._estado = "DESCONECTADO"
        self._reintentos = 0
        self._max_reintentos = 5
        self._espera_inicial = 1.0
        self._parar = False
        self._session = None
        self._on_event_callback = on_event_callback  # For ClienteRobusto cache

    # ── Suscripción a eventos ─────────────────────────────────

    def suscribir(self, tipo_evento, handler_fn):
        self._router.registrar(tipo_evento, handler_fn)

    def desuscribir(self, tipo_evento, handler_fn):
        self._router.desregistrar(tipo_evento, handler_fn)

    # ── Propiedades públicas ──────────────────────────────────

    @property
    def estado(self):
        return self._estado

    @property
    def ultimo_id(self):
        return self._ultimo_id

    # ── Parsing SSE ───────────────────────────────────────────

    def _parsear_linea(self, linea, evento_parcial):
        """Parsea una línea SSE y acumula en evento_parcial."""
        if not linea:
            return
        if linea.startswith(":"):
            # Comentario / keep-alive — se ignora
            return

        if ":" in linea:
            campo, valor = linea.split(":", 1)
            campo = campo.strip()
            valor = valor.lstrip(" ")
        else:
            campo = linea.strip()
            valor = ""

        if campo == "id":
            evento_parcial["id"] = valor
        elif campo == "event":
            evento_parcial["event"] = valor
        elif campo == "data":
            if "data" in evento_parcial:
                evento_parcial["data"] += "\n" + valor
            else:
                evento_parcial["data"] = valor
        elif campo == "retry":
            try:
                evento_parcial["retry"] = int(valor)
            except ValueError:
                pass

    def _procesar_evento(self, evento_parcial):
        """Despacha un evento completo a los handlers registrados."""
        if "id" in evento_parcial:
            self._ultimo_id = evento_parcial["id"]  # Preserve for reconnection (TC-X3)

        tipo = evento_parcial.get("event", "message")
        datos_raw = evento_parcial.get("data", "")

        try:
            datos = json.loads(datos_raw) if datos_raw else {}
        except json.JSONDecodeError:
            datos = {"raw": datos_raw}

        self._router.despachar(tipo, datos)

        if self._on_event_callback:
            try:
                self._on_event_callback(datos)
            except Exception as e:
                logger.error("on_event_callback fallo: %s", e)

        evento_parcial.clear()

    # ── Conexión SSE con reconexión automática ────────────────

    async def conectar(self):
        """Connect to SSE endpoint with auth and retry on failure."""
        self._estado = "CONECTANDO"
        self._reintentos = 0
        while not self._parar and self._reintentos < self._max_reintentos:
            try:
                await self._conectar_sse()
                self._reintentos = 0
            except Exception as e:
                if self._parar:
                    break
                logger.warning("SSE error: %s, retrying...", e)
                self._estado = "RECONECTANDO"
                self._reintentos += 1
                espera = self._espera_inicial * (2 ** (self._reintentos - 1))
                await asyncio.sleep(min(espera, 30))
        self._estado = "DESCONECTADO"

    async def _conectar_sse(self):
        """Real SSE connection using aiohttp."""
        url = f"{self._base_url}/api/alertas"
        headers = self._tm.get_auth_header()
        headers["Accept"] = "text/event-stream"
        if self._ultimo_id:
            headers["Last-Event-ID"] = self._ultimo_id  # TC-X3 reconnection

        session = await self._get_session()

        # Primer intento de conexión
        resp = await session.get(url, headers=headers)

        if resp.status == 401:
            resp.release()
            logger.info("SSE 401 — refrescando token...")
            await self._tm.refresh_access_token()
            headers = self._tm.get_auth_header()
            headers["Accept"] = "text/event-stream"
            if self._ultimo_id:
                headers["Last-Event-ID"] = self._ultimo_id
            # Retry con token fresco (una sola vez)
            resp = await session.get(url, headers=headers)

        if resp.status == 401:
            # Token inválido incluso después del refresh
            resp.release()
            raise aiohttp.ClientResponseError(
                resp.request_info,
                resp.history,
                status=resp.status,
                message="Token inválido después de refresh",
                headers=resp.headers,
            )

        resp.raise_for_status()
        self._estado = "CONECTADO"
        logger.info("SSE conectado a %s", url)

        try:
            evento_parcial = {}
            while True:
                line_b = await resp.content.readline()
                if not line_b:
                    # Conexión cerrada por el servidor
                    break

                line = line_b.decode("utf-8").rstrip("\n").rstrip("\r")

                if not line:
                    # Línea en blanco → fin de evento
                    if evento_parcial:
                        self._procesar_evento(evento_parcial)
                elif line.startswith(":"):
                    # Comentario o keep-alive
                    continue
                else:
                    self._parsear_linea(line, evento_parcial)

            # Procesar evento final si no terminó con línea en blanco
            if evento_parcial:
                self._procesar_evento(evento_parcial)
        finally:
            resp.release()

    # ── Control de ciclo de vida ──────────────────────────────

    def detener(self):
        self._parar = True
        self._estado = "DESCONECTADO"

    async def _get_session(self):
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=None)  # SSE: sin timeout total
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


# ═════════════════════════════════════════════════════════════
# Helpers de ejemplo (handlers SSE)
# ═════════════════════════════════════════════════════════════

def handler_precio_actualizado(datos):
    precio_ant = datos.get("precio_anterior", 0)
    precio_nue = datos.get("precio_nuevo", 0)
    if precio_ant and abs(precio_nue - precio_ant) / precio_ant > 0.05:
        logger.info("ALERTA PRECIO: producto %s cambió >5%%", datos.get("producto_id"))


def handler_stock_critico(datos):
    stock = datos.get("stock_actual", 0)
    if stock <= 3:
        logger.info("URGENTE: Stock crítico de %s = %s", datos.get("producto_id"), stock)


# ═════════════════════════════════════════════════════════════
# DEMO
# ═════════════════════════════════════════════════════════════

async def demo_sse():
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)

    print("=" * 60)
    print("EcoMarket — Demo ClienteSSEMultiplex (real)")
    print("=" * 60)
    print("Asegúrate de que servidor_mock.py esté corriendo en")
    print("http://localhost:3000 antes de continuar.")
    print("=" * 60)
    print()

    tm = TokenManager(base_url="http://localhost:3000")
    await tm.login(username="op1", rol="viewer")
    payload = tm.decode_payload(tm.access_token)
    logger.info("SSE Demo: Login como %s (rol=%s)", payload.get('sub'), payload.get('rol'))

    cliente = ClienteSSEMultiplex(
        base_url="http://localhost:3000",
        token_manager=tm,
        on_event_callback=lambda datos: logger.info("[CACHE] %s", datos),
    )

    cliente.suscribir("precio-actualizado", handler_precio_actualizado)
    cliente.suscribir("stock-critico", handler_stock_critico)
    cliente.suscribir("sistema", lambda d: logger.info("[SISTEMA] %s", d))

    print("Conectando a SSE... (Ctrl+C para detener)")
    try:
        await cliente.conectar()
    except asyncio.CancelledError:
        pass
    finally:
        cliente.detener()
        await cliente.close()
        print("Cliente SSE cerrado.")


if __name__ == "__main__":
    try:
        asyncio.run(demo_sse())
    except KeyboardInterrupt:
        print("\nDetenido por el usuario.")
