"""
TRAZA DE SHORT POLLING (EcoMarket):
- Consulta 1: GET /api/productos -> Status 200 OK | ETag: "abc123" | Intervalo: 5s (se mantiene)
- Consulta 2: GET /api/productos + If-None-Match: "abc123" -> Status 304 Not Modified | Intervalo: 5s
- Consulta 3: GET /api/productos + If-None-Match: "abc123" -> Status 304 Not Modified | Intervalo: 5s
- Consulta 4: GET /api/productos + If-None-Match: "abc123" -> Status 200 OK | Nuevo ETag: "def456" | Intervalo: 5s

¿Por qué ETag es más eficiente que comparar datos completos?
Comparar un ETag (un simple hash de texto) consume mucha menos memoria y CPU en el servidor que 
extraer todos los registros de la base de datos y comparar cada campo del JSON. Además, 
al devolver solo un código 304, nos ahorramos enviar todo el peso de los datos por la red.
"""

