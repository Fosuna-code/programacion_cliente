"""
RECEPTOR ALERTAS V2 — Observer + SSE integrados (RetoIA_5)
============================================================
Semana 6 · Fase PROFUNDIZA · Programación Distribuida del Lado del Cliente · UAN

Integra el patrón Observer de Semana 4 con el cliente SSE:
  - ReceptorAlertas COMPONE Observable (no hereda → ver README para justificación)
  - Cuando llega un evento SSE de tipo X, dispara evento Observable X
  - Suscriptores son funciones independientes (no clases)
  - Un suscriptor que falla NO rompe el receptor ni los demás suscriptores
  - Se mantienen todos los invariantes del RetoIA_2 (ver checklist)

Decisión de diseño: composición vs herencia
-------------------------------------------
Se elige COMPOSICIÓN sobre herencia porque:
  1. ReceptorAlertas YA tiene una responsabilidad clara: gestionar la conexión SSE.
     Heredar de Observable añadiría una segunda responsabilidad (despacho de eventos)
     en la misma clase — violando el Principio de Responsabilidad Única (SRP).
  2. Con composición, Observable puede ser reemplazada o mockeada en tests
     sin cambiar la clase principal.
  3. La herencia implicaría que ReceptorAlertas "es un" Observable, lo cual es
     semánticamente incorrecto: el receptor maneja conexiones de red, no es
     un despachador de eventos en su esencia.
  4. En Python, la herencia múltiple es posible pero introduce complejidad
     (MRO - Method Resolution Order) innecesaria para este caso.

Patrón Observer aplicado a SSE vs Polling (Semana 4):
------------------------------------------------------
  Semana 4 — Observer en polling:
    El Observable era el Sujeto que ACTIVAMENTE comprobaba cambios
    cada N segundos y notificaba a los observadores cuando detectaba
    un cambio. La fuente de eventos era el CLIENTE (pull).

  Semana 6 — Observer en SSE:
    El Observable es un despachador PASIVO: no busca cambios, sino que
    RECIBE eventos empujados por el servidor y los retransmite a los
    suscriptores. La fuente de eventos es el SERVIDOR (push).
    El cliente solo enruta, no inicia.
"""

import asyncio
import json
from datetime import datetime
from typing import Callable, Dict, List, Optional
from collections import defaultdict

try:
    import httpx
except ImportError:
    raise SystemExit("pip install httpx")


# ════════════════════════════════════════════════════════════════════
# Observable — Despachador de eventos (patrón Observer)
# ════════════════════════════════════════════════════════════════════

class Observable:
    """
    Despachador de eventos genérico.
    Permite registrar suscriptores por tipo de evento y notificarlos.
    Equivalente a un EventEmitter simplificado.
    """

    def __init__(self):
        # Dict[tipo_evento, List[callable]] — suscriptores por tipo
        self._suscriptores: Dict[str, List[Callable]] = defaultdict(list)

    def suscribir(self, tipo_evento: str, handler: Callable):
        """Registra un suscriptor para un tipo de evento."""
        self._suscriptores[tipo_evento].append(handler)
        print(f"  📋 Suscriptor registrado para '{tipo_evento}': {handler.__name__}")

    def desuscribir(self, tipo_evento: str, handler: Callable):
        """Elimina un suscriptor."""
        if tipo_evento in self._suscriptores:
            try:
                self._suscriptores[tipo_evento].remove(handler)
            except ValueError:
                pass

    def notificar(self, tipo_evento: str, datos: dict, id_evento: Optional[str] = None):
        """
        Notifica a todos los suscriptores del tipo de evento.
        INVARIANTE: un suscriptor que falla NO interrumpe a los demás.
        """
        handlers = self._suscriptores.get(tipo_evento, [])
        for handler in handlers:
            try:
                handler(datos, id_evento)
            except Exception as e:
                ts = datetime.now().strftime("%H:%M:%S")
                print(f"  ⚡ [{ts}] Suscriptor '{handler.__name__}' lanzó excepción: {e} — continuando.")


# ════════════════════════════════════════════════════════════════════
# Suscriptores (funciones independientes, no clases)
# ════════════════════════════════════════════════════════════════════

# Tabla de precios simulada (estado compartido del suscriptor UI)
_tabla_precios: Dict[str, dict] = {}

# Registro de auditoría (lista de eventos)
_log_auditoria: List[dict] = []


def actualizador_precios_ui(datos: dict, id_evento: Optional[str]):
    """
    SUSCRIPTOR 1: ActualizadorPreciosUI
    Actualiza la tabla de precios simulada cuando llega un evento precio-actualizado.
    """
    producto = datos.get("producto", "?")
    precio = datos.get("precio", 0)
    moneda = datos.get("moneda", "MXN")
    ts = datetime.now().isoformat()

    _tabla_precios[producto] = {
        "precio": precio,
        "moneda": moneda,
        "actualizado": ts,
        "id_evento": id_evento,
    }
    print(f"  🖥️  [UI] Tabla actualizada: {producto} = {precio} {moneda}")
    print(f"       Total productos en tabla: {len(_tabla_precios)}")


def alerta_stock_critico(datos: dict, id_evento: Optional[str]):
    """
    SUSCRIPTOR 2: AlertaStockCritico
    Imprime alerta con nivel de urgencia basado en el stock disponible.
    """
    producto = datos.get("producto", "?")
    stock = datos.get("stock", 0)
    umbral = datos.get("umbral", 5)

    # Nivel de urgencia según stock
    if stock == 0:
        nivel = "🔴 CRÍTICO"
    elif stock <= umbral // 2:
        nivel = "🟠 ALTO"
    else:
        nivel = "🟡 MODERADO"

    print(f"  🚨 [{nivel}] Stock de '{producto}': {stock} unidades "
          f"(umbral={umbral}) [id={id_evento}]")


def registrador_auditoria(datos: dict, id_evento: Optional[str]):
    """
    SUSCRIPTOR 3: RegistradorAuditoria
    Guarda timestamp + tipo + datos en la lista de auditoría.
    (Nota: recibe el tipo desde el closure del dispatcher)
    """
    entrada = {
        "timestamp": datetime.now().isoformat(),
        "id_evento": id_evento,
        "datos": datos,
    }
    _log_auditoria.append(entrada)
    print(f"  📝 [AUDITORÍA] Entrada #{len(_log_auditoria)} registrada (id={id_evento})")


def mostrar_tabla_precios():
    """Muestra el estado actual de la tabla de precios."""
    print("\n📊 === TABLA DE PRECIOS ACTUAL ===")
    if not _tabla_precios:
        print("  (tabla vacía)")
        return
    for prod, info in _tabla_precios.items():
        print(f"  {prod}: {info['precio']} {info['moneda']} "
              f"(última act: {info['actualizado'][:19]})")
    print(f"  Total: {len(_tabla_precios)} productos")


def mostrar_log_auditoria():
    """Muestra el registro de auditoría acumulado."""
    print(f"\n📋 === LOG DE AUDITORÍA ({len(_log_auditoria)} entradas) ===")
    for entrada in _log_auditoria:
        print(f"  [{entrada['timestamp'][:19]}] id={entrada['id_evento']} "
              f"→ {entrada['datos']}")


# ════════════════════════════════════════════════════════════════════
# ReceptorAlertasV2 — SSE + Observer (composición)
# ════════════════════════════════════════════════════════════════════

class ReceptorAlertasV2:
    """
    Cliente SSE para EcoMarket con despachador Observable integrado.

    Usa COMPOSICIÓN: ReceptorAlertasV2 TIENE UN Observable (no lo es).
    El receptor gestiona la conexión SSE; el observable gestiona los suscriptores.
    """

    def __init__(
        self,
        url: str,
        timeout_s: float = 30.0,
        retry_ms: int = 3000,
        max_reintentos: int = 5,
    ):
        self.url = url
        self.timeout_s = timeout_s
        self.retry_ms = retry_ms
        self.max_reintentos = max_reintentos

        self._activo = False
        self._ultimo_id: Optional[str] = None

        # COMPOSICIÓN: el receptor tiene un Observable
        self._dispatcher = Observable()

    # ── API pública ──────────────────────────────────────────────────

    def suscribir(self, tipo_evento: str, handler: Callable):
        """Delega al dispatcher Observable."""
        self._dispatcher.suscribir(tipo_evento, handler)

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
                reintentos = 0

            except httpx.TimeoutException:
                reintentos += 1
                print(f"⏱  Timeout. Intento {reintentos}/{self.max_reintentos}")

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 204:
                    print("✅ 204 No Content — fin del stream.")
                    self._activo = False
                    return
                reintentos += 1

            except (httpx.ConnectError, httpx.RemoteProtocolError) as e:
                reintentos += 1
                print(f"❌ Error: {e}. Intento {reintentos}/{self.max_reintentos}")

            except asyncio.CancelledError:
                self._activo = False
                return

            if not self._activo or reintentos >= self.max_reintentos:
                self._activo = False
                break

            # Backoff exponencial
            espera_ms = min(self.retry_ms * (2 ** (reintentos - 1)), 60_000)
            print(f"⏳ Esperando {espera_ms/1000:.1f}s (backoff exponencial)...")
            try:
                await asyncio.sleep(espera_ms / 1000)
            except asyncio.CancelledError:
                self._activo = False
                return

        print("🏁 ReceptorAlertasV2 detenido limpiamente.")

    def detener(self):
        self._activo = False

    # ── Implementación interna ───────────────────────────────────────

    async def _consumir_stream(self):
        headers = {
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache",
        }
        if self._ultimo_id is not None:
            headers["Last-Event-ID"] = self._ultimo_id

        timeout = httpx.Timeout(connect=self.timeout_s, read=None, write=10.0, pool=5.0)

        async with httpx.AsyncClient() as cliente:
            async with cliente.stream("GET", self.url, headers=headers, timeout=timeout) as resp:
                resp.raise_for_status()

                ts = datetime.now().strftime("%H:%M:%S")
                print(f"✅ [{ts}] Conexión establecida. Escuchando eventos...")

                buffer: dict = {}

                async for linea in resp.aiter_lines():
                    if not self._activo:
                        break

                    evento = self._parsear_linea(linea, buffer)
                    if evento is not None:
                        self._despachar_evento(evento)

    def _parsear_linea(self, linea: str, buffer: dict) -> Optional[dict]:
        """Parsea una línea del stream SSE y acumula en el buffer."""
        if linea == "":
            if not buffer.get("data"):
                buffer.clear()
                return None
            evento = {
                "id": buffer.get("id"),
                "event": buffer.get("event", "message"),
                "data": buffer.get("data", ""),
                "retry_ms": buffer.get("retry_ms"),
            }
            buffer.clear()  # INVARIANTE: reset completo
            return evento

        if linea.startswith(":"):
            ts = datetime.now().strftime("%H:%M:%S")
            print(f"  🔔 [{ts}] keep-alive")
            return None

        if ":" in linea:
            campo, _, valor = linea.partition(":")
            valor = valor.lstrip(" ")
        else:
            campo, valor = linea, ""

        if campo == "id":
            buffer["id"] = valor
        elif campo == "event":
            buffer["event"] = valor
        elif campo == "data":
            buffer["data"] = (buffer.get("data", "") + "\n" + valor).lstrip("\n")
        elif campo == "retry":
            try:
                buffer["retry_ms"] = int(valor)
            except ValueError:
                pass

        return None

    def _despachar_evento(self, evento: dict):
        """Parsea los datos del evento y notifica al dispatcher Observable."""
        ts = datetime.now().strftime("%H:%M:%S")

        if evento.get("retry_ms"):
            self.retry_ms = evento["retry_ms"]

        if evento.get("id") is not None:
            self._ultimo_id = evento["id"]

        tipo = evento.get("event", "message")
        datos_raw = evento.get("data", "")
        id_ev = evento.get("id")

        print(f"\n  📣 [{ts}] EVENTO id={id_ev} | tipo={tipo}")

        # Parsear datos JSON
        try:
            datos = json.loads(datos_raw) if datos_raw else {}
        except json.JSONDecodeError:
            datos = {"raw": datos_raw}

        # INVARIANTE: excepción en suscriptor no cierra el stream (manejado en Observable.notificar)
        self._dispatcher.notificar(tipo, datos, id_ev)


# ════════════════════════════════════════════════════════════════════
# Demostración con 10 eventos mixtos de EcoMarket
# ════════════════════════════════════════════════════════════════════

async def simular_10_eventos():
    """
    Demostración offline de los 3 suscriptores con 10 eventos mixtos.
    No requiere servidor SSE externo.
    """
    print("=" * 60)
    print("  DEMO OFFLINE — 10 eventos mixtos de EcoMarket")
    print("=" * 60)

    receptor = ReceptorAlertasV2("https://sse.dev/test")

    # Registrar los 3 suscriptores
    print("\n📋 Registrando suscriptores...")
    receptor.suscribir("precio-actualizado", actualizador_precios_ui)
    receptor.suscribir("precio-actualizado", registrador_auditoria)
    receptor.suscribir("stock-critico", alerta_stock_critico)
    receptor.suscribir("stock-critico", registrador_auditoria)

    # Simular 10 eventos mixtos directamente a través del dispatcher
    eventos_demo = [
        {"id": "1",  "event": "precio-actualizado",
         "data": '{"producto":"A01","precio":47,"moneda":"MXN"}'},
        {"id": "2",  "event": "stock-critico",
         "data": '{"producto":"B07","stock":0,"umbral":5}'},
        {"id": "3",  "event": "precio-actualizado",
         "data": '{"producto":"C03","precio":120,"moneda":"MXN"}'},
        {"id": "4",  "event": "stock-critico",
         "data": '{"producto":"D11","stock":2,"umbral":5}'},
        {"id": "5",  "event": "precio-actualizado",
         "data": '{"producto":"A01","precio":45,"moneda":"MXN"}'},
        {"id": "6",  "event": "nuevo-pedido",
         "data": '{"pedido":"PED-042","cliente":"C001"}'},        # tipo desconocido
        {"id": "7",  "event": "precio-actualizado",
         "data": '{"producto":"E05","precio":33,"moneda":"MXN"}'},
        {"id": "8",  "event": "stock-critico",
         "data": '{"producto":"B07","stock":1,"umbral":5}'},
        {"id": "9",  "event": "precio-actualizado",
         "data": 'DATOS_INVALIDOS'},                              # JSON inválido
        {"id": "10", "event": "precio-actualizado",
         "data": '{"producto":"C03","precio":115,"moneda":"MXN"}'},
    ]

    print(f"\n🚀 Despachando {len(eventos_demo)} eventos...\n")

    for ev_raw in eventos_demo:
        await asyncio.sleep(0.3)  # simular tiempo entre eventos
        try:
            datos = json.loads(ev_raw["data"])
        except json.JSONDecodeError:
            datos = {"raw": ev_raw["data"]}

        ts = datetime.now().strftime("%H:%M:%S")
        print(f"\n  📣 [{ts}] EVENTO id={ev_raw['id']} | tipo={ev_raw['event']}")
        receptor._dispatcher.notificar(ev_raw["event"], datos, ev_raw["id"])

    # Mostrar estado final
    mostrar_tabla_precios()
    mostrar_log_auditoria()

    print("\n✅ Demo completada. Los 3 suscriptores recibieron eventos.")
    print(f"   - Entradas en auditoría: {len(_log_auditoria)}")
    print(f"   - Productos en tabla: {len(_tabla_precios)}")


async def main():
    print("=" * 60)
    print("  RECEPTOR ALERTAS V2 — Observer + SSE · RetoIA_5 · Semana 6")
    print("  Programación Distribuida del Lado del Cliente · UAN")
    print("=" * 60)
    print()
    print("Modo: Demo offline (10 eventos simulados sin servidor)")
    print()
    await simular_10_eventos()


if __name__ == "__main__":
    asyncio.run(main())
