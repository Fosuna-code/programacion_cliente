"""
Tests para el módulo de validadores de EcoMarket.
Prueba 5 escenarios de fallo para validar la robustez del validador.

Ejecutar con: pytest test_validadores.py -v
"""

import pytest
from validadores import validar_producto, validar_lista_productos, ValidationError


class TestValidadorProducto:
    """Tests para validar_producto() - 5 escenarios de fallo."""

    def test_precio_negativo(self):
        """Caso 1: El precio no puede ser negativo."""
        producto = {
            "id": 1,
            "nombre": "Miel",
            "precio": -10.0,
            "categoria": "miel",
            "disponible": True
        }
        
        with pytest.raises(ValidationError) as exc_info:
            validar_producto(producto)
        
        assert "precio" in str(exc_info.value).lower()
        assert "mayor a 0" in str(exc_info.value)

    def test_tipo_incorrecto_id(self):
        """Caso 2: El ID debe ser un entero, no un string."""
        producto = {
            "id": "42",  # ❌ String en lugar de int
            "nombre": "Fresas",
            "precio": 50.0,
            "categoria": "frutas",
            "disponible": True
        }
        
        with pytest.raises(ValidationError) as exc_info:
            validar_producto(producto)
        
        assert "id" in str(exc_info.value)
        assert "tipo incorrecto" in str(exc_info.value).lower()

    def test_campo_requerido_faltante(self):
        """Caso 3: Debe fallar si falta un campo requerido."""
        producto = {
            "id": 1,
            # ❌ Falta "nombre"
            "precio": 100.0,
            "categoria": "verduras",
            "disponible": True
        }
        
        with pytest.raises(ValidationError) as exc_info:
            validar_producto(producto)
        
        assert "nombre" in str(exc_info.value)
        assert "faltante" in str(exc_info.value).lower()

    def test_categoria_invalida(self):
        """Caso 4: La categoría debe estar en la lista permitida."""
        producto = {
            "id": 1,
            "nombre": "Smartphone",
            "precio": 599.99,
            "categoria": "tecnologia",  # ❌ Categoría no permitida
            "disponible": True
        }
        
        with pytest.raises(ValidationError) as exc_info:
            validar_producto(producto)
        
        assert "tecnologia" in str(exc_info.value)
        assert "no permitida" in str(exc_info.value).lower()

    def test_productor_incompleto(self):
        """Caso 5: El productor debe tener id y nombre."""
        producto = {
            "id": 1,
            "nombre": "Miel Orgánica",
            "precio": 150.0,
            "categoria": "miel",
            "disponible": True,
            "productor": {
                "nombre": "Apiarios"  # ❌ Falta "id"
            }
        }
        
        with pytest.raises(ValidationError) as exc_info:
            validar_producto(producto)
        
        assert "productor" in str(exc_info.value).lower()
        assert "id" in str(exc_info.value)


class TestValidadorListaProductos:
    """Tests para validar_lista_productos()."""

    def test_lista_valida(self):
        """Una lista de productos válidos debe pasar."""
        productos = [
            {"id": 1, "nombre": "Miel", "precio": 100.0, "categoria": "miel", "disponible": True},
            {"id": 2, "nombre": "Lechuga", "precio": 25.0, "categoria": "verduras", "disponible": True}
        ]
        
        resultado = validar_lista_productos(productos)
        
        assert len(resultado) == 2
        assert resultado[0]["nombre"] == "Miel"

    def test_no_es_lista(self):
        """Debe fallar si no es una lista."""
        with pytest.raises(ValidationError) as exc_info:
            validar_lista_productos({"id": 1})
        
        assert "lista" in str(exc_info.value).lower()

    def test_producto_invalido_en_lista(self):
        """Debe reportar el índice del producto inválido."""
        productos = [
            {"id": 1, "nombre": "Miel", "precio": 100.0, "categoria": "miel", "disponible": True},
            {"id": 2, "nombre": "Malo", "precio": -5.0, "categoria": "frutas", "disponible": True}  # ❌
        ]
        
        with pytest.raises(ValidationError) as exc_info:
            validar_lista_productos(productos)
        
        assert "índice 1" in str(exc_info.value)


class TestProductoValido:
    """Tests para productos válidos."""

    def test_producto_minimo_valido(self):
        """Producto con solo campos requeridos debe pasar."""
        producto = {
            "id": 1,
            "nombre": "Naranjas",
            "precio": 35.0,
            "categoria": "frutas",
            "disponible": True
        }
        
        resultado = validar_producto(producto)
        
        assert resultado == producto

    def test_producto_completo_valido(self):
        """Producto con todos los campos opcionales debe pasar."""
        producto = {
            "id": 1,
            "nombre": "Miel Premium",
            "precio": 200.0,
            "categoria": "miel",
            "disponible": True,
            "descripcion": "Miel 100% orgánica",
            "productor": {"id": 5, "nombre": "Apiarios del Norte"},
            "creado_en": "2024-01-15T10:30:00Z"
        }
        
        resultado = validar_producto(producto)
        
        assert resultado["descripcion"] == "Miel 100% orgánica"
        assert resultado["productor"]["nombre"] == "Apiarios del Norte"
