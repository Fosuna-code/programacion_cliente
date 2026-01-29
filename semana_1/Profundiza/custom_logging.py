import time
import logging
from datetime import datetime
from functools import wraps

# Configuración básica del Logger
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("EcoMarket.Observability")

def observability_logger(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        # 1. Preparación de Metadatos
        method = func.__name__.upper().replace('_', ' ')
        url = f"{self.base_url}/..." # Simplificado para el log
        start_time = time.perf_counter()
        timestamp = datetime.now().isoformat()
        
        # Función auxiliar para ocultar secretos
        def scrub_headers(headers):
            scrubbed = dict(headers)
            if 'Authorization' in scrubbed:
                scrubbed['Authorization'] = "Bearer ********"
            return scrubbed

        try:
            # Ejecución de la petición
            response = func(self, *args, **kwargs)
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            # 2. Extracción de datos de respuesta
            status_code = response.status_code
            size_bytes = len(response.content)
            headers_sent = scrub_headers(response.request.headers)
            
            log_msg = (
                f"[{timestamp}] {func.__name__} | {status_code} | "
                f"{duration_ms:.2f}ms | {size_bytes} bytes"
            )

            # 3. Lógica de Niveles de Log
            if duration_ms > 2000:
                logger.warning(f"🐢 PETICIÓN LENTA: {log_msg}")
            elif 200 <= status_code < 300:
                logger.info(f"✅ {log_msg}")
                logger.debug(f"Headers Enviados: {headers_sent}")
            else:
                logger.error(f"❌ ERROR SEMÁNTICO: {log_msg}")

            return response

        except Exception as e:
            # Manejo de fallos críticos de red
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                f"💥 FALLO CRÍTICO: [{timestamp}] {func.__name__} | "
                f"Excepción: {type(e).__name__} | {duration_ms:.2f}ms"
            )
            raise e
            
    return wrapper


    if __name__ == "__main__":
        print("Profe este archivo es solo para mostrar el decorador, no tiene funcionalidad por si solo")
        print("Para ver su funcionamiento, ejecutar el archivo cliente_con_loggin.py")