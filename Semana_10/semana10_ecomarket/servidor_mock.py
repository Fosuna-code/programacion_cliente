"""
servidor_mock.py — Servidor Mock para EcoMarket (Semana 10: Grand Deploy)
Ejecutar: python servidor_mock.py
Endpoint: http://localhost:3000

SEMANA 10 - Cambios respecto a Semana 9:
  - JWT auth real con /auth/login (retorna JWT firmado con payload sub/rol/exp)
  - /auth/token endpoint para refresh (también retorna JWT)
  - Middleware de autenticación Bearer en endpoints protegidos
  - Role-based access: viewer puede GET, admin/supervisor puede todo
  - SSE con soporte para Last-Event-ID y autenticación
  - Contador de peticiones a /auth/token para verificar INV-B3 (refresh singleton)
  - Mantenidos todos los modos de fallo: normal, fallo_503, timeout, auth_401
  - Mantenidos todos los endpoints CRUD de productos
"""

import time
import json
import base64
import hashlib
import hmac
import queue
import threading
from flask import Flask, jsonify, request, Response
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ── JWT SIMPLE (sin PyJWT para no requerir dependencias extra) ──────────
JWT_SECRET = "ecomarket_secret_key_2024"
JWT_ALGORITHM = "HS256"

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')

def _b64url_decode(data: str) -> bytes:
    padding = 4 - len(data) % 4
    if padding != 4:
        data += '=' * padding
    return base64.urlsafe_b64decode(data)

def create_jwt(payload: dict) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    header_enc = _b64url_encode(json.dumps(header).encode())
    payload_enc = _b64url_encode(json.dumps(payload).encode())
    signature = hmac.new(JWT_SECRET.encode(), f"{header_enc}.{payload_enc}".encode(), hashlib.sha256).digest()
    sig_enc = _b64url_encode(signature)
    return f"{header_enc}.{payload_enc}.{sig_enc}"

def decode_jwt(token: str) -> dict | None:
    try:
        partes = token.split('.')
        if len(partes) != 3:
            return None
        payload_bytes = _b64url_decode(partes[1])
        payload = json.loads(payload_bytes)
        # Verificar firma (pero sin rechazar — el cliente solo decodifica)
        header_enc = partes[0]
        payload_enc = partes[1]
        expected_sig = _b64url_encode(
            hmac.new(JWT_SECRET.encode(), f"{header_enc}.{payload_enc}".encode(), hashlib.sha256).digest()
        )
        if expected_sig != partes[2]:
            return None
        return payload
    except Exception:
        return None

def get_bearer_token():
    auth = request.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        return auth[7:].strip()
    return None

def get_current_user():
    token = get_bearer_token()
    if not token:
        return None
    payload = decode_jwt(token)
    if not payload:
        return None
    exp = payload.get('exp', 0)
    if time.time() > exp:
        return None
    return payload

# ── MODO DEL SERVIDOR ─────────────────────────────────────────
modo_servidor = 'normal'
peticiones_recibidas = 0
auth_token_requests = 0
auth_token_requests_lock = threading.Lock()

clientes_sse = []
eventos_sse_historial = []
eventos_sse_lock = threading.Lock()
ultimo_evento_sse_id = int(time.time() * 1000)
MAX_EVENTOS_SSE = 100


def _crear_evento_sse(tipo_evento, datos, guardar=True):
    global ultimo_evento_sse_id
    with eventos_sse_lock:
        ultimo_evento_sse_id = max(ultimo_evento_sse_id + 1, int(time.time() * 1000))
        evento = {
            'id': str(ultimo_evento_sse_id),
            'type': tipo_evento,
            'data': datos,
        }
        if guardar:
            eventos_sse_historial.append(evento)
            del eventos_sse_historial[:-MAX_EVENTOS_SSE]
        return evento


def _eventos_sse_desde(last_event_id):
    try:
        last_id = int(last_event_id)
    except (TypeError, ValueError):
        return []
    with eventos_sse_lock:
        return [evento.copy() for evento in eventos_sse_historial if int(evento['id']) > last_id]


def _formatear_sse(evento):
    event_data = json.dumps(evento.get('data', {}))
    return f"id: {evento['id']}\nevent: {evento.get('type', 'message')}\ndata: {event_data}\n\n"


def notificar_clientes(tipo_evento, datos):
    evento = _crear_evento_sse(tipo_evento, datos)
    for q in clientes_sse:
        q.put(evento)

productos_db = {
    1: {
        "id": 1, "nombre": "Bolsa Reutilizable", "precio": 15.99,
        "categoria": "accesorios", "descripcion": "Bolsa ecologica de algodon", "stock": 100
    },
    2: {
        "id": 2, "nombre": "Botella de Acero", "precio": 29.99,
        "categoria": "bebidas", "descripcion": "Botella termica 500ml", "stock": 50
    },
    3: {
        "id": 3, "nombre": "Cepillo de Bambu", "precio": 8.50,
        "categoria": "higiene", "descripcion": "Cepillo dental biodegradable", "stock": 200
    }
}
next_id = 4
login_counter = 0

def log_request(method, path, status):
    status_emoji = "OK" if status < 400 else "ERR"
    print(f"  [{status_emoji}] [{method}] {path} -> {status}")

def _aplicar_modo(allow_auth_401=True):
    global peticiones_recibidas
    peticiones_recibidas += 1
    if modo_servidor == 'fallo_503':
        return jsonify({"error": "Service Unavailable"}), 503
    if modo_servidor == 'timeout':
        time.sleep(60)
        return None, None
    if modo_servidor == 'auth_401' and allow_auth_401:
        return jsonify({"error": "Unauthorized"}), 401
    return None, None

# ============================================================
# AUTH ENDPOINTS
# ============================================================

@app.route('/auth/login', methods=['POST'])
def auth_login():
    global login_counter
    login_counter += 1
    datos = request.get_json(silent=True) or {}
    username = datos.get('username', 'op1')
    password = datos.get('password', '')

    exp_seconds = datos.get('exp_seconds', 900)
    rol = datos.get('rol', 'viewer')

    if username == 'admin':
        rol = 'admin'

    now = time.time()
    payload = {
        "sub": username,
        "rol": rol,
        "exp": int(now + exp_seconds),
        "iat": int(now)
    }
    access_token = create_jwt(payload)

    refresh_payload = {
        "sub": username,
        "rol": rol,
        "exp": int(now + 86400),
        "iat": int(now),
        "type": "refresh"
    }
    refresh_token = create_jwt(refresh_payload)

    log_request('POST', '/auth/login', 200)
    return jsonify({
        'access_token': access_token,
        'refresh_token': refresh_token,
        'expires_in': exp_seconds,
        'user': {"sub": username, "rol": rol}
    }), 200


@app.route('/auth/token', methods=['POST'])
def auth_token():
    global peticiones_recibidas, auth_token_requests
    peticiones_recibidas += 1
    with auth_token_requests_lock:
        auth_token_requests += 1

    if modo_servidor == 'auth_401':
        log_request('POST', '/auth/token', 401)
        return jsonify({"error": "Unauthorized"}), 401

    old_token = get_bearer_token()
    user = get_current_user()
    sub = user.get('sub', 'op1') if user else 'op1'
    rol = user.get('rol', 'viewer') if user else 'viewer'

    if old_token:
        payload_viejo = decode_jwt(old_token)
        if payload_viejo:
            sub = payload_viejo.get('sub', sub)
            rol = payload_viejo.get('rol', rol)

    now = time.time()
    new_payload = {"sub": sub, "rol": rol, "exp": int(now + 900), "iat": int(now)}
    new_token = create_jwt(new_payload)

    refresh_payload = {"sub": sub, "rol": rol, "exp": int(now + 86400), "iat": int(now), "type": "refresh"}
    new_refresh = create_jwt(refresh_payload)

    log_request('POST', '/auth/token', 200)
    return jsonify({
        'access_token': new_token,
        'refresh_token': new_refresh,
        'expires_in': 900
    }), 200


@app.route('/auth/token-count', methods=['GET'])
def auth_token_count():
    with auth_token_requests_lock:
        count = auth_token_requests
    return jsonify({"auth_token_requests": count}), 200


@app.route('/auth/token-count/reset', methods=['POST'])
def auth_token_count_reset():
    global auth_token_requests
    with auth_token_requests_lock:
        auth_token_requests = 0
    return jsonify({"auth_token_requests": 0}), 200

# ============================================================
# ADMIN ENDPOINTS
# ============================================================

@app.route('/admin/modo', methods=['POST'])
def cambiar_modo():
    global modo_servidor
    datos = request.get_json(silent=True) or {}
    nuevo = datos.get('modo', 'normal')
    if nuevo not in ('normal', 'fallo_503', 'timeout', 'auth_401'):
        return jsonify({"error": f"Modo '{nuevo}' no valido"}), 400
    modo_servidor = nuevo
    log_request('POST', '/admin/modo', 200)
    return jsonify({"modo": modo_servidor, "mensaje": f"Modo cambiado a {modo_servidor}"}), 200


@app.route('/admin/modo', methods=['GET'])
def obtener_modo():
    return jsonify({"modo": modo_servidor, "peticiones_recibidas": peticiones_recibidas}), 200


@app.route('/admin/reset', methods=['POST'])
def reset_contador():
    global peticiones_recibidas, auth_token_requests
    peticiones_recibidas = 0
    with auth_token_requests_lock:
        auth_token_requests = 0
    return jsonify({"mensaje": "Contadores reseteados", "peticiones_recibidas": 0, "auth_token_requests": 0}), 200

# ============================================================
# SSE ENDPOINT (con auth y Last-Event-ID)
# ============================================================

@app.route('/api/alertas', methods=['GET'])
def sse_alertas():
    user = get_current_user()
    if not user:
        log_request('GET', '/api/alertas (SSE - no auth)', 401)
        return jsonify({"error": "Unauthorized - se requiere Bearer token para SSE"}), 401

    last_event_id = request.headers.get('Last-Event-ID')
    if last_event_id:
        log_request('GET', f'/api/alertas (SSE reconectado, Last-Event-ID: {last_event_id}, user: {user.get("sub")})', 200)
    else:
        log_request('GET', f'/api/alertas (SSE conectado, user: {user.get("sub")})', 200)

    q = queue.Queue()
    clientes_sse.append(q)

    def generar_eventos():
        try:
            if last_event_id:
                for evento in _eventos_sse_desde(last_event_id):
                    yield _formatear_sse(evento)
            else:
                initial = _crear_evento_sse(
                    'sistema',
                    {
                        "mensaje": "Conexion SSE establecida con EcoMarket",
                        "user": user.get("sub"),
                        "rol": user.get("rol"),
                    },
                    guardar=False,
                )
                yield _formatear_sse(initial)

            while True:
                try:
                    evento = q.get(timeout=10)
                    yield _formatear_sse(evento)
                except queue.Empty:
                    yield ': ping keep-alive\n\n'
        except GeneratorExit:
            log_request('SSE', '/api/alertas (Desconectado por el cliente)', 204)
        finally:
            if q in clientes_sse:
                clientes_sse.remove(q)

    return Response(generar_eventos(), content_type='text/event-stream',
                    headers={'X-Accel-Buffering': 'no', 'Cache-Control': 'no-cache'})

# ============================================================
# ENDPOINTS CRUD (con autenticación)
# ============================================================

@app.route('/api/inventario', methods=['GET'])
def obtener_inventario():
    user = get_current_user()
    if not user:
        log_request('GET', '/api/inventario', 401)
        return jsonify({"error": "Unauthorized"}), 401

    modo_resp = _aplicar_modo()
    if modo_resp[0] is not None:
        return modo_resp

    log_request('GET', '/api/inventario', 200)
    return jsonify({"productos": len(productos_db), "timestamp": time.time(), "user": user.get('sub')}), 200


@app.route('/api/productos', methods=['GET'])
def listar_productos():
    user = get_current_user()
    if not user:
        log_request('GET', '/api/productos', 401)
        return jsonify({"error": "Unauthorized"}), 401

    categoria = request.args.get('categoria')
    orden = request.args.get('orden')
    delay = request.args.get('delay', type=int)
    if delay:
        time.sleep(delay)

    resultado = list(productos_db.values())
    if categoria:
        resultado = [p for p in resultado if p.get('categoria') == categoria]
    if orden == 'precio_asc':
        resultado.sort(key=lambda x: x.get('precio', 0))
    elif orden == 'precio_desc':
        resultado.sort(key=lambda x: x.get('precio', 0), reverse=True)

    log_request('GET', '/api/productos', 200)
    return jsonify(resultado), 200


@app.route('/api/categorias', methods=['GET'])
def listar_categorias():
    categorias = [
        {"id": 1, "nombre": "accesorios", "descripcion": "Accesorios ecologicos",
         "total_productos": len([p for p in productos_db.values() if p.get('categoria') == 'accesorios'])},
        {"id": 2, "nombre": "bebidas", "descripcion": "Contenedores para bebidas",
         "total_productos": len([p for p in productos_db.values() if p.get('categoria') == 'bebidas'])},
        {"id": 3, "nombre": "higiene", "descripcion": "Productos de higiene personal",
         "total_productos": len([p for p in productos_db.values() if p.get('categoria') == 'higiene'])}
    ]
    log_request('GET', '/api/categorias', 200)
    return jsonify(categorias), 200


@app.route('/api/productos/invalido', methods=['GET'])
def obtener_producto_invalido():
    producto_corrupto = {
        "id": 999, "nombre": "Producto Corrupto", "precio": -15.00,
        "categoria": "frutas", "descripcion": "Este producto tiene precio negativo"
    }
    log_request('GET', '/api/productos/invalido', 200)
    return jsonify(producto_corrupto), 200


@app.route('/api/perfil', methods=['GET'])
def obtener_perfil():
    user = get_current_user()
    if not user:
        log_request('GET', '/api/perfil', 401)
        return jsonify({"error": "Unauthorized"}), 401

    perfil = {
        "id": 1, "nombre": f"Usuario {user.get('sub', 'Demo')}",
        "email": f"{user.get('sub', 'demo')}@ecomarket.com",
        "rol": user.get('rol', 'viewer'),
        "preferencias": {"categoria_favorita": "accesorios", "notificaciones": True},
        "fecha_registro": "2024-01-15T10:30:00Z"
    }
    log_request('GET', '/api/perfil', 200)
    return jsonify(perfil), 200


@app.route('/api/productos/<int:producto_id>', methods=['GET'])
def obtener_producto(producto_id):
    if producto_id not in productos_db:
        log_request('GET', f'/api/productos/{producto_id}', 404)
        return jsonify({"error": "Producto no encontrado"}), 404
    log_request('GET', f'/api/productos/{producto_id}', 200)
    return jsonify(productos_db[producto_id]), 200


@app.route('/api/productos', methods=['POST'])
def crear_producto():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    if user.get('rol') == 'viewer':
        log_request('POST', '/api/productos', 403)
        return jsonify({"error": "Permission denied: viewer cannot create products"}), 403

    global next_id
    if not request.is_json:
        return jsonify({"error": "Content-Type debe ser application/json"}), 400
    datos = request.get_json()
    if not datos.get('nombre'):
        return jsonify({"error": "El campo 'nombre' es requerido"}), 400

    for p in productos_db.values():
        if p['nombre'].lower() == datos.get('nombre', '').lower():
            return jsonify({"error": f"Ya existe un producto con el nombre '{datos['nombre']}'"}), 409

    nuevo = {
        "id": next_id, "nombre": datos.get('nombre'), "precio": datos.get('precio', 0),
        "categoria": datos.get('categoria', 'general'), "descripcion": datos.get('descripcion', ''),
        "stock": datos.get('stock', 0)
    }
    productos_db[next_id] = nuevo
    next_id += 1
    notificar_clientes('nuevo-producto', nuevo)
    if nuevo.get('stock', 0) <= 5:
        notificar_clientes('stock-critico', {"producto": nuevo['nombre'], "stock": nuevo['stock']})
    log_request('POST', '/api/productos', 201)
    return jsonify(nuevo), 201


@app.route('/api/productos/<int:producto_id>', methods=['PUT'])
def actualizar_producto_total(producto_id):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    if user.get('rol') == 'viewer':
        return jsonify({"error": "Permission denied: viewer cannot update products"}), 403

    if producto_id not in productos_db:
        return jsonify({"error": "Producto no encontrado"}), 404
    if not request.is_json:
        return jsonify({"error": "Content-Type debe ser application/json"}), 400

    datos = request.get_json()
    productos_db[producto_id] = {
        "id": producto_id, "nombre": datos.get('nombre', ''), "precio": datos.get('precio', 0),
        "categoria": datos.get('categoria', 'general'), "descripcion": datos.get('descripcion', ''),
        "stock": datos.get('stock', 0)
    }
    notificar_clientes('precio-actualizado', {"producto": productos_db[producto_id]['nombre'], "precio": productos_db[producto_id]['precio']})
    log_request('PUT', f'/api/productos/{producto_id}', 200)
    return jsonify(productos_db[producto_id]), 200


@app.route('/api/productos/<int:producto_id>', methods=['PATCH'])
def actualizar_producto_parcial(producto_id):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    if user.get('rol') == 'viewer':
        return jsonify({"error": "Permission denied: viewer cannot update products"}), 403

    if producto_id not in productos_db:
        return jsonify({"error": "Producto no encontrado"}), 404
    if not request.is_json:
        return jsonify({"error": "Content-Type debe ser application/json"}), 400

    datos = request.get_json()
    for campo, valor in datos.items():
        if campo != 'id':
            productos_db[producto_id][campo] = valor

    if 'precio' in datos:
        notificar_clientes('precio-actualizado', {"producto": productos_db[producto_id]['nombre'], "precio": productos_db[producto_id]['precio']})
    if 'stock' in datos and productos_db[producto_id].get('stock', 0) <= 5:
        notificar_clientes('stock-critico', {"producto": productos_db[producto_id]['nombre'], "stock": productos_db[producto_id]['stock']})
    log_request('PATCH', f'/api/productos/{producto_id}', 200)
    return jsonify(productos_db[producto_id]), 200


@app.route('/api/productos/<int:producto_id>', methods=['DELETE'])
def eliminar_producto(producto_id):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    if user.get('rol') == 'viewer':
        return jsonify({"error": "Permission denied: viewer cannot delete products"}), 403

    if producto_id not in productos_db:
        return jsonify({"error": "Producto no encontrado"}), 404
    nombre = productos_db[producto_id]['nombre']
    del productos_db[producto_id]
    notificar_clientes('producto-eliminado', {"id": producto_id, "producto": nombre})
    log_request('DELETE', f'/api/productos/{producto_id}', 204)
    return '', 204


# ============================================================
# SERVIDOR
# ============================================================

if __name__ == '__main__':
    print("=" * 60)
    print("EcoMarket Mock Server — Semana 10: Grand Deploy")
    print("=" * 60)
    print(f"URL Base: http://localhost:3000/api/")
    print(f"Productos iniciales: {len(productos_db)}")
    print("-" * 60)
    print("Endpoints disponibles:")
    print("  POST   /auth/login              - Login (retorna JWT)")
    print("  POST   /auth/token               - Refresh token (NO pasa por CB)")
    print("  GET    /auth/token-count          - Contar refresh requests (INV-B3)")
    print("  POST   /auth/token-count/reset   - Resetear contador de refresh")
    print("  GET    /api/productos             - Listar productos (auth)")
    print("  GET    /api/productos/{id}        - Obtener producto")
    print("  POST   /api/productos             - Crear producto (rol != viewer)")
    print("  PUT    /api/productos/{id}        - Actualizar (total, rol != viewer)")
    print("  PATCH  /api/productos/{id}        - Actualizar (parcial, rol != viewer)")
    print("  DELETE /api/productos/{id}        - Eliminar (rol != viewer)")
    print("  GET    /api/categorias            - Listar categorias")
    print("  GET    /api/perfil               - Perfil usuario (auth)")
    print("  GET    /api/inventario            - Inventarios (auth, CB testing)")
    print("  GET    /api/alertas              - [SSE] Eventos en tiempo real (auth)")
    print("  GET    /api/productos/invalido     - Producto con precio negativo (testing)")
    print("  POST   /admin/modo               - Cambiar modo servidor")
    print("  GET    /admin/modo               - Consultar modo servidor")
    print("  POST   /admin/reset              - Resetear contadores")
    print("-" * 60)
    print("Modos de fallo:")
    print("  normal     -> Responde 200 OK")
    print("  fallo_503  -> Responde 503 Service Unavailable")
    print("  timeout    -> No responde (simula timeout 60s)")
    print("  auth_401   -> Responde 401 Unauthorized")
    print("-" * 60)
    print("Auth: Enviar Bearer token en Authorization header")
    print("  Login: POST /auth/login  {\"username\":\"op1\",\"rol\":\"viewer\"}")
    print("  Default user: op1 (rol: viewer), admin (rol: admin)")
    print("Presiona Ctrl+C para detener el servidor\n")

    app.run(host='localhost', port=3000, debug=True)
