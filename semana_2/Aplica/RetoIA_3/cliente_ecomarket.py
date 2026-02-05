import requests
import sys
import os

# Añadir retoIA_4 al path para importar validadores
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'retoIA_4'))
from validadores import validar_producto, validar_lista_productos, ValidationError as DataValidationError

# Añadir retoIA_5 al path para importar url_builder
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'RetoIA_5'))
from url_builder import URLBuilder

# Configuración centralizada
BASE_URL = "http://127.0.0.1:4010"
TIMEOUT = 10  # segundos

# Instancia del URLBuilder para construcción segura de URLs
url_builder = URLBuilder(BASE_URL)

class EcoMarketError(Exception):
    """Error base para el cliente de EcoMarket"""
    pass

class ValidationError(EcoMarketError):
    """El servidor rechazó la petición (4xx)"""
    pass

class ConflictError(EcoMarketError):
    """El servidor detectó un recurso duplicado o conflicto (409)"""
    pass

class ServerError(EcoMarketError):
    """Error del servidor (5xx) - puede reintentarse"""
    pass

def _verificar_respuesta(response):
    """Verifica código de estado y Content-Type antes de procesar."""
    # Capa 1: Manejo de errores específicos
    if response.status_code == 409:
        raise ConflictError(f"Conflicto: El recurso ya existe. {response.text}")
    
    if response.status_code >= 500:
        raise ServerError(f"Error del servidor: {response.status_code}")
    
    if response.status_code >= 400:
        raise ValidationError(f"Error de cliente: {response.status_code} - {response.text}")
    
    # Capa 2: Content-Type (si esperamos JSON)
    content_type = response.headers.get('Content-Type', '')
    if 'application/json' not in content_type:
        # El código 204 No Content no debe tener cuerpo
        if response.status_code != 204:  
            raise ValidationError(f"Respuesta no es JSON: {content_type}")
    
    return response

def listar_productos(categoria=None, orden=None):
    """GET /productos con filtros opcionales."""
    params = {}
    if categoria:
        params['categoria'] = categoria
    if orden:
        params['orden'] = orden
    
    url = url_builder.build_url("productos", query_params=params if params else None)
    
    response = requests.get(url, timeout=TIMEOUT)
    _verificar_respuesta(response)
    
    return validar_lista_productos(response.json())

def obtener_producto(producto_id):
    """GET /productos/{id}"""
    url = url_builder.build_url("productos/{}", path_params=[producto_id])
    
    response = requests.get(url, timeout=TIMEOUT)
    _verificar_respuesta(response)
    
    return validar_producto(response.json())

def crear_producto(datos: dict) -> dict:
    """
    POST /productos
    Envía datos JSON para crear un nuevo producto. Espera un código 201 Created.
    
    Ejemplo:
        nuevo = {"nombre": "Miel de Abeja", "precio": 150.0, "categoria": "miel"}
        producto = crear_producto(nuevo)
    """
    url = url_builder.build_url("productos")
    headers = {"Content-Type": "application/json"}
    
    response = requests.post(url, json=datos, headers=headers, timeout=TIMEOUT)
    _verificar_respuesta(response)
    
    if response.status_code != 201:
        raise ValidationError(f"Se esperaba 201 Created, se obtuvo {response.status_code}")
        
    return validar_producto(response.json())

def actualizar_producto_total(producto_id: int, datos: dict) -> dict:
    """
    PUT /productos/{id}
    Reemplaza el recurso completo. Es fundamental enviar todos los campos del producto.
    
    Ejemplo:
        datos_completos = {"nombre": "Miel Editada", "precio": 160.0, "categoria": "miel"}
        actualizado = actualizar_producto_total(42, datos_completos)
    """
    url = url_builder.build_url("productos/{}", path_params=[producto_id])
    headers = {"Content-Type": "application/json"}
    
    response = requests.put(url, json=datos, headers=headers, timeout=TIMEOUT)
    _verificar_respuesta(response)
    
    return response.json()

def actualizar_producto_parcial(producto_id: int, campos: dict) -> dict:
    """
    PATCH /productos/{id}
    Modifica únicamente los campos proporcionados sin afectar el resto del recurso.
    
    Ejemplo:
        solo_precio = {"precio": 180.0}
        actualizado = actualizar_producto_parcial(42, solo_precio)
    """
    url = url_builder.build_url("productos/{}", path_params=[producto_id])
    headers = {"Content-Type": "application/json"}
    
    response = requests.patch(url, json=campos, headers=headers, timeout=TIMEOUT)
    _verificar_respuesta(response)
    
    return response.json()

def eliminar_producto(producto_id: int) -> bool:
    """
    DELETE /productos/{id}
    Elimina el producto especificado. Espera un código 204 No Content.
    
    Ejemplo:
        exito = eliminar_producto(42) # Retorna True si se eliminó
    """
    url = url_builder.build_url("productos/{}", path_params=[producto_id])
    
    response = requests.delete(url, timeout=TIMEOUT)
    _verificar_respuesta(response)
    
    # El éxito en DELETE usualmente devuelve 204
    return response.status_code == 204

if __name__ == "__main__":
    print("Cliente EcoMarket, para saber si jalan las funciones esta el archivo test_client.py")