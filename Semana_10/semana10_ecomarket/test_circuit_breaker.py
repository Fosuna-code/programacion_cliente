"""
test_circuit_breaker.py — Casos de prueba para Semana 10 (Grand Deploy)
========================================================================

Valida los 7 invariantes del Hito 2 y los 3 casos de regresion cruzada (TC-X).

Ejecutar: python -m pytest test_circuit_breaker.py test_tc_x2_refresh_semiaabierto.py -v
          o directamente: python test_circuit_breaker.py

INVARIANTES:
  INV-A1: CB nunca accede a campos del payload JWT
  INV-A2: En SEMIABIERTO, exactamente una peticion pasa; las demas reciben CircuitOpenError
  INV-A3: Al transicionar SEMIABIERTO -> CERRADO, _fallos_consecutivos se resetea a 0
  INV-A4: HTTP 401/403 NO incrementan _fallos_consecutivos
  INV-B1: TokenManager no tiene atributos del CircuitBreaker
  INV-B2: El token nunca aparece en logs, ni parcialmente
  INV-B3: Con multiples peticiones concurrentes expiradas, solo un refresh se ejecuta

CASOS DE REGRESION CRUZADA (TC-X):
  TC-X1: SSE activo + CB transiciona a ABIERTO -> SSE NO se interrumpe
  TC-X2: Token expira mientras CB en SEMIABIERTO -> orden y singleton
  TC-X3: Reconexion SSE con Last-Event-ID tras cierre del circuito
"""

import asyncio
import base64
import json
import time
import sys
import logging

import pytest

from circuit_breaker import CircuitBreaker, CircuitOpenError, EstadoCircuito
from token_manager import TokenManager
from cliente_robusto import ClienteRobusto

logging.basicConfig(level=logging.WARNING)
pytestmark = pytest.mark.asyncio


# ═════════════════════════════════════════════════════════════
# COROUTINES AUXILIARES
# ═════════════════════════════════════════════════════════════

async def _coro_exito():
    await asyncio.sleep(0.01)
    return "ok"


async def _coro_exito_lento(segundos: float = 0.1):
    await asyncio.sleep(segundos)
    return "ok"


class FakeHttpError(Exception):
    def __init__(self, status: int, message: str = ""):
        self.status = status
        self.message = message
        super().__init__(f"HTTP {status}: {message}")


async def _coro_fallo_503():
    await asyncio.sleep(0.01)
    raise FakeHttpError(503, "Service Unavailable")


async def _coro_fallo_401():
    await asyncio.sleep(0.01)
    raise FakeHttpError(401, "Unauthorized")


async def _coro_fallo_403():
    await asyncio.sleep(0.01)
    raise FakeHttpError(403, "Forbidden")


def _jwt_con_exp(exp: int, sub: str = "op1", rol: str = "viewer") -> str:
    """Crea un JWT sintético válido para decode_payload(); la firma no se verifica."""
    def b64url(obj):
        raw = json.dumps(obj, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"sub": sub, "rol": rol, "exp": exp}
    return f"{b64url(header)}.{b64url(payload)}.mock_sig"


class CountingRefreshTokenManager(TokenManager):
    def __init__(self):
        super().__init__(base_url="http://localhost:3000")
        self.refresh_calls = 0

    async def _do_refresh(self) -> str:
        self.refresh_calls += 1
        await asyncio.sleep(0.05)
        token = _jwt_con_exp(int(time.time()) + 900)
        self.store_tokens(token, "mock_refresh")
        return token


class FakeExpiringTokenManager:
    def __init__(self, eventos):
        self.access_token = "token_expirando"
        self._expiring = True
        self.refresh_calls = 0
        self.eventos = eventos

    def is_expiring_soon(self, margen_segundos=None):
        return self._expiring

    async def refresh_access_token(self):
        self.eventos.append("refresh")
        self.refresh_calls += 1
        await asyncio.sleep(0.01)
        self.access_token = "token_fresco"
        self._expiring = False
        return self.access_token

    def get_auth_header(self):
        self.eventos.append("auth_header")
        return {"Authorization": f"Bearer {self.access_token}"}


class FakeResponse:
    status = 200
    headers = {}
    history = ()
    request_info = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return {"ok": True, "productos": 3}

    async def text(self):
        return json.dumps(await self.json())


class FakeSession:
    closed = False

    def __init__(self, eventos):
        self.eventos = eventos
        self.requests = 0
        self.headers = []

    def request(self, method, url, headers=None, **kwargs):
        self.eventos.append("request")
        self.requests += 1
        self.headers.append(headers or {})
        return FakeResponse()

    async def close(self):
        self.closed = True


# ═════════════════════════════════════════════════════════════
# INV-A1: CB nunca accede a campos del payload JWT
# ═════════════════════════════════════════════════════════════

async def test_inv_a1():
    print("\n🧪 INV-A1: CB nunca accede a campos del payload JWT")
    cb = CircuitBreaker(umbral_fallos=5, timeout_apertura=10.0)

    # Importar CB con token malformado — no debe lanzar error de decodificacion
    # El CB ejecuta una corutina lambda que no depende de JWT en absoluto
    resultado = await cb.ejecutar(lambda: _coro_exito())
    assert resultado == "ok", "CB deberia ejecutar correctamente"

    # Verificar que CB no tiene metodos de decodificacion JWT
    assert not hasattr(cb, 'decode_payload'), "CB no debe tener decode_payload"
    assert not hasattr(cb, 'get_auth_header'), "CB no debe tener get_auth_header"

    print("   ✅ INV-A1 PASADO: CB no accede a campos JWT")


# ═════════════════════════════════════════════════════════════
# INV-A2: En SEMIABIERTO, exactamente una peticion pasa
# ═════════════════════════════════════════════════════════════

async def test_inv_a2():
    print("\n🧪 INV-A2: En SEMIABIERTO, exactamente una peticion pasa")
    umbral = 2
    timeout = 1.0
    cb = CircuitBreaker(umbral_fallos=umbral, timeout_apertura=timeout)

    # Fuerza estado ABIERTO
    for _ in range(umbral):
        try:
            await cb.ejecutar(_coro_fallo_503)
        except Exception:
            pass
    assert cb.estado == EstadoCircuito.ABIERTO, "Debe estar ABIERTO"

    # Espera a SEMIABIERTO
    await asyncio.sleep(timeout + 0.3)
    assert cb.estado == EstadoCircuito.SEMIABIERTO, "Debe estar SEMIABIERTO"

    # Lanza 3 peticiones concurrentes — solo 1 debe pasar
    resultados = await asyncio.gather(
        cb.ejecutar(lambda: _coro_exito_lento(0.1)),
        cb.ejecutar(_coro_exito),
        cb.ejecutar(_coro_exito),
        return_exceptions=True
    )

    exitos = sum(1 for r in resultados if not isinstance(r, Exception))
    circuit_errs = sum(1 for r in resultados if isinstance(r, CircuitOpenError))

    print(f"   Resultados: exitos={exitos}, CircuitOpenErrors={circuit_errs}")
    assert exitos == 1, f"Esperaba 1 exito, obtuve {exitos}"
    assert circuit_errs == 2, f"Esperaba 2 CircuitOpenError, obtuve {circuit_errs}"
    assert cb._fallos_consecutivos == 0, "Despues del exito, fallos debe ser 0"
    assert cb.estado == EstadoCircuito.CERRADO, "Despues del exito, debe estar CERRADO"
    print("   ✅ INV-A2 PASADO: Solo 1 peticion paso en SEMIABIERTO")


# ═════════════════════════════════════════════════════════════
# INV-A3: _fallos_consecutivos se resetea a 0 al cerrar
# ═════════════════════════════════════════════════════════════

async def test_inv_a3():
    print("\n🧪 INV-A3: _fallos_consecutivos se resetea a 0 al cerrar")
    timeout = 1.0
    cb = CircuitBreaker(umbral_fallos=2, timeout_apertura=timeout)

    # Abre el circuito
    for _ in range(2):
        try:
            await cb.ejecutar(_coro_fallo_503)
        except Exception:
            pass
    assert cb.estado == EstadoCircuito.ABIERTO

    # Espera a SEMIABIERTO
    await asyncio.sleep(timeout + 0.2)
    assert cb.estado == EstadoCircuito.SEMIABIERTO

    # Peticion exitosa -> CERRADO
    resultado = await cb.ejecutar(_coro_exito)
    assert resultado == "ok"
    assert cb.estado == EstadoCircuito.CERRADO, "Debe estar CERRADO"
    assert cb._fallos_consecutivos == 0, "fallos debe ser 0 al cerrar"
    print("   ✅ INV-A3 PASADO: _fallos_consecutivos = 0 al cerrar")


# ═════════════════════════════════════════════════════════════
# INV-A4: 401/403 NO incrementan _fallos_consecutivos
# ═════════════════════════════════════════════════════════════

async def test_inv_a4():
    print("\n🧪 INV-A4: 401/403 NO incrementan _fallos_consecutivos")
    umbral = 3
    cb = CircuitBreaker(umbral_fallos=umbral, timeout_apertura=10.0)

    # N+5 peticiones con 401
    total_401 = umbral + 5
    for _ in range(total_401):
        try:
            await cb.ejecutar(_coro_fallo_401)
        except Exception:
            pass

    assert cb.estado == EstadoCircuito.CERRADO, "Debe seguir CERRADO tras 401s"
    assert cb._fallos_consecutivos == 0, "fallos debe ser 0 (401 no cuenta)"

    # Lo mismo con 403
    for _ in range(total_401):
        try:
            await cb.ejecutar(_coro_fallo_403)
        except Exception:
            pass

    assert cb.estado == EstadoCircuito.CERRADO, "Debe seguir CERRADO tras 403s"
    assert cb._fallos_consecutivos == 0, "fallos debe ser 0 (403 no cuenta)"
    print(f"   ✅ INV-A4 PASADO ({total_401*2} peticiones 401+403 → circuito sigue CERRADO)")


# ═════════════════════════════════════════════════════════════
# INV-B1: TokenManager no tiene atributos del CB
# ═════════════════════════════════════════════════════════════

async def test_inv_b1():
    print("\n🧪 INV-B1: TokenManager no tiene atributos del CircuitBreaker")
    tm = TokenManager(base_url="http://localhost:3000")

    # Verificar que TM no tiene atributos relacionados con el circuito
    atributos_tm = dir(tm)
    prohibidos = ['_estado', '_circuito', '_breaker', '_open', '_closed', '_semabierto']
    atributos_sospechosos = []
    for attr in atributos_tm:
        attr_lower = attr.lower()
        if any(p in attr_lower for p in ['circuit', 'breaker', '_open', '_closed']):
            if not attr.startswith('__'):
                atributos_sospechosos.append(attr)

    assert len(atributos_sospechosos) == 0, f"TM tiene atributos sospechosos: {atributos_sospechosos}"
    assert not hasattr(tm, '_estado'), "TM no debe tener _estado"
    assert not hasattr(tm, '_breaker'), "TM no debe tener _breaker"

    print("   ✅ INV-B1 PASADO: TM no tiene atributos del CircuitBreaker")


# ═════════════════════════════════════════════════════════════
# INV-B2: Token nunca aparece en logs
# ═════════════════════════════════════════════════════════════

async def test_inv_b2():
    print("\n🧪 INV-B2: Token nunca aparece en logs")

    import io

    # Capturar logs
    log_capture = io.StringIO()
    handler = logging.StreamHandler(log_capture)
    handler.setLevel(logging.DEBUG)
    logger = logging.getLogger("token_manager")
    nivel_previo = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    try:
        tm = TokenManager(base_url="http://localhost:3000")
        tm.store_tokens("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJvcDEiLCJyb2wiOiJ2aWV3ZXIiLCJleHAiOjk5OTk5OTk5OTl9.mock_sig", "mock_refresh")

        # Verificar get_auth_header no loguea el token
        header = tm.get_auth_header()
        log_contents = log_capture.getvalue()
        assert "mock_sig" not in log_contents, "Token no debe aparecer en logs"
        assert "eyJhbGciOiJIUzI1NiJ9" not in log_contents, "Token parcial no debe aparecer"

        # Verificar decode_payload no loguea el token
        try:
            payload = tm.decode_payload(tm.access_token)
        except Exception:
            pass

        log_contents = log_capture.getvalue()
        assert "mock_sig" not in log_contents, "Token no debe filtrar en decode"
    finally:
        logger.removeHandler(handler)
        logger.setLevel(nivel_previo)
        handler.close()


    print("   ✅ INV-B2 PASADO: Token no aparece en logs")


# ═════════════════════════════════════════════════════════════
# INV-B3: Refresh singleton con concurrencia
# ═════════════════════════════════════════════════════════════

async def test_inv_b3():
    print("\n🧪 INV-B3: Refresh singleton — solo 1 refresh con 5 peticiones concurrentes")
    tm = CountingRefreshTokenManager()
    tm.store_tokens(_jwt_con_exp(int(time.time()) - 10), "mock_refresh")

    resultados = await asyncio.gather(
        *(tm.refresh_access_token() for _ in range(5))
    )

    assert tm.refresh_calls == 1, f"Esperaba 1 refresh real, obtuve {tm.refresh_calls}"
    assert len(set(resultados)) == 1, "Todas las corutinas deben recibir el mismo token fresco"
    assert not tm.is_expiring_soon(), "El token fresco no debe considerarse expirando"
    await tm.close()
    print("   ✅ INV-B3 PASADO: 5 corutinas compartieron 1 refresh real")


# ═════════════════════════════════════════════════════════════
# TC-X2: Token expira mientras CB en SEMIABIERTO (prueba automatizada)
# ═════════════════════════════════════════════════════════════

async def test_tc_x2():
    print("\n🧪 TC-X2: Token expira mientras CB en SEMIABIERTO")
    print("   Verifica que el refresh ocurre ANTES de la peticion de prueba")

    eventos = []
    tm = FakeExpiringTokenManager(eventos)
    cliente = ClienteRobusto(
        token_manager=tm,
        umbral_fallos=2,
        timeout_apertura=0.05,
        base_url="http://localhost:3000/api",
        max_retries=0,
    )
    cliente._session = FakeSession(eventos)
    cb = cliente.circuit_breaker

    # Abrir el circuito.
    for _ in range(2):
        try:
            await cb.ejecutar(_coro_fallo_503)
        except Exception:
            pass
    assert cb.estado == EstadoCircuito.ABIERTO

    # Esperar a SEMIABIERTO.
    await asyncio.sleep(0.08)
    assert cb.estado == EstadoCircuito.SEMIABIERTO

    resultado = await cliente.get("/inventario")

    assert resultado["ok"] is True
    assert tm.refresh_calls == 1, "Debe ejecutarse exactamente 1 refresh"
    assert cliente._session.requests == 1, "Debe llegar exactamente 1 peticion de prueba al mock"
    assert eventos.index("refresh") < eventos.index("request"), eventos
    assert cliente._session.headers[0]["Authorization"] == "Bearer token_fresco"
    assert cb.estado == EstadoCircuito.CERRADO
    assert cb._fallos_consecutivos == 0
    await cliente.cerrar()
    print("   ✅ TC-X2 PASADO: refresh=1, peticion_mock=1, orden refresh→request")


# ═════════════════════════════════════════════════════════════
# RUNNER
# ═════════════════════════════════════════════════════════════

async def main():
    print("=" * 60)
    print("🧪 Validacion de Invariantes — Semana 10 Grand Deploy")
    print("=" * 60)

    tests = [
        ("INV-A1", test_inv_a1),
        ("INV-A2", test_inv_a2),
        ("INV-A3", test_inv_a3),
        ("INV-A4", test_inv_a4),
        ("INV-B1", test_inv_b1),
        ("INV-B2", test_inv_b2),
        ("INV-B3", test_inv_b3),
        ("TC-X2", test_tc_x2),
    ]

    pasados = 0
    fallidos = 0
    omitidos = 0

    for nombre, test in tests:
        try:
            await test()
            pasados += 1
        except AssertionError as e:
            print(f"   ❌ {nombre} FALLO: {e}")
            fallidos += 1
        except Exception as e:
            print(f"   ❌ {nombre} ERROR INESPERADO: {e}")
            fallidos += 1

    print("\n" + "=" * 60)
    print(f"📊 RESULTADO: {pasados} pasados / {fallidos} fallidos / {omitidos} omitidos / {len(tests)} total")
    print("=" * 60)

    return fallidos == 0


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
