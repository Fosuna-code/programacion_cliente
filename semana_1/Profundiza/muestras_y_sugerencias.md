# MUESTRAS DE LOGS
(base) ➜  Profundiza python cliente_con_loggin.py
DEBUG:urllib3.connectionpool:Starting new HTTP connection (1): 127.0.0.1:4010
DEBUG:urllib3.connectionpool:http://127.0.0.1:4010 "GET /productos HTTP/1.1" 200 241
INFO:EcoMarket.Observability:✅ [2026-01-29T16:29:13.148971] listar_productos | 200 | 5.11ms | 241 bytes
DEBUG:EcoMarket.Observability:Headers Enviados: {'User-Agent': 'python-requests/2.32.3', 'Accept-Encoding': 'gzip, deflate, br, zstd', 'Accept': 'application/json', 'Connection': 'keep-alive', 'x-Client-Version': '1.0.0', 'Content-Type': 'application/json', 'Authorization': 'Bearer ********'}

✅ PRODUCTOS CARGADOS:
He recibido 1 productos.
- Miel Orgánica de Abeja Melipona: $150.5
DEBUG:urllib3.connectionpool:http://127.0.0.1:4010 "GET /productos/1 HTTP/1.1" 200 239
INFO:EcoMarket.Observability:✅ [2026-01-29T16:29:13.154554] obtener_producto | 200 | 4.86ms | 239 bytes
DEBUG:EcoMarket.Observability:Headers Enviados: {'User-Agent': 'python-requests/2.32.3', 'Accept-Encoding': 'gzip, deflate, br, zstd', 'Accept': 'application/json', 'Connection': 'keep-alive', 'x-Client-Version': '1.0.0', 'Content-Type': 'application/json', 'Authorization': 'Bearer ********'}

✅ PRODUCTO OBTENIDO:
- Miel Orgánica de Abeja Melipona: $150.5
DEBUG:urllib3.connectionpool:http://127.0.0.1:4010 "POST /productos HTTP/1.1" 201 239
INFO:EcoMarket.Observability:✅ [2026-01-29T16:29:13.159625] crear_producto | 201 | 3.61ms | 239 bytes
DEBUG:EcoMarket.Observability:Headers Enviados: {'User-Agent': 'python-requests/2.32.3', 'Accept-Encoding': 'gzip, deflate, br, zstd', 'Accept': 'application/json', 'Connection': 'keep-alive', 'x-Client-Version': '1.0.0', 'Content-Type': 'application/json', 'Content-Length': '187', 'Authorization': 'Bearer ********'}

✅ PRODUCTO CREADO:
- Status: 201
- Respuesta: {'nombre': 'Miel Orgánica de Abeja Melipona', 'descripcion': 'Miel virgen 100% natural recolectada en la sierra de Nayarit.', 'precio': 150.5, 'categoria': 'frutas', 'productor_id': 42, 'disponible': True, 'id': 101, 'creado_en': '2024-02-26T14:30:00Z'}

Nota: no hay de logs de warnings ni de errores porque no hay errores ni warnings xddddddddddddddddddd
bueno al menos no que yo los note, pero si hubiera errores o warnings, el decorador los capturaria y los mostraria en el log

bueno aqui esta un error critico forzado
✅ PRODUCTOS CARGADOS:
ERROR:EcoMarket.Observability:💥 FALLO CRÍTICO: [2026-01-29T16:27:57.725428] listar_productos | Excepción: AttributeError | 5.47ms


# SUGERENCIAS para la version 2.0
Dado que estamos manejando la version 1.0 de la api como una demo, en la version 2.0 ya se plantearia una arquitectura mas robusta, con un manejo de errores mas completo, con un manejo de sesiones mas completo, con un manejo de tokens mas completo.
Empezar a pensar en el usuario final, en el lanzamiento, en requerimientos y en como estos afectan a la arquitectura y experiencia del usuario final. 

Ejemplos:
1. implementar autenticacion estricta en api de prueba real (jwt)
2. implementar manejo de sesiones en api de prueba real (redis)
3. poner escenarios de stress en la api para vigilar que la api no se cae a la minima que suban los usuarios. 
