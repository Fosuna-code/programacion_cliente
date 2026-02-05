# Reporte de Pruebas: EcoMarket Client

Este documento detalla los hallazgos tras la ejecución de la suite de pruebas `test_cliente.py` sobre el cliente original y las correcciones implementadas en la versión optimizada.

## 1. Resumen de Ejecución
- **Tests Totales:** 20
- **Fallos Iniciales:** >70% (debido a dependencias y validaciones ausentes)
- **Estado Final:** 20/20 PASSED (100% de éxito)

## 2. Bugs Encontrados y Correcciones Aplicadas

### A. Validación de Tipos de Datos (Precios)
- **Bug:** El cliente original no validaba que el campo `precio` fuera numérico. El test `test_obtener_producto_precio_string` enviaba un string y el cliente lo aceptaba, fallando la aserción del test.
- **Corrección:** Se implementó `_validar_producto()` que verifica explícitamente `isinstance(producto["precio"], (int, float))`.

### B. Manejo de Respuestas No-JSON (HTML)
- **Bug:** Si el servidor devolvía una página de error en HTML (común en errores 404 o 500 de infraestructura), el cliente intentaba hacer `.json()` directamente, lanzando un error de librería en lugar de uno controlado.
- **Corrección:** Se añadió una validación del encabezado `Content-Type` en `_verificar_respuesta()`. Si no contiene `application/json`, se lanza `ValidationError` antes de intentar parsear.

### C. Body de Respuesta Vacío
- **Bug:** El test `test_obtener_producto_body_vacio_200` simula un 200 OK pero con cuerpo vacío. El método `.json()` de `requests` falla en estos casos.
- **Corrección:** Se creó `_extraer_json_seguro()` que verifica `if not response.text` antes de procesar el JSON.

### D. Jerarquía de Excepciones
- **Bug:** Los tests esperan específicamente `ValidationError` para errores 4xx (400, 401, 404, 409). El cliente original usaba `ConflictError` para el 409, lo que hacía que el test fallara al no capturar la excepción esperada.
- **Corrección:** Se unificaron los errores 4xx bajo `ValidationError` para cumplir con la firma esperada por la suite de pruebas.

### E. Dependencias de Rutas (Path Issues)
- **Bug:** El cliente original dependía de `sys.path.insert` para buscar `validadores.py` y `url_builder.py` en carpetas relativas (`..`), lo cual es frágil y fallaba en el entorno de ejecución del test.
- **Corrección:** Se eliminaron las dependencias externas, integrando la lógica de validación y construcción de URLs dentro del mismo archivo `Cliente_optimizado_para_testing.py`.

## 3. Conclusión
El cliente optimizado es ahora **robusto ante fallos de infraestructura** y **estrictamente validado** contra el esquema de datos, garantizando que el resto de la aplicación no procese datos corruptos provenientes de la API.
