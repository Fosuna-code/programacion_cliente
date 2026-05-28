"""
DECISIONES DE DISEÑO — Cliente EcoMarket / Hito 1
==================================================
[TIMEOUT HTTP]: 10 segundos → Trade-off: Se evitan falsos positivos por redes lentas y bloqueos indefinidos de los hilos de ejecución, aunque se sacrifica la tolerancia a conexiones legítimamente inestables que podrían tardar más de 10 segundos. Decisión: Adecuado para EcoMarket porque prioriza una respuesta rápida (o un fallo rápido) en la interfaz del cliente, mejorando la experiencia del usuario final.

[ESTRATEGIA DE REINTENTOS]: Backoff exponencial (inicio 5s, factor 1.5x, máximo 60s) con intentos infinitos → Trade-off: Se gana resiliencia y se protege al servidor evitando saturarlo, pero se sacrifica el rendimiento del cliente, arriesgando un consumo innecesario de batería y memoria si el servidor nunca se recupera. Decisión: Tu justificación sobre los intentos infinitos fue algo vaga al inicio, aunque reconociste la necesidad de cambiarlo; para EcoMarket, el escalado de tiempo es correcto, pero será vital poner un límite de intentos para no drenar el dispositivo del cliente.

[MONITOR DE INVENTARIO]: Short polling → Trade-off: Se gana mucha facilidad y velocidad de integración en el código, pero se sacrifica drásticamente la batería y el rendimiento de red en clientes móviles por despertar constantemente la antena. Decisión: Aceptable para la etapa temprana de EcoMarket por su simplicidad, aunque tu justificación de que "gasta menos recursos" es inexacta en contextos móviles, siendo un punto crítico a optimizar en futuros hitos.

[PATRÓN OBSERVER]: 2 observadores iniciales (UI y Alertas) suscritos desde el main → Trade-off: Se gana una excelente mantenibilidad y se respeta el principio Open/Closed, a costa de una ligera complejidad arquitectónica inicial frente a tener un código espagueti directo. Decisión: Excelente para EcoMarket, ya que garantiza que el sistema cliente pueda escalar fácilmente agregando nuevas vías de notificación (como correos o push) sin tocar la lógica del monitor de inventario.

[PRIORIDAD DE REFACTORIZACIÓN]: Desacoplamiento y planeación sobre funcionalidad pura → Trade-off: Se sacrifica velocidad de entrega a corto plazo para ganar un código mantenible, limpio y escalable a largo plazo, reduciendo la deuda técnica. Decisión: Es la mentalidad correcta para EcoMarket; asegurar que las piezas del cliente sean modulares permitirá que el proyecto no colapse sobre su propio peso conforme agregues más características.
"""
import asyncio
import aiohttp
import logging
from abc import ABC, abstractmethod

# Configuración básica de logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# =============================================================================
# Interfaz Observador (proporcionada, no reimplementar)
# =============================================================================
class Observador(ABC):
    @abstractmethod
    def actualizar(self, datos):
        pass

# =============================================================================
# Observable (proporcionado, no reimplementar)
# =============================================================================
class Observable:
    def __init__(self):
        self._observadores = []

    def suscribir(self, observador):
        if observador not in self._observadores:
            self._observadores.append(observador)
        
    def desuscribir(self, observador):
        if observador in self._observadores:
            self._observadores.remove(observador)
        
    def _notificar(self, datos):
        # llama a actualizar() de cada obs
        for observador in self._observadores:
            observador.actualizar(datos)

# =============================================================================
# IMPLEMENTACIÓN DEL SIMULACRO
# =============================================================================
class MonitorPedidos(Observable):
    INTERVALO_BASE = 5.0  # Segundos
    MAX_INTERVALO = 60.0  # Tope para el backoff

    def __init__(self, base_url, sesion_http):
        super().__init__()
        # Guardar url y sesión
        self.base_url = base_url.rstrip("/")
        self.sesion_http = sesion_http
        
        # Inicializar bandera ejecutando = False
        self.ejecutando = False
        
        # Inicializar intervalo_actual = INTERVALO_BASE
        self.intervalo_actual = self.INTERVALO_BASE
        
        # Inicializar ultimo_estado = None (para detectar cambios)
        self.ultimo_estado = None

    async def _consultar_pedidos(self):
        url = f"{self.base_url}/pedidos"
        # GET a /pedidos con timeout y manejo de errores
        timeout = aiohttp.ClientTimeout(total=10.0)
        
        try:
            async with self.sesion_http.get(url, timeout=timeout) as respuesta:
                # Manejar 4xx vs 5xx de forma diferenciada
                if respuesta.status >= 500:
                    logger.error(f"Error del Servidor (5xx) al consultar API: HTTP {respuesta.status}")
                    return None
                elif respuesta.status >= 400:
                    logger.warning(f"Error del Cliente (4xx) al consultar API: HTTP {respuesta.status}")
                    return None
                
                respuesta.raise_for_status()
                
                # Extraemos el JSON
                datos_api = await respuesta.json()
                
                # Devolver lista de pedidos o None si falla (extrayendo la clave correcta del payload)
                return datos_api.get("pedidos", [])
                
        # Manejar Timeout (no crashear, registrar warning)
        except asyncio.TimeoutError:
            logger.warning("Timeout: La API tardó demasiado en responder.")
            return None
        except Exception as e:
            logger.error(f"Error inesperado de red: {e}")
            return None

    async def iniciar(self):
        # Poner ejecutando = True
        self.ejecutando = True
        logger.info("Iniciando Monitor de Pedidos...")
        
        # Ciclo while ejecutando
        while self.ejecutando:
            # Llamar _consultar_pedidos()
            pedidos_actuales = await self._consultar_pedidos()
            
            if pedidos_actuales is not None:
                # Si hay cambios respecto al ultimo_estado → _notificar
                if pedidos_actuales != self.ultimo_estado:
                    self._notificar(pedidos_actuales)
                    self.ultimo_estado = pedidos_actuales
                    
                    # Reiniciamos el intervalo al base porque hubo cambios exitosos
                    self.intervalo_actual = self.INTERVALO_BASE
                else:
                    # Lógica de backoff (intervalo crece si no hay cambios)
                    self.intervalo_actual = min(self.intervalo_actual * 1.5, self.MAX_INTERVALO)
            else:
                # Si la consulta falló (None), también aplicamos backoff para no saturar la API caída
                self.intervalo_actual = min(self.intervalo_actual * 1.5, self.MAX_INTERVALO)
            
            # await sleep(intervalo)
            await asyncio.sleep(self.intervalo_actual)

    def detener(self):
        # ejecutando = False (cierre suave)
        self.ejecutando = False
        logger.info("Deteniendo Monitor de Pedidos...")

# =============================================================================
# Observadores — implementados
# =============================================================================
class ObservadorPedidosUI(Observador):
    def actualizar(self, pedidos):
        # Mostrar en consola los pedidos con formato legible
        print("\n" + "="*50)
        print("🖥️  [DASHBOARD UI] Estado de Pedidos Actualizado")
        print("="*50)
        if not pedidos:
            print("No hay pedidos registrados en este momento.")
        else:
            for pedido in pedidos:
                p_id = pedido.get('id', 'N/A')
                p_cliente = pedido.get('cliente', 'Desconocido')
                p_total = pedido.get('total', 0.0)
                p_status = pedido.get('status', 'DESCONOCIDO')
                print(f"📦 ID: {p_id: <6} | Cliente: {p_cliente: <8} | Total: ${p_total: <7.2f} | Estado: {p_status}")
        print("="*50 + "\n")

class ObservadorPedidosCriticos(Observador):
    def actualizar(self, pedidos):
        # Filtrar pedidos con status "RETRASADO" y mostrar alerta
        if not pedidos:
            return
            
        retrasados = [p for p in pedidos if p.get('status') == "RETRASADO"]
        
        if retrasados:
            print("!"*50)
            print("🚨 [ALERTA] SE DETECTARON PEDIDOS RETRASADOS 🚨")
            print("!"*50)
            for p in retrasados:
                print(f"⚠️  ATENCIÓN REQUERIDA: Pedido {p.get('id')} del cliente {p.get('cliente')} está RETRASADO.")
            print("!"*50 + "\n")

# =============================================================================
# Ejemplo de uso / Pruebas
# =============================================================================
async def main():
    # Usamos una URL ficticia
    URL_API = "ip de eccomarket"
    
    async with aiohttp.ClientSession() as sesion:
        monitor = MonitorPedidos(URL_API, sesion)
        
        # Instanciar y suscribir
        ui = ObservadorPedidosUI()
        alertas = ObservadorPedidosCriticos()
        monitor.suscribir(ui)
        monitor.suscribir(alertas)
        
        # Ejecutar en segundo plano
        tarea = asyncio.create_task(monitor.iniciar())
        
        # Simulamos que dejamos el monitor corriendo 15 segundos
        await asyncio.sleep(15)
        
        # Detener suavemente
        monitor.detener()
        await tarea

if __name__ == "__main__":
    asyncio.run(main())