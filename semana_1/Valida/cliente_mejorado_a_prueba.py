#este codigo es para probar el cliente http mejorado en el reto 8
import requests
from clientehttp_mejorado import APIservices, BusinessError

BASE_URL = "http://127.0.0.1:4010"

def ejecutar_prueba_caos(nombre, headers_caos, api_instance):
    print(f"\n🔥 EJECUTANDO: {nombre}")
    print("-" * 50)
    
    # Inyectamos los headers de caos directamente en la sesión para esta prueba
    api_instance.session.headers.update(headers_caos)
    
    try:
        # Intentamos una operación común
        api_instance.listar_productos()
        print("✅ Resultado inesperado: La petición tuvo éxito (no hubo caos).")
    except BusinessError as e:
        print(f"✔️ Caos controlado: {e.mensaje} (Código: {e.codigo})")
    except requests.exceptions.Timeout:
        print("✔️ Caos controlado: Se disparó el Timeout correctamente.")
    except Exception as e:
        print(f"❌ Error no controlado: {type(e).__name__} - {e}")
    finally:
        # Limpiamos los headers de caos para la siguiente prueba
        for header in headers_caos:
            if header in api_instance.session.headers:
                del api_instance.session.headers[header]

if __name__ == "__main__":
    # Inicializamos nuestro servicio
    api = APIservices(BASE_URL, token="test-token")

    # Definición de escenarios de caos para Prism
    escenarios = [
        {
            "nombre": "Escenario 1: Latencia Extrema (Timeout)",
            "headers": {"Prefer": "delay=12000"} # Prism tardará 12s (tu limite es 10s)
        },
        {
            "nombre": "Escenario 2: Error de Servidor (503)",
            "headers": {"Prefer": "code=503"}
        },
        {
            "nombre": "Escenario 3: Sesión Expirada (401)",
            "headers": {"Prefer": "code=401"} # Debería activar tu mapeo 'AUTH_EXPIRED'
        },
        {
            "nombre": "Escenario 4: Formato Inesperado (No JSON)",
            "headers": {"Accept": "text/plain"} # Obliga a Prism a no enviar JSON
        }
    ]

    print("🚀 Iniciando Auditoría de Resiliencia...")
    for escenario in escenarios:
        ejecutar_prueba_caos(escenario["nombre"], escenario["headers"], api)