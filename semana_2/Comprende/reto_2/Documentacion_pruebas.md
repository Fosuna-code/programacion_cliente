# Documentación de Pruebas - Validador de Productos EcoMarket

## Descripción General

Este documento detalla las pruebas implementadas para el validador de productos de EcoMarket (`validadores.py`). El objetivo es verificar que el validador detecte correctamente diferentes tipos de errores en los datos de entrada, incluyendo problemas de tipo, validación semántica, y estructura de datos.

---

## Suite de Pruebas

### Caso 1: El "Precio Fantasma" (Valor Negativo)

**Objetivo:** Verificar que el validador rechace productos con precios negativos o cero.

**Entrada:**
```json
{
  "id": 42,
  "nombre": "Miel",
  "precio": -10.0,
  "categoria": "miel",
  "disponible": true
}
```

**Comportamiento Esperado:**
- El validador debe lanzar un `ValueError` durante la validación semántica
- El error debe indicar que el precio debe ser mayor a 0

**Validación Específica:**
- Línea 27-28 del validador: `if data["precio"] <= 0`
- Tipo de validación: **Semántica (Lógica de negocio)**

**Resultado Esperado:**
```
✅ ÉXITO: Validación semántica detectó el error
Mensaje: Precio inválido: -10.0. Debe ser mayor a 0.
```

---

### Caso 2: La "Invasión HTML"

**Objetivo:** Verificar que el validador rechace respuestas que no sean objetos JSON válidos (diccionarios).

**Entrada:**
```html
<html><body>500 Internal Server Error</body></html>
```

**Comportamiento Esperado:**
- El validador debe fallar en el primer check de tipo
- Debe lanzar un `ValueError` indicando que la entrada no es un diccionario

**Validación Específica:**
- Línea 8-9 del validador: `if not isinstance(data, dict)`
- Tipo de validación: **Tipo de dato básico**

**Resultado Esperado:**
```
✅ ÉXITO: Detectó que no es un diccionario
Mensaje: La respuesta no es un objeto JSON (dict).
```

**Contexto:**
Este caso simula una respuesta de error del servidor (500 Internal Server Error) que devuelve HTML en lugar de JSON. Es crucial para proteger contra errores de integración con APIs.

---

### Caso 3: El "Tipo Camaleón" (ID como String)

**Objetivo:** Verificar que el validador detecte tipos de datos incorrectos en campos requeridos.

**Entrada:**
```json
{
  "id": "42",
  "nombre": "Miel",
  "precio": 150.0,
  "categoria": "miel",
  "disponible": true
}
```

**Comportamiento Esperado:**
- El validador debe detectar que el campo `id` es un string cuando se espera un entero
- Debe lanzar un `ValueError` indicando el tipo incorrecto

**Validación Específica:**
- Línea 23-24 del validador: `if not isinstance(data[campo], tipo)`
- Campo afectado: `id` (se espera `int`, se recibe `str`)
- Tipo de validación: **Tipo de dato de campo**

**Resultado Esperado:**
```
✅ ÉXITO: Detectó tipo incorrecto en campo 'id'
Mensaje: Tipo incorrecto para 'id': se esperaba <class 'int'>
```

**Contexto:**
Este caso es común cuando se reciben datos de formularios web o APIs que no tienen tipado estricto, donde los números pueden llegar como strings.

---

### Caso 4: El "Productor Incompleto"

**Objetivo:** Verificar que el validador detecte objetos anidados incompletos.

**Entrada:**
```json
{
  "id": 42,
  "nombre": "Miel Orgánica",
  "precio": 150.0,
  "categoria": "miel",
  "disponible": true,
  "productor": {
    "nombre": "Solo Nombre, Sin ID"
  }
}
```

**Comportamiento Esperado:**
- El validador anidado debe detectar que falta el campo `id` en el objeto `productor`
- Debe lanzar un `ValueError` indicando que el productor está incompleto

**Validación Específica:**
- Líneas 35-43 del validador: Validación de objeto anidado `productor`
- Campos requeridos en productor: `id` y `nombre`
- Tipo de validación: **Validación de objeto anidado**

**Resultado Esperado:**
```
✅ ÉXITO: Validador anidado detectó productor incompleto
Mensaje: Productor incompleto: falta 'id'
```

**Contexto:**
Este caso verifica que el validador maneja correctamente estructuras de datos complejas y relaciones entre entidades (producto-productor).

---

### Caso 5: La "Categoría Alucinada"

**Objetivo:** Verificar que el validador rechace categorías no permitidas según las reglas de negocio de EcoMarket.

**Entrada:**
```json
{
  "id": 42,
  "nombre": "Smartphone",
  "precio": 599.99,
  "categoria": "tecnologia",
  "disponible": true
}
```

**Comportamiento Esperado:**
- El validador debe rechazar la categoría "tecnologia" por no estar en la lista blanca
- Debe lanzar un `ValueError` indicando que la categoría no está permitida

**Validación Específica:**
- Líneas 30-32 del validador: Validación de categorías permitidas
- Categorías válidas: `["frutas", "verduras", "lacteos", "miel", "conservas"]`
- Tipo de validación: **Semántica (Reglas de negocio)**

**Resultado Esperado:**
```
✅ ÉXITO: Rechazó categoría no permitida
Mensaje: Categoría 'tecnologia' no permitida.
```

**Contexto:**
EcoMarket es una plataforma especializada en productos orgánicos y locales. Este validador asegura que solo se acepten productos dentro del dominio de negocio definido.

---

## Caso Bonus: Producto Válido

**Objetivo:** Verificar que el validador acepta productos correctamente formados.

**Entrada:**
```json
{
  "id": 1,
  "nombre": "Miel de Abeja",
  "precio": 120.50,
  "categoria": "miel",
  "disponible": true,
  "productor": {
    "id": 10,
    "nombre": "Apiarios del Valle"
  }
}
```

**Comportamiento Esperado:**
- El validador debe aceptar el producto sin lanzar excepciones
- Debe retornar el mismo objeto validado

**Resultado Esperado:**
```
✅ ÉXITO: Producto válido aceptado
Resultado: {objeto completo}
```

---

## Caso 6: Campos No Permitidos en Productor (Caso Personal)

**Objetivo:** Verificar que el validador rechace campos adicionales no permitidos en el objeto anidado `productor`.

**Entrada:**
```json
{
  "id": 42,
  "nombre": "Miel Organica",
  "precio": 150.0,
  "categoria": "miel",
  "disponible": true,
  "productor": {
    "id": 1,
    "nombre": "apple",
    "apodo": "manzana"
  }
}
```

**Comportamiento Esperado:**
- El validador debe detectar el campo extra `apodo` que no está en la lista de campos permitidos
- Debe lanzar un `ValueError` indicando que el campo no está permitido

**Validación Específica:**
- Líneas 47-49 del validador: Validación estricta de campos permitidos en `productor`
- Campos permitidos en productor: solo `id` y `nombre`
- Tipo de validación: **Validación estricta de esquema en objeto anidado**

**Resultado Esperado:**
```
✅ ÉXITO: Validador detectó campo no permitido en productor
Mensaje: Campo no permitido en productor: 'apodo'
```

**Contexto:**
Este caso implementa una validación estricta del esquema, rechazando cualquier campo que no esté explícitamente permitido. Esto es importante para:
- **Seguridad:** Prevenir inyección de datos no esperados
- **Integridad:** Asegurar que solo se procesen datos conocidos
- **Contrato de API:** Mantener un esquema estricto y predecible

> [!NOTE]
> Este caso fue creado de forma personalizada (no generado por IA) para probar la validación estricta de campos en objetos anidados. Requirió una mejora en el validador para implementar la verificación de campos no permitidos.

---

## Ejecución de las Pruebas

Para ejecutar las pruebas, simplemente ejecuta el archivo como script de Python:

```bash
python validadores.py
```

O desde WSL:

```bash
python3 validadores.py
```

---

## Resumen de Cobertura

| Tipo de Validación | Casos de Prueba | Estado |
|-------------------|-----------------|--------|
| Tipo de dato básico (dict) | Caso 2 | ✅ |
| Tipo de campo requerido | Caso 3 | ✅ |
| Validación semántica (precio) | Caso 1 | ✅ |
| Validación semántica (categoría) | Caso 5 | ✅ |
| Validación de objeto anidado (campos faltantes) | Caso 4 | ✅ |
| Validación de objeto anidado (campos extras) | Caso 6 | ✅ |
| Producto válido | Caso Bonus | ✅ |

**Total de casos de prueba:** 7 (5 casos principales + 1 caso bonus + 1 caso personal)

---

## Notas Técnicas

### Estrategia de Validación

El validador implementa una estrategia de **validación en capas**:

1. **Capa 1 - Tipo básico:** Verifica que la entrada sea un diccionario
2. **Capa 2 - Campos requeridos:** Verifica presencia y tipo de campos obligatorios
3. **Capa 3 - Semántica:** Valida reglas de negocio (precio > 0, categorías permitidas)
4. **Capa 4 - Objetos anidados:** Valida estructuras complejas (productor)
   - **4a. Campos requeridos:** Verifica que existan `id` y `nombre`
   - **4b. Validación estricta:** Rechaza campos no permitidos (solo acepta `id` y `nombre`)
5. **Capa 5 - Formatos especiales:** Valida formatos como fechas ISO 8601

> [!IMPORTANT]
> La validación estricta de esquema (Capa 4b) fue agregada para mejorar la seguridad y mantener un contrato de API predecible. Esto previene la inyección de datos no esperados en objetos anidados.

### Manejo de Errores

Todos los errores se reportan mediante `ValueError` con mensajes descriptivos que indican:
- El campo problemático
- El tipo de error (faltante, tipo incorrecto, valor inválido)
- El valor esperado o permitido

### Extensibilidad

El validador puede extenderse fácilmente para incluir:
- Validación de campos opcionales adicionales
- Reglas de negocio más complejas
- Validación de otros objetos anidados (ej: dirección de entrega)
- Validación de rangos numéricos (ej: stock mínimo/máximo)

---

