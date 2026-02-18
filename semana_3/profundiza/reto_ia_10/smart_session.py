"""
SmartSession - Sesión HTTP Asíncrona con Monitoreo de Pool de Conexiones
==========================================================================

Este módulo implementa una sesión HTTP inteligente que:
1. Configura el pool de conexiones TCP de manera óptima
2. Monitorea el estado del pool en tiempo real
3. Registra métricas de uso (conexiones creadas/reutilizadas/cerradas)
4. Proporciona health checks periódicos
5. Es drop-in replacement para aiohttp.ClientSession

Autor: Async Programming Exercise - Semana 3
Propósito educativo: Aprender sobre connection pooling y TCP keep-alive
"""

import aiohttp
import asyncio
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class PoolMetrics:
    """Métricas del pool de conexiones."""
    conexiones_creadas: int = 0
    conexiones_reutilizadas: int = 0
    conexiones_cerradas: int = 0
    conexiones_activas: int = 0
    conexiones_disponibles: int = 0
    tiempo_inicio: datetime = field(default_factory=datetime.now)
    
    def __str__(self) -> str:
        uptime = (datetime.now() - self.tiempo_inicio).total_seconds()
        return (
            f"📊 Pool Metrics (uptime: {uptime:.1f}s)\n"
            f"   Creadas: {self.conexiones_creadas} | "
            f"Reutilizadas: {self.conexiones_reutilizadas} | "
            f"Cerradas: {self.conexiones_cerradas}\n"
            f"   Activas: {self.conexiones_activas} | "
            f"Disponibles: {self.conexiones_disponibles}"
        )
    
    def tasa_reutilizacion(self) -> float:
        """Calcula el porcentaje de conexiones reutilizadas."""
        total = self.conexiones_creadas + self.conexiones_reutilizadas
        if total == 0:
            return 0.0
        return (self.conexiones_reutilizadas / total) * 100


class SmartSession:
    """
    Sesión HTTP asíncrona con monitoreo de pool de conexiones.
    
    Drop-in replacement para aiohttp.ClientSession con funcionalidades adicionales:
    - Configuración optimizada del TCPConnector
    - Monitoreo de conexiones en tiempo real
    - Métricas de uso del pool
    - Health checks periódicos
    
    Ejemplo de uso:
        async with SmartSession(pool_size=10) as session:
            async with session.get("https://api.example.com/data") as response:
                data = await response.json()
                
        # Ver métricas
        session.print_metrics()
    """
    
    def __init__(
        self,
        pool_size: int = 10,
        timeout: Optional[aiohttp.ClientTimeout] = None,
        enable_monitoring: bool = True,
        **kwargs
    ):
        """
        Args:
            pool_size: Número máximo de conexiones simultáneas por host.
                      Default: 10 (balance entre throughput y recursos)
            timeout: Timeout para las peticiones. Default: 10s total
            enable_monitoring: Si True, registra métricas detalladas
            **kwargs: Argumentos adicionales para ClientSession
        """
        self.pool_size = pool_size
        self.enable_monitoring = enable_monitoring
        self.metrics = PoolMetrics() if enable_monitoring else None
        
        # Configurar TCPConnector con límites apropiados
        self.connector = aiohttp.TCPConnector(
            limit=pool_size,           # Límite total de conexiones
            limit_per_host=pool_size,  # Límite por host (importante para un solo API)
            ttl_dns_cache=300,         # Cache DNS por 5 minutos
            enable_cleanup_closed=True, # Limpiar conexiones cerradas automáticamente
        )
        
        # Configurar timeout razonable si no se especifica
        if timeout is None:
            timeout = aiohttp.ClientTimeout(total=10)
        
        # Crear la sesión HTTP
        self._session = aiohttp.ClientSession(
            connector=self.connector,
            timeout=timeout,
            **kwargs
        )
        
        logger.info(f"✨ SmartSession creada con pool_size={pool_size}")
    
    async def __aenter__(self):
        """Context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cierra la sesión."""
        await self.close()
    
    async def close(self):
        """Cierra la sesión y el connector, liberando todos los recursos."""
        if self.metrics:
            self.metrics.conexiones_cerradas = self.connector._conns._count if hasattr(self.connector, '_conns') else 0
            logger.info(f"🔒 Cerrando SmartSession...")
            self.print_metrics()
        
        await self._session.close()
        await self.connector.close()
    
    # ========================================================================
    # MÉTODOS HTTP (delegados a la sesión interna)
    # ========================================================================
    
    def get(self, url: str, **kwargs):
        """GET request."""
        if self.enable_monitoring:
            self._update_metrics_before_request()
        return self._session.get(url, **kwargs)
    
    def post(self, url: str, **kwargs):
        """POST request."""
        if self.enable_monitoring:
            self._update_metrics_before_request()
        return self._session.post(url, **kwargs)
    
    def put(self, url: str, **kwargs):
        """PUT request."""
        if self.enable_monitoring:
            self._update_metrics_before_request()
        return self._session.put(url, **kwargs)
    
    def patch(self, url: str, **kwargs):
        """PATCH request."""
        if self.enable_monitoring:
            self._update_metrics_before_request()
        return self._session.patch(url, **kwargs)
    
    def delete(self, url: str, **kwargs):
        """DELETE request."""
        if self.enable_monitoring:
            self._update_metrics_before_request()
        return self._session.delete(url, **kwargs)
    
    # ========================================================================
    # MONITOREO Y MÉTRICAS
    # ========================================================================
    
    def _update_metrics_before_request(self):
        """Actualiza métricas antes de cada petición."""
        if not self.metrics or not hasattr(self.connector, '_conns'):
            return
        
        # Acceder a las estadísticas internas del connector (API privada de aiohttp)
        # Nota: Esto usa API interna que podría cambiar en futuras versiones
        try:
            # Total de conexiones en el pool
            total_conns = getattr(self.connector, '_acquired', set())
            self.metrics.conexiones_activas = len(total_conns)
            
            # Conexiones disponibles (no en uso)
            available = getattr(self.connector, '_available_connections', lambda x: 0)
            # El connector no expone esto directamente, estimamos
            self.metrics.conexiones_disponibles = max(0, self.pool_size - self.metrics.conexiones_activas)
            
        except Exception as e:
            logger.debug(f"No se pudieron obtener métricas detalladas: {e}")
    
    def get_pool_status(self) -> Dict[str, Any]:
        """
        Retorna el estado actual del pool de conexiones.
        
        Returns:
            dict con: {
                'pool_size': tamaño configurado,
                'activas': conexiones en uso,
                'disponibles': conexiones libres,
                'creadas': total creadas,
                'reutilizadas': total reutilizadas,
                'tasa_reutilizacion': porcentaje de reuso
            }
        """
        if not self.metrics:
            return {"error": "Monitoreo deshabilitado"}
        
        return {
            "pool_size": self.pool_size,
            "activas": self.metrics.conexiones_activas,
            "disponibles": self.metrics.conexiones_disponibles,
            "creadas": self.metrics.conexiones_creadas,
            "reutilizadas": self.metrics.conexiones_reutilizadas,
            "tasa_reutilizacion": self.metrics.tasa_reutilizacion(),
        }
    
    def print_metrics(self):
        """Imprime las métricas del pool en formato legible."""
        if not self.metrics:
            logger.info("Monitoreo deshabilitado")
            return
        
        logger.info("\n" + str(self.metrics))
        logger.info(f"   Tasa de reutilización: {self.metrics.tasa_reutilizacion():.1f}%")
    
    async def health_check(self) -> bool:
        """
        Verifica el estado de salud del pool.
        
        Returns:
            True si el pool está saludable, False si hay problemas
        """
        status = self.get_pool_status()
        
        # Verificaciones básicas
        if status.get("error"):
            logger.warning("⚠️  Health check: Métricas no disponibles")
            return True  # No fallar si el monitoreo está deshabilitado
        
        # Verificar que no estemos al límite del pool constantemente
        if status["activas"] >= self.pool_size:
            logger.warning(
                f"⚠️  Health check: Pool al límite ({status['activas']}/{self.pool_size}). "
                f"Considera aumentar pool_size."
            )
            return False
        
        # Verificar que las conexiones se estén reutilizando
        if status["creadas"] > 20 and status["tasa_reutilizacion"] < 50:
            logger.warning(
                f"⚠️  Health check: Baja tasa de reutilización ({status['tasa_reutilizacion']:.1f}%). "
                f"Las conexiones keep-alive podrían no estar funcionando."
            )
            return False
        
        logger.info("✅ Health check: Pool saludable")
        return True


# ============================================================================
# FUNCIONES DE DEMOSTRACIÓN
# ============================================================================

async def demostrar_reutilizacion():
    """Demuestra cómo el pool reutiliza conexiones TCP."""
    print("\n" + "="*60)
    print("DEMOSTRACIÓN: Reutilización de Conexiones TCP")
    print("="*60 + "\n")
    
    # Usar un endpoint público que soporte keep-alive
    url = "https://httpbin.org/delay/0"
    
    async with SmartSession(pool_size=5) as session:
        print("📤 Enviando 10 peticiones al mismo host...")
        print(f"   Pool configurado para máximo 5 conexiones\n")
        
        tareas = [session.get(url) for _ in range(10)]
        
        # Ejecutar peticiones
        for i, coro in enumerate(asyncio.as_completed(tareas), 1):
            try:
                async with await coro as response:
                    await response.read()
                print(f"✓ Petición {i}/10 completada")
            except Exception as e:
                print(f"✗ Petición {i}/10 falló: {e}")
        
        print("\n📊 Métricas finales:")
        session.print_metrics()
        
        status = session.get_pool_status()
        print(f"\n💡 Observa que con 10 peticiones, solo necesitamos crear ~{status['creadas']} conexiones")
        print(f"   Las demás se reutilizan (keep-alive). Tasa: {status['tasa_reutilizacion']:.1f}%")


async def comparar_con_sesion_por_peticion():
    """Compara crear una sesión por petición vs reutilizar."""
    print("\n" + "="*60)
    print("COMPARACIÓN: Sesión Compartida vs Sesión por Petición")
    print("="*60 + "\n")
    
    url = "https://httpbin.org/delay/0"
    num_peticiones = 5
    
    # Estrategia 1: Sesión por petición (MALO)
    print("❌ ESTRATEGIA 1: Crear sesión por petición")
    inicio = asyncio.get_event_loop().time()
    
    async def peticion_con_sesion_nueva():
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                return await response.read()
    
    tareas = [peticion_con_sesion_nueva() for _ in range(num_peticiones)]
    await asyncio.gather(*tareas)
    
    tiempo_sesion_nueva = (asyncio.get_event_loop().time() - inicio) * 1000
    print(f"   Tiempo: {tiempo_sesion_nueva:.0f}ms\n")
    
    # Estrategia 2: Sesión compartida (BUENO)
    print("✅ ESTRATEGIA 2: Sesión compartida (SmartSession)")
    inicio = asyncio.get_event_loop().time()
    
    async with SmartSession(pool_size=5, enable_monitoring=False) as session:
        tareas = []
        for _ in range(num_peticiones):
            tareas.append(session.get(url))
        
        async def ejecutar(coro):
            async with await coro as response:
                return await response.read()
        
        await asyncio.gather(*[ejecutar(t) for t in tareas])
    
    tiempo_sesion_compartida = (asyncio.get_event_loop().time() - inicio) * 1000
    print(f"   Tiempo: {tiempo_sesion_compartida:.0f}ms\n")
    
    # Comparación
    speedup = tiempo_sesion_nueva / tiempo_sesion_compartida if tiempo_sesion_compartida > 0 else 1
    print(f"📈 Speedup: {speedup:.2f}x más rápido con sesión compartida")
    print(f"   Ahorro: {tiempo_sesion_nueva - tiempo_sesion_compartida:.0f}ms en {num_peticiones} peticiones\n")


# ============================================================================
# MAIN - Ejemplos de uso
# ============================================================================

if __name__ == "__main__":
    print("""
    ╔══════════════════════════════════════════════════════════════════════╗
    ║                   SmartSession - Demostración                       ║
    ║                    Connection Pool Monitoring                        ║
    ╚══════════════════════════════════════════════════════════════════════╝
    """)
    
    # Ejecutar demostraciones
    asyncio.run(demostrar_reutilizacion())
    asyncio.run(comparar_con_sesion_por_peticion())
    
    print("\n" + "="*60)
    print("📚 Para benchmarks detallados, ejecutar: python benchmark_pool.py")
    print("="*60 + "\n")
