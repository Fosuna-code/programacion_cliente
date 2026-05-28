# EcoMarket — Semana 10: Grand Deploy

Cliente HTTP completo que integra los componentes de Semanas 6–9 (SSE, JWT, Circuit Breaker) en un cliente robusto y resiliente.

## Requisitos

```bash
pip install -r requirements.txt
```

## Estructura del proyecto

```
semana10_ecomarket/
├── servidor_mock.py          # Servidor mock con JWT auth, SSE, CRUD, modos de fallo
├── circuit_breaker.py         # CircuitBreaker con 3 estados, callbacks UI
├── token_manager.py           # TokenManager con JWT decode, refresh singleton
├── cliente_robusto.py         # ClienteRobusto: orquesta CB + TM + Observer
├── cliente_sse_multiplex.py   # ClienteSSEMultiplex con auth y Last-Event-ID
├── cliente_integrado.py       # Script de integracion (Reto 4)
├── test_circuit_breaker.py     # Pruebas de invariantes INV-A1..INV-B3, TC-X2
├── test_tc_x2_refresh_semiaabierto.py # Prueba formal obligatoria de TC-X2
├── pytest.ini                  # Configuracion pytest-asyncio
├── run_demo.py                 # Runner: servidor + demo + tests
└── README.md                   # Este archivo
```

## Ejecutar

### 1. Iniciar el servidor mock

```bash
python servidor_mock.py
```

### 2. Ejecutar el demo integrado

```bash
python cliente_integrado.py
```

### 3. Ejecutar pruebas de invariantes

```bash
python test_circuit_breaker.py
python -m pytest test_circuit_breaker.py test_tc_x2_refresh_semiaabierto.py -q
```

### 4. Ejecutar todo automaticamente

```bash
python run_demo.py
```

## Componentes

### TokenManager (token_manager.py)

- `decode_payload(token)`: Decodifica JWT sin verificar firma (INV-A1 compatible)
- `is_expiring_soon(margen=60)`: Verifica si el token expira pronto
- `get_auth_header()`: Retorna `{"Authorization": "Bearer <token>"}`
- `refresh_access_token()`: Refresh singleton con asyncio.Lock (INV-B3)
- `login(username, rol)`: POST /auth/login, almacena tokens
- INV-B1: No tiene atributos del CircuitBreaker
- INV-B2: El token nunca aparece en logs

### CircuitBreaker (circuit_breaker.py)

- 3 estados: CERRADO, ABIERTO, SEMIABIERTO
- `ejecutar(fn)`: Punto de entrada principal
- INV-A1: Nunca accede a campos JWT
- INV-A2: En SEMIABIERTO, exactamente una peticion pasa (asyncio.Lock)
- INV-A3: `_fallos_consecutivos = 0` al cerrar
- INV-A4: HTTP 401/403 no incrementan fallos
- Callbacks: `on_circuit_open`, `on_circuit_close` para UI observable

### ClienteRobusto (cliente_robusto.py)

- Orquesta TokenManager + CircuitBreaker sin duplicar logica (SRP)
- Peticiones de auth NO pasan por el CB (evita deadlock Auth-Breaker)
- Refresh proactivo antes de `cb.ejecutar()`; refresh reactivo por 401 vía bypass silencioso
- Retry con backoff exponencial (max 3)
- Observer pattern para notificar estado a la UI
- Cache SSE como fallback cuando el circuito esta abierto

### ClienteSSEMultiplex (cliente_sse_multiplex.py)

- Conexion SSE independiente del CircuitBreaker (TC-X1/TC-X3)
- Auth Bearer en cada conexion
- Last-Event-ID preservado para reconexion (TC-X3)
- El servidor mock mantiene historial SSE en memoria y reenvia eventos con `id > Last-Event-ID`
- Reconexion automatica con backoff exponencial
- EventRouter con handlers dict

## Invariantes verificados

| Invariante | Descripcion | Estado |
|---|---|---|
| INV-A1 | CB nunca accede a campos JWT | ✅ |
| INV-A2 | SEMIABIERTO: exactamente 1 peticion pasa | ✅ |
| INV-A3 | `_fallos_consecutivos = 0` al cerrar | ✅ |
| INV-A4 | 401/403 no incrementan fallos | ✅ |
| INV-B1 | TM no tiene atributos del CB | ✅ |
| INV-B2 | Token nunca aparece en logs | ✅ |
| INV-B3 | Refresh singleton con concurrencia real | ✅ |

## Endpoints del servidor mock

| Metodo | Endpoint | Auth | Descripcion |
|---|---|---|---|
| POST | /auth/login | No | Login con JWT |
| POST | /auth/token | Opcional | Refresh token |
| GET | /api/inventario | Si | Inventarios (CB testing) |
| GET | /api/alertas | Si | SSE con eventos en tiempo real |
| GET | /api/productos | Si | Listar productos |
| GET | /api/productos/{id} | No | Obtener producto |
| POST | /api/productos | Si (rol != viewer) | Crear producto |
| PUT | /api/productos/{id} | Si (rol != viewer) | Actualizar total |
| PATCH | /api/productos/{id} | Si (rol != viewer) | Actualizar parcial |
| DELETE | /api/productos/{id} | Si (rol != viewer) | Eliminar |
| GET | /api/categorias | No | Listar categorias |
| GET | /api/perfil | Si | Perfil del usuario |
| POST | /admin/modo | No | Cambiar modo servidor |
| GET | /admin/modo | No | Consultar modo |
| POST | /admin/reset | No | Resetear contadores |

### Modos de fallo

- `normal`: Responde 200 OK
- `fallo_503`: Responde 503 Service Unavailable
- `timeout`: No responde (simula timeout 60s)
- `auth_401`: Responde 401 Unauthorized
