"""
Benchmarks para comparar el rendimiento de diferentes métodos de validación:
- Validación Manual
- Validación con Pydantic
- Validación con JSON Schema
"""

import time
import statistics
from typing import List, Dict, Any
from comparacion_validacion import (
    validar_manual,
    Producto,
    validar_schema
)


# Datos de prueba
datos_validos = {
    "id": 1,
    "nombre": "Manzanas Orgánicas",
    "precio": 25.50,
    "categoria": "frutas",
    "productor": {
        "id": 101,
        "nombre": "Granja El Valle"
    }
}

datos_invalidos_precio = {
    "id": 2,
    "nombre": "Producto Invalido",
    "precio": -10,
    "categoria": "frutas"
}

datos_invalidos_categoria = {
    "id": 3,
    "nombre": "Producto Test",
    "precio": 15.00,
    "categoria": "invalida"
}

datos_sin_campos = {
    "id": 4,
    "nombre": "Incompleto"
}


def medir_tiempo(func, data: Dict[str, Any], iteraciones: int = 10000) -> Dict[str, float]:
    """
    Mide el tiempo de ejecución de una función de validación.
    
    Args:
        func: Función de validación a medir
        data: Datos a validar
        iteraciones: Número de veces que ejecutar la función
    
    Returns:
        Diccionario con estadísticas de tiempo
    """
    tiempos = []
    
    for _ in range(iteraciones):
        inicio = time.perf_counter()
        try:
            func(data)
        except Exception:
            pass  # Ignoramos errores para benchmark
        fin = time.perf_counter()
        tiempos.append((fin - inicio) * 1000)  # Convertir a milisegundos
    
    return {
        "promedio": statistics.mean(tiempos),
        "mediana": statistics.median(tiempos),
        "min": min(tiempos),
        "max": max(tiempos),
        "desv_std": statistics.stdev(tiempos) if len(tiempos) > 1 else 0
    }


def validar_con_pydantic(data: Dict[str, Any]):
    """Wrapper para validación con Pydantic"""
    return Producto(**data)


def ejecutar_benchmarks():
    """Ejecuta todos los benchmarks y muestra resultados"""
    print("=" * 80)
    print("BENCHMARKS DE VALIDACIÓN DE DATOS")
    print("=" * 80)
    print()
    
    iteraciones = 10000
    print(f"Número de iteraciones por prueba: {iteraciones:,}")
    print()
    
    # --- BENCHMARK 1: Datos válidos ---
    print("-" * 80)
    print("BENCHMARK 1: Validación de datos VÁLIDOS")
    print("-" * 80)
    
    print("\n1. Validación Manual:")
    resultado_manual_valido = medir_tiempo(validar_manual, datos_validos, iteraciones)
    print(f"   Promedio: {resultado_manual_valido['promedio']:.6f} ms")
    print(f"   Mediana:  {resultado_manual_valido['mediana']:.6f} ms")
    print(f"   Mín/Máx:  {resultado_manual_valido['min']:.6f} / {resultado_manual_valido['max']:.6f} ms")
    print(f"   Desv.Std: {resultado_manual_valido['desv_std']:.6f} ms")
    
    print("\n2. Validación con Pydantic:")
    resultado_pydantic_valido = medir_tiempo(validar_con_pydantic, datos_validos, iteraciones)
    print(f"   Promedio: {resultado_pydantic_valido['promedio']:.6f} ms")
    print(f"   Mediana:  {resultado_pydantic_valido['mediana']:.6f} ms")
    print(f"   Mín/Máx:  {resultado_pydantic_valido['min']:.6f} / {resultado_pydantic_valido['max']:.6f} ms")
    print(f"   Desv.Std: {resultado_pydantic_valido['desv_std']:.6f} ms")
    
    print("\n3. Validación con JSON Schema:")
    resultado_schema_valido = medir_tiempo(validar_schema, datos_validos, iteraciones)
    print(f"   Promedio: {resultado_schema_valido['promedio']:.6f} ms")
    print(f"   Mediana:  {resultado_schema_valido['mediana']:.6f} ms")
    print(f"   Mín/Máx:  {resultado_schema_valido['min']:.6f} / {resultado_schema_valido['max']:.6f} ms")
    print(f"   Desv.Std: {resultado_schema_valido['desv_std']:.6f} ms")
    
    # Comparación relativa
    print("\n[COMPARACION] Comparacion relativa (datos validos):")
    base = resultado_manual_valido['promedio']
    print(f"   Manual:       1.00x (baseline: {base:.6f} ms)")
    print(f"   Pydantic:     {resultado_pydantic_valido['promedio']/base:.2f}x")
    print(f"   JSON Schema:  {resultado_schema_valido['promedio']/base:.2f}x")
    
    # --- BENCHMARK 2: Precio inválido ---
    print("\n" + "-" * 80)
    print("BENCHMARK 2: Validación de datos INVÁLIDOS (precio negativo)")
    print("-" * 80)
    
    print("\n1. Validación Manual:")
    resultado_manual_invalido = medir_tiempo(validar_manual, datos_invalidos_precio, iteraciones)
    print(f"   Promedio: {resultado_manual_invalido['promedio']:.6f} ms")
    
    print("\n2. Validación con Pydantic:")
    resultado_pydantic_invalido = medir_tiempo(validar_con_pydantic, datos_invalidos_precio, iteraciones)
    print(f"   Promedio: {resultado_pydantic_invalido['promedio']:.6f} ms")
    
    print("\n3. Validación con JSON Schema:")
    resultado_schema_invalido = medir_tiempo(validar_schema, datos_invalidos_precio, iteraciones)
    print(f"   Promedio: {resultado_schema_invalido['promedio']:.6f} ms")
    
    # --- BENCHMARK 3: Categoría inválida ---
    print("\n" + "-" * 80)
    print("BENCHMARK 3: Validación de datos INVÁLIDOS (categoría inválida)")
    print("-" * 80)
    
    print("\n1. Validación Manual:")
    # La validación manual no valida categoría, adaptamos
    print("   (No implementada en validación manual)")
    
    print("\n2. Validación con Pydantic:")
    resultado_pydantic_cat = medir_tiempo(validar_con_pydantic, datos_invalidos_categoria, iteraciones)
    print(f"   Promedio: {resultado_pydantic_cat['promedio']:.6f} ms")
    
    print("\n3. Validación con JSON Schema:")
    # JSON Schema tampoco valida categorías específicas en el ejemplo
    print("   (No implementada en JSON Schema básico)")
    
    # --- BENCHMARK 4: Campos faltantes ---
    print("\n" + "-" * 80)
    print("BENCHMARK 4: Validación de datos INVÁLIDOS (campos faltantes)")
    print("-" * 80)
    
    print("\n1. Validación Manual:")
    resultado_manual_faltantes = medir_tiempo(validar_manual, datos_sin_campos, iteraciones)
    print(f"   Promedio: {resultado_manual_faltantes['promedio']:.6f} ms")
    
    print("\n2. Validación con Pydantic:")
    resultado_pydantic_faltantes = medir_tiempo(validar_con_pydantic, datos_sin_campos, iteraciones)
    print(f"   Promedio: {resultado_pydantic_faltantes['promedio']:.6f} ms")
    
    print("\n3. Validación con JSON Schema:")
    resultado_schema_faltantes = medir_tiempo(validar_schema, datos_sin_campos, iteraciones)
    print(f"   Promedio: {resultado_schema_faltantes['promedio']:.6f} ms")
    
    # --- RESUMEN FINAL ---
    print("\n" + "=" * 80)
    print("RESUMEN DE RENDIMIENTO")
    print("=" * 80)
    
    ganador_valido = min(
        [("Manual", resultado_manual_valido['promedio']),
         ("Pydantic", resultado_pydantic_valido['promedio']),
         ("JSON Schema", resultado_schema_valido['promedio'])],
        key=lambda x: x[1]
    )
    
    ganador_invalido = min(
        [("Manual", resultado_manual_invalido['promedio']),
         ("Pydantic", resultado_pydantic_invalido['promedio']),
         ("JSON Schema", resultado_schema_invalido['promedio'])],
        key=lambda x: x[1]
    )
    
    print(f"\n[GANADOR] Metodo mas rapido (datos validos):   {ganador_valido[0]} ({ganador_valido[1]:.6f} ms)")
    print(f"[GANADOR] Metodo mas rapido (datos invalidos): {ganador_invalido[0]} ({ganador_invalido[1]:.6f} ms)")
    
    print("\n[RECOMENDACIONES]:")
    print("   - Validación Manual: Más rápida, pero requiere más código y es propensa a errores")
    print("   - Pydantic: Balance entre rendimiento y features (serialización, IDE support)")
    print("   - JSON Schema: Estándar universal, mejor para APIs y documentación")
    
    print("\n" + "=" * 80)
    

def benchmark_escalabilidad():
    """Prueba escalabilidad con diferentes tamaños de datos"""
    print("\n" + "=" * 80)
    print("BENCHMARK DE ESCALABILIDAD")
    print("=" * 80)
    print("\nProbando con múltiples productos simultáneos...\n")
    
    tamaños = [1, 10, 100, 1000]
    
    for tamaño in tamaños:
        print(f"--- Validando {tamaño} productos ---")
        productos = [datos_validos.copy() for _ in range(tamaño)]
        
        # Manual
        inicio = time.perf_counter()
        for p in productos:
            try:
                validar_manual(p)
            except Exception:
                pass
        tiempo_manual = (time.perf_counter() - inicio) * 1000
        
        # Pydantic
        inicio = time.perf_counter()
        for p in productos:
            try:
                Producto(**p)
            except Exception:
                pass
        tiempo_pydantic = (time.perf_counter() - inicio) * 1000
        
        # JSON Schema
        inicio = time.perf_counter()
        for p in productos:
            try:
                validar_schema(p)
            except Exception:
                pass
        tiempo_schema = (time.perf_counter() - inicio) * 1000
        
        print(f"  Manual:       {tiempo_manual:.3f} ms")
        print(f"  Pydantic:     {tiempo_pydantic:.3f} ms")
        print(f"  JSON Schema:  {tiempo_schema:.3f} ms")
        print()


if __name__ == "__main__":
    print("\n[INICIO] Iniciando benchmarks de validacion...\n")
    ejecutar_benchmarks()
    benchmark_escalabilidad()
    print("\n[OK] Benchmarks completados!\n")
