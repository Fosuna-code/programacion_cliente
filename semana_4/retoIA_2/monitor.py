import logging
import os

if os.path.exists("validacion.log"):
    os.remove("validacion.log")

for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

logging.basicConfig(
    filename="validacion.log",
    filemode="w",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


class Observable:
    def __init__(self):
        # Dictionary: keys are event names, values are lists of callback functions
        self._observers = {}

    def suscribir(self, evento, callback):
        """Adds a callback to a specific event."""
        # If it's the first subscription to this event, create the list
        if evento not in self._observers:
            self._observers[evento] = []

        # Add the callback to the list for that event
        self._observers[evento].append(callback)

    def desuscribir(self, evento, callback):
        """Removes a specific callback from an event."""
        if evento in self._observers:
            try:
                self._observers[evento].remove(callback)
            except ValueError:
                # Handle cases where the callback might not be in the list
                pass

    async def notificar(self, evento, datos=None):
        """Executes all callbacks subscribed to the event with the provided data."""
        if evento in self._observers:
            for cb in self._observers[evento]:
                try:
                    if asyncio.iscoroutinefunction(cb):
                        await cb(datos)
                    else:
                        cb(datos)
                except Exception as e:
                    logging.error(f"Observador falló en evento '{evento}': {e}")


# --- Example Usage (Inheritance) ---
import asyncio
import aiohttp
import json
from datetime import datetime

from cliente_async_ecomarket import listar_productos, BASE_URL, TIMEOUT


class ServicioPolling(Observable):
    def __init__(self, intervalo_seg):
        super().__init__()
        self.url_base = BASE_URL
        self.intervalo_base = intervalo_seg
        self.intervalo_actual = intervalo_seg
        self.intervalo_max = 60
        self._ultima_lista = None
        self._activo = False

    async def iniciar(self):
        self._activo = True
        print(f"[*] Iniciando monitoreo en {self.url_base}...")

        while self._activo:
            await self._consultar()
            await asyncio.sleep(self.intervalo_actual)

    async def _consultar(self):
        try:
            async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
                productos = await listar_productos(session)

            lista_actual = json.dumps(productos, sort_keys=True)

            if self._ultima_lista is None:
                self._ultima_lista = lista_actual
                self.intervalo_actual = self.intervalo_base
                await self.notificar("datos_actualizados", productos)

            elif lista_actual != self._ultima_lista:
                self._ultima_lista = lista_actual
                self.intervalo_actual = self.intervalo_base
                await self.notificar("datos_actualizados", productos)

            else:
                self.intervalo_actual = min(
                    self.intervalo_actual * 1.5, self.intervalo_max
                )
                print(
                    f"[!] Sin cambios. Aumentando intervalo a {self.intervalo_actual:.1f}s"
                )

        except Exception as e:
            print(f"Error inesperado: {e}")
            self.intervalo_actual = self.intervalo_max
            await self.notificar("error_servidor", str(e))

    def detener(self):
        self._activo = False
        print("[!] Deteniendo servicio...")


# === USO en EcoMarket ===


async def actualizar_ui(datos):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] UI Actualizada: {datos}")


async def mostrar_error(codigo):
    print(f"Error en servidor: {codigo}. Reintentando en el fondo...")


async def guardar_validacion(datos):
    logging.info(f"Validación: {datos}")


async def main():
    monitor = ServicioPolling(5)

    # Suscribir funciones
    monitor.suscribir("datos_actualizados", actualizar_ui)
    monitor.suscribir("datos_actualizados", guardar_validacion)
    monitor.suscribir("error_servidor", mostrar_error)

    # Iniciar el loop (se puede cancelar con Ctrl+C)
    try:
        await monitor.iniciar()
    except KeyboardInterrupt:
        monitor.detener()


if __name__ == "__main__":
    asyncio.run(main())
