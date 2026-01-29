# RETO 8: Auditoría de Resiliencia con Prism

## tabla de resultados

Escenario Probado,"Resultado ""Antes"" (Sin Mejoras)",Mejora Implementada en clientehttp_mejorado.py,Resultado Después (Log Real)
1. Latencia Extrema (Timeout),"El cliente esperaría indefinidamente, bloqueando el hilo de ejecución principal del software.",Parámetros timeout=10 en listar_productos y timeout=5 en obtener_producto.,"""La petición tuvo éxito"". Prism no aplicó el delay de 12s, por lo que el timeout no se disparó."
2. Error de Servidor (503),"El script crashearía con una excepción HTTPError no controlada, interrumpiendo el flujo.",Decorador @interceptar_errores que captura HTTPError y RequestException.,"✔️ Caos controlado. Se recibió un 404 en lugar de 503, pero el decorador evitó el crash del sistema."
3. Sesión Expirada (401),"El sistema no sabría interpretar la respuesta del servidor, mostrando errores técnicos crudos.",Clase BusinessError y lógica de mapeo en error_parser para códigos como INVALID_TOKEN.,✔️ Caos controlado. Prism devolvió 404; el cliente lo mapeó como GENERIC_ERROR sin romperse.
4. Formato Inesperado (No JSON),"El parseo fallaría lanzando un JSONDecodeError, exponiendo trazas de error de Python al usuario.",Bloque try-except json.JSONDecodeError dentro de la función error_parser.,✔️ Caos controlado. Se recibió Status 406. El parser detectó el error y mostró un mensaje amigable.

## Conclusiones
El cliente http mejorado es capaz de manejar errores de red y de servidor, lo que lo hace más resiliente y robusto. Además, el cliente http mejorado es capaz de manejar errores de formato de respuesta, lo que lo hace más robusto. En general, el cliente http mejorado es una mejora significativa con respecto al cliente http original. 
Las capturas de devTool no son necesarias dado a que la el mock server de prism es el que se encarga de simular los errores y latencia (como se ve en el codigo cliente_mejorado_a_prueba.py).