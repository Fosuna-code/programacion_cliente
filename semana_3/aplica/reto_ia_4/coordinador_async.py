"""
Coordinador Asíncrono - Timeout y Cancelación
==============================================

Este módulo implementa 3 estrategias avanzadas de control de flujo asíncrono:
1. Timeout individual por petición (configurable)
2. Cancelación en cadena de tareas
3. Carga con prioridad (procesar conforme llegan)

Autor: Semana 3 - Reto IA #4
"""

import asyncio
import aiohttp
import time
from typing import List, Dict, Any, Optional
import sys
import os

# Import async client
sys.path.insert(0, os.path.dirname(__file__))

BASE_URL = "http://127.0.0.1:4010"


# ============================================================================
# STRATEGY 1: Individual Timeout Wrapper
# ============================================================================

async def con_timeout_individual(coro, timeout_segundos: float, nombre: str = "petición"):
    """
    Wraps any async function with an individual timeout using asyncio.wait_for().
    
    If this specific request exceeds its timeout, it raises TimeoutError,
    but OTHER requests in a gather() continue normally.
    
    Args:
        coro: Coroutine to execute
        timeout_segundos: Timeout in seconds for THIS specific request
        nombre: Name for logging purposes
    
    Returns:
        Result of the coroutine
    
    Raises:
        asyncio.TimeoutError: If the request exceeds its timeout
    
    Example:
        # productos has 5s, categorias has 3s, perfil has 2s
        resultados = await asyncio.gather(
            con_timeout_individual(obtener_productos(session), 5.0, "productos"),
            con_timeout_individual(obtener_categorias(session), 3.0, "categorias"),
            con_timeout_individual(obtener_perfil(session), 2.0, "perfil"),
            return_exceptions=True
        )
    """
    try:
        print(f"⏱️  [{nombre}] Starting with timeout={timeout_segundos}s")
        resultado = await asyncio.wait_for(coro, timeout=timeout_segundos)
        print(f"✅ [{nombre}] Completed successfully")
        return resultado
    except asyncio.TimeoutError:
        print(f"⏰ [{nombre}] TIMEOUT after {timeout_segundos}s")
        raise asyncio.TimeoutError(f"{nombre} excedió {timeout_segundos}s")


async def cargar_dashboard_con_timeouts_individuales():
    """
    Demonstrates individual timeouts: each request has its OWN limit.
    
    If one request is slow and times out, the others complete normally.
    This is different from a global timeout that would cancel ALL requests.
    """
    print("\n" + "="*60)
    print("STRATEGY 1: Individual Timeouts per Request")
    print("="*60 + "\n")
    
    async with aiohttp.ClientSession() as session:
        # Simulate slow endpoint by adding delay BEFORE the request
        async def peticion_lenta(delay_ms):
            """Simulates a slow request"""
            await asyncio.sleep(delay_ms / 1000)
            async with session.get(f"{BASE_URL}/productos") as resp:
                return await resp.json()
        
        async def peticion_rapida():
            """Simulates a fast request"""
            async with session.get(f"{BASE_URL}/productos") as resp:
                return await resp.json()
        
        print("Launching 3 requests with different timeouts:")
        print("  - productos: 5s timeout, takes ~0.2s → should SUCCEED")
        print("  - categorias: 3s timeout, takes ~0.1s → should SUCCEED")
        print("  - perfil: 2s timeout, takes ~8s → should TIMEOUT")
        print()
        
        inicio = time.time()
        
        # Launch with individual timeouts
        resultados = await asyncio.gather(
            con_timeout_individual(peticion_rapida(), 5.0, "productos"),
            con_timeout_individual(peticion_rapida(), 3.0, "categorias"),
            con_timeout_individual(peticion_lenta(8000), 2.0, "perfil"),  # This one times out
            return_exceptions=True  # CRITICAL: don't stop if one fails
        )
        
        tiempo_total = (time.time() - inicio) * 1000
        
        # Process results
        print(f"\n⏱️  Total time: {tiempo_total:.0f}ms")
        print(f"📊 Results:")
        
        labels = ["productos", "categorias", "perfil"]
        for label, resultado in zip(labels, resultados):
            if isinstance(resultado, asyncio.TimeoutError):
                print(f"   ❌ {label}: TIMEOUT (as expected)")
            elif isinstance(resultado, Exception):
                print(f"   ❌ {label}: Error - {resultado}")
            else:
                print(f"   ✅ {label}: OK")
        
        print(f"\n💡 Notice: Even though 'perfil' timed out, the other 2 completed successfully!")
        print(f"   With a GLOBAL timeout, we would have lost all 3.\n")
        
        return resultados


# ============================================================================
# STRATEGY 2: Chain Cancellation
# ============================================================================

async def cancel_remaining(tareas: List[asyncio.Task], motivo: str = ""):
    """
    Cancels all pending tasks in a list.
    
    Scenario: If perfil returns 401 (Unauthorized), there's no point
    continuing to load other data - cancel everything.
    
    Args:
        tareas: List of asyncio.Task objects to cancel
        motivo: Reason for cancellation (for logging)
    """
    print(f"\n🚫 Cancelling {len(tareas)} remaining tasks. Reason: {motivo}")
    
    for tarea in tareas:
        if not tarea.done():
            tarea.cancel()
            print(f"   ⏹️  Cancelled task: {tarea.get_name()}")
    
    # Wait for all cancellations to complete
    if tareas:
        await asyncio.gather(*tareas, return_exceptions=True)
        print(f"✅ All tasks cancelled\n")


async def cargar_con_cancelacion_en_cadena():
    """
    Demonstrates chain cancellation: if a CRITICAL request fails with 401,
    cancel all other requests (no point loading data without auth).
    """
    print("\n" + "="*60)
    print("STRATEGY 2: Chain Cancellation (Fail-Fast on Auth Error)")
    print("="*60 + "\n")
    
    async with aiohttp.ClientSession() as session:
        # Simulate auth failure (401)
        async def peticion_con_401():
            """Simulates unauthorized request"""
            await asyncio.sleep(0.1)
            # Simulate 401 error
            raise aiohttp.ClientResponseError(
                request_info=None,
                history=None,
                status=401,
                message="Unauthorized"
            )
        
        async def peticion_normal():
            """Normal request that would succeed"""
            await asyncio.sleep(2)  # Takes 2 seconds
            async with session.get(f"{BASE_URL}/productos") as resp:
                return await resp.json()
        
        print("Scenario: perfil returns 401 (Unauthorized)")
        print("Expected behavior: Cancel productos and categorias (no point without auth)")
        print()
        
        # Create tasks explicitly so we can cancel them
        tarea_productos = asyncio.create_task(peticion_normal(), name="productos")
        tarea_categorias = asyncio.create_task(peticion_normal(), name="categorias")
        tarea_perfil = asyncio.create_task(peticion_con_401(), name="perfil")
        
        tareas = [tarea_productos, tarea_categorias, tarea_perfil]
        
        # Wait for first completion (or first exception)
        completadas, pendientes = await asyncio.wait(
            tareas,
            return_when=asyncio.FIRST_EXCEPTION
        )
        
        # Check if any task failed with 401
        for tarea in completadas:
            try:
                resultado = await tarea
            except aiohttp.ClientResponseError as e:
                if e.status == 401:
                    print(f"❌ {tarea.get_name()} returned 401 UNAUTHORIZED")
                    print(f"🚨 Authentication required - cancelling all other tasks\n")
                    
                    # Cancel remaining tasks
                    await cancel_remaining(list(pendientes), "Authentication failed (401)")
                    
                    return {"error": "Authentication required"}
            except Exception as e:
                print(f"❌ {tarea.get_name()} failed: {e}")
        
        print("✅ All tasks completed or cancelled\n")


# ============================================================================
# STRATEGY 3: Priority Loading (Process as They Arrive)
# ============================================================================

async def cargar_con_prioridad():
    """
    Loads dashboard with priority: shows partial UI as soon as critical
    data (productos, perfil) arrives, without waiting for secondary data.
    
    Uses asyncio.wait() with FIRST_COMPLETED to process results as they arrive.
    """
    print("\n" + "="*60)
    print("STRATEGY 3: Priority Loading (Progressive UI)")
    print("="*60 + "\n")
    
    async with aiohttp.ClientSession() as session:
        # Simulate different latencies
        async def peticion_con_latencia(endpoint: str, latencia_ms: int):
            """Simulates request with specific latency"""
            await asyncio.sleep(latencia_ms / 1000)
            async with session.get(f"{BASE_URL}/productos") as resp:
                return {"endpoint": endpoint, "data": await resp.json()}
        
        print("Launching 4 requests with different priorities:")
        print("  - productos (CRITICAL): 200ms")
        print("  - perfil (CRITICAL): 500ms")
        print("  - categorias (SECONDARY): 100ms")
        print("  - notificaciones (SECONDARY): 300ms")
        print()
        print("Strategy: Show partial dashboard when BOTH critical complete")
        print()
        
        # Create tasks
        tareas_criticas = {
            asyncio.create_task(peticion_con_latencia("productos", 200), name="productos"),
            asyncio.create_task(peticion_con_latencia("perfil", 500), name="perfil"),
        }
        
        tareas_secundarias = {
            asyncio.create_task(peticion_con_latencia("categorias", 100), name="categorias"),
            asyncio.create_task(peticion_con_latencia("notificaciones", 300), name="notificaciones"),
        }
        
        todas_las_tareas = tareas_criticas | tareas_secundarias
        
        # Track what we've loaded
        datos_criticos = {}
        datos_secundarios = {}
        dashboard_mostrado = False
        
        inicio = time.time()
        
        # Process results as they arrive
        while todas_las_tareas:
            completadas, pendientes = await asyncio.wait(
                todas_las_tareas,
                return_when=asyncio.FIRST_COMPLETED
            )
            
            for tarea in completadas:
                tiempo_actual = (time.time() - inicio) * 1000
                nombre = tarea.get_name()
                
                try:
                    resultado = await tarea
                    
                    # Classify as critical or secondary
                    if tarea in tareas_criticas:
                        datos_criticos[nombre] = resultado
                        print(f"✅ T={tiempo_actual:.0f}ms: {nombre} (CRITICAL) loaded")
                    else:
                        datos_secundarios[nombre] = resultado
                        print(f"✅ T={tiempo_actual:.0f}ms: {nombre} (SECONDARY) loaded")
                    
                    # Check if we can show partial dashboard
                    if not dashboard_mostrado and len(datos_criticos) == 2:
                        print(f"\n🎉 T={tiempo_actual:.0f}ms: SHOWING PARTIAL DASHBOARD")
                        print(f"   Critical data complete! Secondary data will load in background.\n")
                        dashboard_mostrado = True
                
                except Exception as e:
                    print(f"❌ T={tiempo_actual:.0f}ms: {nombre} failed - {e}")
            
            todas_las_tareas = pendientes
        
        tiempo_total = (time.time() - inicio) * 1000
        
        print(f"⏱️  Total time: {tiempo_total:.0f}ms")
        print(f"📊 Loaded: {len(datos_criticos)} critical + {len(datos_secundarios)} secondary")
        print(f"\n💡 User saw dashboard much earlier than if we waited for ALL data!\n")
        
        return {
            "criticos": datos_criticos,
            "secundarios": datos_secundarios
        }


# ============================================================================
# TEMPORAL DIAGRAM
# ============================================================================

def mostrar_diagramas_temporales():
    """Shows temporal diagrams explaining each strategy."""
    print("\n" + "="*70)
    print("TEMPORAL DIAGRAMS: How Each Strategy Works")
    print("="*70 + "\n")
    
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║ STRATEGY 1: Individual Timeouts                                     ║
╚══════════════════════════════════════════════════════════════════════╝

Time (ms) →
0ms         1000ms      2000ms      3000ms      4000ms
│           │           │           │           │
├───────────┼───────────┼───────────┼───────────┼──────►

productos (timeout=5s, latency=200ms)
├─────────►│ ✅ DONE
│           │

categorias (timeout=3s, latency=100ms)
├────►│     │ ✅ DONE
│           │

perfil (timeout=2s, latency=8000ms)
├───────────────────────┼───────────┼───────────┤ ⏰ TIMEOUT at 2000ms
│                       │           │           │
│                       CANCELLED   │           │
│                                   │           │
Result: productos ✅, categorias ✅, perfil ❌ (but others succeeded!)
""")
    
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║ STRATEGY 2: Chain Cancellation                                      ║
╚══════════════════════════════════════════════════════════════════════╝

Time (ms) →
0ms         100ms       200ms       300ms
│           │           │           │
├───────────┼───────────┼───────────┼──────►

perfil (checks auth)
├──────────►│ ❌ 401 UNAUTHORIZED!
│           │
│           🚨 ABORT! Cancel everything
│           │
productos (loading...)
├───────────┼───────────🚫 CANCELLED
│           │
categorias (loading...)
├───────────┼───────────🚫 CANCELLED
│           │

Result: All cancelled - no point loading data without auth
""")
    
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║ STRATEGY 3: Priority Loading                                        ║
╚══════════════════════════════════════════════════════════════════════╝

Time (ms) →
0ms         100ms       200ms       300ms       500ms
│           │           │           │           │
├───────────┼───────────┼───────────┼───────────┼──────►

categorias (SECONDARY, 100ms)
├──────────►│ ✅ Load in background
│           │
productos (CRITICAL, 200ms)
├───────────────────────►│ ✅ Critical 1/2
│           │           │
notificaciones (SECONDARY, 300ms)
├───────────────────────────────────►│ ✅ Load in background
│           │           │           │
perfil (CRITICAL, 500ms)
├───────────────────────────────────────────────►│ ✅ Critical 2/2
│           │           │           │           │
│           │           │           │           🎉 SHOW DASHBOARD!
│           │           │           │
All critical data ready at 500ms! User sees UI immediately.
Secondary data appears as it arrives (100ms, 300ms).
""")


# ============================================================================
# MAIN - DEMONSTRATION
# ============================================================================

async def main():
    """Demonstrates all 3 timeout and cancellation strategies."""
    print("""
    ╔══════════════════════════════════════════════════════════════════════╗
    ║         Coordinador Asíncrono - Timeout y Cancelación               ║
    ║                    3 Advanced Strategies                             ║
    ╚══════════════════════════════════════════════════════════════════════╝
    """)
    
    # Strategy 1: Individual timeouts
    await cargar_dashboard_con_timeouts_individuales()
    
    # Strategy 2: Chain cancellation
    await cargar_con_cancelacion_en_cadena()
    
    # Strategy 3: Priority loading
    await cargar_con_prioridad()
    
    # Show temporal diagrams
    mostrar_diagramas_temporales()
    
    print("\n✅ All strategies demonstrated!\n")


if __name__ == "__main__":
    asyncio.run(main())
