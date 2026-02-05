"""
Cliente HTTP Mejorado para Auditoría de Contrato OpenAPI
=========================================================
Este cliente implementa TODOS los endpoints definidos en openapiM2.yaml:
- Productos: CRUD completo (GET, POST, PUT, PATCH, DELETE)
- Productores: Listar, Crear, Eliminar, Productos por productor
- Pedidos: Crear pedido

Autor: Generado para auditoría de contrato
"""

import requests
from typing import Optional, List, Dict, Any

# Configuración centralizada
BASE_URL = "http://127.0.0.1:4010"
TIMEOUT = 10  # segundos


class EcoMarketError(Exception):
    """Error base para el cliente de EcoMarket"""
    pass


class ValidationError(EcoMarketError):
    """El servidor rechazó la petición por validación (400, 422)"""
    pass


class AuthenticationError(EcoMarketError):
    """El servidor rechazó la petición por autenticación (401)"""
    pass


class NotFoundError(EcoMarketError):
    """El recurso no fue encontrado (404)"""
    pass


class ConflictError(EcoMarketError):
    """El servidor detectó un recurso duplicado o conflicto (409)"""
    pass


class ServerError(EcoMarketError):
    """Error del servidor (5xx) - puede reintentarse"""
    pass


class EcoMarketClient:
    """
    Cliente HTTP completo para la API de EcoMarket.
    Implementa todos los endpoints definidos en el contrato OpenAPI.
    """
    
    def __init__(self, base_url: str = BASE_URL, token: str = ""):
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json"
        })
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"
    
    def _verificar_respuesta(self, response: requests.Response) -> requests.Response:
        """Verifica código de estado y Content-Type antes de procesar."""
        # Manejo de errores específicos por código de estado
        if response.status_code == 400:
            raise ValidationError(f"Error de validación (400): {response.text}")
        
        if response.status_code == 401:
            raise AuthenticationError(f"No autorizado (401): {response.text}")
        
        if response.status_code == 404:
            raise NotFoundError(f"Recurso no encontrado (404): {response.text}")
        
        if response.status_code == 409:
            raise ConflictError(f"Conflicto (409): {response.text}")
        
        if response.status_code == 422:
            raise ValidationError(f"Entidad no procesable (422): {response.text}")
        
        if response.status_code >= 500:
            raise ServerError(f"Error del servidor: {response.status_code}")
        
        if response.status_code >= 400:
            raise ValidationError(f"Error de cliente: {response.status_code} - {response.text}")
        
        return response
    
    # =========================================================================
    # ENDPOINTS DE PRODUCTOS (/productos)
    # =========================================================================
    
    def listar_productos(self, categoria: Optional[str] = None, nombre: Optional[str] = None) -> List[Dict]:
        """
        GET /productos
        Lista productos con filtros opcionales.
        
        Códigos manejados: 200, 422
        """
        params = {}
        if categoria:
            params['categoria'] = categoria
        if nombre:
            params['nombre'] = nombre
        
        response = self.session.get(
            f"{self.base_url}/productos",
            params=params if params else None,
            timeout=TIMEOUT
        )
        
        # Manejo explícito de códigos 200 y 422
        if response.status_code == 200:
            return response.json()
        
        if response.status_code == 422:
            raise ValidationError(f"Parámetros de consulta inválidos (422): {response.text}")
        
        self._verificar_respuesta(response)
        return response.json()
    
    def crear_producto(self, datos: Dict[str, Any]) -> Dict:
        """
        POST /productos
        Crea un nuevo producto.
        
        Códigos manejados: 201, 400, 401
        """
        response = self.session.post(
            f"{self.base_url}/productos",
            json=datos,
            timeout=TIMEOUT
        )
        
        # Manejo explícito de códigos 201, 400 y 401
        if response.status_code == 201:
            if response.text:
                return response.json()
            return {"status": "created"}
        
        if response.status_code == 400:
            raise ValidationError(f"Error de validación (400): {response.text}")
        
        if response.status_code == 401:
            raise AuthenticationError(f"No autorizado (401): {response.text}")
        
        self._verificar_respuesta(response)
        return response.json()
    
    def obtener_producto(self, producto_id: int) -> Dict:
        """
        GET /productos/{id}
        Obtiene el detalle de un producto.
        
        Códigos manejados: 200, 404, 422
        """
        response = self.session.get(
            f"{self.base_url}/productos/{producto_id}",
            timeout=TIMEOUT
        )
        
        # Manejo explícito de códigos 200, 404 y 422
        if response.status_code == 200:
            return response.json()
        
        if response.status_code == 404:
            raise NotFoundError(f"Producto no encontrado (404): {response.text}")
        
        if response.status_code == 422:
            raise ValidationError(f"ID de producto inválido (422): {response.text}")
        
        self._verificar_respuesta(response)
        return response.json()
    
    def actualizar_producto_total(self, producto_id: int, datos: Dict[str, Any]) -> Dict:
        """
        PUT /productos/{id}
        Reemplaza el producto completo (actualización total).
        
        Códigos manejados: 200, 400, 401, 404, 422
        """
        response = self.session.put(
            f"{self.base_url}/productos/{producto_id}",
            json=datos,
            timeout=TIMEOUT
        )
        
        # Manejo explícito de códigos 200, 400, 401, 404 y 422
        if response.status_code == 200:
            if response.text:
                return response.json()
            return {"status": "updated"}
        
        if response.status_code == 400:
            raise ValidationError(f"Error de validación (400): {response.text}")
        
        if response.status_code == 401:
            raise AuthenticationError(f"No autorizado (401): {response.text}")
        
        if response.status_code == 404:
            raise NotFoundError(f"Producto no encontrado (404): {response.text}")
        
        if response.status_code == 422:
            raise ValidationError(f"Datos de producto inválidos (422): {response.text}")
        
        self._verificar_respuesta(response)
        return response.json()
    
    def actualizar_producto_parcial(self, producto_id: int, campos: Dict[str, Any]) -> Dict:
        """
        PATCH /productos/{id}
        Modifica solo los campos proporcionados (actualización parcial).
        
        Códigos manejados: 200, 400, 401, 404, 422
        """
        response = self.session.patch(
            f"{self.base_url}/productos/{producto_id}",
            json=campos,
            timeout=TIMEOUT
        )
        
        # Manejo explícito de códigos 200, 400, 401, 404 y 422
        if response.status_code == 200:
            if response.text:
                return response.json()
            return {"status": "modified"}
        
        if response.status_code == 400:
            raise ValidationError(f"Error de validación (400): {response.text}")
        
        if response.status_code == 401:
            raise AuthenticationError(f"No autorizado (401): {response.text}")
        
        if response.status_code == 404:
            raise NotFoundError(f"Producto no encontrado (404): {response.text}")
        
        if response.status_code == 422:
            raise ValidationError(f"Campos de producto inválidos (422): {response.text}")
        
        self._verificar_respuesta(response)
        return response.json()
    
    def eliminar_producto(self, producto_id: int) -> bool:
        """
        DELETE /productos/{id}
        Elimina un producto.
        
        Códigos manejados: 204, 400, 401, 404, 422
        """
        response = self.session.delete(
            f"{self.base_url}/productos/{producto_id}",
            timeout=TIMEOUT
        )
        
        # Manejo explícito de códigos 204, 400, 401, 404 y 422
        if response.status_code == 204:
            return True
        
        if response.status_code == 400:
            raise ValidationError(f"Error de validación (400): {response.text}")
        
        if response.status_code == 401:
            raise AuthenticationError(f"No autorizado (401): {response.text}")
        
        if response.status_code == 404:
            raise NotFoundError(f"Producto no encontrado (404): {response.text}")
        
        if response.status_code == 422:
            raise ValidationError(f"ID de producto inválido (422): {response.text}")
        
        self._verificar_respuesta(response)
        return response.status_code == 204
    
    # =========================================================================
    # ENDPOINTS DE PRODUCTORES (/productores)
    # =========================================================================
    
    def listar_productores(self) -> List[Dict]:
        """
        GET /productores
        Lista todos los productores registrados.
        
        Códigos manejados: 200
        """
        response = self.session.get(
            f"{self.base_url}/productores",
            timeout=TIMEOUT
        )
        
        # Manejo explícito de código 200
        if response.status_code == 200:
            return response.json()
        
        self._verificar_respuesta(response)
        return response.json()
    
    def obtener_productor(self, productor_id: int) -> Dict:
        """
        GET /productores/{id}
        Obtiene el detalle de un productor.
        
        Códigos manejados: 200, 404, 422
        """
        response = self.session.get(
            f"{self.base_url}/productores/{productor_id}",
            timeout=TIMEOUT
        )
        
        # Manejo explícito de códigos 200, 404 y 422
        if response.status_code == 200:
            return response.json()
        
        if response.status_code == 404:
            raise NotFoundError(f"Productor no encontrado (404): {response.text}")
        
        if response.status_code == 422:
            raise ValidationError(f"ID de productor inválido (422): {response.text}")
        
        self._verificar_respuesta(response)
        return response.json()
    
    def crear_productor(self, datos: Dict[str, Any]) -> Dict:
        """
        POST /productores
        Registra un nuevo productor.
        
        Códigos manejados: 201, 400, 401
        """
        response = self.session.post(
            f"{self.base_url}/productores",
            json=datos,
            timeout=TIMEOUT
        )
        
        # Manejo explícito de códigos 201, 400 y 401
        if response.status_code == 201:
            if response.text:
                return response.json()
            return {"status": "created"}
        
        if response.status_code == 400:
            raise ValidationError(f"Error de validación (400): {response.text}")
        
        if response.status_code == 401:
            raise AuthenticationError(f"No autorizado (401): {response.text}")
        
        self._verificar_respuesta(response)
        return response.json()
    
    def eliminar_productor(self, productor_id: int) -> bool:
        """
        DELETE /productores/{id}
        Elimina un productor. Falla con 409 si tiene productos asociados.
        
        Códigos manejados: 204, 400, 401, 404, 409, 422
        """
        response = self.session.delete(
            f"{self.base_url}/productores/{productor_id}",
            timeout=TIMEOUT
        )
        
        # Manejo explícito de códigos 204, 400, 401, 404, 409 y 422
        if response.status_code == 204:
            return True
        
        if response.status_code == 400:
            raise ValidationError(f"Error de validación (400): {response.text}")
        
        if response.status_code == 401:
            raise AuthenticationError(f"No autorizado (401): {response.text}")
        
        if response.status_code == 404:
            raise NotFoundError(f"Productor no encontrado (404): {response.text}")
        
        if response.status_code == 409:
            raise ConflictError("Conflicto de integridad referencial: el productor tiene productos asociados")
        
        if response.status_code == 422:
            raise ValidationError(f"ID de productor inválido (422): {response.text}")
        
        self._verificar_respuesta(response)
        return response.status_code == 204
    
    def obtener_productos_de_productor(self, productor_id: int) -> List[Dict]:
        """
        GET /productores/{id}/productos
        Obtiene los productos de un productor específico (recurso anidado).
        
        Códigos manejados: 200, 404, 422
        """
        response = self.session.get(
            f"{self.base_url}/productores/{productor_id}/productos",
            timeout=TIMEOUT
        )
        
        # Manejo explícito de códigos 200, 404 y 422
        if response.status_code == 200:
            return response.json()
        
        if response.status_code == 404:
            raise NotFoundError(f"Productor no encontrado (404): {response.text}")
        
        if response.status_code == 422:
            raise ValidationError(f"ID de productor inválido (422): {response.text}")
        
        self._verificar_respuesta(response)
        return response.json()
    
    # =========================================================================
    # ENDPOINTS DE PEDIDOS (/pedidos)
    # =========================================================================
    
    def crear_pedido(self, datos: Dict[str, Any]) -> Dict:
        """
        POST /pedidos
        Crea un nuevo pedido.
        
        Códigos manejados: 201, 400, 401
        """
        response = self.session.post(
            f"{self.base_url}/pedidos",
            json=datos,
            timeout=TIMEOUT
        )
        
        # Manejo explícito de códigos 201, 400 y 401
        if response.status_code == 201:
            if response.text:
                return response.json()
            return {"status": "created"}
        
        if response.status_code == 400:
            raise ValidationError(f"Error de validación (400): {response.text}")
        
        if response.status_code == 401:
            raise AuthenticationError(f"No autorizado (401): {response.text}")
        
        self._verificar_respuesta(response)
        return response.json()
    
    def cerrar(self):
        """Cierra la sesión HTTP."""
        self.session.close()


# --- EJECUCIÓN DE DEMOSTRACIÓN ---
if __name__ == "__main__":
    print("=" * 60)
    print("Cliente EcoMarket - Listo para Auditoría de Contrato")
    print("=" * 60)
    print("\nEndpoints implementados:")
    print("\n📦 PRODUCTOS:")
    print("  - GET    /productos                  → listar_productos()")
    print("  - POST   /productos                  → crear_producto()")
    print("  - GET    /productos/{id}             → obtener_producto()")
    print("  - PUT    /productos/{id}             → actualizar_producto_total()")
    print("  - PATCH  /productos/{id}             → actualizar_producto_parcial()")
    print("  - DELETE /productos/{id}             → eliminar_producto()")
    print("\n👤 PRODUCTORES:")
    print("  - GET    /productores                → listar_productores()")
    print("  - POST   /productores                → crear_productor()")
    print("  - DELETE /productores/{id}           → eliminar_productor()")
    print("  - GET    /productores/{id}/productos → obtener_productos_de_productor()")
    print("\n🛒 PEDIDOS:")
    print("  - POST   /pedidos                    → crear_pedido()")
    print("\n✅ Total: 11 endpoints implementados")
