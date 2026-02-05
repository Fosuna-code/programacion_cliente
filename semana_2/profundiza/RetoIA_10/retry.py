import time
import random
import logging
from functools import wraps

# Configuración básica de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RetrySystem")

def with_retry(max_retries=3, initial_delay=1, backoff_factor=2, jitter=0.5):
    """
    Decorador para reintentar funciones con Exponential Backoff y Jitter.
    
    Args:
        max_retries (int): Número máximo de intentos fallidos antes de rendirse.
        initial_delay (float): Tiempo de espera inicial en segundos.
        backoff_factor (int): Multiplicador para el tiempo de espera (1s, 2s, 4s...).
        jitter (float): Rango máximo de aleatoriedad añadida en segundos.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            delay = initial_delay

            while True:
                try:
                    return func(*args, **kwargs)
                
                except Exception as e:
                    # 1. Determinar si debemos reintentar
                    status_code = getattr(e, 'response', None) and getattr(e.response, 'status_code', None)
                    
                    # Si es un error 4xx (Cliente), NO reintentar y lanzar error inmediatamente
                    if status_code and 400 <= status_code < 500:
                        logger.error(f"Error 4xx detectado ({status_code}). No se reintenta.")
                        raise e

                    # Si llegamos al límite de intentos, lanzar la última excepción
                    if retries >= max_retries:
                        logger.error(f"Max reintentos alcanzados ({max_retries}) para {func.__name__}. Error final: {e}")
                        raise e

                    # 2. Calcular Backoff Exponencial
                    # Formula: delay * (factor ^ retries)
                    calc_delay = delay * (backoff_factor ** retries)
                    
                    # 3. Agregar Jitter (Aleatoriedad)
                    # Esto evita que todos los clientes reintenten al unísono exacto
                    actual_delay = calc_delay + random.uniform(0, jitter)

                    logger.warning(
                        f"Fallo detectado ({e}). Reintentando {func.__name__} en {actual_delay:.2f}s "
                        f"(Intento {retries + 1}/{max_retries})"
                    )
                    
                    time.sleep(actual_delay)
                    retries += 1
        return wrapper
    return decorator