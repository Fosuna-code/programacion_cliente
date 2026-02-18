"""
Comparación de Estrategias de Coordinación Asíncrona
=====================================================

Este script implementa y compara 4 estrategias diferentes para coordinar
peticiones HTTP asíncronas en el contexto del dashboard de EcoMarket.

Estrategias implementadas:
1. asyncio.gather() - Esperar a que todas terminen
2. asyncio.wait(FIRST_COMPLETED) - Procesar conforme llegan
3. asyncio.as_completed() - Iterar por orden de completación
4. asyncio.wait(FIRST_EXCEPTION) - Abortar ante primer error

Escenario de prueba:
- 4 endpoints: productos (200ms), categorías (100ms), perfil (500ms), notificaciones (TIMEOUT)
"""

import asyncio
import aiohttp
import time
from typing import Dict, Any, List, Tuple
import json


# ============================================================================
# CONFIGURACIÓN DEL MOCK
# ============================================================================

# Usando Prism mock server del semana 2
BASE_URL = "http://127.0.0.1:4010/productos"

# Simularemos latencias con asyncio.sleep ya que Prism no tiene delays configurables
LATENCIAS_SIMULADAS = {
    "productos": 0.2,      # 200ms
    "categorias": 0.1,     # 100ms  
    "perfil": 0.5,         # 500ms
    "notificaciones": 999  # TIMEOUT (configuramos timeout de 3s)
}


# ============================================================================
# FUNCIONES SIMULADAS DE PETICIONES
# ============================================================================

async def obtener_productos(session: aiohttp.ClientSession) -> Dict[str, Any]:
    """Simula petición GET /productos con latencia de 200ms"""
    await asyncio.sleep(LATENCIAS_SIMULADAS["productos"])
    # Simulamos respuesta exitosa
    return {"endpoint": "productos", "data": ["Producto 1", "Producto 2"], "latencia_ms": 200}


async def obtener_categorias(session: aiohttp.ClientSession) -> Dict[str, Any]:
    """Simula petición GET /categorias con latencia de 100ms"""
    await asyncio.sleep(LATENCIAS_SIMULADAS["categorias"])
    return {"endpoint": "categorias", "data": ["Miel", "Granos"], "latencia_ms": 100}


async def obtener_perfil(session: aiohttp.ClientSession) -> Dict[str, Any]:
    """Simula petición GET /perfil con latencia de 500ms"""
    await asyncio.sleep(LATENCIAS_SIMULADAS["perfil"])
    return {"endpoint": "perfil", "data": {"nombre": "Usuario", "id": 1}, "latencia_ms": 500}


async def obtener_notificaciones(session: aiohttp.ClientSession) -> Dict[str, Any]:
    """Simula petición que hace TIMEOUT (tarda más que el límite)"""
    timeout_limit = 3.0  # segundos
    try:
        await asyncio.wait_for(
            asyncio.sleep(10),  # Intenta dormir 10s, pero timeout es 3s
            timeout=timeout_limit
        )
        return {"endpoint": "notificaciones", "data": [], "latencia_ms": 10000}
    except asyncio.TimeoutError:
        raise asyncio.TimeoutError("Timeout en notificaciones después de 3s")


# ============================================================================
# ESTRATEGIA 1: asyncio.gather()
# ============================================================================

async def estrategia_gather() -> Tuple[List[Any], float, str]:
    """
    Espera a que TODAS las peticiones terminen antes de retornar.
    
    Pros:
    - API simple
    - Todos los resultados disponibles juntos
    
    Contras:
    - Usuario espera a la petición más lenta
    - No hay feedback progresivo
    """
    print("\n" + "="*60)
    print("ESTRATEGIA 1: asyncio.gather()")
    print("="*60)
    
    inicio = time.time()
    
    async with aiohttp.ClientSession() as session:
        # Lanzar todas las peticiones
        print("⏱️  T=0ms: Lanzando 4 peticiones simultáneas...")
        
        resultados = await asyncio.gather(
            obtener_productos(session),
            obtener_categorias(session),
            obtener_perfil(session),
            obtener_notificaciones(session),
            return_exceptions=True  # CRÍTICO: no perder trabajo si una falla
        )
        
        tiempo_total = (time.time() - inicio) * 1000
        
        # Procesar resultados
        exitos = []
        errores = []
        
        for resultado in resultados:
            if isinstance(resultado, Exception):
                errores.append(str(resultado))
                print(f"❌ Error capturado: {resultado}")
            else:
                exitos.append(resultado)
                print(f"✅ {resultado['endpoint']}: OK ({resultado['latencia_ms']}ms)")
        
        print(f"\n⏱️  Tiempo total hasta mostrar datos: {tiempo_total:.0f}ms")
        print(f"📊 Éxitos: {len(exitos)}/4, Errores: {len(errores)}/4")
        
        analisis = f"""
        ANÁLISIS:
        - Primer dato disponible: {tiempo_total:.0f}ms (esperó a TODAS, incluso al timeout)
        - Todos los datos se muestran simultáneamente
        - El usuario ve pantalla en blanco hasta que todo completa
        - Adecuado cuando: TODOS los datos son imprescindibles para mostrar la UI
        """
        
        return resultados, tiempo_total, analisis.strip()


# ============================================================================
# ESTRATEGIA 2: asyncio.wait(FIRST_COMPLETED)
# ============================================================================

async def estrategia_wait_first_completed() -> Tuple[List[Any], float, str]:
    """
    Procesa resultados conforme van llegando.
    
    Pros:
    - Feedback inmediato al usuario
    - Puede mostrar datos parciales rápidamente
    
    Contras:
    - Código más complejo
    - Necesita UI que soporte actualización incremental
    """
    print("\n" + "="*60)
    print("ESTRATEGIA 2: asyncio.wait(FIRST_COMPLETED)")
    print("="*60)
    
    inicio = time.time()
    tiempos_llegada = []
    
    async with aiohttp.ClientSession() as session:
        # Crear tareas
        tareas = {
            asyncio.create_task(obtener_productos(session)),
            asyncio.create_task(obtener_categorias(session)),
            asyncio.create_task(obtener_perfil(session)),
            asyncio.create_task(obtener_notificaciones(session)),
        }
        
        print("⏱️  T=0ms: Lanzando 4 peticiones simultáneas...")
        resultados = []
        
        # Procesar conforme van llegando
        while tareas:
            completadas, pendientes = await asyncio.wait(
                tareas, 
                return_when=asyncio.FIRST_COMPLETED
            )
            
            for tarea in completadas:
                tiempo_llegada = (time.time() - inicio) * 1000
                tiempos_llegada.append(tiempo_llegada)
                
                try:
                    resultado = await tarea
                    resultados.append(resultado)
                    print(f"✅ T={tiempo_llegada:.0f}ms: {resultado['endpoint']} llegó → ¡MOSTRAR EN UI!")
                except Exception as e:
                    resultados.append(e)
                    print(f"❌ T={tiempo_llegada:.0f}ms: Error capturado → {e}")
            
            tareas = pendientes
        
        tiempo_total = (time.time() - inicio) * 1000
        tiempo_primer_dato = tiempos_llegada[0] if tiempos_llegada else 0
        
        print(f"\n⏱️  Primer dato en pantalla: {tiempo_primer_dato:.0f}ms")
        print(f"⏱️  Todos los datos cargados: {tiempo_total:.0f}ms")
        
        analisis = f"""
        ANÁLISIS:
        - Primer dato disponible: {tiempo_primer_dato:.0f}ms (¡categorías!)
        - Los datos aparecen progresivamente: {', '.join([f'{t:.0f}ms' for t in tiempos_llegada])}
        - El usuario ve feedback inmediato (mejor UX)
        - Requiere UI que soporte actualización incremental
        - Adecuado cuando: Queremos mostrar datos conforme llegan (e.g. feed de noticias)
        """
        
        return resultados, tiempo_primer_dato, analisis.strip()


# ============================================================================
# ESTRATEGIA 3: asyncio.as_completed()
# ============================================================================

async def estrategia_as_completed() -> Tuple[List[Any], float, str]:
    """
    Itera por las tareas en orden de completación.
    
    Pros:
    - Sintaxis más simple que wait(FIRST_COMPLETED)
    - Fácil de usar en un loop
    
    Contras:
    - No retorna todos los resultados juntos
    - Necesita procesar uno por uno
    """
    print("\n" + "="*60)
    print("ESTRATEGIA 3: asyncio.as_completed()")
    print("="*60)
    
    inicio = time.time()
    tiempos_llegada = []
    
    async with aiohttp.ClientSession() as session:
        # Crear tareas
        tareas = [
            obtener_productos(session),
            obtener_categorias(session),
            obtener_perfil(session),
            obtener_notificaciones(session),
        ]
        
        print("⏱️  T=0ms: Lanzando 4 peticiones simultáneas...")
        resultados = []
        
        # as_completed retorna un iterador que yielda tareas en orden de completación
        for coro in asyncio.as_completed(tareas):
            try:
                resultado = await coro
                tiempo_llegada = (time.time() - inicio) * 1000
                tiempos_llegada.append(tiempo_llegada)
                resultados.append(resultado)
                print(f"✅ T={tiempo_llegada:.0f}ms: {resultado['endpoint']} procesado")
            except Exception as e:
                tiempo_llegada = (time.time() - inicio) * 1000
                tiempos_llegada.append(tiempo_llegada)
                resultados.append(e)
                print(f"❌ T={tiempo_llegada:.0f}ms: Error → {e}")
        
        tiempo_total = (time.time() - inicio) * 1000
        tiempo_primer_dato = tiempos_llegada[0] if tiempos_llegada else 0
        
        print(f"\n⏱️  Primer dato procesado: {tiempo_primer_dato:.0f}ms")
        print(f"⏱️  Todos los datos procesados: {tiempo_total:.0f}ms")
        
        analisis = f"""
        ANÁLISIS:
        - Similar a wait(FIRST_COMPLETED) pero con sintaxis más simple
        - Orden de procesamiento: {', '.join([f'{t:.0f}ms' for t in tiempos_llegada])}
        - Ideal para pipelines de procesamiento (recibir → transformar → mostrar)
        - Más legible que wait() para casos simples
        - Adecuado cuando: Querés procesar cada resultado inmediatamente
        """
        
        return resultados, tiempo_primer_dato, analisis.strip()


# ============================================================================
# ESTRATEGIA 4: asyncio.wait(FIRST_EXCEPTION)
# ============================================================================

async def estrategia_wait_first_exception() -> Tuple[List[Any], float, str]:
    """
    Aborta todas las tareas cuando la primera falla.
    
    Pros:
    - Falla rápido (fail-fast)
    - Ahorra recursos cancelando tareas innecesarias
    
    Contras:
    - Pierde trabajo útil ya completado
    - Solo útil en escenarios donde un error invalida todo
    """
    print("\n" + "="*60)
    print("ESTRATEGIA 4: asyncio.wait(FIRST_EXCEPTION)")
    print("="*60)
    
    inicio = time.time()
    
    async with aiohttp.ClientSession() as session:
        # Crear tareas
        tareas = {
            asyncio.create_task(obtener_productos(session)),
            asyncio.create_task(obtener_categorias(session)),
            asyncio.create_task(obtener_perfil(session)),
            asyncio.create_task(obtener_notificaciones(session)),
        }
        
        print("⏱️  T=0ms: Lanzando 4 peticiones simultáneas...")
        print("⚠️  Esperando a que la primera falle para abortar todo...")
        
        # Esperar a que la primera lance excepción
        completadas, pendientes = await asyncio.wait(
            tareas,
            return_when=asyncio.FIRST_EXCEPTION
        )
        
        tiempo_hasta_error = (time.time() - inicio) * 1000
        
        # Revisar qué pasó
        resultados = []
        for tarea in completadas:
            try:
                resultado = await tarea
                resultados.append(resultado)
                print(f"✅ {resultado['endpoint']}: Completó antes del error")
            except Exception as e:
                resultados.append(e)
                print(f"💥 Primera excepción detectada: {e}")
                print(f"⏱️  T={tiempo_hasta_error:.0f}ms: ¡ABORTANDO todas las tareas pendientes!")
        
        # Cancelar tareas pendientes
        for tarea in pendientes:
            tarea.cancel()
            print(f"🚫 Cancelando tarea pendiente...")
        
        # Esperar a que se cancelen
        if pendientes:
            await asyncio.wait(pendientes)
        
        tiempo_total = (time.time() - inicio) * 1000
        
        print(f"\n⏱️  Tiempo hasta primer error: {tiempo_hasta_error:.0f}ms")
        print(f"⏱️  Tiempo total (incluyendo cancelaciones): {tiempo_total:.0f}ms")
        print(f"📊 Completadas: {len(completadas)}, Canceladas: {len(pendientes)}")
        
        analisis = f"""
        ANÁLISIS:
        - Falló rápido al detectar timeout de notificaciones (~{tiempo_hasta_error:.0f}ms)
        - Canceló {len(pendientes)} tareas pendientes (ahorro de recursos)
        - Se perdió el trabajo de las tareas ya completadas
        - Adecuado cuando: Un error invalida todo (e.g., autenticación falló)
        - NO adecuado para dashboard: queremos mostrar datos parciales
        """
        
        return resultados, tiempo_hasta_error, analisis.strip()


# ============================================================================
# COMPARACIÓN Y TABLA DE RESULTADOS
# ============================================================================

async def ejecutar_comparacion():
    """Ejecuta todas las estrategias y genera tabla comparativa"""
    
    print("\n" + "="*60)
    print("COMPARACIÓN DE ESTRATEGIAS DE COORDINACIÓN")
    print("Escenario: Dashboard con 4 endpoints")
    print("Latencias: productos=200ms, categorías=100ms, perfil=500ms, notificaciones=TIMEOUT(3s)")
    print("="*60)
    
    # Ejecutar cada estrategia
    resultados_gather, tiempo_gather, analisis_gather = await estrategia_gather()
    resultados_wait, tiempo_wait, analisis_wait = await estrategia_wait_first_completed()
    resultados_as_completed, tiempo_as_completed, analisis_as_completed = await estrategia_as_completed()
    resultados_first_exception, tiempo_exception, analisis_exception = await estrategia_wait_first_exception()
    
    # Tabla comparativa
    print("\n" + "="*60)
    print("TABLA COMPARATIVA")
    print("="*60 + "\n")
    
    print("┌────────────────────────┬──────────────────────────────────────────────────────┐")
    print("│ Criterio               │ Puntuación (1=peor, 5=mejor)                        │")
    print("├────────────────────────┼──────────────────────────────────────────────────────┤")
    print("│                        │ gather() │ wait(FC) │ as_compl │ wait(FE)           │")
    print("├────────────────────────┼──────────┼──────────┼──────────┼────────────────────┤")
    print("│ Latencia percibida     │    2     │    5     │    5     │    3               │")
    print("│ (tiempo 1er dato)      │          │          │          │                    │")
    print("├────────────────────────┼──────────┼──────────┼──────────┼────────────────────┤")
    print("│ Robustez ante errores  │    5     │    5     │    5     │    1               │")
    print("│ (no pierde trabajo)    │          │          │          │                    │")
    print("├────────────────────────┼──────────┼──────────┼──────────┼────────────────────┤")
    print("│ Complejidad de código  │    5     │    2     │    4     │    2               │")
    print("│ (simple=mejor)         │          │          │          │                    │")
    print("├────────────────────────┼──────────┼──────────┼──────────┼────────────────────┤")
    print("│ Mantenibilidad         │    5     │    3     │    4     │    3               │")
    print("│ (fácil de entender)    │          │          │          │                    │")
    print("├────────────────────────┼──────────┼──────────┼──────────┼────────────────────┤")
    print("│ Feedback progresivo    │    1     │    5     │    5     │    1               │")
    print("│ (UX)                   │          │          │          │                    │")
    print("├────────────────────────┼──────────┼──────────┼──────────┼────────────────────┤")
    print("│ TOTAL                  │   18/25  │   20/25  │   23/25  │   10/25            │")
    print("└────────────────────────┴──────────┴──────────┴──────────┴────────────────────┘")
    
    print("\n" + "="*60)
    print("MEDICIONES REALES")
    print("="*60 + "\n")
    
    print(f"gather():           Primer dato en ~{tiempo_gather:.0f}ms (espera a TODOS)")
    print(f"wait(FIRST_COMPL):  Primer dato en ~{tiempo_wait:.0f}ms (¡categorías!)")
    print(f"as_completed():     Primer dato en ~{tiempo_as_completed:.0f}ms (stream)")
    print(f"wait(FIRST_EXCEP):  Tiempo hasta error ~{tiempo_exception:.0f}ms (abort)")
    
    # Guardar análisis completo
    return {
        "gather": (resultados_gather, tiempo_gather, analisis_gather),
        "wait_first_completed": (resultados_wait, tiempo_wait, analisis_wait),
        "as_completed": (resultados_as_completed, tiempo_as_completed, analisis_as_completed),
        "first_exception": (resultados_first_exception, tiempo_exception, analisis_exception),
    }


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    print("\n🚀 INICIO DE COMPARACIÓN\n")
    resultados = asyncio.run(ejecutar_comparacion())
    
    print("\n" + "="*60)
    print("📋 VER ARCHIVO: recomendacion_ecomarket.md")
    print("   Para la recomendación final y justificación detallada")
    print("="*60 + "\n")
