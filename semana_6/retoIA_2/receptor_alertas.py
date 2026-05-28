"""
RECEPTOR ALERTAS ECOMARKET — Semana 6 · RetoIA_2
=================================================
Cliente SSE (Server-Sent Events) para EcoMarket que:
  - Conecta a un endpoint /api/alertas con Accept: text/event-stream
  - Parsea campos id, event, data línea a línea (parseo manual del protocolo)
  - Despacha eventos por tipo: precio-actualizado, stock-critico
  - Rastrea el último id recibido y reconecta con Last-Event-ID
  - Respeta el campo retry: enviado por el servidor
  - Implementa backoff exponencial con máximo 5 intentos
  - Detención limpia mediante bandera sin tareas huérfanas
  - Timeout de 30s en la conexión inicial

TRAZA SSE:
  t=0s  → Cliente abre GET /api/alertas + Accept:text/event-stream (timeout=30s)
  t=0s  ← Servidor responde 200 OK + Content-Type:text/event-stream (chunked)
  t=2s  ← id:1 event:precio-actualizado data:{...} (línea en blanco → mensaje completo)
  t=5s  ← id:2 event:stock-critico data:{...}
  t=15s ← : ping (comentario keep-alive — cliente lo ignora como dato)
  t=18s ← id:3 event:precio-actualizado data:{...}
  t=25s ✗ CORTE DE RED
  t=28s → Cliente espera retry_ms (3000ms default), luego abre nueva conexión:
          GET /api/alertas + Last-Event-ID: 3  ← permite al servidor reanudar desde id=4

Por qué SSE reduce peticiones vacías vs polling:
  Polling (Semana 4): cada ciclo genera 1 petición TCP nueva → 300 peticiones en 15 min
  con interval=3s. La mayoría responden "sin cambios". SSE: 1 conexión permanente;
  el servidor solo envía bytes cuando realmente hay un cambio. Con 800 usuarios,
  eso es la diferencia entre 144,000 peticiones/min y prácticamente cero.

Invariantes respetados:
  ✓ Timeout 30s configurado en la conexión inicial
  ✓ Buffer reseteado completamente después de cada mensaje
  ✓ retry: del servidor se respeta (actualiza retry_ms)
  ✓ Last-Event-ID enviado en reconexiones
  ✓ Máximo 5 intentos de reconexión con backoff exponencial
  ✓ 204 No Content detiene reconexión (fin de stream intencional)
  ✓ Excepción en handler no cierra el stream (log + continuar)
  ✓ Detención limpia: bandera _activo sin tareas huérfanas

Autor: Fosuna · Semana 6 · Programación Distribuida del Lado del Cliente · UAN
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

# ── Requiere: pip install httpx
try:
    import httpx
except ImportError:
    raise SystemExit(
        "Instala httpx primero: pip install httpx\n"
        "O usa: pip install httpx[http2]"
    )


# ════════════════════════════════════════════════════════════════════
# Modelos de datos
# ════════════════════════════════════════════════════════════════════

@dataclass
class EventoSSE:
    """Representa un mensaje SSE completamente parseado."""
    id: Optional[str] = None
    event: str = "message"          # default cuando no hay campo event:
    data: str = ""
    retry_ms: Optional[int] = None  # si el servidor envió campo retry:


@dataclass
class TablaPrecios:
    """Tabla de precios simulada que se actualiza con eventos SSE."""
    precios: dict = field(default_factory=dict)

    def actualizar(self, producto: str, precio: float, moneda: str = "MXN"):
        self.precios[producto] = {"precio": precio, "moneda": moneda,
                                   "actualizado": datetime.now().isoformat()}
        print(f"  💰 Precio actualizado: {producto} = {precio} {moneda}")

    def mostrar(self):
        if not self.precios:
            print("  (tabla vacía)")
            return
        for prod, info in self.precios.items():
            print(f"  {prod}: {info['precio']} {info['moneda']} "
                  f"(última actualización: {info['actualizado']})")


# ════════════════════════════════════════════════════════════════════
# Handlers por tipo de evento
# ════════════════════════════════════════════════════════════════════

tabla_precios = TablaPrecios()


def manejar_precio_actualizado(datos_raw: str, id_evento: Optional[str]):
    """Handler para evento 'precio-actualizado'."""
    try:
        datos = json.loads(datos_raw)
        producto = datos.get("producto", "?")
        precio = datos.get("precio", 0.0)
        moneda = datos.get("moneda", "MXN")
        tabla_precios.actualizar(producto, precio, moneda)
    except json.JSONDecodeError as e:
        # Una excepción en el handler NO debe cerrar la conexión
        _log_warning(f"[precio-actualizado] JSON inválido (id={id_evento}): {e}")


def manejar_stock_critico(datos_raw: str, id_evento: Optional[str]):
    """Handler para evento 'stock-critico'."""
    try:
        datos = json.loads(datos_raw)
        producto = datos.get("producto", "?")
        stock = datos.get("stock", 0)
        umbral = datos.get("umbral", 5)
        print(f"  ⚠️  ALERTA STOCK CRÍTICO: {producto} | stock={stock} "
              f"(umbral={umbral}) [id={id_evento}]")
    except json.JSONDecodeError as e:
        _log_warning(f"[stock-critico] JSON inválido (id={id_evento}): {e}")


def _log_warning(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"  ⚡ [{ts}] ADVERTENCIA: {msg}")


# Registro de handlers por tipo de evento
HANDLERS = {
    "precio-actualizado": manejar_precio_actualizado,
    "stock-critico": manejar_stock_critico,
}


# ════════════════════════════════════════════════════════════════════
# Parser de stream SSE
# ════════════════════════════════════════════════════════════════════

def parsear_linea(linea: str, buffer: dict) -> Optional[EventoSSE]:
    """
    Procesa una línea del stream SSE y acumula en el buffer.
    Retorna un EventoSSE completo cuando se encuentra la línea en blanco.

    Formato SSE:
      id: 42
      event: precio-actualizado
      data: {"producto":"A01","precio":45.00}
      retry: 3000
                          ← línea en blanco = fin del mensaje
    """
    # Línea en blanco = mensaje completo → crear EventoSSE y resetear buffer
    if linea == "":
        if not buffer.get("data"):
            # Mensaje vacío (keep-alive sin data) → ignorar, solo resetear
            buffer.clear()
            return None
        evento = EventoSSE(
            id=buffer.get("id"),
            event=buffer.get("event", "message"),
            data=buffer.get("data", ""),
            retry_ms=buffer.get("retry_ms"),
        )
        # INVARIANTE: buffer DEBE resetearse completamente después de cada mensaje
        buffer.clear()
        return evento

    # Comentario de keep-alive: líneas que empiezan con ':'
    if linea.startswith(":"):
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"  🔔 [{ts}] keep-alive recibido (ignorado como dato)")
        return None

    # Separar campo: valor (solo el primer ':')
    if ":" in linea:
        campo, _, valor = linea.partition(":")
        valor = valor.lstrip(" ")  # El espacio después de ':' es opcional
    else:
        # Línea sin ':' → campo con valor vacío según el estándar
        campo = linea
        valor = ""

    # Procesar campo
    if campo == "id":
        buffer["id"] = valor
    elif campo == "event":
        buffer["event"] = valor
    elif campo == "data":
        # data multilínea: concatenar con '\n' (según estándar WHATWG)
        if "data" in buffer:
            buffer["data"] += "\n" + valor
        else:
            buffer["data"] = valor
    elif campo == "retry":
        try:
            buffer["retry_ms"] = int(valor)
        except ValueError:
            _log_warning(f"Campo retry: con valor inválido: '{valor}'")
    # Campos desconocidos se ignoran silenciosamente

    return None


# ════════════════════════════════════════════════════════════════════
# ReceptorAlertas — Cliente SSE principal
# ════════════════════════════════════════════════════════════════════

class ReceptorAlertas:
    """
    Cliente SSE para EcoMarket.

    Parámetros
    ----------
    url         : endpoint SSE a consumir
    timeout_s   : timeout de la conexión inicial (default 30s)
    retry_ms    : tiempo de espera inicial antes de reconectar (ms)
    max_reintentos : máximo de reintentos con backoff exponencial
    """

    MAX_REINTENTOS_DEFAULT = 5
    TIMEOUT_DEFAULT = 30.0

    def __init__(
        self,
        url: str,
        timeout_s: float = TIMEOUT_DEFAULT,
        retry_ms: int = 3000,
        max_reintentos: int = MAX_REINTENTOS_DEFAULT,
    ):
        self.url = url
        self.timeout_s = timeout_s
        self.retry_ms = retry_ms           # puede ser actualizado por campo retry:
        self.max_reintentos = max_reintentos

        self._activo = False               # bandera de control de ciclo
        self._ultimo_id: Optional[str] = None  # para Last-Event-ID

    # ── API pública ──────────────────────────────────────────────────

    async def iniciar(self):
        """Inicia el receptor SSE con reconexión automática."""
        self._activo = True
        reintentos = 0

        while self._activo:
            try:
                print(f"\n🔌 Conectando a {self.url} ...")
                if self._ultimo_id:
                    print(f"   Last-Event-ID: {self._ultimo_id}")

                await self._consumir_stream()

                # Si llegamos aquí sin excepción = servidor cerró el stream
                print("ℹ️  El servidor cerró el stream normalmente.")
                reintentos = 0  # conexión exitosa → resetear contador

            except httpx.TimeoutException:
                reintentos += 1
                print(f"⏱  Timeout de {self.timeout_s}s alcanzado. "
                      f"Intento {reintentos}/{self.max_reintentos}")

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 204:
                    # 204 No Content = stream terminó intencionalmente
                    print("✅ Servidor envió 204 No Content — fin del stream. "
                          "No se reconecta.")
                    self._activo = False
                    return
                reintentos += 1
                print(f"❌ Error HTTP {e.response.status_code}. "
                      f"Intento {reintentos}/{self.max_reintentos}")

            except (httpx.ConnectError, httpx.RemoteProtocolError) as e:
                reintentos += 1
                print(f"❌ Error de conexión: {e}. "
                      f"Intento {reintentos}/{self.max_reintentos}")

            except asyncio.CancelledError:
                print("🛑 Receptor cancelado externamente.")
                self._activo = False
                return

            if not self._activo:
                break

            if reintentos >= self.max_reintentos:
                print(f"🚫 Se alcanzó el límite de {self.max_reintentos} reintentos. "
                      "Deteniendo reconexión.")
                self._activo = False
                break

            # Backoff exponencial: retry_ms × 2^(reintentos-1), cap en 60s
            espera_ms = min(self.retry_ms * (2 ** (reintentos - 1)), 60_000)
            espera_s = espera_ms / 1000
            print(f"⏳ Esperando {espera_s:.1f}s antes de reconectar "
                  f"(backoff exponencial)...")
            try:
                await asyncio.sleep(espera_s)
            except asyncio.CancelledError:
                self._activo = False
                return

        print("🏁 ReceptorAlertas detenido limpiamente.")

    def detener(self):
        """
        Detiene el receptor limpiamente levantando la bandera _activo.
        Después de llamar a detener(), no quedan tareas activas.
        """
        print("\n🛑 Deteniendo ReceptorAlertas...")
        self._activo = False

    # ── Implementación interna ───────────────────────────────────────

    async def _consumir_stream(self):
        """Abre la conexión SSE y lee el stream línea a línea."""
        headers = {
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache",
        }
        if self._ultimo_id is not None:
            headers["Last-Event-ID"] = self._ultimo_id

        # INVARIANTE: timeout de 30s configurado en la conexión inicial
        timeout = httpx.Timeout(
            connect=self.timeout_s,
            read=None,      # lectura sin límite (stream abierto)
            write=10.0,
            pool=5.0,
        )

        async with httpx.AsyncClient() as cliente:
            async with cliente.stream(
                "GET",
                self.url,
                headers=headers,
                timeout=timeout,
            ) as respuesta:
                respuesta.raise_for_status()

                content_type = respuesta.headers.get("content-type", "")
                if "text/event-stream" not in content_type:
                    raise ValueError(
                        f"El servidor no devolvió text/event-stream. "
                        f"Content-Type: {content_type}"
                    )

                ts = datetime.now().strftime("%H:%M:%S")
                print(f"✅ [{ts}] Conexión establecida. Leyendo stream...")

                # INVARIANTE: buffer reseteado completamente
                buffer: dict = {}

                async for linea in respuesta.aiter_lines():
                    if not self._activo:
                        break

                    ts = datetime.now().strftime("%H:%M:%S")
                    print(f"  📥 [{ts}] RAW: {repr(linea)}")

                    evento = parsear_linea(linea, buffer)

                    if evento is not None:
                        self._procesar_evento(evento)

    def _procesar_evento(self, evento: EventoSSE):
        """Despacha el evento al handler correspondiente."""
        ts = datetime.now().strftime("%H:%M:%S")

        # Actualizar retry_ms si el servidor lo especificó
        if evento.retry_ms is not None:
            self.retry_ms = evento.retry_ms
            print(f"  🔄 [{ts}] retry actualizado a {self.retry_ms}ms por el servidor")

        # Actualizar último ID recibido (para Last-Event-ID en reconexión)
        if evento.id is not None:
            self._ultimo_id = evento.id

        print(f"\n  📣 [{ts}] EVENTO id={evento.id} | tipo={evento.event}")

        handler = HANDLERS.get(evento.event)

        if handler:
            try:
                # INVARIANTE: excepción en handler NO cierra la conexión
                handler(evento.data, evento.id)
            except Exception as e:
                _log_warning(
                    f"Handler '{evento.event}' lanzó excepción (id={evento.id}): {e}. "
                    "Continuando stream..."
                )
        else:
            # Evento desconocido: ignorar silenciosamente con log de advertencia
            _log_warning(
                f"Evento de tipo desconocido '{evento.event}' recibido "
                f"(id={evento.id}) — ignorado."
            )


# ════════════════════════════════════════════════════════════════════
# Entrada principal
# ════════════════════════════════════════════════════════════════════

async def main():
    """
    Demostración usando sse.dev/test — un endpoint SSE público
    que genera eventos cada pocos segundos sin necesitar servidor propio.

    Para usar con un servidor propio:
      receptor = ReceptorAlertas("http://localhost:8000/api/alertas")
    """
    URL_SSE = "https://sse.dev/test"   # endpoint SSE público para pruebas

    receptor = ReceptorAlertas(
        url=URL_SSE,
        timeout_s=30.0,
        retry_ms=3000,
        max_reintentos=5,
    )

    print("=" * 60)
    print("  RECEPTOR ALERTAS ECOMARKET — RetoIA_2 · Semana 6")
    print("  Programación Distribuida del Lado del Cliente · UAN")
    print("=" * 60)
    print(f"  Endpoint: {URL_SSE}")
    print(f"  Timeout:  {receptor.timeout_s}s")
    print(f"  Max reintentos: {receptor.max_reintentos} (backoff exponencial)")
    print("  Presiona Ctrl+C para detener limpiamente")
    print("=" * 60)

    try:
        await receptor.iniciar()
    except KeyboardInterrupt:
        receptor.detener()

    print("\n📊 Estado final de la tabla de precios:")
    tabla_precios.mostrar()


if __name__ == "__main__":
    asyncio.run(main())
