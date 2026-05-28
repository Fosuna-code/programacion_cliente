"""
    this file is for testing purposes only profe, i wanted to do it this way so i don't have to modify the code to test the
    excercises scenarios
"""

""" Scenario A  - Timeout Error"""
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from monitor import ServicioPolling

# 1. Patch 'listar_productos' where it is used (inside the monitor module)
# We use new_callable=AsyncMock because it's an 'async def' function
@patch('monitor.listar_productos', new_callable=AsyncMock)
def test_inventario_timeout(mock_listar):
    mock_listar.side_effect = asyncio.TimeoutError("Connection timed out")

    monitor = ServicioPolling(5)
    
    # 1. Create a variable to track if the error was broadcasted
    error_was_broadcasted = False
    
    # 2. Create a fake function to act as an observer
    def spy_error_observer(datos):
        nonlocal error_was_broadcasted
        error_was_broadcasted = True
        
    # 3. Subscribe the spy to listen for errors
    monitor.suscribir("error_servidor", spy_error_observer)
    
    asyncio.run(monitor._consultar())
    
    if monitor.intervalo_actual == monitor.intervalo_max and error_was_broadcasted:
        print("Success! The timeout was handled AND the error was broadcasted.")
    else:
        print("Failed. The timeout was not handled properly.")


""" Scenario B - HTML response instead of JSON"""
import json

@patch('monitor.listar_productos', new_callable=AsyncMock)
def test_inventario_html_response(mock_listar):
    # Simulate the JSON decode error that occurs when trying to parse HTML as JSON
    mock_listar.side_effect = json.JSONDecodeError("Expecting value", "<html><body>Bad Gateway</body></html>", 0)

    monitor = ServicioPolling(5)
    
    # 1. Create a variable to track if the error was broadcasted
    error_was_broadcasted = False
    
    # 2. Create a fake function to act as an observer
    def spy_error_observer(datos):
        nonlocal error_was_broadcasted
        error_was_broadcasted = True
        
    # 3. Subscribe the spy to listen for errors
    monitor.suscribir("error_servidor", spy_error_observer)
    
    # 4. Run the async method.
    asyncio.run(monitor._consultar())
    
    # 5. Verify the behavior
    if monitor.intervalo_actual == monitor.intervalo_max and error_was_broadcasted:
        print("Success! The HTML response error was handled AND the error was broadcasted.")
    else:
        print("Failed. The HTML response error was not handled properly.")
""" Scenario C - Un observador lanza una excepcion no capturada dentro de su callback """

@patch('monitor.listar_productos', new_callable=AsyncMock)
def test_observer_exception(mock_listar):
    # Simulamos que la red funciona perfecto devolviendo datos ficticios
    mock_listar.return_value = [{"id": 1, "nombre": "Test"}]
    
    success_observer_was_called = False
    
    # Este observador simula un crash (ej. UI rota)
    def spy_crash_observer(datos):
        raise Exception("Something went wrong in the observer!")
        
    # Este observador simula uno que sí funciona
    def spy_success_observer(datos):
        nonlocal success_observer_was_called
        success_observer_was_called = True

    monitor = ServicioPolling(5)
    
    # El orden de suscripción importa para el test: 
    # Queremos que el crash ocurra primero, para ver si el segundo sobrevive.
    monitor.suscribir("datos_actualizados", spy_crash_observer)
    monitor.suscribir("datos_actualizados", spy_success_observer)

    # 1. ¡FALTABA ESTA LÍNEA! Ejecutar el monitor
    asyncio.run(monitor._consultar())

    # 2. VALIDACIÓN CORREGIDA:
    # Verificamos que el segundo observador se ejecutó a pesar del crash del primero.
    if success_observer_was_called:
        print("Success! The observer exception was handled AND the success observer was called.")
    else:
        print("Failed. The observer exception was not handled properly.")
    
""" Scenario D El servidor devuelve 200 pero el campo "productos" viene como null""" 
@patch('monitor.listar_productos', new_callable=AsyncMock)
def test_Null_Data(mock_listar):
     # 1. Simulamos la respuesta "Correcta" del servidor (HTTP 200 OK) pero con datos nulos
    mock_listar.return_value = None
    nullish_was_handled = False 
    monitor = ServicioPolling(5)

    def spy_nullish_observer(datos):
        nonlocal nullish_was_handled
        nullish_was_handled = True

    monitor.suscribir("error_servidor", spy_nullish_observer)

    asyncio.run(monitor._consultar())

    if nullish_was_handled:
        print("Success! The nullish data was handled AND the error was broadcasted.")
    else:
        print("Failed. The nullish data was not handled properly.")

         
"""PRUEBA DE DESAPLOCAMIENTO"""
def test_desacoplamiento_extremo():
    """
    Verifica que ServicioPolling no depende de ninguna clase concreta de la app.
    Podemos conectarle un objeto completamente ajeno (un mock puro) y funciona.
    """
    monitor = ServicioPolling(5)
    
    # 1. Creamos un "Alien": una función falsa que no tiene nada que ver con EcoMarket
    # Si el Monitor requiere que el observador herede de "ClaseUIBase", esto fallará.
    alien_observer = MagicMock()
    
    # 2. Lo suscribimos
    monitor.suscribir("datos_actualizados", alien_observer)
    
    # 3. Simulamos que el monitor recibe datos internamente y lanza la notificación
    datos_ficticios = [{"id": 99, "nombre": "Teclado Alienígena"}]
    asyncio.run(monitor.notificar("datos_actualizados", datos_ficticios))
    
    # 4. Verificación
    # Si el monitor está bien desacoplado, solo le importa llamar a la función (callable)
    # y pasarle los datos, sin importarle quién es o de dónde viene.
    alien_observer.assert_called_once_with(datos_ficticios)
    print("¡Éxito! El ServicioPolling está perfectamente desacoplado.")
    
    


if __name__ == "__main__":
    print("--- Running Scenario A ---")
    test_inventario_timeout()
    
    print("\n--- Running Scenario B ---")
    test_inventario_html_response()

    print("\n--- Running Scenario C ---")
    test_observer_exception()

    print("\n--- Running Scenario D ---")
    test_Null_Data()
    
    print("\n--- Running Test Desacoplamiento ---")
    test_desacoplamiento_extremo()




