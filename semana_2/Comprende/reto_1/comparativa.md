# Mi diseño

Implemente los 6 operaciones CRUD para todos los recursos (productos,pedidos,productores), y para todos el mismo manejo de errores con codigos de estado http y mensajes genericos

# Tabla de recursos generada por mi

## Productos

| Operación | Método | Endpoint | Body de ejemplo | Respuesta exitosa | Posibles errores |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Crear | POST | /api/productos | `{"nombre": "Miel de Abeja", "precio": 120.50, "categoria": "miel", "productor_id": 7}` | 201 Created | 400 (Datos inválidos), 409 (Ya existe) |
| Listar | GET | /api/productos | Ninguno | 200 OK (Lista de objetos) | 500 (Error de servidor) |
| Detalle | GET | /api/productos/{id} | Ninguno | 200 OK (Objeto único) | 404 (No encontrado) |
| Reemplazo | PUT | /api/productos/{id} | `{"nombre": "Miel Organica", "precio": 130.0, "categoria": "miel", "productor_id": 7, "disponible": true}` | 200 OK | 400 (Faltan campos obligatorios) |
| Modificar | PATCH | /api/productos/{id} | `{"precio": 115.0}` | 200 OK | 400 (Tipo de dato incorrecto) |
| Eliminar | DELETE | /api/productos/{id} | Ninguno | 204 No Content | 404 (No existe), 403 (No autorizado) |

## Pedidos

| Operación | Método | Endpoint | Body de ejemplo | Respuesta exitosa | Posibles errores |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Crear | POST | /api/pedidos | `{"producto_id": 42, "cantidad": 3, "usuario_id": 10}` | 201 Created | 400 (Stock insuficiente) |
| Listar | GET | /api/pedidos | Ninguno | 200 OK (Historial de pedidos) | 401 (No autorizado) |
| Detalle | GET | /api/pedidos/{id} | Ninguno | 200 OK (Detalle del pedido) | 404 (ID no encontrado) |
| Reemplazo | PUT | /api/pedidos/{id} | `{"producto_id": 42, "cantidad": 5, "usuario_id": 10, "estado": "pendiente"}` | 200 OK | 400 (Error en campos obligatorios) |
| Modificar | PATCH | /api/pedidos/{id} | `{"estado": "enviado"}` | 200 OK | 403 (No se puede cambiar estado) |
| Eliminar | DELETE | /api/pedidos/{id} | Ninguno | 204 No Content | 404 (Pedido inexistente) |

## Productores

| Operación | Método | Endpoint | Body de ejemplo | Respuesta exitosa | Posibles errores |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Crear | POST | /api/productores | `{"nombre": "Rancho El Olvido", "ubicacion": "Tepic"}` | 201 Created | 400 (Nombre inválido) |
| Listar | GET | /api/productores | Ninguno | 200 OK (Lista de productores) | 500 (Error de conexión) |
| Detalle | GET | /api/productores/{id} | Ninguno | 200 OK (Detalle productor) | 404 (No existe) |
| Reemplazo | PUT | /api/productores/{id} | `{"nombre": "Rancho Nuevo", "ubicacion": "San Blas"}` | 200 OK | 400 (Estructura incompleta) |
| Modificar | PATCH | /api/productores/{id} | `{"ubicacion": "Santiago Ixcuintla"}` | 200 OK | 422 (Entidad no procesable) |
| Eliminar | DELETE | /api/productores/{id} | Ninguno | 204 No Content | 409 (Tiene productos asociados) |


# Tabla de recursos generada por la IA

## Productos

| Operación | Método | Endpoint | Body de ejemplo | Respuesta exitosa | Posibles errores |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Crear | POST | /api/productos | `{"nombre": "Miel de Abeja", "precio": 120.50, "categoria": "miel"}` | 201 Created | 400 (Datos inválidos), 409 (Ya existe) |
| Listar | GET | /api/productos | Ninguno | 200 OK (Lista de objetos) | 500 (Error de base de datos) |
| Detalle | GET | /api/productos/{id} | Ninguno | 200 OK (Objeto único) | 404 (No encontrado) |
| Reemplazo | PUT | /api/productos/{id} | `{"nombre": "Miel Organica", "precio": 130.0, "categoria": "miel"}` | 200 OK | 400 (Faltan campos obligatorios) |
| Modificar | PATCH | /api/productos/{id} | `{"precio": 115.0}` | 200 OK | 400 (Tipo de dato incorrecto) |
| Eliminar | DELETE | /api/productos/{id} | Ninguno | 204 No Content | 404 (No existe), 403 (No autorizado) |


## productores

| Operación | Método | Endpoint | Body de ejemplo | Respuesta exitosa | Posibles errores |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Crear | POST | /api/productores | `{"nombre": "Rancho El Olvido", "ubicacion": "Tepic"}` | 201 Created | 400 (Nombre duplicado) |
| Listar | GET | /api/productores | Ninguno | 200 OK | 500 (Servidor caído) |
| Detalle | GET | /api/productores/{id} | Ninguno | 200 OK | 404 (Productor inexistente) |
| Eliminar | DELETE | /api/productores/{id} | Ninguno | 204 No Content | 409 (Conflicto: tiene productos) |

## Pedidos

| Operación | Método | Endpoint | Body de ejemplo | Respuesta exitosa | Posibles errores |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Crear | POST | /api/pedidos | `{"producto_id": 42, "cantidad": 5, "usuario_id": 7}` | 201 Created | 400 (Stock insuficiente) |
| Listar | GET | /api/pedidos | Ninguno | 200 OK | 401 (No autenticado) |
| Cancelar | DELETE | /api/pedidos/{id} | Ninguno | 204 No Content | 403 (Ya fue enviado, no se puede) |

## Manejo de errores IA
La IA planteo un manejo de errores mas detallado y especifico para cada recurso:

| Escenario | Código HTTP | Estructura JSON sugerida | Acción del Cliente |
| :--- | :--- | :--- | :--- |
| Error de Sintaxis | 400 Bad Request | `{"code": "INVALID_FORMAT", "message": "..."}` | Corregir el formato del JSON. |
| Falla de Negocio | 422 Unprocessable Entity | `{"code": "VAL_ERROR", "fields": ["precio"]}` | Notificar al usuario sobre el valor inválido. |
| Conflicto Relacional | 409 Conflict | `{"code": "HAS_DEPENDENCIES", "message": "..."}` | Impedir la acción hasta limpiar dependencias. |

# Tabla comparativa

| Recurso | Diseño Universal (Tuyo) | Diseño Selectivo (IA) | Justificación del Diseño IA | Mi Preferencia / Justificación |
| :--- | :--- | :--- | :--- | :--- |
| Productos | CRUD Completo (6 ops) | CRUD Completo + Búsqueda por nombre. | Es el recurso principal; requiere flexibilidad total para el catálogo. | la opcion de la ia es mas completa, olvide las queries para filtrar por nombre |
| Productores | CRUD Completo (6 ops) | Registro, Listado, Eliminación Protegida y Recurso Anidado. | Se omitió PUT/PATCH para simplificar la demo, pero se añadió /productores/{id}/productos para mejorar la navegación. | para demo puede ser una opcion, pero es importante que put y patch esten ahi, aunque lo de rutas anidadas me parece limpio |
| Pedidos | CRUD Completo (6 ops) | Solo POST (Creación). | Los pedidos suelen ser inmutables o manejarse vía estados. Un PUT total podría corromper el historial financiero. | para demo funciona , péro en produccion hay que agragar patch, por el tema de la idempotencia y no crear el mismo pedido 2 veces |