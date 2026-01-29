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
    #TERCERA MEJORA (mejora), no teniamos manejo de errores de parseo de JSON (si habia pero era generico, ahora es especifico)
    except json.JSONDecodeError:
        return BusinessError("Error desconocido en el servidor", "SERVER_ERROR")

    # Mapeamos errores técnicos a errores de negocio
    error_code = data.get("code")

    if error_code == "INSUFFICIENT_STOCK":
        return BusinessError("Lo sentimos, ya no queda miel en inventario.", "STOCK_OUT")
    elif error_code == "INVALID_TOKEN":
        return BusinessError("Tu sesión ha expirado, por favor entra de nuevo.", "AUTH_EXPIRED")

    return BusinessError(data.get("message", "Error inesperado"), "GENERIC_ERROR")




class BearerAuth(requests.auth.AuthBase):
    def __init__(   self, token_callback):
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
        #SEGUNDA MEJORA (CRITICA), no esta inicializado el token
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
            try:
                result = func(self, *args, **kwargs)
                # Si el resultado es una Response, verificamos el status
                if isinstance(result, requests.Response):
                    result.raise_for_status()
                return result
            except requests.exceptions.HTTPError as e:
                print(f"❌ LOG: Falló {func.__name__} en {e.response.url} - Status: {e.response.status_code}")
                biz_error = error_parser(e.response)
                print(f"📢 Mensaje para usuario: {biz_error.mensaje}")
                raise biz_error
            #primera mejora (critica), no teniamos manejo de errores de conexion
            except requests.exceptions.RequestException as e:
                print(f"❌ LOG: Falló {func.__name__} en {e.response.url} - Status: {e.response.status_code}")
                biz_error = error_parser(e.response)
                print(f"📢 Mensaje para usuario: {biz_error.mensaje}")
                raise biz_error
        return wrapper

    @interceptar_errores
    def listar_productos(self):
        # USAMOS self.session para aprovechar los headers y la conexión keep-alive

        response = self.session.get(f"{self.base_url}/productos", timeout=10)
        response.raise_for_status()
        
        productos = response.json()
        print("\n✅ PRODUCTOS CARGADOS:")
        # print(json.dumps(productos, indent=4, ensure_ascii=False))
        return productos

    @interceptar_errores
    def obtener_producto(self, producto_id):
        url = f"{self.base_url}/productos/{producto_id}"
        response = self.session.get(url, timeout=5)
        response.raise_for_status()
        return response.json()

    @interceptar_errores
    def crear_producto(self, nuevo_producto):
        url = f"{self.base_url}/productos"
        response = self.session.post(url, json=nuevo_producto, timeout=10)
        return response

# --- EJECUCIÓN ---
if __name__ == "__main__":
    # Mock token for Prism testing - replace with real JWT in production
    api = APIservices(BASE_URL, token="mock-jwt-token-for-testing")

    listaProductos = api.listar_productos()
    #mejora 4, manejar Impresion de productos en main en lugar del metodo de clases (separacion de responsabilidades)
    print(f"He recibido {len(listaProductos)} productos.")
    for p in listaProductos:
        print(f"- {p['nombre']}: ${p['precio']}")



    producto = api.obtener_producto(1)
    print(f"\n✅ PRODUCTO OBTENIDO:")
    print(f"- {producto['nombre']}: ${producto['precio']}")

    data = {
        "nombre": "Miel Orgánica de Abeja",
        "descripcion": "Miel virgen 100% natural recolectada en la sierra.",
        "precio": 150.50,
        "categoria": "miel",
        "productor_id": 1,
        "disponible": True
    }
    resultado = api.crear_producto(data)
    print(f"\n✅ PRODUCTO CREADO:")
    print(f"- Status: {resultado.status_code}")
    print(f"- Respuesta: {resultado.json()}")

    api.session.close()