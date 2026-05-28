"""
circuit_breaker.py — CircuitBreaker del lado del cliente para EcoMarket
Semana 10: Resiliencia y Tolerancia a Fallos (copiado de Semana 9,
auto-contenido, con callbacks de observabilidad para el UI).

DECISIONES DE DISEÑO:
  1. Errores que cuentan como fallo del servidor:
     - asyncio.TimeoutError (petición no recibe respuesta)
     - ConnectionRefusedError, ConnectionResetError, OSError de red
     - HTTP 5xx (cuando la excepción/respuesta lleva status >= 500)
     - Errores de conexión de aiohttp (ServerConnectionError, ClientConnectorError)
  2. Umbral de fallos: 5
     → Justificación: Equilibra entre detectar fallos reales rápidamente y evitar
     falsos positivos por network blips breves. Con 5 fallos consecutivos tenemos
     evidencia sólida de que el servidor está en problemas sostenidos.
  3. Timeout de apertura: 10 segundos (demo) / 60 segundos (producción)
     → Justificación: En producción 60s permite que el servidor se recupere
     completamente antes de la primera prueba. Para el demo usamos 10s para
     que las pruebas sean ágiles.
  4. time.monotonic() para todos los cálculos de tiempo
     → Justificación: Evita el "timer fantasma" si el reloj del sistema cambia
     (NTP sync, cambio de zona horaria).
  5. asyncio.Lock() en estado SEMIABIERTO
     → Justificación: Garantiza que exactamente UNA petición de prueba ejecuta
     simultáneamente. Segundas peticiones concurrentes reciben CircuitOpenError.
"""

import asyncio
import time
import logging
from enum import Enum, auto

logger = logging.getLogger(__name__)


class EstadoCircuito(Enum):
    CERRADO      = auto()   # Operación normal
    ABIERTO      = auto()   # Falla inmediatamente, no contacta al servidor
    SEMIABIERTO  = auto()   # Una petición de prueba permitida


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
        timeout_apertura: float = 10.0,
        nombre: str = "EcoMarketAPI"
    ):
        self._umbral_fallos = umbral_fallos
        self._timeout_apertura = timeout_apertura
        self._nombre = nombre

        self._estado = EstadoCircuito.CERRADO
        self._fallos_consecutivos = 0
        self._tiempo_apertura = None  # type: float | None
        self._lock = asyncio.Lock()

        # Callbacks de observabilidad para el UI (Reto 4)
        self._on_circuit_open = None   # Called when circuit transitions to ABIERTO
        self._on_circuit_close = None  # Called when circuit transitions to CERRADO

    @property
    def estado(self) -> EstadoCircuito:
        """Retorna el estado actual. Lee _revisar_timeout() antes de retornar."""
        self._revisar_timeout()
        return self._estado

    @property
    def esta_abierto(self) -> bool:
        return self.estado == EstadoCircuito.ABIERTO

    @property
    def umbral_fallos(self) -> int:
        return self._umbral_fallos

    @property
    def timeout_apertura(self) -> float:
        return self._timeout_apertura

    # ------------------------------------------------------------------
    # Callbacks de observabilidad
    # ------------------------------------------------------------------
    @property
    def on_circuit_open(self):
        """Callable invocado cuando el circuito pasa a ABIERTO."""
        return self._on_circuit_open

    @on_circuit_open.setter
    def on_circuit_open(self, callback):
        self._on_circuit_open = callback

    @property
    def on_circuit_close(self):
        """Callable invocado cuando el circuito pasa a CERRADO."""
        return self._on_circuit_close

    @on_circuit_close.setter
    def on_circuit_close(self, callback):
        self._on_circuit_close = callback

    def _revisar_timeout(self) -> None:
        """
        Si el circuito está ABIERTO y el timeout_apertura expiró,
        transiciona a SEMIABIERTO para permitir una petición de prueba.
        """
        if self._estado == EstadoCircuito.ABIERTO and self._tiempo_apertura is not None:
            transcurrido = time.monotonic() - self._tiempo_apertura
            if transcurrido >= self._timeout_apertura:
                self._estado = EstadoCircuito.SEMIABIERTO
                self._tiempo_apertura = None
                logger.info(
                    "[%s] Transición ABIERTO → SEMIABIERTO (timeout expiró)",
                    self._nombre
                )

    def _es_fallo_servidor(self, excepcion: Exception) -> bool:
        """
        Decide si una excepción debe contar como fallo del servidor.

        CUENTA como fallo:
          - asyncio.TimeoutError
          - ConnectionRefusedError, ConnectionResetError, ConnectionAbortedError
          - OSError de red (errno relacionados con conexión)
          - HTTP 5xx (cuando la excepción/respuesta tiene .status >= 500)
          - Errores de conexión de bibliotecas HTTP (aiohttp, httpx, requests)

        NO cuenta:
          - HTTP 4xx (incluyendo 401, 403, 404, 409)
          - ValueError, TypeError
          - Errores de parseo JSON
          - CircuitOpenError (el breaker ya está abierto — no es fallo del servidor)
        """
        # CircuitOpenError NUNCA cuenta como fallo del servidor
        if isinstance(excepcion, CircuitOpenError):
            return False

        # TimeoutError siempre cuenta como fallo de infraestructura
        if isinstance(excepcion, asyncio.TimeoutError):
            return True

        # Errores de conexión TCP/OS
        if isinstance(excepcion, (
            ConnectionRefusedError,
            ConnectionResetError,
            ConnectionAbortedError,
            ConnectionError,
            BrokenPipeError,
        )):
            return True

        # OSError de red — verificamos errno
        if isinstance(excepcion, OSError):
            import errno
            # Errores de red comunes: ENETUNREACH, EHOSTUNREACH, ECONNREFUSED, ETIMEDOUT, etc.
            errores_red = {
                errno.ENETUNREACH, errno.EHOSTUNREACH, errno.ECONNREFUSED,
                errno.ETIMEDOUT, errno.ECONNRESET, errno.EPIPE,
                errno.ECONNABORTED, errno.ENETDOWN, errno.ENOTCONN
            }
            if excepcion.errno in errores_red:
                return True

        # Excepciones con atributo .status (aiohttp, httpx, etc.)
        status = getattr(excepcion, "status", None)
        if status is not None and status >= 500:
            return True

        # Excepciones con .code (algunas bibliotecas)
        code = getattr(excepcion, "code", None)
        if code is not None and code >= 500:
            return True

        # Errores de bibliotecas HTTP conocidas por nombre de clase
        nombre_clase = type(excepcion).__name__
        errores_http_cliente = {
            "ServerConnectionError", "ClientConnectorError", "ClientOSError",
            "ServerDisconnectedError", "ServerTimeoutError", "ConnectTimeout",
            "ReadTimeout", "NetworkError", "ConnectionError"
        }
        if nombre_clase in errores_http_cliente:
            return True

        # Mensaje que indica fallo de servidor (heurística conservadora)
        msg = str(excepcion).lower()
        if any(p in msg for p in ("503", "502", "504", "500", "502 bad gateway",
                                    "503 service unavailable", "504 gateway timeout",
                                    "internal server error")):
            return True

        return False

    def _registrar_exito(self) -> None:
        """Registra éxito: resetea contador y cierra el circuito."""
        estado_previo = self._estado
        self._fallos_consecutivos = 0

        if self._estado == EstadoCircuito.SEMIABIERTO:
            self._estado = EstadoCircuito.CERRADO
            logger.info(
                "[%s] Transición SEMIABIERTO → CERRADO (recuperación exitosa)",
                self._nombre
            )
            # INV-A3: _fallos_consecutivos ya se reseteó arriba.
            # Notificar al UI que el circuito se cerró.
            if self._on_circuit_close is not None:
                try:
                    self._on_circuit_close()
                except Exception:
                    logger.exception(
                        "[%s] Error en on_circuit_close callback",
                        self._nombre
                    )
        elif estado_previo == EstadoCircuito.CERRADO and self._fallos_consecutivos == 0:
            # Éxito en estado cerrado — aseguramos que el contador esté en 0
            pass

    def _registrar_fallo(self) -> None:
        """Registra fallo del servidor: incrementa contador o abre el circuito."""
        estado_previo = self._estado
        self._fallos_consecutivos += 1
        logger.warning(
            "[%s] Fallo registrado #%d/%d",
            self._nombre, self._fallos_consecutivos, self._umbral_fallos
        )

        if self._fallos_consecutivos >= self._umbral_fallos:
            self._estado = EstadoCircuito.ABIERTO
            self._tiempo_apertura = time.monotonic()
            logger.error(
                "[%s] Transición %s → ABIERTO (umbral alcanzado: %d fallos)",
                self._nombre, estado_previo.name, self._fallos_consecutivos
            )
            # Solo notificar al UI si la transición es desde CERRADO o SEMIABIERTO
            # (evita notificaciones duplicadas si ya estaba ABIERTO)
            if estado_previo != EstadoCircuito.ABIERTO:
                if self._on_circuit_open is not None:
                    try:
                        self._on_circuit_open()
                    except Exception:
                        logger.exception(
                            "[%s] Error en on_circuit_open callback",
                            self._nombre
                        )

    async def ejecutar(self, fn):
        """
        Punto de entrada principal. Uso:
            resultado = await cb.ejecutar(lambda: cliente.get("/inventario"))

        `fn` es un callable que retorna una coroutine (awaitable).
        Se invoca SÓLO si el circuito permite la ejecución, evitando
        crear coroutines que nunca se ejecutan (y generan warnings).

        Flujo:
          1. Verifica el estado del circuito
          2. Si ABIERTO → lanza CircuitOpenError con tiempo restante
          3. Si SEMIABIERTO → adquiere lock (solo una petición de prueba)
          4. Ejecuta fn() → await coro
          5. En éxito → _registrar_exito()
          6. En fallo de servidor → _registrar_fallo(), re-lanza la excepción
          7. En fallo de cliente (4xx) → re-lanza SIN registrar fallo
        """
        estado_actual = self.estado  # llama _revisar_timeout() internamente

        # 2. ABIERTO → falla rápido
        if estado_actual == EstadoCircuito.ABIERTO:
            if self._tiempo_apertura is not None:
                transcurrido = time.monotonic() - self._tiempo_apertura
                tiempo_restante = max(0.0, self._timeout_apertura - transcurrido)
            else:
                tiempo_restante = 0.0
            raise CircuitOpenError(tiempo_restante)

        # 3. SEMIABIERTO → adquiere lock (solo UNA petición de prueba)
        lock_adquirido = False
        if estado_actual == EstadoCircuito.SEMIABIERTO:
            # En asyncio single-threaded, locked() + acquire() es atómico respecto
            # a otras tareas porque no cedemos control entre ambas operaciones.
            if self._lock.locked():
                raise CircuitOpenError(0.0)
            await self._lock.acquire()
            lock_adquirido = True

        try:
            # 4. Ejecuta la coroutine (se crea aquí, no antes)
            coro = fn()
            resultado = await coro

            # 5. Éxito → registra y retorna
            self._registrar_exito()
            return resultado

        except Exception as e:
            # 6. Fallo de servidor → registra y re-lanza
            # 7. Fallo de cliente → solo re-lanza
            if self._es_fallo_servidor(e):
                self._registrar_fallo()
            # Siempre re-lanza — el caller decide cómo manejar
            raise

        finally:
            # Libera el lock SI lo adquirimos en SEMIABIERTO
            if lock_adquirido:
                try:
                    self._lock.release()
                except RuntimeError:
                    # Lock ya liberado — ignora silenciosamente
                    pass
