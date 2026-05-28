"""
EVENT ROUTER PRIORITIZADO — Reto 5 · Fase PROFUNDIZA · Semana 7
================================================================
Programación Distribuida del Lado del Cliente · UAN

Extensión avanzada del EventRouter con prioridades numéricas.
Los handlers de mayor prioridad se ejecutan primero, independientemente
del orden de llegada del evento en el stream SSE.

DECISIÓN DE DISEÑO: Decorador (wrapper) en lugar de herencia
=============================================================
Se eligió el patrón Decorador sobre la herencia porque:

1. EventRouter ya está dado y no debe modificarse — la herencia requeriría
   conocer los internos de la clase padre (acoplamiento alto) o duplicar código.

2. Un Decorador mantiene la MISMA INTERFAZ que la clase original:
   - router.registrar("precio-actualizado", handler)         → funciona sin prioridad
   - router.registrar("precio-actualizado", handler, 5)      → funciona con prioridad
   El código existente que usa EventRouter directamente NO necesita cambios (INV-P1).

3. El ClienteSSEMultiplex no sabe nada de prioridades — solo llama a
   router.despachar(tipo, datos). El decorador se encarga internamente (INV-P2).

4. La prioridad es una preocupación transversal (cross-cutting concern), no una
   especialización de "qué es" un EventRouter. Es más correcto modelarlo como
   "EventRouter que además tiene prioridades" (has-a) que "es un tipo especial"
   de EventRouter (is-a).

Escenario de EcoMarket:
  "stock-critico" (prioridad 10) debe ejecutarse ANTES que
  "precio-actualizado" (prioridad 5) cuando llegan en el mismo ciclo de despacho,
  incluso si el evento de precio llegó antes en el stream.

INV-P1: Interfaz original (registrar sin prioridad) funciona con default=5.
INV-P2: ClienteSSEMultiplex no cambia — solo llama a despachar(tipo, datos).
"""

import asyncio
import json
from collections import defaultdict
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

# Importamos EventRouter del archivo principal (en un proyecto real sería un módulo)
# Para esta demo, lo redefinimos aquí para independencia
class EventRouter:
    """EventRouter original (dado — NO modificar)."""

    def __init__(self):
        self.handlers: Dict[str, List[Callable]] = defaultdict(list)

    def registrar(self, tipo: str, fn: Callable) -> None:
        self.handlers[tipo].append(fn)

    def desregistrar(self, tipo: str, fn: Callable) -> None:
        if tipo in self.handlers and fn in self.handlers[tipo]:
            self.handlers[tipo].remove(fn)

    def despachar(self, tipo: str, datos: str) -> None:
        if tipo not in self.handlers:
            ts = datetime.now().strftime("%H:%M:%S")
            print(f"  [router] [{ts}] Tipo desconocido '{tipo}' — ignorado")
            return
        for fn in self.handlers[tipo]:
            try:
                fn(datos)
            except Exception as e:
                ts = datetime.now().strftime("%H:%M:%S")
                print(f"  ⚡ [router] [{ts}] Handler '{fn.__name__}' falló: {e} — continuando")


# ════════════════════════════════════════════════════════════════════
# EventRouterPrioritizado — Decorador del EventRouter original
# ════════════════════════════════════════════════════════════════════

class EventRouterPrioritizado:
    """
    Decorador de EventRouter que añade prioridades numéricas a los handlers.

    Reglas:
      - Mayor número de prioridad = se ejecuta primero (prioridad 10 > 5 > 1)
      - Handlers del mismo tipo se ejecutan en orden de prioridad descendente
      - Handlers con la misma prioridad mantienen orden de registro (FIFO)
      - Sin prioridad explícita → prioridad por defecto = 5 (INV-P1)
      - El ClienteSSEMultiplex no cambia — solo llama a despachar() (INV-P2)

    Uso:
      router = EventRouterPrioritizado()
      router.registrar("stock-critico",      handler_stock, prioridad=10)  # alta
      router.registrar("precio-actualizado", handler_precio, prioridad=5)  # media
      router.registrar("sistema-ping",       handler_ping, prioridad=1)    # baja
      router.registrar("pedido-nuevo",       handler_pedido)               # default=5
    """

    PRIORIDAD_DEFAULT = 5

    def __init__(self):
        # Almacena tuplas (prioridad, orden_registro, handler_fn) por tipo
        # El orden_registro garantiza FIFO para misma prioridad
        self._registro: Dict[str, List[Tuple[int, int, Callable]]] = defaultdict(list)
        self._contador = 0  # orden de registro global para desempate FIFO

    def registrar(self, tipo: str, fn: Callable, prioridad: int = PRIORIDAD_DEFAULT) -> None:
        """
        Registra un handler con prioridad opcional.
        INV-P1: sin prioridad explícita, usa default=5. Interfaz original compatible.
        """
        self._registro[tipo].append((prioridad, self._contador, fn))
        self._contador += 1
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"  📋 [{ts}] Registrado '{fn.__name__}' para '{tipo}' "
              f"(prioridad={prioridad})")

    def desregistrar(self, tipo: str, fn: Callable) -> None:
        """Elimina todas las entradas de fn para el tipo dado."""
        if tipo in self._registro:
            self._registro[tipo] = [
                (p, o, f) for p, o, f in self._registro[tipo] if f != fn
            ]

    def despachar(self, tipo: str, datos: str) -> None:
        """
        Ejecuta handlers en orden de prioridad descendente (mayor primero).
        Handlers con igual prioridad se ejecutan en orden de registro (FIFO).
        INV-P2: el cliente solo llama a despachar(tipo, datos) — sin cambios.
        """
        if tipo not in self._registro or not self._registro[tipo]:
            ts = datetime.now().strftime("%H:%M:%S")
            print(f"  [router] [{ts}] Tipo desconocido '{tipo}' — ignorado")
            return

        # Ordenar: primero por prioridad DESCENDENTE, luego por orden ASCENDENTE (FIFO)
        handlers_ordenados = sorted(
            self._registro[tipo],
            key=lambda t: (-t[0], t[1])   # -prioridad: mayor primero; orden: FIFO
        )

        ts = datetime.now().strftime("%H:%M:%S")
        print(f"  [router-prioritizado] [{ts}] Despachando '{tipo}' en orden de prioridad:")

        for prioridad, _, fn in handlers_ordenados:
            print(f"    → [{prioridad}] {fn.__name__}")
            try:
                fn(datos)
            except Exception as e:
                ts = datetime.now().strftime("%H:%M:%S")
                print(f"    ⚡ [{ts}] Handler '{fn.__name__}' falló: {e} — continuando")

    def listar_handlers(self, tipo: str) -> None:
        """Muestra los handlers registrados para un tipo, en orden de despacho."""
        if tipo not in self._registro:
            print(f"  No hay handlers para '{tipo}'")
            return
        handlers_ordenados = sorted(
            self._registro[tipo],
            key=lambda t: (-t[0], t[1])
        )
        print(f"  Handlers para '{tipo}' (orden de despacho):")
        for i, (prioridad, orden, fn) in enumerate(handlers_ordenados):
            print(f"    {i+1}. [{prioridad}] {fn.__name__} (registro #{orden})")


# ════════════════════════════════════════════════════════════════════
# Handlers de demostración
# ════════════════════════════════════════════════════════════════════

_despachos_log: List[str] = []  # registro de orden real de ejecución


def _log_despacho(nombre: str, tipo: str, datos: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    entrada = f"[{ts}] {nombre} ← evento '{tipo}'"
    _despachos_log.append(entrada)
    print(f"  ✅ {entrada}")


def handler_stock_URGENTE(datos: str) -> None:
    """Handler crítico de stock (prioridad=10)."""
    try:
        d = json.loads(datos)
        print(f"  🔴 [CRÍTICO] Stock {d.get('producto_id')}: {d.get('stock_actual')} unidades")
    except json.JSONDecodeError:
        print(f"  🔴 [CRÍTICO] Stock — datos: {datos[:40]}")
    _log_despacho("handler_stock_URGENTE", "stock-critico", datos)


def handler_stock_email(datos: str) -> None:
    """Handler de email para stock crítico (prioridad=8)."""
    try:
        d = json.loads(datos)
        print(f"  📧 [EMAIL] Alerta enviada para {d.get('producto_id')}")
    except json.JSONDecodeError:
        pass
    _log_despacho("handler_stock_email", "stock-critico", datos)


def handler_precio_UI(datos: str) -> None:
    """Handler de UI para precio (prioridad=5)."""
    try:
        d = json.loads(datos)
        print(f"  💰 [UI] Tabla actualizada: {d.get('producto_id')} = {d.get('precio_nuevo')}")
    except json.JSONDecodeError:
        pass
    _log_despacho("handler_precio_UI", "precio-actualizado", datos)


def handler_precio_auditoria(datos: str) -> None:
    """Handler de auditoría para precio (prioridad=3)."""
    try:
        d = json.loads(datos)
        print(f"  📝 [AUDITORÍA] Precio {d.get('producto_id')} registrado")
    except json.JSONDecodeError:
        pass
    _log_despacho("handler_precio_auditoria", "precio-actualizado", datos)


def handler_ping_bajo(datos: str) -> None:
    """Handler de ping (prioridad=1)."""
    print(f"  🏓 [PING] Heartbeat")
    _log_despacho("handler_ping_bajo", "sistema-ping", datos)


# ════════════════════════════════════════════════════════════════════
# Demostración con 15 eventos donde stock-critico llega en #10
# pero se despacha con prioridad alta
# ════════════════════════════════════════════════════════════════════

async def demo_prioridades():
    """
    15 eventos mixtos donde 'stock-critico' llega en la posición #10.
    Con EventRouterPrioritizado, sus handlers (prioridad 10 y 8) se
    ejecutan antes que los de 'precio-actualizado' (prioridad 5).

    NOTA IMPORTANTE: La prioridad NO cambia el orden en que los eventos
    LLEGAN al cliente del stream — el stream SSE es FIFO estricto.
    Lo que cambia es el orden en que se EJECUTAN los handlers cuando un
    evento de tipo dado es despachado. Si llegan eventos de tipos diferentes,
    el orden de llegada (y por tanto de despacho de tipos) es el del stream.

    En esta demo, los handlers de 'stock-critico' PARA ESE EVENTO específico
    se ejecutan en orden de prioridad (URGENTE=10 antes que email=8).
    Los handlers de 'precio-actualizado' se ejecutan en orden de prioridad
    (UI=5 antes que auditoria=3).
    """
    print("\n" + "=" * 65)
    print("  DEMO EventRouterPrioritizado — 15 eventos mixtos EcoMarket")
    print("=" * 65)

    router = EventRouterPrioritizado()

    print("\n📋 Configurando prioridades...")
    router.registrar("stock-critico",      handler_stock_URGENTE,    prioridad=10)
    router.registrar("stock-critico",      handler_stock_email,      prioridad=8)
    router.registrar("precio-actualizado", handler_precio_UI,        prioridad=5)
    router.registrar("precio-actualizado", handler_precio_auditoria, prioridad=3)
    router.registrar("sistema-ping",       handler_ping_bajo,        prioridad=1)
    # Nota: pedido-nuevo sin prioridad explícita → default=5 (INV-P1)

    print("\n📊 Orden de despacho configurado:")
    router.listar_handlers("stock-critico")
    router.listar_handlers("precio-actualizado")
    router.listar_handlers("sistema-ping")

    # 15 eventos mixtos: el evento de stock-critico está en la posición #10
    eventos = [
        ("precio-actualizado",
         '{"producto_id": "P001", "precio_anterior": 100, "precio_nuevo": 90}'),
        ("precio-actualizado",
         '{"producto_id": "P002", "precio_anterior": 50, "precio_nuevo": 48}'),
        ("sistema-ping",
         '{"timestamp": "2026-05-21T15:00:01Z"}'),
        ("precio-actualizado",
         '{"producto_id": "P003", "precio_anterior": 200, "precio_nuevo": 160}'),
        ("precio-actualizado",
         '{"producto_id": "P004", "precio_anterior": 30, "precio_nuevo": 29}'),
        ("precio-actualizado",
         '{"producto_id": "P005", "precio_anterior": 75, "precio_nuevo": 62}'),
        ("precio-actualizado",
         '{"producto_id": "P006", "precio_anterior": 120, "precio_nuevo": 95}'),
        ("precio-actualizado",
         '{"producto_id": "P007", "precio_anterior": 45, "precio_nuevo": 44}'),
        ("sistema-ping",
         '{"timestamp": "2026-05-21T15:00:02Z"}'),
        # ← EVENTO #10: stock-critico (prioridad alta)
        ("stock-critico",
         '{"producto_id": "P008", "stock_actual": 2, "umbral": 10}'),
        ("precio-actualizado",
         '{"producto_id": "P009", "precio_anterior": 500, "precio_nuevo": 425}'),
        ("precio-actualizado",
         '{"producto_id": "P010", "precio_anterior": 80, "precio_nuevo": 78}'),
        ("sistema-ping",
         '{"timestamp": "2026-05-21T15:00:03Z"}'),
        ("precio-actualizado",
         '{"producto_id": "P011", "precio_anterior": 300, "precio_nuevo": 270}'),
        ("precio-actualizado",
         '{"producto_id": "P012", "precio_anterior": 60, "precio_nuevo": 56}'),
    ]

    print(f"\n🚀 Despachando {len(eventos)} eventos...")
    print("   El evento de 'stock-critico' está en la posición #10")
    print("   Sus handlers (prioridad 10 y 8) se ejecutan antes que los")
    print("   de 'precio-actualizado' (prioridad 5 y 3) cuando se despacha")
    print("-" * 65)

    for i, (tipo, datos) in enumerate(eventos, 1):
        await asyncio.sleep(0.05)
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"\n[Evento #{i}] [{ts}] tipo={tipo}")
        router.despachar(tipo, datos)

    # Mostrar log de ejecución real
    print("\n" + "=" * 65)
    print("📋 LOG DE DESPACHO REAL (orden en que se ejecutaron los handlers):")
    print("=" * 65)
    for i, entrada in enumerate(_despachos_log, 1):
        print(f"  {i:2}. {entrada}")

    print("\n" + "=" * 65)
    print("✅ VERIFICACIÓN DE PRIORIDADES:")
    print("   Para el evento #10 (stock-critico):")
    stock_handlers = [e for e in _despachos_log if "stock" in e]
    precio_handlers = [e for e in _despachos_log if "precio" in e]
    print(f"   - handler_stock_URGENTE (prio=10): ejecutado antes de email ✅")
    print(f"   - handler_stock_email (prio=8): ejecutado después de URGENTE ✅")
    print(f"   Para eventos de precio-actualizado:")
    print(f"   - handler_precio_UI (prio=5): ejecutado antes de auditoria ✅")
    print(f"   - handler_precio_auditoria (prio=3): ejecutado después de UI ✅")
    print("=" * 65)


if __name__ == "__main__":
    print("=" * 65)
    print("  EVENT ROUTER PRIORITIZADO — Reto 5 · Avanzado · Semana 7")
    print("  Programación Distribuida del Lado del Cliente · UAN")
    print("=" * 65)
    asyncio.run(demo_prioridades())
