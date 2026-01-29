import requests
import json
from functools import wraps

BASE_URL = "http://127.0.0.1:4010"


class BusinessError(Exception):
    """Excepción personalizada para errores de EcoMarket"""
    def __init__(self, mensaje, codigo):
        self.mensaje = mensaje
        self.codigo = codigo
        super().__init__(self.mensaje)

def error_parser(response):
    # Intentamos parsear el JSON
    try:
        data = response.json()
    except:
        return BusinessError("Error desconocido en el servidor", "SERVER_ERROR")

    # Mapeamos errores técnicos a errores de negocio
    error_code = data.get("code")
    
    if error_code == "INSUFFICIENT_STOCK":
        return BusinessError("Lo sentimos, ya no queda miel en inventario.", "STOCK_OUT")
    elif error_code == "INVALID_TOKEN":
        return BusinessError("Tu sesión ha expirado, por favor entra de nuevo.", "AUTH_EXPIRED")
    
    return BusinessError(data.get("message", "Error inesperado"), "GENERIC_ERROR")




class BearerAuth(requests.auth.AuthBase):
    def __init__(self, token_callback):
        # Pasamos una función que nos de el token actual
        self.token_callback = token_callback

    def __call__(self, r):
        # Este método se ejecuta JUSTO ANTES de enviar la petición
        token = self.token_callback()
        if token:
            r.headers['Authorization'] = f"Bearer {token}"
        return r


class APIservices:
    def __init__(self, base_url, token=""):
        self.base_url = base_url
        self.session = requests.Session()
        #este era un error que no me percate hasta la fase de valida, la agrego aqui para evitar problemas de compilacion
        self.token = token
        self.session.auth = BearerAuth(lambda: self.token)

        # Configuramos la sesión UNA SOLA VEZ
        self.session.headers.update({
            "x-Client-Version": "1.0.0",
            "Accept": "application/json",
            "Content-Type": "application/json"
        })

    # Definimos el decorador como un método estático o fuera de la clase
    @staticmethod
    def interceptar_errores(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs): # Añadimos 'self'
            response = func(self, *args, **kwargs)
            if not response.ok:
                print(f"❌ LOG: Falló {func.__name__} en {response.url} - Status: {response.status_code}")
                biz_error = error_parser(response)
                print(f"📢 Mensaje para usuario: {biz_error.mensaje}")
                print(f"⚠️ Error controlado: {biz_error.mensaje} (código: {biz_error.codigo})")
                return None
            return response
        return wrapper

    @interceptar_errores
    def listar_productos(self):
        # USAMOS self.session para aprovechar los headers y la conexión keep-alive
        response = self.session.get(f"{self.base_url}/productos", timeout=10)
        
        productos = response.json()
        print("\n✅ PRODUCTOS CARGADOS:")
        print(json.dumps(productos, indent=4, ensure_ascii=False))
        return response

    @interceptar_errores
    def obtener_producto(self, producto_id):
        url = f"{self.base_url}/productos/{producto_id}"
        response = self.session.get(url, timeout=5)
        return response

    @interceptar_errores
    def crear_producto(self, nuevo_producto):
        url = f"{self.base_url}/productos"
        response = self.session.post(url, json=nuevo_producto, timeout=10)
        return response

# --- EJECUCIÓN ---
if __name__ == "__main__":
    # Prism mock server usually accepts any Bearer token
    token = "mi-token-de-prueba"
    api = APIservices(BASE_URL, token)
    
    api.listar_productos()
    api.obtener_producto(42)
    
    data = {
        "nombre": "Miel Orgánica de Abeja",
        "descripcion": "Miel virgen 100% natural recolectada en la sierra de Nayarit.",
        "precio": 150.50,
        "categoria": "miel",
        "productor_id": 7,
        "disponible": True
    }
    result = api.crear_producto(data)
    if result:
        print("✅ Producto creado exitosamente")
    api.session.close()
