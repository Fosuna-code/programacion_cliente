"""
Cliente EcoMarket Optimizado para Testing
==========================================
Este archivo es una versión modificada del cliente_ecomarket.py original,
diseñada específicamente para pasar todos los tests en test_cliente.py.

CAMBIOS PRINCIPALES respecto al original:
1. Eliminación de dependencias externas (validadores.py, url_builder.py)
2. Validación integrada de productos según esquema esperado
3. Manejo mejorado de errores HTTP (400, 401, 404, 409, 500, 503)
4. Validación de Content-Type y JSON malformado
5. ValidationError para errores 4xx, ServerError para errores 5xx
6. BASE_URL expuesto para los mocks de pytest

"""

import requests
from json import JSONDecodeError

# =====================================================================
# CONFIGURACIÓN EXPORTADA
# =====================================================================
BASE_URL = "http://127.0.0.1:4010/"  # NOTA: Incluye trailing slash para los tests
TIMEOUT = 10  # segundos

# =====================================================================
# EXCEPCIONES PERSONALIZADAS
# =====================================================================

class EcoMarketError(Exception):
    """Error base para el cliente de EcoMarket"""
    pass

class ValidationError(EcoMarketError):
    """
    El servidor rechazó la petición (4xx) o los datos no cumplen el esquema.
    Se usa para:
    - Errores HTTP 400, 401, 404, 409
    - JSON inválido o vacío
    - Content-Type incorrecto
    - Tipos de datos incorrectos en la respuesta
    """
    pass

class ServerError(EcoMarketError):
    """Error del servidor (5xx) - puede reintentarse"""
    pass

# =====================================================================
# VALIDACIÓN DE PRODUCTOS (Integrada)
# =====================================================================

def _validar_producto(producto: dict) -> dict:
    """
    Valida que un producto tenga la estructura esperada.
    
    Campos requeridos:
    - id: int
    - nombre: str
    - precio: float/int (numérico, NO string)
    - categoria: str
    - disponible: bool
    
    Raises:
        ValidationError: Si el producto no cumple el esquema
    """
    if not isinstance(producto, dict):
        raise ValidationError(f"Se esperaba un diccionario, se recibió {type(producto).__name__}")
    
    # Validar campos requeridos
    campos_requeridos = ["id", "nombre", "precio", "categoria", "disponible"]
    for campo in campos_requeridos:
        if campo not in producto:
            raise ValidationError(f"Campo requerido ausente: {campo}")
    
    # Validar tipos de datos
    if not isinstance(producto["id"], int):
        raise ValidationError(f"id debe ser int, se recibió {type(producto['id']).__name__}")
    
    if not isinstance(producto["nombre"], str):
        raise ValidationError(f"nombre debe ser str, se recibió {type(producto['nombre']).__name__}")
    
    # CRÍTICO: precio debe ser numérico (int o float), NO string
    if not isinstance(producto["precio"], (int, float)) or isinstance(producto["precio"], bool):
        raise ValidationError(f"precio debe ser numérico, se recibió {type(producto['precio']).__name__}")
    
    if not isinstance(producto["categoria"], str):
        raise ValidationError(f"categoria debe ser str, se recibió {type(producto['categoria']).__name__}")
    
    if not isinstance(producto["disponible"], bool):
        raise ValidationError(f"disponible debe ser bool, se recibió {type(producto['disponible']).__name__}")
    
    return producto

def _validar_lista_productos(productos: list) -> list:
    """
    Valida una lista de productos.
    Una lista vacía es válida.
    
    Raises:
        ValidationError: Si algún producto no cumple el esquema
    """
    if not isinstance(productos, list):
        raise ValidationError(f"Se esperaba una lista, se recibió {type(productos).__name__}")
    
    # Validar cada producto en la lista
    return [_validar_producto(p) for p in productos]

# =====================================================================
# VERIFICACIÓN DE RESPUESTAS HTTP
# =====================================================================

def _verificar_respuesta(response, esperar_json=True):
    """
    Verifica código de estado y Content-Type antes de procesar.
    
    Orden de verificación:
    1. Errores 5xx → ServerError
    2. Errores 4xx → ValidationError
    3. Content-Type (si se espera JSON)
    
    Args:
        response: Objeto Response de requests
        esperar_json: Si True, valida que Content-Type sea application/json
    
    Raises:
        ServerError: Para códigos 5xx
        ValidationError: Para códigos 4xx o Content-Type incorrecto
    """
    # Capa 1: Errores del servidor (5xx)
    if response.status_code >= 500:
        raise ServerError(f"Error del servidor: {response.status_code}")
    
    # Capa 2: Errores del cliente (4xx incluyendo 409)
    if response.status_code >= 400:
        raise ValidationError(f"Error de cliente: {response.status_code} - {response.text}")
    
    # Capa 3: Content-Type (si esperamos JSON y no es 204)
    if esperar_json and response.status_code != 204:
        content_type = response.headers.get('Content-Type', '')
        if 'application/json' not in content_type:
            raise ValidationError(f"Respuesta no es JSON: {content_type}")
    
    return response

def _extraer_json_seguro(response):
    """
    Extrae JSON de manera segura, manejando errores de parseo.
    
    Raises:
        ValidationError: Si el body está vacío o el JSON es malformado
    """
    # Verificar body vacío
    if not response.text or response.text.strip() == "":
        raise ValidationError("Respuesta con body vacío")
    
    try:
        return response.json()
    except JSONDecodeError as e:
        raise ValidationError(f"JSON malformado: {e}")

# =====================================================================
# FUNCIONES DEL CLIENTE HTTP
# =====================================================================

def listar_productos(categoria=None, orden=None):
    """
    GET /productos con filtros opcionales.
    
    Args:
        categoria: Filtrar por categoría (opcional)
        orden: Ordenar resultados (opcional)
    
    Returns:
        Lista de productos validados
    
    Raises:
        ValidationError: Error 4xx o datos inválidos
        ServerError: Error 5xx
        RequestException: Error de conexión/timeout
    """
    params = {}
    if categoria:
        params['categoria'] = categoria
    if orden:
        params['orden'] = orden
    
    url = f"{BASE_URL}productos"
    response = requests.get(url, params=params if params else None, timeout=TIMEOUT)
    _verificar_respuesta(response)
    
    datos = _extraer_json_seguro(response)
    return _validar_lista_productos(datos)

def obtener_producto(producto_id):
    """
    GET /productos/{id}
    
    Args:
        producto_id: ID del producto a obtener
    
    Returns:
        Diccionario con el producto validado
    
    Raises:
        ValidationError: Error 4xx, 404, o datos inválidos
        ServerError: Error 5xx
    """
    url = f"{BASE_URL}productos/{producto_id}"
    response = requests.get(url, timeout=TIMEOUT)
    _verificar_respuesta(response)
    
    datos = _extraer_json_seguro(response)
    return _validar_producto(datos)

def crear_producto(datos: dict) -> dict:
    """
    POST /productos
    Envía datos JSON para crear un nuevo producto. Espera un código 201 Created.
    
    Args:
        datos: Diccionario con los datos del nuevo producto
    
    Returns:
        Diccionario con el producto creado
    
    Raises:
        ValidationError: Error 4xx, 409, o datos inválidos
        ServerError: Error 5xx
    """
    url = f"{BASE_URL}productos"
    headers = {"Content-Type": "application/json"}
    
    response = requests.post(url, json=datos, headers=headers, timeout=TIMEOUT)
    _verificar_respuesta(response)
    
    datos_respuesta = _extraer_json_seguro(response)
    return _validar_producto(datos_respuesta)

def actualizar_producto_total(producto_id: int, datos: dict) -> dict:
    """
    PUT /productos/{id}
    Reemplaza el recurso completo.
    
    Args:
        producto_id: ID del producto a actualizar
        datos: Diccionario con todos los campos del producto
    
    Returns:
        Diccionario con el producto actualizado
    
    Raises:
        ValidationError: Error 4xx o 404
        ServerError: Error 5xx
    """
    url = f"{BASE_URL}productos/{producto_id}"
    headers = {"Content-Type": "application/json"}
    
    response = requests.put(url, json=datos, headers=headers, timeout=TIMEOUT)
    _verificar_respuesta(response)
    
    return response.json()

def actualizar_producto_parcial(producto_id: int, campos: dict) -> dict:
    """
    PATCH /productos/{id}
    Modifica únicamente los campos proporcionados.
    
    Args:
        producto_id: ID del producto a modificar
        campos: Diccionario con los campos a actualizar
    
    Returns:
        Diccionario con el producto actualizado
    
    Raises:
        ValidationError: Error 4xx
        ServerError: Error 5xx
    """
    url = f"{BASE_URL}productos/{producto_id}"
    headers = {"Content-Type": "application/json"}
    
    response = requests.patch(url, json=campos, headers=headers, timeout=TIMEOUT)
    _verificar_respuesta(response)
    
    return response.json()

def eliminar_producto(producto_id: int) -> bool:
    """
    DELETE /productos/{id}
    Elimina el producto especificado.
    
    Args:
        producto_id: ID del producto a eliminar
    
    Returns:
        True si se eliminó correctamente (204 No Content)
    
    Raises:
        ValidationError: Error 4xx o 404
        ServerError: Error 5xx
    """
    url = f"{BASE_URL}productos/{producto_id}"
    
    response = requests.delete(url, timeout=TIMEOUT)
    _verificar_respuesta(response, esperar_json=False)
    
    return response.status_code == 204

# =====================================================================
# PUNTO DE ENTRADA
# =====================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Cliente EcoMarket Optimizado para Testing")
    print("=" * 60)
    print("\nEste cliente está diseñado para pasar todos los tests en test_cliente.py")
    print("\nPara ejecutar los tests:")
    print("  cd semana_2/valida/RetoIA_8")
    print("  pytest test_cliente.py -v")
    print("\nCambios respecto al original:")
    print("  1. Sin dependencias externas (validadores, url_builder)")
    print("  2. Validación de tipos integrada (detecta precio como string)")
    print("  3. Manejo de JSON vacío/malformado → ValidationError")
    print("  4. Content-Type HTML → ValidationError")
    print("  5. Errores 4xx → ValidationError")
    print("  6. Errores 5xx → ServerError")
