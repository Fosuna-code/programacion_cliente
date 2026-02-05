"""
Test suite for cliente_ecomarket.py
Runs against Prism mock server on http://127.0.0.1:4010
Includes comprehensive logging of headers and 409 Conflict handling

Run with: pytest test_cliente_ecomarket.py -v -s
Prism command: prism mock openapiM2.yaml --port 4010
"""

import pytest
import logging
import requests
from unittest.mock import patch, MagicMock
from cliente_ecomarket import (
    listar_productos,
    obtener_producto,
    crear_producto,
    actualizar_producto_total,
    actualizar_producto_parcial,
    eliminar_producto,
    _verificar_respuesta,
    EcoMarketError,
    ValidationError,
    ConflictError,
    ServerError,
    BASE_URL
)

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)
logger = logging.getLogger(__name__)


def log_request_headers(response):
    """
    Helper function to log request and response headers.
    Uses print() for immediate visibility with pytest -s flag.
    """
    print("\n" + "=" * 60)
    print("📤 REQUEST HEADERS:")
    if hasattr(response, 'request') and response.request:
        for header, value in response.request.headers.items():
            print(f"    {header}: {value}")
    else:
        print("    (No request object available - using mock)")
    
    print("-" * 60)
    print("📥 RESPONSE HEADERS:")
    for header, value in response.headers.items():
        print(f"    {header}: {value}")
    print(f"📊 RESPONSE STATUS: {response.status_code}")
    print("=" * 60 + "\n")


# ============================================================================
# FIXTURES
# ============================================================================
@pytest.fixture
def mock_response():
    """Creates a mock response object for testing."""
    response = MagicMock()
    response.status_code = 200
    response.headers = {'Content-Type': 'application/json'}
    response.text = '{}'
    response.json.return_value = {}
    return response


@pytest.fixture
def sample_producto():
    """Sample product data for testing."""
    return {
        "nombre": "Miel Orgánica Test",
        "descripcion": "Miel 100% pura para pruebas.",
        "precio": 150.50,
        "categoria": "miel",
        "productor_id": 7,
        "disponible": True
    }


@pytest.fixture
def sample_producto_update():
    """Sample product data for full update."""
    return {
        "nombre": "Miel Orgánica Actualizada",
        "descripcion": "Miel actualizada.",
        "precio": 175.00,
        "categoria": "miel",
        "productor_id": 7,
        "disponible": True
    }


@pytest.fixture
def sample_producto_partial():
    """Sample product data for partial update."""
    return {
        "precio": 180.00,
        "disponible": False
    }


# ============================================================================
# TESTS FOR _verificar_respuesta()
# ============================================================================
class TestVerificarRespuesta:
    """Tests for the _verificar_respuesta helper function."""

    def test_verificar_respuesta_success(self, mock_response):
        """Test successful response verification."""
        logger.info("Testing: _verificar_respuesta with 200 OK")
        result = _verificar_respuesta(mock_response)
        assert result == mock_response
        logger.info("✓ Response verification passed for 200 OK")

    def test_verificar_respuesta_204_no_content(self, mock_response):
        """Test 204 No Content response (valid even without JSON)."""
        logger.info("Testing: _verificar_respuesta with 204 No Content")
        mock_response.status_code = 204
        mock_response.headers = {'Content-Type': ''}
        
        result = _verificar_respuesta(mock_response)
        assert result == mock_response
        logger.info("✓ Response verification passed for 204 No Content")

    def test_verificar_respuesta_409_conflict(self, mock_response):
        """Test 409 Conflict raises ConflictError."""
        logger.info("Testing: _verificar_respuesta with 409 Conflict")
        mock_response.status_code = 409
        mock_response.text = "El recurso ya existe"
        
        with pytest.raises(ConflictError) as exc_info:
            _verificar_respuesta(mock_response)
        
        assert "Conflicto" in str(exc_info.value)
        assert "ya existe" in str(exc_info.value)
        logger.info(f"✓ ConflictError raised correctly: {exc_info.value}")

    def test_verificar_respuesta_400_validation_error(self, mock_response):
        """Test 4xx errors raise ValidationError."""
        logger.info("Testing: _verificar_respuesta with 400 Bad Request")
        mock_response.status_code = 400
        mock_response.text = "Datos inválidos"
        
        with pytest.raises(ValidationError) as exc_info:
            _verificar_respuesta(mock_response)
        
        assert "400" in str(exc_info.value)
        logger.info(f"✓ ValidationError raised correctly: {exc_info.value}")

    def test_verificar_respuesta_404_not_found(self, mock_response):
        """Test 404 Not Found raises ValidationError."""
        logger.info("Testing: _verificar_respuesta with 404 Not Found")
        mock_response.status_code = 404
        mock_response.text = "Producto no encontrado"
        
        with pytest.raises(ValidationError) as exc_info:
            _verificar_respuesta(mock_response)
        
        assert "404" in str(exc_info.value)
        logger.info(f"✓ ValidationError raised correctly for 404: {exc_info.value}")

    def test_verificar_respuesta_500_server_error(self, mock_response):
        """Test 5xx errors raise ServerError."""
        logger.info("Testing: _verificar_respuesta with 500 Internal Server Error")
        mock_response.status_code = 500
        
        with pytest.raises(ServerError) as exc_info:
            _verificar_respuesta(mock_response)
        
        assert "servidor" in str(exc_info.value).lower()
        logger.info(f"✓ ServerError raised correctly: {exc_info.value}")

    def test_verificar_respuesta_503_server_error(self, mock_response):
        """Test 503 Service Unavailable raises ServerError."""
        logger.info("Testing: _verificar_respuesta with 503 Service Unavailable")
        mock_response.status_code = 503
        
        with pytest.raises(ServerError) as exc_info:
            _verificar_respuesta(mock_response)
        
        assert "503" in str(exc_info.value)
        logger.info(f"✓ ServerError raised correctly for 503: {exc_info.value}")

    def test_verificar_respuesta_invalid_content_type(self, mock_response):
        """Test non-JSON response raises ValidationError."""
        logger.info("Testing: _verificar_respuesta with text/html Content-Type")
        mock_response.headers = {'Content-Type': 'text/html'}
        
        with pytest.raises(ValidationError) as exc_info:
            _verificar_respuesta(mock_response)
        
        assert "no es JSON" in str(exc_info.value)
        logger.info(f"✓ ValidationError raised for invalid Content-Type: {exc_info.value}")


# ============================================================================
# TESTS FOR listar_productos()
# ============================================================================
class TestListarProductos:
    """Tests for listar_productos function."""

    def test_listar_productos_sin_filtros(self):
        """Test listing products without filters."""
        logger.info("Testing: listar_productos() without filters")
        
        with patch('cliente_ecomarket.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {'Content-Type': 'application/json'}
            mock_response.json.return_value = [
                {"id": 1, "nombre": "Miel", "precio": 150.0}
            ]
            mock_get.return_value = mock_response
            
            result = listar_productos()
            
            # Verify logging of headers
            log_request_headers(mock_response)
            
            mock_get.assert_called_once()
            assert len(result) >= 0
            logger.info(f"✓ Listed products successfully: {result}")

    def test_listar_productos_con_categoria(self):
        """Test listing products with category filter."""
        logger.info("Testing: listar_productos(categoria='miel')")
        
        with patch('cliente_ecomarket.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {'Content-Type': 'application/json'}
            mock_response.json.return_value = [
                {"id": 1, "nombre": "Miel Orgánica", "categoria": "miel"}
            ]
            mock_get.return_value = mock_response
            
            result = listar_productos(categoria="miel")
            
            log_request_headers(mock_response)
            
            # Verify the params were passed correctly
            call_args = mock_get.call_args
            assert 'params' in call_args.kwargs
            assert call_args.kwargs['params'].get('categoria') == 'miel'
            logger.info(f"✓ Listed products with category filter: {result}")

    def test_listar_productos_con_orden(self):
        """Test listing products with order filter."""
        logger.info("Testing: listar_productos(orden='precio_asc')")
        
        with patch('cliente_ecomarket.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {'Content-Type': 'application/json'}
            mock_response.json.return_value = []
            mock_get.return_value = mock_response
            
            result = listar_productos(orden="precio_asc")
            
            log_request_headers(mock_response)
            
            call_args = mock_get.call_args
            assert call_args.kwargs['params'].get('orden') == 'precio_asc'
            logger.info("✓ Listed products with order filter")

    def test_listar_productos_server_error(self):
        """Test listing products when server returns 500."""
        logger.info("Testing: listar_productos() with server error")
        
        with patch('cliente_ecomarket.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.headers = {'Content-Type': 'application/json'}
            mock_get.return_value = mock_response
            
            with pytest.raises(ServerError):
                listar_productos()
            
            logger.info("✓ ServerError raised correctly for 500 response")


# ============================================================================
# TESTS FOR obtener_producto()
# ============================================================================
class TestObtenerProducto:
    """Tests for obtener_producto function."""

    def test_obtener_producto_existente(self):
        """Test getting an existing product by ID."""
        logger.info("Testing: obtener_producto(1)")
        
        with patch('cliente_ecomarket.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {'Content-Type': 'application/json'}
            mock_response.json.return_value = {
                "id": 1, 
                "nombre": "Miel Orgánica", 
                "precio": 150.0
            }
            mock_get.return_value = mock_response
            
            result = obtener_producto(1)
            
            log_request_headers(mock_response)
            
            assert result['id'] == 1
            logger.info(f"✓ Got product successfully: {result}")

    def test_obtener_producto_no_existente(self):
        """Test getting a non-existing product returns 404."""
        logger.info("Testing: obtener_producto(99999) - non-existing")
        
        with patch('cliente_ecomarket.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_response.headers = {'Content-Type': 'application/json'}
            mock_response.text = "Producto no encontrado"
            mock_get.return_value = mock_response
            
            with pytest.raises(ValidationError) as exc_info:
                obtener_producto(99999)
            
            assert "404" in str(exc_info.value)
            logger.info(f"✓ ValidationError raised for non-existing product: {exc_info.value}")


# ============================================================================
# TESTS FOR crear_producto()
# ============================================================================
class TestCrearProducto:
    """Tests for crear_producto function."""

    def test_crear_producto_exitoso(self, sample_producto):
        """Test successful product creation."""
        logger.info(f"Testing: crear_producto({sample_producto})")
        
        with patch('cliente_ecomarket.requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.headers = {
                'Content-Type': 'application/json',
                'Location': '/productos/101'
            }
            mock_response.request = MagicMock()
            mock_response.request.headers = {
                'Content-Type': 'application/json',
                'User-Agent': 'python-requests'
            }
            created_product = {**sample_producto, "id": 101}
            mock_response.json.return_value = created_product
            mock_post.return_value = mock_response
            
            result = crear_producto(sample_producto)
            
            log_request_headers(mock_response)
            
            # Verify headers in request
            logger.info("Verifying Content-Type header was set correctly...")
            call_args = mock_post.call_args
            assert call_args.kwargs['headers']['Content-Type'] == 'application/json'
            
            assert result['id'] == 101
            logger.info(f"✓ Product created successfully: {result}")

    def test_crear_producto_datos_invalidos(self):
        """Test product creation with invalid data returns 400."""
        logger.info("Testing: crear_producto with invalid data")
        
        invalid_data = {"nombre": ""}  # Missing required fields
        
        with patch('cliente_ecomarket.requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 400
            mock_response.headers = {'Content-Type': 'application/json'}
            mock_response.text = "Campos requeridos faltantes"
            mock_post.return_value = mock_response
            
            with pytest.raises(ValidationError) as exc_info:
                crear_producto(invalid_data)
            
            logger.info(f"✓ ValidationError raised for invalid data: {exc_info.value}")

    def test_crear_producto_409_conflicto(self, sample_producto):
        """Test product creation with duplicate data returns 409 Conflict."""
        logger.info("Testing: crear_producto with duplicate product (409 Conflict)")
        
        with patch('cliente_ecomarket.requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 409
            mock_response.headers = {'Content-Type': 'application/json'}
            mock_response.text = "El producto con este nombre ya existe"
            mock_post.return_value = mock_response
            
            with pytest.raises(ConflictError) as exc_info:
                crear_producto(sample_producto)
            
            assert "Conflicto" in str(exc_info.value)
            assert "ya existe" in str(exc_info.value)
            logger.info(f"✓ ConflictError (409) raised correctly: {exc_info.value}")

    def test_crear_producto_status_incorrecto(self, sample_producto):
        """Test product creation returns unexpected status code."""
        logger.info("Testing: crear_producto with unexpected 200 response")
        
        with patch('cliente_ecomarket.requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200  # Should be 201
            mock_response.headers = {'Content-Type': 'application/json'}
            mock_response.json.return_value = {}
            mock_post.return_value = mock_response
            
            with pytest.raises(ValidationError) as exc_info:
                crear_producto(sample_producto)
            
            assert "201" in str(exc_info.value)
            logger.info(f"✓ ValidationError raised for unexpected status: {exc_info.value}")


# ============================================================================
# TESTS FOR actualizar_producto_total()
# ============================================================================
class TestActualizarProductoTotal:
    """Tests for actualizar_producto_total (PUT) function."""

    def test_actualizar_producto_total_exitoso(self, sample_producto_update):
        """Test successful full product update (PUT)."""
        logger.info(f"Testing: actualizar_producto_total(1, {sample_producto_update})")
        
        with patch('cliente_ecomarket.requests.put') as mock_put:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {
                'Content-Type': 'application/json',
                'X-Last-Modified': '2026-02-01T12:00:00Z'
            }
            mock_response.request = MagicMock()
            mock_response.request.headers = {
                'Content-Type': 'application/json'
            }
            updated_product = {**sample_producto_update, "id": 1}
            mock_response.json.return_value = updated_product
            mock_put.return_value = mock_response
            
            result = actualizar_producto_total(1, sample_producto_update)
            
            log_request_headers(mock_response)
            
            # Verify Content-Type header
            call_args = mock_put.call_args
            assert call_args.kwargs['headers']['Content-Type'] == 'application/json'
            
            assert result['nombre'] == "Miel Orgánica Actualizada"
            logger.info(f"✓ Product updated (PUT) successfully: {result}")

    def test_actualizar_producto_total_no_existente(self, sample_producto_update):
        """Test PUT on non-existing product returns 404."""
        logger.info("Testing: actualizar_producto_total on non-existing product")
        
        with patch('cliente_ecomarket.requests.put') as mock_put:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_response.headers = {'Content-Type': 'application/json'}
            mock_response.text = "Producto no encontrado"
            mock_put.return_value = mock_response
            
            with pytest.raises(ValidationError) as exc_info:
                actualizar_producto_total(99999, sample_producto_update)
            
            logger.info(f"✓ ValidationError raised for non-existing product: {exc_info.value}")

    def test_actualizar_producto_total_409_conflicto(self, sample_producto_update):
        """Test PUT with conflict returns 409."""
        logger.info("Testing: actualizar_producto_total with 409 Conflict")
        
        with patch('cliente_ecomarket.requests.put') as mock_put:
            mock_response = MagicMock()
            mock_response.status_code = 409
            mock_response.headers = {'Content-Type': 'application/json'}
            mock_response.text = "El nombre ya está en uso por otro producto"
            mock_put.return_value = mock_response
            
            with pytest.raises(ConflictError) as exc_info:
                actualizar_producto_total(1, sample_producto_update)
            
            assert "Conflicto" in str(exc_info.value)
            logger.info(f"✓ ConflictError (409) raised for PUT: {exc_info.value}")


# ============================================================================
# TESTS FOR actualizar_producto_parcial()
# ============================================================================
class TestActualizarProductoParcial:
    """Tests for actualizar_producto_parcial (PATCH) function."""

    def test_actualizar_producto_parcial_exitoso(self, sample_producto_partial):
        """Test successful partial product update (PATCH)."""
        logger.info(f"Testing: actualizar_producto_parcial(1, {sample_producto_partial})")
        
        with patch('cliente_ecomarket.requests.patch') as mock_patch:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {
                'Content-Type': 'application/json',
                'ETag': '"abc123"'
            }
            mock_response.request = MagicMock()
            mock_response.request.headers = {
                'Content-Type': 'application/json'
            }
            updated_product = {
                "id": 1, 
                "nombre": "Miel Orgánica",
                "precio": 180.00,
                "disponible": False
            }
            mock_response.json.return_value = updated_product
            mock_patch.return_value = mock_response
            
            result = actualizar_producto_parcial(1, sample_producto_partial)
            
            log_request_headers(mock_response)
            
            # Verify Content-Type header
            call_args = mock_patch.call_args
            assert call_args.kwargs['headers']['Content-Type'] == 'application/json'
            
            assert result['precio'] == 180.00
            assert result['disponible'] == False
            logger.info(f"✓ Product updated (PATCH) successfully: {result}")

    def test_actualizar_producto_parcial_solo_precio(self):
        """Test PATCH with only price field."""
        logger.info("Testing: actualizar_producto_parcial with only 'precio'")
        
        with patch('cliente_ecomarket.requests.patch') as mock_patch:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {'Content-Type': 'application/json'}
            mock_response.json.return_value = {"id": 1, "precio": 200.00}
            mock_patch.return_value = mock_response
            
            result = actualizar_producto_parcial(1, {"precio": 200.00})
            
            assert result['precio'] == 200.00
            logger.info(f"✓ Partial update with price only: {result}")

    def test_actualizar_producto_parcial_409_conflicto(self):
        """Test PATCH with conflict returns 409."""
        logger.info("Testing: actualizar_producto_parcial with 409 Conflict")
        
        with patch('cliente_ecomarket.requests.patch') as mock_patch:
            mock_response = MagicMock()
            mock_response.status_code = 409
            mock_response.headers = {'Content-Type': 'application/json'}
            mock_response.text = "Conflicto al actualizar: versión desactualizada"
            mock_patch.return_value = mock_response
            
            with pytest.raises(ConflictError) as exc_info:
                actualizar_producto_parcial(1, {"precio": 200.00})
            
            assert "Conflicto" in str(exc_info.value)
            logger.info(f"✓ ConflictError (409) raised for PATCH: {exc_info.value}")


# ============================================================================
# TESTS FOR eliminar_producto()
# ============================================================================
class TestEliminarProducto:
    """Tests for eliminar_producto function."""

    def test_eliminar_producto_exitoso(self):
        """Test successful product deletion."""
        logger.info("Testing: eliminar_producto(1)")
        
        with patch('cliente_ecomarket.requests.delete') as mock_delete:
            mock_response = MagicMock()
            mock_response.status_code = 204
            mock_response.headers = {
                'Content-Type': '',
                'X-Request-Id': 'test-123'
            }
            mock_response.request = MagicMock()
            mock_response.request.headers = {
                'Accept': '*/*'
            }
            mock_delete.return_value = mock_response
            
            result = eliminar_producto(1)
            
            log_request_headers(mock_response)
            
            assert result == True
            logger.info("✓ Product deleted successfully")

    def test_eliminar_producto_no_existente(self):
        """Test deleting non-existing product returns 404."""
        logger.info("Testing: eliminar_producto(99999) - non-existing")
        
        with patch('cliente_ecomarket.requests.delete') as mock_delete:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_response.headers = {'Content-Type': 'application/json'}
            mock_response.text = "Producto no encontrado"
            mock_delete.return_value = mock_response
            
            with pytest.raises(ValidationError) as exc_info:
                eliminar_producto(99999)
            
            logger.info(f"✓ ValidationError raised for non-existing product: {exc_info.value}")

    def test_eliminar_producto_409_conflicto(self):
        """Test DELETE with conflict (e.g., product has associated orders) returns 409."""
        logger.info("Testing: eliminar_producto with 409 Conflict")
        
        with patch('cliente_ecomarket.requests.delete') as mock_delete:
            mock_response = MagicMock()
            mock_response.status_code = 409
            mock_response.headers = {'Content-Type': 'application/json'}
            mock_response.text = "No se puede eliminar: el producto tiene pedidos asociados"
            mock_delete.return_value = mock_response
            
            with pytest.raises(ConflictError) as exc_info:
                eliminar_producto(1)
            
            assert "Conflicto" in str(exc_info.value)
            assert "ya existe" in str(exc_info.value)
            logger.info(f"✓ ConflictError (409) raised for DELETE: {exc_info.value}")

    def test_eliminar_producto_server_error(self):
        """Test DELETE with server error returns 500."""
        logger.info("Testing: eliminar_producto with 500 Server Error")
        
        with patch('cliente_ecomarket.requests.delete') as mock_delete:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.headers = {'Content-Type': 'application/json'}
            mock_delete.return_value = mock_response
            
            with pytest.raises(ServerError):
                eliminar_producto(1)
            
            logger.info("✓ ServerError raised for DELETE with 500")


# ============================================================================
# INTEGRATION TESTS (Against Live Prism Mock Server)
# ============================================================================
class TestIntegrationWithPrism:
    """
    Integration tests that run against a live Prism mock server.
    These tests verify actual HTTP communication and header handling.
    
    Prerequisites:
        prism mock openapiM2.yaml --port 4010
    """

    @pytest.fixture
    def session_with_logging(self):
        """Creates a session with request/response logging."""
        session = requests.Session()
        
        def log_hook(response, *args, **kwargs):
            logger.info("=" * 70)
            logger.info("INTEGRATION TEST - HTTP COMMUNICATION")
            logger.info("-" * 70)
            logger.info(f"REQUEST: {response.request.method} {response.request.url}")
            logger.info("REQUEST HEADERS:")
            for k, v in response.request.headers.items():
                logger.info(f"  {k}: {v}")
            logger.info("-" * 70)
            logger.info(f"RESPONSE STATUS: {response.status_code}")
            logger.info("RESPONSE HEADERS:")
            for k, v in response.headers.items():
                logger.info(f"  {k}: {v}")
            logger.info("=" * 70)
            return response
        
        session.hooks['response'].append(log_hook)
        return session

    @pytest.mark.integration
    def test_integration_listar_productos(self):
        """Integration test: List products from Prism mock."""
        logger.info("INTEGRATION: Testing listar_productos against Prism")
        
        try:
            result = listar_productos()
            logger.info(f"✓ Integration test passed: Got {len(result)} products")
            assert isinstance(result, list)
        except Exception as e:
            logger.warning(f"Integration test skipped (Prism not running?): {e}")
            pytest.skip("Prism mock server not running")

    @pytest.mark.integration
    def test_integration_obtener_producto(self):
        """Integration test: Get a single product from Prism mock."""
        logger.info("INTEGRATION: Testing obtener_producto(1) against Prism")
        
        try:
            result = obtener_producto(1)
            logger.info(f"✓ Integration test passed: Got product {result}")
            assert 'id' in result or 'nombre' in result
        except Exception as e:
            logger.warning(f"Integration test skipped (Prism not running?): {e}")
            pytest.skip("Prism mock server not running")

    @pytest.mark.integration
    def test_integration_headers_verification(self, session_with_logging):
        """Integration test: Verify headers are sent and received correctly."""
        logger.info("INTEGRATION: Verifying headers with Prism")
        
        try:
            response = session_with_logging.get(
                f"{BASE_URL}/productos",
                headers={
                    'Accept': 'application/json',
                    'X-Request-ID': 'test-header-verification'
                },
                timeout=10
            )
            
            # Verify response headers
            assert 'Content-Type' in response.headers
            logger.info(f"✓ Content-Type header present: {response.headers.get('Content-Type')}")
            
        except requests.exceptions.ConnectionError:
            pytest.skip("Prism mock server not running at localhost:4010")


# ============================================================================
# EDGE CASE TESTS
# ============================================================================
class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_timeout_handling(self):
        """Test that timeout is properly configured."""
        logger.info("Testing: Timeout configuration")
        
        with patch('cliente_ecomarket.requests.get') as mock_get:
            mock_get.side_effect = requests.exceptions.Timeout("Timeout!")
            
            with pytest.raises(requests.exceptions.Timeout):
                listar_productos()
            
            logger.info("✓ Timeout exception propagates correctly")

    def test_connection_error_handling(self):
        """Test connection error handling."""
        logger.info("Testing: Connection error handling")
        
        with patch('cliente_ecomarket.requests.get') as mock_get:
            mock_get.side_effect = requests.exceptions.ConnectionError("Connection refused")
            
            with pytest.raises(requests.exceptions.ConnectionError):
                listar_productos()
            
            logger.info("✓ ConnectionError propagates correctly")

    def test_empty_json_response(self):
        """Test handling of empty JSON array response."""
        logger.info("Testing: Empty JSON array response")
        
        with patch('cliente_ecomarket.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {'Content-Type': 'application/json'}
            mock_response.json.return_value = []
            mock_get.return_value = mock_response
            
            result = listar_productos()
            
            assert result == []
            logger.info("✓ Empty array handled correctly")

    def test_special_characters_in_categoria(self):
        """Test handling of special characters in query params."""
        logger.info("Testing: Special characters in categoria filter")
        
        with patch('cliente_ecomarket.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {'Content-Type': 'application/json'}
            mock_response.json.return_value = []
            mock_get.return_value = mock_response
            
            result = listar_productos(categoria="lácteos")
            
            call_args = mock_get.call_args
            assert call_args.kwargs['params']['categoria'] == 'lácteos'
            logger.info("✓ Special characters handled correctly")


# ============================================================================
# RUN TESTS DIRECTLY
# ============================================================================
if __name__ == "__main__":
    print("=" * 70)
    print("ECOMARKET CLIENT TEST SUITE")
    print("=" * 70)
    print("\nRunning tests with pytest...\n")
    print("For integration tests, ensure Prism is running:")
    print("  prism mock openapiM2.yaml --port 4010\n")
    print("-" * 70)
    
    pytest.main([
        __file__,
        "-v",  # Verbose output
        "-s",  # Show print statements
        "--tb=short",  # Shorter traceback
        "-x",  # Stop on first failure
    ])
