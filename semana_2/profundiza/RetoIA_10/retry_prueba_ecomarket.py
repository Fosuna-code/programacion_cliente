import sys
import os
import logging

# Añadir ruta para importar cliente_ecomarket
# cliente_ecomarket.py está en ../Aplica/RetoIA_3 relativo a este archivo
current_dir = os.path.dirname(os.path.abspath(__file__))
client_path = os.path.join(current_dir, '..', 'Aplica', 'RetoIA_3')
sys.path.append(client_path)

# Importar la función original y excepciones
from cliente_ecomarket import obtener_producto, ServerError, EcoMarketError

# Importar el decorador de retry
from retry import with_retry, logger

# Implementar obtener_producto con retry
# Usamos el decorador con parámetros personalizados
@with_retry(max_retries=3, initial_delay=1, backoff_factor=2)
def obtener_producto_con_retry(producto_id):
    """
    Versión con retry de obtener_producto.
    Reintentará automáticamente en caso de ServerError o excepciones no manejadas
    que no sean errores del cliente (4xx).
    """
    return obtener_producto(producto_id)

if __name__ == "__main__":
    print("Iniciando prueba de obtener_producto con retry...")
    
    # Pruebo con un ID que debería funcionar si el servidor está activo
    try:
        # ID 1 suele existir en datos de prueba
        producto = obtener_producto_con_retry(1)
        print(f"Producto obtenido exitosamente: {producto}")
    except Exception as e:
        print(f"Error al obtener producto tras reintentos: {e}")
