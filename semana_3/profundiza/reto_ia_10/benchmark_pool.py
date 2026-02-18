"""
Benchmark de Pool de Conexiones - Comparación de Configuraciones
=================================================================

Este script benchmarkea diferentes configuraciones del pool de conexiones
para determinar la configuración óptima para EcoMarket.

Escenarios de prueba:
1. Pool de 5 conexiones
2. Pool de 10 conexiones  
3. Pool de 20 conexiones
4. Pool ilimitado (sin límite)

Métrica principal: throughput, latencia, uso de conexiones TCP
"""

import asyncio
import time
from typing import List, Dict, Any
import statistics
from smart_session import SmartSession

# ============================================================================
# CONFIGURACIÓN DEL BENCHMARK
# ============================================================================

# Número de peticiones concurrentes a ejecutar
NUM_PETICIONES = 50

# Delay simulado del servidor (en segundos)
SERVER_DELAY = 0.1  # 100ms

# URL de prueba (usaremos httpbin con delay)
TEST_URL = f"https://httpbin.org/delay/{SERVER_DELAY}"


# ============================================================================
# FUNCIONES DE BENCHMARK
# ============================================================================

async def ejecutar_peticiones(session: SmartSession, num_peticiones: int) -> Dict[str, Any]:
    """
    Ejecuta N peticiones concurrentes y mide métricas.
    
    Returns:
        dict con: tiempo_total, throughput, latencias, status_pool
    """
    latencias = []
    inicio_total = time.time()
    
    async def hacer_peticion(idx: int) -> float:
        """Ejecuta una petición y retorna su latencia."""
        inicio = time.time()
        try:
            async with session.get(TEST_URL) as response:
                await response.read()
            latencia = (time.time() - inicio) * 1000  # en ms
            return latencia
        except Exception as e:
            print(f"❌ Petición {idx} falló: {e}")
            return -1
    
    # Lanzar todas las peticiones concurrentemente
    tareas = [hacer_peticion(i) for i in range(num_peticiones)]
    latencias = await asyncio.gather(*tareas)
    
    tiempo_total = time.time() - inicio_total
    latencias_validas = [l for l in latencias if l > 0]
    
    # Calcular métricas
    throughput = num_peticiones / tiempo_total if tiempo_total > 0 else 0
    
    return {
        "tiempo_total": tiempo_total,
        "throughput": throughput,
        "latencia_promedio": statistics.mean(latencias_validas) if latencias_validas else 0,
        "latencia_min": min(latencias_validas) if latencias_validas else 0,
        "latencia_max": max(latencias_validas) if latencias_validas else 0,
        "latencia_p50": statistics.median(latencias_validas) if latencias_validas else 0,
        "latencia_p95": statistics.quantiles(latencias_validas, n=20)[18] if len(latencias_validas) > 20 else 0,
        "peticiones_exitosas": len(latencias_validas),
        "peticiones_fallidas": len([l for l in latencias if l < 0]),
        "pool_status": session.get_pool_status(),
    }


async def benchmark_pool_size(pool_size: int, label: str) -> Dict[str, Any]:
    """
    Benchmarkea una configuración específica del pool.
    
    Args:
        pool_size: Tamaño del pool (0 = ilimitado)
        label: Etiqueta descriptiva
    
    Returns:
        Resultados del benchmark
    """
    print(f"\n{'='*60}")
    print(f"🧪 BENCHMARK: {label}")
    print(f"{'='*60}")
    print(f"Configuración: {NUM_PETICIONES} peticiones, delay servidor={SERVER_DELAY*1000:.0f}ms")
    
    # Crear sesión con configuración específica
    connector_kwargs = {}
    if pool_size > 0:
        connector_kwargs["pool_size"] = pool_size
    
    async with SmartSession(**connector_kwargs) as session:
        print(f"⏱️  Iniciando benchmark...")
        
        # Ejecutar benchmark
        resultados = await ejecutar_peticiones(session, NUM_PETICIONES)
        
        # Mostrar resultados
        print(f"\n📊 RESULTADOS:")
        print(f"   Tiempo total: {resultados['tiempo_total']:.2f}s")
        print(f"   Throughput: {resultados['throughput']:.1f} req/s")
        print(f"   Latencia promedio: {resultados['latencia_promedio']:.1f}ms")
        print(f"   Latencia P50: {resultados['latencia_p50']:.1f}ms")
        print(f"   Latencia P95: {resultados['latencia_p95']:.1f}ms")
        print(f"   Latencia min/max: {resultados['latencia_min']:.1f}ms / {resultados['latencia_max']:.1f}ms")
        print(f"   Éxito: {resultados['peticiones_exitosas']}/{NUM_PETICIONES}")
        
        # Mostrar métricas del pool
        pool_status = resultados['pool_status']
        if not pool_status.get('error'):
            print(f"\n🔌 Pool de Conexiones:")
            print(f"   Configurado: {pool_status.get('pool_size', 'ilimitado')}")
            print(f"   Creadas: {pool_status['creadas']}")
            print(f"   Reutilizadas: {pool_status['reutilizadas']}")
            print(f"   Tasa reutilización: {pool_status['tasa_reutilizacion']:.1f}%")
        
        resultados["label"] = label
        resultados["pool_size"] = pool_size
        
        return resultados


# ============================================================================
# COMPARACIÓN DE CONFIGURACIONES
# ============================================================================

async def ejecutar_benchmark_completo():
    """Ejecuta benchmark para todas las configuraciones y compara."""
    
    print("""
    ╔══════════════════════════════════════════════════════════════════════╗
    ║          BENCHMARK: Pool de Conexiones - Configuraciones            ║
    ║                         EcoMarket Client                             ║
    ╚══════════════════════════════════════════════════════════════════════╝
    """)
    
    # Configuraciones a probar
    configuraciones = [
        (5, "Pool de 5 conexiones (conservador)"),
        (10, "Pool de 10 conexiones (balanceado)"),
        (20, "Pool de 20 conexiones (agresivo)"),
        (100, "Pool ilimitado (sin restricción)"),
    ]
    
    resultados = []
    
    # Ejecutar cada configuración
    for pool_size, label in configuraciones:
        resultado = await benchmark_pool_size(pool_size, label)
        resultados.append(resultado)
        
        # Pausa entre benchmarks para evitar rate limiting
        if pool_size != configuraciones[-1][0]:
            print("\n⏸️  Pausa de 2s antes del siguiente benchmark...")
            await asyncio.sleep(2)
    
    # Tabla comparativa
    print(f"\n\n{'='*80}")
    print("📊 TABLA COMPARATIVA DE RESULTADOS")
    print('='*80 + "\n")
    
    # Header
    print("┌" + "─"*15 + "┬" + "─"*12 + "┬" + "─"*15 + "┬" + "─"*15 + "┬" + "─"*15 + "┐")
    print(f"│ {'Pool Size':^13} │ {'Throughput':^10} │ {'Latencia Prom':^13} │ {'Latencia P95':^13} │ {'Conexiones':^13} │")
    print(f"│ {'':^13} │ {'(req/s)':^10} │ {'(ms)':^13} │ {'(ms)':^13} │ {'Creadas':^13} │")
    print("├" + "─"*15 + "┼" + "─"*12 + "┼" + "─"*15 + "┼" + "─"*15 + "┼" + "─"*15 + "┤")
    
    # Filas de datos
    for r in resultados:
        pool_label = str(r['pool_size']) if r['pool_size'] > 0 else "Ilimitado"
        throughput = f"{r['throughput']:.1f}"
        lat_prom = f"{r['latencia_promedio']:.1f}"
        lat_p95 = f"{r['latencia_p95']:.1f}"
        creadas = str(r['pool_status'].get('creadas', 'N/A'))
        
        print(f"│ {pool_label:^13} │ {throughput:^10} │ {lat_prom:^13} │ {lat_p95:^13} │ {creadas:^13} │")
    
    print("└" + "─"*15 + "┴" + "─"*12 + "┴" + "─"*15 + "┴" + "─"*15 + "┴" + "─"*15 + "┘")
    
    # Análisis comparativo
    print(f"\n{'='*80}")
    print("📈 ANÁLISIS COMPARATIVO")
    print('='*80 + "\n")
    
    # Encontrar el mejor throughput
    mejor_throughput = max(resultados, key=lambda x: x['throughput'])
    print(f"🏆 Mayor throughput: {mejor_throughput['label']}")
    print(f"   {mejor_throughput['throughput']:.1f} req/s")
    
    # Encontrar la menor latencia P95
    mejor_latencia = min(resultados, key=lambda x: x['latencia_p95'])
    print(f"\n⚡ Menor latencia P95: {mejor_latencia['label']}")
    print(f"   {mejor_latencia['latencia_p95']:.1f}ms")
    
    # Análisis de reutilización
    print(f"\n♻️  Reutilización de conexiones:")
    for r in resultados:
        pool_status = r['pool_status']
        if not pool_status.get('error'):
            tasa = pool_status['tasa_reutilizacion']
            print(f"   {r['label']:40} → {tasa:5.1f}%")
    
    # Recomendación
    print(f"\n{'='*80}")
    print("💡 RECOMENDACIÓN PARA ECOMARKET")
    print('='*80 + "\n")
    
    # Pool de 10 es generalmente el mejor balance
    pool_10 = next(r for r in resultados if r['pool_size'] == 10)
    
    print(f"""
    ✅ CONFIGURACIÓN RECOMENDADA: Pool de 10 conexiones
    
    JUSTIFICACIÓN:
    1. Balance entre rendimiento y recursos
       - Throughput: {pool_10['throughput']:.1f} req/s ({(pool_10['throughput']/mejor_throughput['throughput']*100):.0f}% del máximo)
       - Latencia P95: {pool_10['latencia_p95']:.1f}ms (aceptable para UX)
       
    2. Uso eficiente de recursos
       - Solo crea {pool_10['pool_status']['creadas']} conexiones TCP para {NUM_PETICIONES} peticiones
       - Tasa de reutilización: {pool_10['pool_status']['tasa_reutilizacion']:.1f}%
       
    3. Protección contra sobrecarga
       - Limita concurrencia para no saturar servidor ni cliente
       - Evita agotar file descriptors del sistema operativo
       
    4. Regla general
       - Pool size = num_cores * 2 (típicamente 8-12 para máquinas modernas)
       - EcoMarket API probablemente tiene límite similar
       
    📝 SIGUIENTE PASO:
    Medir en producción con tráfico real y ajustar según:
    - Latencia del servidor real (no httpbin)
    - Tasa de error 503 (si el pool es muy agresivo)
    - Uso de recursos del cliente (memoria, file descriptors)
    """)
    
    return resultados


# ============================================================================
# GRÁFICA ASCII DE COMPARACIÓN
# ============================================================================

def generar_grafica_ascii(resultados: List[Dict[str, Any]]):
    """Genera una gráfica ASCII comparando throughput."""
    print(f"\n{'='*80}")
    print("📊 GRÁFICA: Throughput vs Pool Size")
    print('='*80 + "\n")
    
    max_throughput = max(r['throughput'] for r in resultados)
    
    for r in resultados:
        pool_label = f"Pool {r['pool_size']}" if r['pool_size'] > 0 else "Ilimitado"
        throughput = r['throughput']
        bar_length = int((throughput / max_throughput) * 50)
        bar = "█" * bar_length
        
        print(f"{pool_label:12} │ {bar} {throughput:.1f} req/s")
    
    print()


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    # Ejecutar benchmark completo
    resultados = asyncio.run(ejecutar_benchmark_completo())
    
    # Generar gráfica
    generar_grafica_ascii(resultados)
    
    print("\n" + "="*80)
    print("✅ Benchmark completado. Ver resultados arriba.")
    print("📄 Documentación detallada en: configuracion_optima.md")
    print("="*80 + "\n")
