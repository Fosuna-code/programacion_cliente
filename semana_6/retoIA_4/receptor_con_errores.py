"""
CLIENTE SSE CON ERRORES — Generado para auditoría (RetoIA_4)
=============================================================
Este código fue generado intencionalmente con 4 errores sutiles
que violan invariantes del cliente SSE robusto.

INSTRUCCIÓN: Encuentra los 4 errores antes de leer auditoria_sse.md.
Los 6 invariantes que un cliente SSE robusto NO debe romper:
  1. Buffer reseteado completamente después de cada mensaje
  2. Timeout de 30s configurado en la conexión inicial
  3. Last-Event-ID enviado en reconexión
  4. Máximo 5 intentos de reconexión (con backoff)
  5. Excepción en handler no cierra el stream
  6. 204 No Content detiene reconexión permanentemente

¿Encuentras los 4 errores?
"""

import asyncio
import json
from datetime import datetime
from typing import Optional

try:
    import httpx
except ImportError:
    raise SystemExit("pip install httpx")


# ════════════════════════════════════════════════════════════════════
# CÓDIGO CON ERRORES — para auditoría del RetoIA_4
# ════════════════════════════════════════════════════════════════════

class ReceptorAuditado:
    """
    Cliente SSE para EcoMarket.
    ¿Puedes encontrar los 4 errores antes de ejecutarlo?
    """

    def __init__(self, url: str):
        self.url = url
        self._activo = False
        self._ultimo_id: Optional[str] = None
        self.retry_ms = 3000
        self.max_reintentos = 5

    async def iniciar(self):
        self._activo = True
        reintentos = 0

        while self._activo:
            try:
                await self._consumir_stream()
                reintentos = 0

            except httpx.TimeoutException:
                reintentos += 1
                print(f"Timeout. Intento {reintentos}/{self.max_reintentos}")

            except httpx.ConnectError as e:
                reintentos += 1
                print(f"Error de conexión: {e}. Intento {reintentos}/{self.max_reintentos}")

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 204:
                    print("204 No Content — fin del stream.")
                    # ERROR #3 ESTÁ AQUÍ
                    reintentos += 1  # BUG: 204 debería detener el ciclo completamente
                    # pero solo incrementa el contador y sigue intentando

            if not self._activo:
                break

            if reintentos >= self.max_reintentos:
                print("Máximo de reintentos alcanzado.")
                self._activo = False
                break

            espera = self.retry_ms / 1000
            await asyncio.sleep(espera)  # ERROR #4 ESTÁ AQUÍ: sin backoff exponencial

    def detener(self):
        self._activo = False

    async def _consumir_stream(self):
        headers = {
            "Accept": "text/event-stream",
        }
        # ERROR #1 ESTÁ AQUÍ: falta Last-Event-ID en headers de reconexión
        # (se guarda _ultimo_id pero nunca se envía)

        timeout = httpx.Timeout(
            connect=None,  # ERROR #2 ESTÁ AQUÍ: connect=None = sin timeout de conexión
            read=None,
            write=10.0,
            pool=5.0,
        )

        async with httpx.AsyncClient() as cliente:
            async with cliente.stream(
                "GET", self.url, headers=headers, timeout=timeout
            ) as respuesta:
                respuesta.raise_for_status()

                buffer: dict = {}  # buffer declarado fuera del bucle ✓

                async for linea in respuesta.aiter_lines():
                    if not self._activo:
                        break

                    evento = self._parsear_linea(linea, buffer)
                    if evento:
                        self._procesar_evento(evento)

    def _parsear_linea(self, linea: str, buffer: dict):
        if linea == "":
            if not buffer.get("data"):
                buffer.clear()
                return None

            evento = {
                "id": buffer.get("id"),
                "event": buffer.get("event", "message"),
                "data": buffer.get("data", ""),
            }
            buffer.clear()
            return evento

        if linea.startswith(":"):
            return None

        if ":" in linea:
            campo, _, valor = linea.partition(":")
            valor = valor.lstrip(" ")
        else:
            campo = linea
            valor = ""

        if campo == "id":
            buffer["id"] = valor
        elif campo == "event":
            buffer["event"] = valor
        elif campo == "data":
            if "data" in buffer:
                buffer["data"] += "\n" + valor
            else:
                buffer["data"] = valor
        elif campo == "retry":
            try:
                self.retry_ms = int(valor)
            except ValueError:
                pass

        return None

    def _procesar_evento(self, evento: dict):
        ts = datetime.now().strftime("%H:%M:%S")

        if evento.get("id"):
            self._ultimo_id = evento["id"]

        tipo = evento.get("event", "message")
        datos = evento.get("data", "")

        print(f"[{ts}] Evento id={evento.get('id')} | tipo={tipo}")

        if tipo == "precio-actualizado":
            # BUG latente: si json.loads() falla aquí, la excepción NO está
            # capturada → se propaga hacia _consumir_stream() y CIERRA el stream
            # (Este es el quinto problema si el docente quiere 5, pero el enunciado
            #  pide 4; los 4 principales están numerados arriba)
            datos_dict = json.loads(datos)
            print(f"  💰 Precio: {datos_dict.get('producto')} = {datos_dict.get('precio')}")

        elif tipo == "stock-critico":
            datos_dict = json.loads(datos)
            print(f"  ⚠️ Stock crítico: {datos_dict.get('producto')}")

        else:
            print(f"  [ADVERTENCIA] Evento desconocido: {tipo}")


async def main():
    receptor = ReceptorAuditado("https://sse.dev/test")
    try:
        await receptor.iniciar()
    except KeyboardInterrupt:
        receptor.detener()


if __name__ == "__main__":
    asyncio.run(main())
