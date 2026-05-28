"""
cliente_robusto.py — Cliente robusto que integra CircuitBreaker + TokenManager
Semana 9: Resiliencia y Tolerancia a Fallos
UAN · Programación Distribuida del Lado del Cliente

Este archivo contiene:
  1. ClienteRobusto: orquesta la comunicación con el servidor mock usando
     CircuitBreaker y TokenManager.
  2. ServidorMockEcoMarket: servidor aiohttp local que simula estados de fallo.
  3. Harness de pruebas para los 7 Casos de Validación.
"""

import sys
import os
import asyncio
import time
import logging
from aiohttp import web
import httpx

# Asegurar codificación utf-8 en Windows para caracteres especiales en consola
if sys.platform.startswith("win"):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Importar TokenManager de Semana 8
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "semana_8")))
try:
    from token_manager import TokenManager
except ImportError:
    # Dummy TokenManager por si acaso hay problemas de importación
    print("⚠️  No se pudo cargar token_manager.py de semana_8. Usando TokenManager Dummy para fallback.")
    class TokenManager:
        def __init__(self):
            self._access_token = "dummy.access.token"
            self._refresh_token = "dummy.refresh.token"
            self._refresh_endpoint = "http://localhost:8080/api/auth/refresh"
            self._refresh_lock = asyncio.Lock()
        def get_auth_header(self) -> dict:
            return {"Authorization": f"Bearer {self._access_token}"}
        def is_expiring_soon(self) -> bool: return False
        def store_tokens(self, a, r): self._access_token = a; self._refresh_token = r
        async def refresh_access_token(self) -> bool:
            await asyncio.sleep(0.1)
            self._access_token = "dummy.refreshed.token"
            return True
        def logout(self): self._access_token = None; self._refresh_token = None

# Importar CircuitBreaker
from circuit_breaker import CircuitBreaker, EstadoCircuito, CircuitOpenError


# ════════════════════════════════════════════════════════════════════
# ClienteRobusto
# ════════════════════════════════════════════════════════════════════

class ClienteRobusto:
    """
    Cliente robusto e inteligente de EcoMarket.
    
    Orquesta CircuitBreaker y TokenManager para peticiones de negocio seguras,
    previniendo saturación de servidores mediante fail-fast e implementando
    actualización reactiva de tokens con refresh singleton.
    
    Principio de Responsabilidad Única:
      - ClienteRobusto: orquesta y despacha.
      - CircuitBreaker: gestiona estados y fallos de infraestructura.
      - TokenManager: custodia tokens y decide su expiración/renovación.
    """
    def __init__(self, token_manager: TokenManager, circuit_breaker: CircuitBreaker):
        self.token_manager = token_manager
        self.circuit_breaker = circuit_breaker

    async def hacer_peticion(self, method: str, url: str, **kwargs) -> dict:
        """
        Envuelve la petición HTTP en el Circuit Breaker.
        Lanza CircuitOpenError si el circuito está abierto (fail-fast).
        De lo contrario, delega la petición HTTP a un interceptor robusto de autenticación.
        """
        async def _peticion_con_auth():
            # 1. Obtener headers con token actual
            headers = kwargs.pop('headers', {})
            auth_headers = self.token_manager.get_auth_header()
            headers.update(auth_headers)
            
            async with httpx.AsyncClient() as client:
                resp = await client.request(method, url, headers=headers, **kwargs)
                
                # Si la llamada es exitosa (no es 401), procesar
                if resp.status_code != 401:
                    # Si es error de servidor (>= 500), lanzamos HTTPStatusError para que el breaker lo capte
                    resp.raise_for_status()
                    try:
                        return resp.json()
                    except Exception:
                        return {"text": resp.text}
                
                # 2. Recibimos 401 -> Renovamos token usando refresh singleton
                # Evitamos bucles infinitos en el endpoint de refresh
                if url == self.token_manager._refresh_endpoint:
                    self.token_manager.logout()
                    raise httpx.HTTPStatusError(
                        "401 Unauthorized en Endpoint de Refresh",
                        request=resp.request,
                        response=resp
                    )

                ts = time.strftime('%H:%M:%S')
                print(f"  🔑 [{ts}] [ClienteRobusto] 401 Detectado en {url}. Disparando refresh singleton...")
                
                # refresh_access_token() es singleton por asyncio.Lock en TokenManager
                refresh_ok = await self.token_manager.refresh_access_token()
                if not refresh_ok:
                    self.token_manager.logout()
                    raise RuntimeError("Autenticación fallida: el refresh_token expiró. Logout forzado.")

                # 3. Reintentar la petición original con el nuevo token
                print(f"  🔁 [{ts}] [ClienteRobusto] Reintentando petición con token renovado...")
                nuevos_headers = kwargs.pop('headers', {})
                nuevos_headers.update(self.token_manager.get_auth_header())
                
                resp2 = await client.request(method, url, headers=nuevos_headers, **kwargs)
                
                if resp2.status_code == 401:
                    print(f"  ❌ [{ts}] [ClienteRobusto] Reintento falló con 401. Forzando logout.")
                    self.token_manager.logout()
                    raise RuntimeError("Autenticación revocada tras reintento con 401. Logout forzado.")
                
                resp2.raise_for_status()
                try:
                    return resp2.json()
                except Exception:
                    return {"text": resp2.text}

        # Ejecutamos a través de la capa de Circuit Breaker
        return await self.circuit_breaker.ejecutar(_peticion_con_auth())


# ════════════════════════════════════════════════════════════════════
# ServidorMockEcoMarket
# ════════════════════════════════════════════════════════════════════

class ServidorMockEcoMarket:
    """
    Servidor mock local asíncrono para simular escenarios adversos.
    """
    def __init__(self):
        self.modo = 'normal'  # 'normal' | 'fallo_503' | 'timeout' | 'auth'
        self._peticiones_recibidas = 0
        self.app = web.Application()
        self.app.router.add_get('/api/inventario', self._handler_inventario)
        self.app.router.add_get('/api/inventario_delay', self._handler_inventario_delay)
        self.app.router.add_post('/api/auth/refresh', self._handler_auth)
        self.runner = None

    async def _handler_inventario(self, request):
        self._peticiones_recibidas += 1
        ts = time.strftime('%H:%M:%S')
        print(f"[MOCK SERVER] [{ts}] Petición #{self._peticiones_recibidas} recibida | modo={self.modo}")

        if self.modo == 'fallo_503':
            return web.Response(status=503, text='Service Unavailable')
        elif self.modo == 'timeout':
            await asyncio.sleep(5.0)  # Simular un timeout largo
            return web.Response(status=200, text='Tardísimo')
        elif self.modo == 'auth':
            return web.Response(status=401, text='Unauthorized')
        else:  # normal
            return web.json_response({'productos': 42, 'timestamp': 'ahora', 'status': 'OK'})

    async def _handler_inventario_delay(self, request):
        self._peticiones_recibidas += 1
        ts = time.strftime('%H:%M:%S')
        print(f"[MOCK SERVER] [{ts}] Petición con delay #{self._peticiones_recibidas} recibida | modo={self.modo}")
        await asyncio.sleep(0.5)  # Simular latencia de 0.5s para concurrencia
        return web.json_response({'productos': 42, 'timestamp': 'ahora', 'status': 'OK'})

    async def _handler_auth(self, request):
        # Simular renovación exitosa de tokens
        ts = time.strftime('%H:%M:%S')
        print(f"[MOCK SERVER] [{ts}] Petición de refresh recibida")
        return web.json_response({
            'access_token': 'nuevo.access.token',
            'refresh_token': 'nuevo.refresh.token',
            'expires_in': 900
        })

    @property
    def peticiones_recibidas(self) -> int:
        return self._peticiones_recibidas

    async def iniciar(self, puerto: int = 8080):
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, 'localhost', puerto)
        await site.start()
        print(f"[MOCK SERVER] Servidor mock activo en http://localhost:{puerto}")

    async def detener(self):
        if self.runner:
            await self.runner.cleanup()
            print("[MOCK SERVER] Servidor mock apagado")


# ════════════════════════════════════════════════════════════════════
# Harness de Pruebas y Validación (7 Casos de Prueba)
# ════════════════════════════════════════════════════════════════════

async def ejecutar_pruebas():
    print("\n" + "═" * 70)
    print("   INICIANDO EJECUCIÓN DEL HARNESS DE PRUEBAS — CIRCUIT BREAKER")
    print("═" * 70)
    
    # Levantar mock server
    mock = ServidorMockEcoMarket()
    await mock.iniciar(8080)
    
    # Inicializar TokenManager de Semana 8
    tm = TokenManager()
    tm.store_tokens("inicial.access.token", "inicial.refresh.token")
    
    # Inicializar CircuitBreaker de Semana 9
    # Reducimos timeout_apertura a 2.0s para que el suite de pruebas corra rápido!
    cb = CircuitBreaker(umbral_fallos=5, timeout_apertura=2.0, nombre="EcoMarket-TestAPI")
    
    cliente = ClienteRobusto(tm, cb)
    
    reporte_casos = []

    try:
        # ── CASO 1: Estado inicial y operación normal ────────────────
        print("\n" + "─" * 60)
        print("   CASO 1: Estado inicial y operación normal")
        print("─" * 60)
        mock.modo = 'normal'
        mock._peticiones_recibidas = 0
        
        exitosos = 0
        for i in range(5):
            res = await cliente.hacer_peticion("GET", "http://localhost:8080/api/inventario")
            if res.get('status') == 'OK':
                exitosos += 1
                
        caso1_ok = cb.estado == EstadoCircuito.CERRADO and cb._fallos_consecutivos == 0 and exitosos == 5
        print(f"Resultado: {exitosos}/5 exitosos. Breaker: {cb.estado.name}, Fallos={cb._fallos_consecutivos}")
        print(f"VEREDICTO CASO 1: {'✅ PASADO' if caso1_ok else '❌ FALLADO'}")
        reporte_casos.append(("Caso 1: Op Normal", caso1_ok, "CERRADO y fallos = 0"))

        # ── CASO 2: Transición CERRADO → ABIERTO ─────────────────────
        print("\n" + "─" * 60)
        print("   CASO 2: Transición CERRADO → ABIERTO")
        print("─" * 60)
        mock.modo = 'fallo_503'
        mock._peticiones_recibidas = 0
        
        # Hacemos 5 peticiones fallidas consecutivos para abrir el circuito
        for i in range(cb._umbral_fallos):
            try:
                await cliente.hacer_peticion("GET", "http://localhost:8080/api/inventario")
            except Exception as e:
                pass # Capturamos 503

        abrio_en_5 = cb.esta_abierto
        
        # Una sexta petición debe fallar de inmediato con CircuitOpenError (fail fast)
        peticiones_mock_antes = mock.peticiones_recibidas
        fail_fast_ok = False
        try:
            await cliente.hacer_peticion("GET", "http://localhost:8080/api/inventario")
        except CircuitOpenError as e:
            print(f"  ⚡ Fail Fast Exitoso: {e}")
            fail_fast_ok = True
        except Exception:
            pass
            
        peticiones_mock_despues = mock.peticiones_recibidas
        cero_peticiones_al_mock = (peticiones_mock_antes == peticiones_mock_despues)
        
        caso2_ok = abrio_en_5 and fail_fast_ok and cero_peticiones_al_mock
        print(f"Breaker abierto: {abrio_en_5}. Falla rápido: {fail_fast_ok}. Protege servidor: {cero_peticiones_al_mock}")
        print(f"VEREDICTO CASO 2: {'✅ PASADO' if caso2_ok else '❌ FALLADO'}")
        reporte_casos.append(("Caso 2: CERRADO → ABIERTO", caso2_ok, "Falla rápido y protege servidor"))

        # ── CASO 3: Los 4xx no abren el circuito ──────────────────────
        print("\n" + "─" * 60)
        print("   CASO 3: Los 4xx no abren el circuito (Evasión Deadlock)")
        print("─" * 60)
        # Primero reseteamos el breaker a cerrado
        cb._estado = EstadoCircuito.CERRADO
        cb._fallos_consecutivos = 0
        cb._tiempo_apertura = None
        
        mock.modo = 'auth' # Devuelve 401
        mock._peticiones_recibidas = 0
        
        # Lanzamos peticiones. El cliente interceptará el 401, intentará refrescar token,
        # y volverá a fallar (porque mock.modo es auth). Debe lanzar excepción, pero NO abrir el circuito!
        for i in range(7):
            try:
                await cliente.hacer_peticion("GET", "http://localhost:8080/api/inventario")
            except Exception:
                pass
                
        caso3_ok = cb.estado == EstadoCircuito.CERRADO and cb._fallos_consecutivos == 0
        print(f"Breaker: {cb.estado.name}, Fallos consec={cb._fallos_consecutivos} (debe ser 0)")
        print(f"VEREDICTO CASO 3: {'✅ PASADO' if caso3_ok else '❌ FALLADO'}")
        reporte_casos.append(("Caso 3: Exclusión 4xx", caso3_ok, "401s no incrementan fallos ni abren circuito"))

        # ── CASO 4: Transición ABIERTO → SEMIABIERTO por timeout ─────
        print("\n" + "─" * 60)
        print("   CASO 4: Transición ABIERTO → SEMIABIERTO por timeout")
        print("─" * 60)
        # Primero abrimos el circuito de nuevo de forma forzada
        cb._estado = EstadoCircuito.ABIERTO
        cb._tiempo_apertura = time.monotonic()
        
        print("Esperando a que expire el timeout_apertura (2 segundos)...")
        await asyncio.sleep(2.2)
        
        # Revisar si transiciona
        cb._revisar_timeout()
        caso4_ok = cb.estado == EstadoCircuito.SEMIABIERTO
        print(f"Breaker tras sleep: {cb.estado.name} (debe ser SEMIABIERTO)")
        print(f"VEREDICTO CASO 4: {'✅ PASADO' if caso4_ok else '❌ FALLADO'}")
        reporte_casos.append(("Caso 4: ABIERTO → SEMIABIERTO", caso4_ok, "Transición por timeout tras sleep"))

        # ── CASO 5: Recuperación exitosa (SEMIABIERTO → CERRADO) ──────
        print("\n" + "─" * 60)
        print("   CASO 5: Recuperación exitosa (SEMIABIERTO → CERRADO)")
        print("─" * 60)
        # Breaker está en SEMIABIERTO. Hacemos que el mock responda normal
        mock.modo = 'normal'
        mock._peticiones_recibidas = 0
        
        res = await cliente.hacer_peticion("GET", "http://localhost:8080/api/inventario")
        
        caso5_ok = cb.estado == EstadoCircuito.CERRADO and cb._fallos_consecutivos == 0
        print(f"Resultado petición: {res}. Breaker: {cb.estado.name}, Fallos consec={cb._fallos_consecutivos}")
        print(f"VEREDICTO CASO 5: {'✅ PASADO' if caso5_ok else '❌ FALLADO'}")
        reporte_casos.append(("Caso 5: SEMIABIERTO → CERRADO", caso5_ok, "Prueba exitosa cierra breaker"))

        # ── CASO 6: Fallo en SEMIABIERTO (SEMIABIERTO → ABIERTO) ──────
        print("\n" + "─" * 60)
        print("   CASO 6: Fallo en SEMIABIERTO (SEMIABIERTO → ABIERTO)")
        print("─" * 60)
        # Ponemos el breaker en SEMIABIERTO de nuevo
        cb._estado = EstadoCircuito.SEMIABIERTO
        cb._prueba_pendiente = False
        
        # El mock vuelve a fallar con 503
        mock.modo = 'fallo_503'
        
        try:
            await cliente.hacer_peticion("GET", "http://localhost:8080/api/inventario")
        except Exception:
            pass
            
        caso6_ok = cb.esta_abierto
        print(f"Breaker tras fallo en prueba: {cb.estado.name} (debe ser ABIERTO)")
        print(f"VEREDICTO CASO 6: {'✅ PASADO' if caso6_ok else '❌ FALLADO'}")
        reporte_casos.append(("Caso 6: SEMIABIERTO → ABIERTO", caso6_ok, "Prueba fallida reabre breaker"))

        # ── CASO 7: Concurrencia en SEMIABIERTO ──────────────────────
        print("\n" + "─" * 60)
        print("   CASO 7: Concurrencia en SEMIABIERTO (INV-A2)")
        print("─" * 60)
        # Ponemos el breaker en SEMIABIERTO
        cb._estado = EstadoCircuito.SEMIABIERTO
        cb._prueba_pendiente = False
        
        # Mock normal pero simula una pequeña latencia para que las peticiones se solapen
        mock.modo = 'normal'
        mock._peticiones_recibidas = 0
        
        print("Lanzando 3 peticiones concurrentes en SEMIABIERTO...")
        resultados = await asyncio.gather(
            cliente.hacer_peticion("GET", "http://localhost:8080/api/inventario_delay"),
            cliente.hacer_peticion("GET", "http://localhost:8080/api/inventario_delay"),
            cliente.hacer_peticion("GET", "http://localhost:8080/api/inventario_delay"),
            return_exceptions=True
        )
        
        exitos = sum(1 for r in resultados if not isinstance(r, Exception))
        open_errs = sum(1 for r in resultados if isinstance(r, CircuitOpenError))
        print(f"  Resultados concurrentes: {resultados}")
        print(f"  Éxitos: {exitos} | CircuitOpenErrors: {open_errs} | Peticiones al servidor: {mock.peticiones_recibidas}")
        
        caso7_ok = exitos == 1 and open_errs == 2 and mock.peticiones_recibidas == 1
        print(f"VEREDICTO CASO 7: {'✅ PASADO' if caso7_ok else '❌ FALLADO'}")
        reporte_casos.append(("Caso 7: Concurrencia", caso7_ok, "Exactamente 1 pasa, 2 rebotan"))

    finally:
        await mock.detener()

    # Imprimir reporte resumen en consola
    print("\n" + "═" * 70)
    print("   RESUMEN DEL REPORTE DE VALIDACIÓN — 7 CASOS DE PRUEBA")
    print("═" * 70)
    print(f"  {'Caso':<28} {'Veredicto':<12} Descripción")
    print("  " + "─" * 64)
    for nombre, ok, desc in reporte_casos:
        estado = "✅ PASADO" if ok else "❌ FALLADO"
        print(f"  {nombre:<28} {estado:<12} {desc}")
    print("═" * 70)


if __name__ == "__main__":
    asyncio.run(ejecutar_pruebas())
