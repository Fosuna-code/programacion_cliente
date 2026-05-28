"""
circuit_breaker.py — CircuitBreaker del lado del cliente para EcoMarket
Semana 9: Resiliencia y Tolerancia a Fallos
UAN · Programación Distribuida del Lado del Cliente

DECISIONES DE DISEÑO:
  1. ¿Qué errores cuentan como fallo del servidor?
     - asyncio.TimeoutError, httpx.RequestError (timeouts, errores de red, DNS, conexión).
     - httpx.HTTPStatusError con código HTTP >= 500 (500, 502, 503, 504).
     - ConnectionError, OSError a nivel de socket.
  2. ¿Qué umbral de fallos elegiste y por qué?
     - 5 fallos consecutivos. Evita falsos positivos de micro-cortes temporales de red,
       pero abre rápido ante una caída real o reinicio del servidor.
  3. ¿Qué timeout de apertura elegiste y por qué?
     - 60.0 segundos. En el escenario inmersivo, el servidor tarda 45 segundos en recuperarse.
       60 segundos da suficiente margen para que el backend se recupere completamente.
  4. Evasión de Deadlock Auth-Breaker:
     - Las llamadas de autenticación y renovación de token NO pasan por el Circuit Breaker de negocio.
"""

import asyncio
import time
import logging
from enum import Enum, auto

# Configuración básica de logs para visibilidad en consola
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("CircuitBreaker")


class EstadoCircuito(Enum):
    CERRADO = auto()      # Operación normal
    ABIERTO = auto()      # Falla inmediatamente, no contacta al servidor
    SEMIABIERTO = auto()   # Una petición de prueba permitida


class CircuitOpenError(Exception):
    """El circuito está abierto — no se intentó la petición."""
    def __init__(self, tiempo_restante: float):
        self.tiempo_restante = tiempo_restante
        super().__init__(
            f"Circuit breaker abierto. Reintenta en {tiempo_restante:.1f}s"
        )


class CircuitBreaker:
    """
    Implementa el patrón Circuit Breaker del lado del cliente.
    
    El cliente llama a cb.ejecutar(coro) en lugar de await coro directamente.
    Si el circuito está abierto, lanza CircuitOpenError inmediatamente.
    """

    def __init__(
        self,
        umbral_fallos: int = 5,
        timeout_apertura: float = 60.0,
        nombre: str = "EcoMarketAPI"
    ):
        self._estado = EstadoCircuito.CERRADO
        self._fallos_consecutivos = 0
        self._tiempo_apertura = None
        self._lock = asyncio.Lock()
        
        # Parámetros configurables
        self._umbral_fallos = umbral_fallos
        self._timeout_apertura = timeout_apertura
        self._nombre = nombre
        
        # Control estricto de concurrencia en SEMIABIERTO (INV-A2)
        self._prueba_pendiente = False

        ts = time.strftime('%H:%M:%S')
        print(f"🔌 [{ts}] [{self._nombre}] CircuitBreaker inicializado en CERRADO. Umbral={self._umbral_fallos}, Timeout={self._timeout_apertura}s")

    @property
    def estado(self) -> EstadoCircuito:
        """Retorna el estado actual. Lee _revisar_timeout() antes de retornar."""
        self._revisar_timeout()
        return self._estado

    @property
    def esta_abierto(self) -> bool:
        return self.estado == EstadoCircuito.ABIERTO

    def _revisar_timeout(self) -> None:
        """
        Si el circuito está ABIERTO y el timeout_apertura expiró,
        transiciona a SEMIABIERTO para permitir una petición de prueba.
        """
        if self._estado == EstadoCircuito.ABIERTO:
            if self._tiempo_apertura is not None:
                tiempo_transcurrido = time.monotonic() - self._tiempo_apertura
                if tiempo_transcurrido >= self._timeout_apertura:
                    self._estado = EstadoCircuito.SEMIABIERTO
                    self._prueba_pendiente = False
                    ts = time.strftime('%H:%M:%S')
                    print(f"⚠️  [{ts}] [{self._nombre}] TRANSICIÓN: ABIERTO → SEMIABIERTO (Timeout de apertura de {self._timeout_apertura}s expirado. Permitiendo petición de prueba)")

    def _es_fallo_servidor(self, excepcion: Exception) -> bool:
        """
        Decide si una excepción debe contar como fallo del servidor.
        
        CUENTA como fallo: asyncio.TimeoutError, httpx.RequestError (timeouts,
            errores de red, DNS), respuestas 5xx, ConnectionError, OSError.
        NO cuenta: ValueError, errores de parseo JSON, 4xx en general.
        """
        if isinstance(excepcion, CircuitOpenError):
            return False

        # Timeouts de python estándar o asyncio
        if isinstance(excepcion, (asyncio.TimeoutError, TimeoutError)):
            return True

        # Errores de socket y de red estándar de Python
        if isinstance(excepcion, (ConnectionError, ConnectionRefusedError, ConnectionResetError, OSError)):
            return True

        # Errores específicos de httpx si está instalado
        try:
            import httpx
            if isinstance(excepcion, httpx.TimeoutException):
                return True
            if isinstance(excepcion, httpx.NetworkError):
                return True
            if isinstance(excepcion, httpx.HTTPStatusError):
                # Errores 5xx cuentan como fallo, 4xx NO cuentan
                es_5xx = excepcion.response.status_code >= 500
                return es_5xx
            if isinstance(excepcion, httpx.RequestError):
                return True
        except ImportError:
            pass

        # Atributos personalizados status o status_code
        status = getattr(excepcion, "status_code", None) or getattr(excepcion, "status", None)
        if isinstance(status, int):
            return status >= 500

        return False

    def _registrar_exito(self) -> None:
        """Registra éxito: resetea contador y cierra el circuito."""
        ts = time.strftime('%H:%M:%S')
        if self._estado == EstadoCircuito.SEMIABIERTO:
            self._estado = EstadoCircuito.CERRADO
            self._fallos_consecutivos = 0
            self._tiempo_apertura = None
            self._prueba_pendiente = False
            print(f"🟢 [{ts}] [{self._nombre}] TRANSICIÓN: SEMIABIERTO → CERRADO (Petición de prueba exitosa! Servidor recuperado)")
        elif self._estado == EstadoCircuito.CERRADO:
            # Reseteamos contador en CERRADO para evitar acumular fallos antiguos
            if self._fallos_consecutivos > 0:
                print(f"🟢 [{ts}] [{self._nombre}] Petición exitosa en CERRADO. Reseteando fallos consecutivos ({self._fallos_consecutivos} → 0)")
                self._fallos_consecutivos = 0

    def _registrar_fallo(self) -> None:
        """Registra fallo del servidor: incrementa contador o abre el circuito."""
        ts = time.strftime('%H:%M:%S')
        if self._estado == EstadoCircuito.SEMIABIERTO:
            # Fallo en semiabierto -> reabre inmediatamente
            self._estado = EstadoCircuito.ABIERTO
            self._tiempo_apertura = time.monotonic()
            self._prueba_pendiente = False
            print(f"🔴 [{ts}] [{self._nombre}] TRANSICIÓN: SEMIABIERTO → ABIERTO (Fallo en la petición de prueba! Reabriendo circuito por otros {self._timeout_apertura}s)")
        elif self._estado == EstadoCircuito.CERRADO:
            self._fallos_consecutivos += 1
            print(f"⚠️  [{ts}] [{self._nombre}] Fallo registrado ({self._fallos_consecutivos}/{self._umbral_fallos} consecutivos)")
            if self._fallos_consecutivos >= self._umbral_fallos:
                self._estado = EstadoCircuito.ABIERTO
                self._tiempo_apertura = time.monotonic()
                print(f"🔴 [{ts}] [{self._nombre}] TRANSICIÓN: CERRADO → ABIERTO (Umbral de fallos alcanzado. Circuito abierto por {self._timeout_apertura}s)")

    async def ejecutar(self, coro):
        """
        Punto de entrada principal. Uso:
            resultado = await cb.ejecutar(cliente.get("/inventario"))
        
        Flujo:
          1. Verifica el estado del circuito
          2. Si ABIERTO → lanza CircuitOpenError con tiempo restante
          3. Si SEMIABIERTO → adquiere lock (solo una petición de prueba permitida)
          4. Ejecuta el coro
          5. En éxito → _registrar_exito()
          6. En fallo de servidor → _registrar_fallo(), re-lanza la excepción
          7. En fallo de cliente (4xx) → re-lanza SIN registrar fallo
        """
        estado_actual = self.estado  # Llama internamente a _revisar_timeout()

        if estado_actual == EstadoCircuito.ABIERTO:
            # Evitar advertencias de corrutinas no esperadas (coroutine was never awaited)
            self._cancelar_coro_no_esperado(coro)
            
            tiempo_transcurrido = time.monotonic() - self._tiempo_apertura
            tiempo_restante = max(0.0, self._timeout_apertura - tiempo_transcurrido)
            raise CircuitOpenError(tiempo_restante)

        adquirio_lock = False
        if estado_actual == EstadoCircuito.SEMIABIERTO:
            # INV-A2: En semiabierto, exactamente UNA petición simultánea pasa.
            # Si llega una petición concurrente mientras otra ya está probando, falla rápido.
            if self._prueba_pendiente or self._lock.locked():
                self._cancelar_coro_no_esperado(coro)
                raise CircuitOpenError(0.0)
            
            # Tomamos el lock de forma segura y marcamos el inicio de la prueba
            self._prueba_pendiente = True
            await self._lock.acquire()
            adquirio_lock = True

        try:
            resultado = await coro
            self._registrar_exito()
            return resultado
        except Exception as e:
            if self._es_fallo_servidor(e):
                self._registrar_fallo()
            raise e
        finally:
            if adquirio_lock:
                self._prueba_pendiente = False
                self._lock.release()

    def _cancelar_coro_no_esperado(self, coro) -> None:
        """Limpia de forma segura una corrutina que no se va a esperar para evitar advertencias de asyncio."""
        if asyncio.iscoroutine(coro):
            try:
                coro.close()
            except Exception:
                pass
