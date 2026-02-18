"""
Cliente Asíncrono para EcoMarket API
=====================================

Migración del cliente síncrono (requests) a asíncrono (aiohttp).
Todas las funciones CRUD mantienen la misma validación y manejo de errores.

Autor: Semana 3 - Async Programming
"""

import aiohttp
import asyncio
import sys
import os
import time

# Importing validators from semana2
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'semana_2', 'Aplica', 'retoIA_4'))
from validadores import validar_producto, validar_lista_productos

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'semana_2', 'Aplica', 'RetoIA_5'))
from url_builder import URLBuilder

# Centralized configuration
BASE_URL = "http://127.0.0.1:4010"
TIMEOUT = aiohttp.ClientTimeout(total=10)  # 10 seconds total timeout

# URLBuilder instance
url_builder = URLBuilder(BASE_URL)


# ============================================================================
# CUSTOM EXCEPTIONS (unchanged from sync version)
# ============================================================================

class EcoMarketError(Exception):
    """Base error for EcoMarket client"""
    pass


class ValidationError(EcoMarketError):
    """Server rejected the request (4xx)"""
    pass


class ConflictError(EcoMarketError):
    """Server detected a duplicate or conflict resource (409)"""
    pass


class ServerError(EcoMarketError):
    """Server error (5xx) - can be retried"""
    pass


# ============================================================================
# ASYNC HELPER FUNCTION
# ============================================================================

async def _verificar_respuesta(response: aiohttp.ClientResponse):
    """
    Verifies status code and Content-Type before processing (async version).
    
    CRITICAL: This function maintains the EXACT same error handling logic
    as the sync version, just adapted for aiohttp.
    """
    # Layer 1: Specific error handling
    if response.status == 409:
        text = await response.text()
        raise ConflictError(f"Conflict: Resource already exists. {text}")
    
    if response.status >= 500:
        raise ServerError(f"Server error: {response.status}")
    
    if response.status >= 400:
        text = await response.text()
        raise ValidationError(f"Client error: {response.status} - {text}")
    
    # Layer 2: Content-Type (if expecting JSON)
    content_type = response.headers.get('Content-Type', '')
    if 'application/json' not in content_type:
        # 204 No Content should not have a body
        if response.status != 204:
            raise ValidationError(f"Response is not JSON: {content_type}")
    
    return response


# ============================================================================
# ASYNC CRUD FUNCTIONS
# ============================================================================

async def listar_productos(session: aiohttp.ClientSession, categoria=None, orden=None):
    """
    GET /productos with optional filters (ASYNC VERSION).
    
    Args:
        session: aiohttp.ClientSession to use for the request
        categoria: Optional category filter
        orden: Optional sort order
    
    Returns:
        Validated list of products
    """
    params = {}
    if categoria:
        params['categoria'] = categoria
    if orden:
        params['orden'] = orden
    
    url = url_builder.build_url("productos", query_params=params if params else None)
    
    async with session.get(url) as response:
        await _verificar_respuesta(response)
        data = await response.json()
        return validar_lista_productos(data)


async def obtener_producto(session: aiohttp.ClientSession, producto_id):
    """
    GET /productos/{id} (ASYNC VERSION).
    
    Args:
        session: aiohttp.ClientSession to use for the request
        producto_id: ID of the product to retrieve
    
    Returns:
        Validated product data
    """
    url = url_builder.build_url("productos/{}", path_params=[producto_id])
    
    async with session.get(url) as response:
        await _verificar_respuesta(response)
        data = await response.json()
        return validar_producto(data)


async def crear_producto(session: aiohttp.ClientSession, datos: dict) -> dict:
    """
    POST /productos (ASYNC VERSION).
    Sends JSON data to create a new product. Expects a 201 Created status.
    
    Args:
        session: aiohttp.ClientSession to use for the request
        datos: Product data dict
    
    Example:
        async with aiohttp.ClientSession() as session:
            nuevo = {"nombre": "Miel de Abeja", "precio": 150.0, "categoria": "miel"}
            producto = await crear_producto(session, nuevo)
    """
    url = url_builder.build_url("productos")
    headers = {"Content-Type": "application/json"}
    
    async with session.post(url, json=datos, headers=headers) as response:
        await _verificar_respuesta(response)
        
        if response.status != 201:
            raise ValidationError(f"Expected 201 Created, got {response.status}")
        
        data = await response.json()
        return validar_producto(data)


async def actualizar_producto_total(session: aiohttp.ClientSession, producto_id: int, datos: dict) -> dict:
    """
    PUT /productos/{id} (ASYNC VERSION).
    Replaces the entire resource. It's crucial to send all product fields.
    
    Args:
        session: aiohttp.ClientSession to use for the request
        producto_id: ID of the product to update
        datos: Complete product data
    
    Example:
        datos_completos = {"nombre": "Miel Editada", "precio": 160.0, "categoria": "miel"}
        actualizado = await actualizar_producto_total(session, 42, datos_completos)
    """
    url = url_builder.build_url("productos/{}", path_params=[producto_id])
    headers = {"Content-Type": "application/json"}
    
    async with session.put(url, json=datos, headers=headers) as response:
        await _verificar_respuesta(response)
        return await response.json()


async def actualizar_producto_parcial(session: aiohttp.ClientSession, producto_id: int, campos: dict) -> dict:
    """
    PATCH /productos/{id} (ASYNC VERSION).
    Modifies only the provided fields without affecting the rest of the resource.
    
    Args:
        session: aiohttp.ClientSession to use for the request
        producto_id: ID of the product to update
        campos: Partial product data (only fields to update)
    
    Example:
        solo_precio = {"precio": 180.0}
        actualizado = await actualizar_producto_parcial(session, 42, solo_precio)
    """
    url = url_builder.build_url("productos/{}", path_params=[producto_id])
    headers = {"Content-Type": "application/json"}
    
    async with session.patch(url, json=campos, headers=headers) as response:
        await _verificar_respuesta(response)
        return await response.json()


async def eliminar_producto(session: aiohttp.ClientSession, producto_id: int) -> bool:
    """
    DELETE /productos/{id} (ASYNC VERSION).
    Deletes the specified product. Expects a 204 No Content status.
    
    Args:
        session: aiohttp.ClientSession to use for the request
        producto_id: ID of the product to delete
    
    Returns:
        True if deleted successfully
    
    Example:
        exito = await eliminar_producto(session, 42)  # Returns True if deleted
    """
    url = url_builder.build_url("productos/{}", path_params=[producto_id])
    
    async with session.delete(url) as response:
        await _verificar_respuesta(response)
        return response.status == 204


# ============================================================================
# PARALLEL LOADING FUNCTIONS
# ============================================================================

async def cargar_dashboard():
    """
    Loads dashboard data in parallel: productos + categorias + perfil.
    
    Uses gather() with return_exceptions=True to ensure one failure doesn't
    cancel the others. This is the main demonstration of async benefits.
    
    Returns:
        dict with:
            - 'exitosos': dict with successfully loaded data
            - 'errores': dict with errors encountered
    """
    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        print("📊 Loading dashboard...")
        inicio = time.time()
        
        # Launch all requests in parallel
        # NOTE: Mock server might not have /categorias or /perfil endpoints
        # Using /productos with different params as demonstration
        resultados = await asyncio.gather(
            listar_productos(session),  # All products
            listar_productos(session, categoria="miel"),  # Category filter
            obtener_producto(session, 1),  # Product detail (simulating profile)
            return_exceptions=True  # CRITICAL: don't lose work if one fails
        )
        
        tiempo_total = (time.time() - inicio) * 1000
        
        # Separate successes from errors
        exitosos = {}
        errores = {}
        
        labels = ["productos", "categorias", "perfil"]
        for i, (label, resultado) in enumerate(zip(labels, resultados)):
            if isinstance(resultado, Exception):
                errores[label] = str(resultado)
                print(f"❌ {label}: {resultado}")
            else:
                exitosos[label] = resultado
                print(f"✅ {label}: OK")
        
        print(f"\n⏱️  Total time: {tiempo_total:.0f}ms")
        print(f"📈 Success rate: {len(exitosos)}/{len(labels)}")
        
        return {
            "exitosos": exitosos,
            "errores": errores,
            "tiempo_ms": tiempo_total
        }


async def crear_multiples_productos(lista_productos: list) -> tuple:
    """
    Creates multiple products in parallel with concurrency limiting.
    
    Uses asyncio.Semaphore to limit to max 5 simultaneous requests,
    preventing server overload.
    
    Args:
        lista_productos: List of product data dicts
    
    Returns:
        tuple: (productos_creados, productos_fallidos)
    
    Example:
        productos = [
            {"nombre": "Producto 1", "precio": 100, "categoria": "cat1"},
            {"nombre": "Producto 2", "precio": 200, "categoria": "cat2"},
            # ... 18 more
        ]
        creados, fallidos = await crear_multiples_productos(productos)
    """
    # Limiter: max 5 concurrent requests
    semaforo = asyncio.Semaphore(5)
    
    async def crear_con_limite(session, datos, idx):
        """Helper function that respects the semaphore."""
        async with semaforo:
            print(f"🔄 Creating product {idx+1}/{len(lista_productos)}...")
            try:
                resultado = await crear_producto(session, datos)
                print(f"✅ Created product {idx+1}")
                return ("success", resultado)
            except Exception as e:
                print(f"❌ Failed product {idx+1}: {e}")
                return ("error", {"index": idx, "datos": datos, "error": str(e)})
    
    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        print(f"\n📦 Creating {len(lista_productos)} products with max 5 concurrent...")
        inicio = time.time()
        
        # Launch all creations in parallel (but semaphore limits actual concurrency)
        tareas = [
            crear_con_limite(session, datos, i) 
            for i, datos in enumerate(lista_productos)
        ]
        
        resultados = await asyncio.gather(*tareas)
        
        tiempo_total = (time.time() - inicio) * 1000
        
        # Separate successes from failures
        creados = [r[1] for r in resultados if r[0] == "success"]
        fallidos = [r[1] for r in resultados if r[0] == "error"]
        
        print(f"\n⏱️  Total time: {tiempo_total:.0f}ms")
        print(f"✅ Created: {len(creados)}/{len(lista_productos)}")
        print(f"❌ Failed: {len(fallidos)}/{len(lista_productos)}")
        
        return (creados, fallidos)


# ============================================================================
# COMPARISON: SYNC VS ASYNC
# ============================================================================

def cargar_dashboard_sincrono():
    """
    Loads dashboard SYNCHRONOUSLY for comparison.
    Uses the sync client from semana2.
    """
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'semana_2', 'Aplica', 'RetoIA_3'))
    import cliente_ecomarket as sync_client
    
    print("📊 Loading dashboard (SYNC)...")
    inicio = time.time()
    
    try:
        productos = sync_client.listar_productos()
        categorias = sync_client.listar_productos(categoria="miel")
        perfil = sync_client.obtener_producto(1)
        
        tiempo_total = (time.time() - inicio) * 1000
        print(f"⏱️  Total time (SYNC): {tiempo_total:.0f}ms")
        
        return {
            "exitosos": {
                "productos": productos,
                "categorias": categorias,
                "perfil": perfil
            },
            "errores": {},
            "tiempo_ms": tiempo_total
        }
    except Exception as e:
        tiempo_total = (time.time() - inicio) * 1000
        print(f"❌ Error (SYNC): {e}")
        return {
            "exitosos": {},
            "errores": {"general": str(e)},
            "tiempo_ms": tiempo_total
        }


async def comparar_sync_vs_async():
    """Compares sync vs async performance for dashboard loading."""
    print("\n" + "="*60)
    print("COMPARISON: Sync vs Async Dashboard Loading")
    print("="*60 + "\n")
    
    # Run sync version
    resultado_sync = cargar_dashboard_sincrono()
    
    print("\n")
    
    # Run async version
    resultado_async = await cargar_dashboard()
    
    # Calculate speedup
    tiempo_sync = resultado_sync['tiempo_ms']
    tiempo_async = resultado_async['tiempo_ms']
    speedup = tiempo_sync / tiempo_async if tiempo_async > 0 else 1
    
    print("\n" + "="*60)
    print("RESULTS:")
    print("="*60)
    print(f"Sync version:  {tiempo_sync:.0f}ms")
    print(f"Async version: {tiempo_async:.0f}ms")
    print(f"Speedup:       {speedup:.2f}x faster")
    print(f"Time saved:    {tiempo_sync - tiempo_async:.0f}ms")
    print("="*60 + "\n")


# ============================================================================
# MAIN - DEMONSTRATION
# ============================================================================

async def main():
    """Main demonstration of async client capabilities."""
    print("""
    ╔══════════════════════════════════════════════════════════════════════╗
    ║            Cliente Asíncrono EcoMarket - Demostración               ║
    ║                   Migración de Síncrono a Async                      ║
    ╚══════════════════════════════════════════════════════════════════════╝
    """)
    
    # Demo 1: Dashboard loading
    print("\n🔹 DEMO 1: Dashboard Parallel Loading\n")
    resultado = await cargar_dashboard()
    
    # Demo 2: Bulk creation with semaphore
    print("\n🔹 DEMO 2: Bulk Product Creation (Semaphore Limiting)\n")
    productos_demo = [
        {"nombre": f"Producto {i}", "precio": 100 + i*10, "categoria": "demo"}
        for i in range(10)
    ]
    creados, fallidos = await crear_multiples_productos(productos_demo)
    
    # Demo 3: Sync vs Async comparison
    print("\n🔹 DEMO 3: Performance Comparison\n")
    await comparar_sync_vs_async()
    
    print("\n✅ All demos completed!\n")


if __name__ == "__main__":
    asyncio.run(main())
