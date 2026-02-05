import pytest
import responses
import requests
import sys
from pathlib import Path

# Import from the optimized client in the same folder
from Cliente_optimizado_para_testing import (
    listar_productos, obtener_producto, crear_producto,
    actualizar_producto_total, actualizar_producto_parcial,
    eliminar_producto, ValidationError, ServerError, BASE_URL
)

# --- CONFIGURACIÓN DE DATOS DE PRUEBA ---
MOCK_PRODUCTO = {
    "id": 42,
    "nombre": "Miel orgánica",
    "precio": 150.0,
    "categoria": "miel",
    "disponible": True
}

# =================================================================
# 1. HAPPY PATH (6 TESTS)
# =================================================================

@responses.activate
def test_listar_productos_exito():
    """Prueba que GET /productos retorna una lista de productos con código 200."""
    responses.add(responses.GET, f"{BASE_URL}productos",
                  json=[MOCK_PRODUCTO], status=200)
    
    resultado = listar_productos()
    assert len(resultado) == 1
    assert resultado[0]["nombre"] == "Miel orgánica"

@responses.activate
def test_obtener_producto_exito():
    """Prueba que GET /productos/42 retorna el detalle del recurso."""
    responses.add(responses.GET, f"{BASE_URL}productos/42",
                  json=MOCK_PRODUCTO, status=200)
    
    resultado = obtener_producto(42)
    assert resultado["id"] == 42

@responses.activate
def test_crear_producto_exito():
    """Prueba que POST /productos crea un recurso y retorna 201 Created."""
    responses.add(responses.POST, f"{BASE_URL}productos",
                  json=MOCK_PRODUCTO, status=201)
    
    resultado = crear_producto(MOCK_PRODUCTO)
    assert resultado["id"] == 42

@responses.activate
def test_actualizar_producto_total_exito():
    """Prueba que PUT /productos/42 reemplaza el recurso completamente."""
    responses.add(responses.PUT, f"{BASE_URL}productos/42",
                  json=MOCK_PRODUCTO, status=200)
    
    resultado = actualizar_producto_total(42, MOCK_PRODUCTO)
    assert resultado["id"] == 42

@responses.activate
def test_actualizar_producto_parcial_exito():
    """Prueba que PATCH /productos/42 modifica solo ciertos campos."""
    cambios = {"precio": 160.0}
    producto_actualizado = {**MOCK_PRODUCTO, **cambios}
    responses.add(responses.PATCH, f"{BASE_URL}productos/42",
                  json=producto_actualizado, status=200)
    
    resultado = actualizar_producto_parcial(42, cambios)
    assert resultado["precio"] == 160.0

@responses.activate
def test_eliminar_producto_exito():
    """Prueba que DELETE /productos/42 elimina el recurso y retorna True (204 No Content)."""
    responses.add(responses.DELETE, f"{BASE_URL}productos/42", status=204)
    
    resultado = eliminar_producto(42)
    assert resultado is True

# =================================================================
# 2. ERRORES HTTP (8 TESTS)
# =================================================================

@responses.activate
def test_crear_producto_bad_request_400():
    """Prueba manejo de error 400 cuando los datos enviados son inválidos."""
    responses.add(responses.POST, f"{BASE_URL}productos",
                  json={"error": "Datos inválidos"}, status=400)
    
    with pytest.raises(ValidationError):
        crear_producto({"nombre": ""})

@responses.activate
def test_obtener_producto_unauthorized_401():
    """Prueba manejo de error 401 cuando no se proveen credenciales."""
    responses.add(responses.GET, f"{BASE_URL}productos/42", status=401)
    
    with pytest.raises(ValidationError):
        obtener_producto(42)

@responses.activate
def test_obtener_producto_not_found_404():
    """Prueba que obtener un ID inexistente lanza ResourceNotFoundError (vía ValidationError)."""
    responses.add(responses.GET, f"{BASE_URL}productos/999", status=404)
    
    with pytest.raises(ValidationError):
        obtener_producto(999)

@responses.activate
def test_crear_producto_conflict_409():
    """Prueba manejo de error 409 cuando se intenta crear un producto duplicado."""
    responses.add(responses.POST, f"{BASE_URL}productos", status=409)
    
    with pytest.raises(ValidationError):
        crear_producto(MOCK_PRODUCTO)

@responses.activate
def test_listar_productos_internal_error_500():
    """Prueba que un error 500 lanza ServerError."""
    responses.add(responses.GET, f"{BASE_URL}productos", status=500)
    
    with pytest.raises(ServerError):
        listar_productos()

@responses.activate
def test_listar_productos_service_unavailable_503():
    """Prueba que un error 503 (mantenimiento) lanza ServerError."""
    responses.add(responses.GET, f"{BASE_URL}productos", status=503)
    
    with pytest.raises(ServerError):
        listar_productos()

@responses.activate
def test_actualizar_producto_not_found_404():
    """Prueba que intentar hacer PUT a un recurso inexistente falla."""
    responses.add(responses.PUT, f"{BASE_URL}productos/999", status=404)
    
    with pytest.raises(ValidationError):
        actualizar_producto_total(999, MOCK_PRODUCTO)

@responses.activate
def test_eliminar_producto_not_found_404():
    """Prueba que intentar eliminar un recurso inexistente falla con 404."""
    responses.add(responses.DELETE, f"{BASE_URL}productos/999", status=404)
    
    with pytest.raises(ValidationError):
        eliminar_producto(999)

# =================================================================
# 3. EDGE CASES (6 TESTS)
# =================================================================

@responses.activate
def test_obtener_producto_body_vacio_200():
    """Prueba que un 200 con body vacío falle la validación de esquema."""
    responses.add(responses.GET, f"{BASE_URL}productos/42",
                  body="", status=200, content_type="application/json")
    
    with pytest.raises(ValidationError):
        obtener_producto(42)

@responses.activate
def test_listar_productos_html_content_type():
    """Prueba que si el servidor devuelve HTML en lugar de JSON, el cliente falle elegantemente."""
    responses.add(responses.GET, f"{BASE_URL}productos",
                  body="<html>Error</html>", status=200, content_type="text/html")
    
    with pytest.raises(ValidationError):
        listar_productos()

@responses.activate
def test_obtener_producto_json_invalido():
    """Prueba que un JSON malformado sea detectado antes de usarse."""
    responses.add(responses.GET, f"{BASE_URL}productos/42",
                  body='{"id": 42, "nombre": "Incompleto"', status=200)
    
    with pytest.raises(ValidationError):
        obtener_producto(42)

@responses.activate
def test_listar_productos_timeout():
    """Prueba que el cliente respete el timeout configurado."""
    responses.add(responses.GET, f"{BASE_URL}productos",
                  body=requests.exceptions.Timeout())
    
    with pytest.raises(requests.exceptions.RequestException):
        listar_productos()

@responses.activate
def test_obtener_producto_precio_string():
    """Prueba que la validación detecte tipos incorrectos (ej. precio como string)."""
    data_corrupta = MOCK_PRODUCTO.copy()
    data_corrupta["precio"] = "150.0" # Debería ser float
    
    responses.add(responses.GET, f"{BASE_URL}productos/42",
                  json=data_corrupta, status=200)
    
    with pytest.raises(ValidationError):
        obtener_producto(42)

@responses.activate
def test_listar_productos_lista_vacia():
    """Prueba que una lista vacía sea un resultado válido."""
    responses.add(responses.GET, f"{BASE_URL}productos",
                  json=[], status=200)
    
    resultado = listar_productos()
    assert resultado == []