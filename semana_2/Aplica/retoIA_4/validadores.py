"""
Módulo de validación para respuestas de la API de EcoMarket.
Proporciona validación robusta de productos antes de procesarlos.
"""

import datetime


class ValidationError(Exception):
    """
    Error de validación con mensaje descriptivo.
    Indica QUÉ campo falló y POR QUÉ.
    """
    pass


def validar_producto(data: dict) -> dict:
    """
    Valida un producto de EcoMarket.
    
    Args:
        data: Diccionario con los datos del producto
        
    Returns:
        El diccionario validado si pasa todas las verificaciones
        
    Raises:
        ValidationError: Si alguna validación falla, con mensaje descriptivo
    """
    # Verificar que sea un diccionario
    if not isinstance(data, dict):
        raise ValidationError(
            f"La respuesta no es un objeto JSON válido. "
            f"Se recibió: {type(data).__name__}"
        )
    
    # 1. Campos requeridos y sus tipos
    campos_requeridos = {
        "id": int,
        "nombre": str,
        "precio": (float, int),  # Aceptamos int para conversión automática
        "categoria": str,
        "disponible": bool
    }
    
    for campo, tipo_esperado in campos_requeridos.items():
        # Verificar presencia del campo
        if campo not in data:
            raise ValidationError(
                f"Campo requerido faltante: '{campo}'. "
                f"Los campos requeridos son: {list(campos_requeridos.keys())}"
            )
        
        # Verificar tipo del campo
        if not isinstance(data[campo], tipo_esperado):
            tipo_recibido = type(data[campo]).__name__
            if isinstance(tipo_esperado, tuple):
                tipos_str = " o ".join(t.__name__ for t in tipo_esperado)
            else:
                tipos_str = tipo_esperado.__name__
            raise ValidationError(
                f"Tipo incorrecto para '{campo}': "
                f"se esperaba {tipos_str}, se recibió {tipo_recibido}"
            )
    
    # 2. Validación semántica: precio > 0
    if data["precio"] <= 0:
        raise ValidationError(
            f"Precio inválido: {data['precio']}. "
            f"El precio debe ser mayor a 0."
        )
    
    # 3. Validación de categoría
    categorias_validas = ["frutas", "verduras", "lacteos", "miel", "conservas"]
    if data["categoria"] not in categorias_validas:
        raise ValidationError(
            f"Categoría no permitida: '{data['categoria']}'. "
            f"Las categorías válidas son: {categorias_validas}"
        )
    
    # 4. Campos opcionales
    
    # 4.1 Descripción (str, puede faltar)
    if "descripcion" in data and data["descripcion"] is not None:
        if not isinstance(data["descripcion"], str):
            raise ValidationError(
                f"Tipo incorrecto para 'descripcion': "
                f"se esperaba str, se recibió {type(data['descripcion']).__name__}"
            )
    
    # 4.2 Productor (dict con id y nombre, puede faltar)
    if "productor" in data and data["productor"] is not None:
        productor = data["productor"]
        
        if not isinstance(productor, dict):
            raise ValidationError(
                f"Tipo incorrecto para 'productor': "
                f"se esperaba dict, se recibió {type(productor).__name__}"
            )
        
        # Validar sub-campos requeridos del productor
        if "id" not in productor:
            raise ValidationError(
                "Productor incompleto: falta el campo 'id'"
            )
        if "nombre" not in productor:
            raise ValidationError(
                "Productor incompleto: falta el campo 'nombre'"
            )
        
        # Validar tipos de sub-campos
        if not isinstance(productor["id"], int):
            raise ValidationError(
                f"Tipo incorrecto para 'productor.id': "
                f"se esperaba int, se recibió {type(productor['id']).__name__}"
            )
        if not isinstance(productor["nombre"], str):
            raise ValidationError(
                f"Tipo incorrecto para 'productor.nombre': "
                f"se esperaba str, se recibió {type(productor['nombre']).__name__}"
            )
    
    # 4.3 Fecha de creación (str ISO 8601, puede faltar)
    if "creado_en" in data and data["creado_en"] is not None:
        if not isinstance(data["creado_en"], str):
            raise ValidationError(
                f"Tipo incorrecto para 'creado_en': "
                f"se esperaba str, se recibió {type(data['creado_en']).__name__}"
            )
        
        try:
            # Parsear fecha ISO 8601 (con soporte para 'Z' como UTC)
            fecha_str = data["creado_en"].replace('Z', '+00:00')
            datetime.datetime.fromisoformat(fecha_str)
        except ValueError:
            raise ValidationError(
                f"Formato de fecha inválido en 'creado_en': '{data['creado_en']}'. "
                f"Se esperaba formato ISO 8601 (ej: '2024-01-15T10:30:00Z')"
            )
    
    return data


def validar_lista_productos(data: list) -> list:
    """
    Valida una lista de productos de EcoMarket.
    
    Args:
        data: Lista de diccionarios con datos de productos
        
    Returns:
        La lista validada si todos los productos pasan las verificaciones
        
    Raises:
        ValidationError: Si la entrada no es una lista o algún producto falla
    """
    # Verificar que sea una lista
    if not isinstance(data, list):
        raise ValidationError(
            f"Se esperaba una lista de productos, "
            f"se recibió: {type(data).__name__}"
        )
    
    # Validar cada producto
    productos_validados = []
    for i, producto in enumerate(data):
        try:
            producto_validado = validar_producto(producto)
            productos_validados.append(producto_validado)
        except ValidationError as e:
            raise ValidationError(
                f"Error en producto índice {i}: {e}"
            )
    
    return productos_validados


# Ejecución de pruebas manuales
if __name__ == "__main__":
    print("=" * 70)
    print("PRUEBAS DEL MÓDULO DE VALIDADORES")
    print("=" * 70)
    
    # Caso válido
    producto_valido = {
        "id": 1,
        "nombre": "Miel Orgánica",
        "precio": 150.50,
        "categoria": "miel",
        "disponible": True,
        "productor": {"id": 10, "nombre": "Apiarios del Valle"}
    }
    
    try:
        resultado = validar_producto(producto_valido)
        print("\n✅ Producto válido aceptado correctamente")
    except ValidationError as e:
        print(f"\n❌ Error inesperado: {e}")
    
    # Caso inválido: precio negativo
    producto_precio_negativo = {
        "id": 2,
        "nombre": "Fresas",
        "precio": -10.0,
        "categoria": "frutas",
        "disponible": True
    }
    
    try:
        validar_producto(producto_precio_negativo)
        print("\n❌ Debería haber lanzado ValidationError")
    except ValidationError as e:
        print(f"\n✅ Precio negativo detectado: {e}")
    
    print("\n" + "=" * 70)
