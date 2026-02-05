import datetime

def validar_producto(data):
    """
    Validador robusto para recursos de EcoMarket.
    Lanza ValueError con descripciones detalladas si falla.
    """
    if not isinstance(data, dict):
        raise ValueError("La respuesta no es un objeto JSON (dict).")

    # 1. Campos requeridos y tipos básicos
    requeridos = {
        "id": int,
        "nombre": str,
        "precio": (float, int), # Aceptamos int para convertir a float
        "categoria": str,
        "disponible": bool
    }

    for campo, tipo in requeridos.items():
        if campo not in data:
            raise ValueError(f"Campo faltante: '{campo}'")
        if not isinstance(data[campo], tipo):
            raise ValueError(f"Tipo incorrecto para '{campo}': se esperaba {tipo}")

    # 2. Validación semántica (Lógica de negocio)
    if data["precio"] <= 0:
        raise ValueError(f"Precio inválido: {data['precio']}. Debe ser mayor a 0.")

    categorias_validas = ["frutas", "verduras", "lacteos", "miel", "conservas"]
    if data["categoria"] not in categorias_validas:
        raise ValueError(f"Categoría '{data['categoria']}' no permitida.")

    # 3. Manejo de objetos anidados (Productor) - Opcional según contrato
    if "productor" in data and data["productor"] is not None:
        productor = data["productor"]
        if not isinstance(productor, dict):
             raise ValueError("El campo 'productor' debe ser un objeto.")
        
        # Validar sub-campos del productor
        campos_requeridos = ["id", "nombre"]
        for p_campo in campos_requeridos:
            if p_campo not in productor:
                raise ValueError(f"Productor incompleto: falta '{p_campo}'")
        
        # Validar que no haya campos no permitidos
        for campo in productor.keys():
            if campo not in campos_requeridos:
                raise ValueError(f"Campo no permitido en productor: '{campo}'")

    # 4. Validación de fecha ISO 8601 (Campo opcional)
    if "creado_en" in data and data["creado_en"]:
        try:
            datetime.datetime.fromisoformat(data["creado_en"].replace('Z', '+00:00'))
        except ValueError:
            raise ValueError(f"Formato de fecha inválido en 'creado_en': {data['creado_en']}")

    return data


if __name__ == "__main__":
    print("=" * 80)
    print("SUITE DE PRUEBAS - VALIDADOR DE PRODUCTOS ECOMARKET")
    print("=" * 80)
    
    # Caso 1: El "Precio Fantasma" (Valor Negativo)
    print("\n[CASO 1] El 'Precio Fantasma' (Valor Negativo)")
    print("-" * 80)
    caso_1 = {
        "id": 42,
        "nombre": "Miel",
        "precio": -10.0,
        "categoria": "miel",
        "disponible": True
    }
    print(f"Entrada: {caso_1}")
    try:
        validar_producto(caso_1)
        print("[FAIL] Se esperaba un ValueError")
    except ValueError as e:
        print("[OK] EXITO: Validacion semantica detecto el error")
        print(f"    Mensaje: {e}")
    
    # Caso 2: La "Invasión HTML"
    print("\n[CASO 2] La 'Invasion HTML'")
    print("-" * 80)
    caso_2 = "<html><body>500 Internal Server Error</body></html>"
    print(f"Entrada: {caso_2}")
    try:
        validar_producto(caso_2)
        print("[FAIL] Se esperaba un ValueError")
    except ValueError as e:
        print("[OK] EXITO: Detecto que no es un diccionario")
        print(f"    Mensaje: {e}")
    
    # Caso 3: El "Tipo Camaleón" (ID como String)
    print("\n[CASO 3] El 'Tipo Camaleon' (ID como String)")
    print("-" * 80)
    caso_3 = {
        "id": "42",  # String en lugar de int
        "nombre": "Miel",
        "precio": 150.0,
        "categoria": "miel",
        "disponible": True
    }
    print(f"Entrada: {caso_3}")
    try:
        validar_producto(caso_3)
        print("[FAIL] Se esperaba un ValueError")
    except ValueError as e:
        print("[OK] EXITO: Detecto tipo incorrecto en campo 'id'")
        print(f"    Mensaje: {e}")
    
    # Caso 4: El "Productor Incompleto"
    print("\n[CASO 4] El 'Productor Incompleto'")
    print("-" * 80)
    caso_4 = {
        "id": 42,
        "nombre": "Miel Organica",
        "precio": 150.0,
        "categoria": "miel",
        "disponible": True,
        "productor": {
            "nombre": "Solo Nombre, Sin ID"
            # Falta el campo "id"
        }
    }
    print(f"Entrada: {caso_4}")
    try:
        validar_producto(caso_4)
        print("[FAIL] Se esperaba un ValueError")
    except ValueError as e:
        print("[OK] EXITO: Validador anidado detecto productor incompleto")
        print(f"    Mensaje: {e}")
    
    # Caso 5: La "Categoría Alucinada"
    print("\n[CASO 5] La 'Categoria Alucinada'")
    print("-" * 80)
    caso_5 = {
        "id": 42,
        "nombre": "Smartphone",
        "precio": 599.99,
        "categoria": "tecnologia",  # Categoría no permitida
        "disponible": True
    }
    print(f"Entrada: {caso_5}")
    try:
        validar_producto(caso_5)
        print("[FAIL] Se esperaba un ValueError")
    except ValueError as e:
        print("[OK] EXITO: Rechazo categoria no permitida")
        print(f"    Mensaje: {e}")
    
    # Caso BONUS: Producto válido
    print("\n[CASO BONUS] Producto Valido")
    print("-" * 80)
    caso_valido = {
        "id": 1,
        "nombre": "Miel de Abeja",
        "precio": 120.50,
        "categoria": "miel",
        "disponible": True,
        "productor": {
            "id": 10,
            "nombre": "Apiarios del Valle"
        }
    }
    print(f"Entrada: {caso_valido}")
    try:
        resultado = validar_producto(caso_valido)
        print("[OK] EXITO: Producto valido aceptado")
        print(f"    Resultado: {resultado}")
    except ValueError as e:
        print("[FAIL] No se esperaba error en producto valido")
        print(f"    Mensaje: {e}")
    
   

    #Caso personal no generado por IA 
    print("\n[CASO 6] Caso personal no generado por IA")
    print("-" * 80)
    caso_6 = {
        "id": 42,
        "nombre": "Miel Organica",
        "precio": 150.0,
        "categoria": "miel",
        "disponible": True,
        "productor": {
            "id": 1,
            "nombre": "apple",
            "apodo": "manzana"
            # apodo no existe wtf pero lo probamos
        }
    }
    print(f"Entrada: {caso_6}")
    try:
        validar_producto(caso_6)
        print("[FAIL] Se esperaba un ValueError")
    except ValueError as e:
        print("[OK] EXITO: Validador detecto campo no permitido en productor")
        print(f"    Mensaje: {e}")
    print("\n" + "=" * 80)
    print("FIN DE LAS PRUEBAS")
    print("=" * 80)