"""
cliente_integrado.py — Script de integracion para Reto 4 (Semana 10)
=====================================================================

Demuestra la integracion completa de:
  1. TokenManager (login, JWT decode, refresh singleton)
  2. CircuitBreaker (3 estados, transiciones, fail-fast)
  3. ClienteRobusto (orquesta CB + TM sin duplicar logica)
  4. Estado observable de UI al abrir/cerrar circuito

Secuencia:
  Login exitoso → 3 respuestas 200 → 5 fallos 503 → recuperacion

Requiere servidor_mock.py corriendo en http://localhost:3000
"""

import asyncio
import json
import logging
import sys
import time

import aiohttp

from token_manager import TokenManager
from circuit_breaker import CircuitBreaker, CircuitOpenError, EstadoCircuito
from cliente_robusto import ClienteRobusto


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)


def notificador_ui(estado, mensaje, datos):
    emoji = {"conectado": "🟢", "degradado": "🟡", "desconectado": "🔴"}.get(estado, "⚪")
    print(f"[UI] {emoji} {estado.upper()} — {mensaje}")
    if datos:
        for k, v in datos.items():
            print(f"     {k}={v}")


async def demo_integrado():
    print("=" * 70)
    print("  EcoMarket — Cliente Integrado (Reto 4: Grand Deploy)")
    print("=" * 70)
    print()

    tm = TokenManager(base_url="http://localhost:3000")
    cliente = ClienteRobusto(
        token_manager=tm,
        umbral_fallos=5,
        timeout_apertura=60.0,
        base_url="http://localhost:3000/api",
        max_retries=0,
    )
    cliente.suscribir_estado(notificador_ui)

    # ── FASE 0: Login ─────────────────────────────────────────
    print("\n" + "─" * 70)
    print("FASE 0: Login")
    print("─" * 70)

    try:
        login_data = await tm.login(username="op1", rol="viewer")
        payload = tm.decode_payload(tm.access_token)
        print(f"[LOGIN] Token almacenado · rol={payload.get('rol')} · sub={payload.get('sub')}")
        print(f"[LOGIN] Token expira en {payload.get('exp', 0) - int(time.time())}s")
    except Exception as e:
        print(f"[LOGIN] ERROR: {e}")
        print("Asegurate de que servidor_mock.py esta corriendo en localhost:3000")
        await tm.close()
        return

    # ── Admin helpers ──────────────────────────────────────────
    session = await cliente._session_actual()

    async def cambiar_modo(modo: str):
        async with session.post("http://localhost:3000/admin/modo", json={"modo": modo}) as resp:
            data = await resp.json()
            print(f"[ADMIN] Modo servidor -> {data['modo']}")

    async def reset_contador():
        async with session.post("http://localhost:3000/admin/reset") as resp:
            return await resp.json()

    # ── FASE 1: 3 respuestas 200 ──────────────────────────────
    print("\n" + "─" * 70)
    print("FASE 1: Peticiones exitosas (3 × 200)")
    print("─" * 70)
    await cambiar_modo("normal")

    for i in range(1, 4):
        try:
            resp = await cliente.get("/inventario")
            cb = cliente.circuit_breaker
            print(f"[HTTP #{i}] 200 · productos={resp.get('productos')} · CB: {cb.estado.name} (fallos={cb._fallos_consecutivos})")
        except Exception as e:
            print(f"[HTTP #{i}] fallo — {type(e).__name__}: {e}")

    # ── FASE 2: 5 fallos 503 → CB se abre ────────────────────
    print("\n" + "─" * 70)
    print("FASE 2: Fallos 503 sostenidos (CB se abre)")
    print("─" * 70)
    await cambiar_modo("fallo_503")
    await reset_contador()

    peticion_num = 4
    for i in range(5):
        try:
            resp = await cliente.get("/inventario")
            cb = cliente.circuit_breaker
            print(f"[HTTP #{peticion_num}] 200 · CB: {cb.estado.name} (fallos={cb._fallos_consecutivos})")
        except CircuitOpenError as e:
            print(f"[HTTP #{peticion_num}] CircuitOpenError — reintenta en {e.tiempo_restante:.0f}s")
            print("[UI] banner=Servidor temporalmente no disponible · action=disable_checkout")
        except aiohttp.ClientResponseError as e:
            cb = cliente.circuit_breaker
            print(f"[HTTP #{peticion_num}] {e.status} · CB: {cb.estado.name} (fallos={cb._fallos_consecutivos})")
        except Exception as e:
            cb = cliente.circuit_breaker
            print(f"[HTTP #{peticion_num}] {type(e).__name__} · CB: {cb.estado.name} (fallos={cb._fallos_consecutivos})")
        peticion_num += 1

    # ── FASE 3: Fail-fast (CB ABIERTO) ────────────────────────
    print("\n" + "─" * 70)
    print("FASE 3: Fail-fast (CB ABIERTO — sin tocar el servidor)")
    print("─" * 70)

    try:
        await cliente.get("/inventario")
    except CircuitOpenError as e:
        print(f"[BREAKER] Fail fast — CircuitOpenError (sin tocar el servidor)")
        print(f"[BREAKER] Tiempo restante: {e.tiempo_restante:.1f}s")

    # ── FASE 4: Esperar timeout → SEMIABIERTO ─────────────────
    print("\n" + "─" * 70)
    print(f"FASE 4: Esperando timeout ({cliente.circuit_breaker.timeout_apertura}s) → SEMIABIERTO...")
    print("─" * 70)

    timeout_cb = cliente.circuit_breaker.timeout_apertura
    await asyncio.sleep(timeout_cb + 1.0)
    print(f"[BREAKER] Timeout {timeout_cb}s → SEMIABIERTO")
    print(f"[BREAKER] Estado actual: {cliente.estado_circuito.name}")

    # ── FASE 5: Recuperacion ──────────────────────────────────
    print("\n" + "─" * 70)
    print("FASE 5: Recuperacion (restaurar modo normal)")
    print("─" * 70)
    await cambiar_modo("normal")
    await reset_contador()

    try:
        resp = await cliente.get("/inventario")
        cb = cliente.circuit_breaker
        print(f"[HTTP #{peticion_num}] 200 · productos={resp.get('productos')} · CB: {cb.estado.name} (fallos={cb._fallos_consecutivos})")
        peticion_num += 1
        print("[UI] banner=oculto · action=enable_checkout")
    except Exception as e:
        print(f"[HTTP #{peticion_num}] fallo — {type(e).__name__}: {e}")

    # Verificar estado final
    cb = cliente.circuit_breaker
    print(f"\nEstado final: circuito={cb.estado.name} · fallos={cb._fallos_consecutivos} · token_valido={not tm.is_expiring_soon()}")

    # ── FASE 6: Verificar que viewer puede hacer GET ───────────
    print("\n" + "─" * 70)
    print("FASE 6: Verificar que rol 'viewer' puede hacer GET")
    print("─" * 70)

    try:
        resp = await cliente.get("/inventario")
        print(f"[HTTP GET /inventario] 200 · rol=viewer puede consultar inventario ✅")
    except Exception as e:
        print(f"[HTTP GET /inventario] ERROR: {type(e).__name__}: {e}")

    # ── Cerrar ────────────────────────────────────────────────
    await cliente.cerrar()
    await tm.close()

    print("\n" + "=" * 70)
    print("  🏁 Demo integrado finalizado.")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(demo_integrado())
