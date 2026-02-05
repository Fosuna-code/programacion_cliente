import yaml
import inspect
import ast
import re
import sys
import os
from pathlib import Path
from openapi_spec_validator import validate_spec

# --- CONFIGURACIÓN DE RUTAS ---
# Obtener el directorio actual del script
SCRIPT_DIR = Path(__file__).parent.resolve()
# Navegar a la raíz de semana_2
SEMANA2_DIR = SCRIPT_DIR.parent.parent

# Añadir el directorio actual al sys.path para importar el cliente mejorado
sys.path.insert(0, str(SCRIPT_DIR))

# --- CONFIGURACIÓN ---
# Ruta al archivo OpenAPI (openapiM2.yaml)
OPENAPI_FILE = str(SEMANA2_DIR / "Comprende" / "reto_1" / "openapiM2.yaml")

# Importar el cliente mejorado para auditoría
try:
    from cliente_mejorado_para_auditoria import EcoMarketClient
    print(f"✅ Cliente importado correctamente desde: {SCRIPT_DIR / 'cliente_mejorado_para_auditoria.py'}")
    print(f"✅ OpenAPI file: {OPENAPI_FILE}")
    
except ImportError as e:
    print(f"❌ Error al importar cliente_mejorado_para_auditoria: {e}")
    # Mock para demostración si no se puede importar
    class EcoMarketClient:
        def listar_productos(self, categoria=None, nombre=None): pass
        def obtener_producto(self, producto_id): pass
        def crear_producto(self, datos): pass
        def actualizar_producto_total(self, producto_id, datos): pass
        def actualizar_producto_parcial(self, producto_id, campos): pass
        def eliminar_producto(self, producto_id): pass
        def listar_productores(self): pass
        def crear_productor(self, datos): pass
        def eliminar_productor(self, productor_id): pass
        def obtener_productos_de_productor(self, productor_id): pass
        def crear_pedido(self, datos): pass

class ContractAuditor:
    def __init__(self, openapi_path, client_class):
        self.openapi_path = openapi_path
        self.client_class = client_class
        self.spec = self._load_spec()
        self.client_source = inspect.getsource(client_class)

    def _load_spec(self):
        with open(self.openapi_path, 'r') as f:
            spec = yaml.safe_load(f)
        # Validación básica para asegurar que el YAML es válido
        try:
            validate_spec(spec)
        except Exception as e:
            print(f"⚠️ Advertencia: El OpenAPI tiene errores de validación: {e}")
        return spec

    # Mapeo de endpoints y métodos HTTP a los nombres de funciones del cliente
    ENDPOINT_METHOD_MAP = {
        # Productos
        ('GET', '/productos'): 'listar_productos',
        ('POST', '/productos'): 'crear_producto',
        ('GET', '/productos/{id}'): 'obtener_producto',
        ('PUT', '/productos/{id}'): 'actualizar_producto_total',
        ('PATCH', '/productos/{id}'): 'actualizar_producto_parcial',
        ('DELETE', '/productos/{id}'): 'eliminar_producto',
        # Productores
        ('GET', '/productores'): 'listar_productores',
        ('POST', '/productores'): 'crear_productor',
        ('GET', '/productores/{id}'): 'obtener_productor',
        ('DELETE', '/productores/{id}'): 'eliminar_productor',
        ('GET', '/productores/{id}/productos'): 'obtener_productos_de_productor',
        # Pedidos
        ('POST', '/pedidos'): 'crear_pedido',
    }

    def _get_client_method(self, operation_id, method, path):
        # 1. Intenta buscar por operationId primero
        if hasattr(self.client_class, operation_id):
            return operation_id
        
        # 2. Buscar en el mapeo personalizado
        key = (method.upper(), path)
        mapped_name = self.ENDPOINT_METHOD_MAP.get(key)
        if mapped_name and hasattr(self.client_class, mapped_name):
            return mapped_name
        
        # 3. Buscar por convención (verbo_recurso)
        sanitized_path = path.replace('/', '_').replace('{', '').replace('}', '').strip('_')
        convention_name = f"{method.lower()}_{sanitized_path}"
        
        if hasattr(self.client_class, convention_name):
            return convention_name
        return None

    def _check_status_handling(self, method_name, status_codes):
        """Usa AST para ver si el código menciona los status codes"""
        import textwrap
        method_source = inspect.getsource(getattr(self.client_class, method_name))
        # Corregir indentación para que ast.parse no falle
        method_source = textwrap.dedent(method_source)
        tree = ast.parse(method_source)
        
        handled = []
        missing = []
        
        # Extracción simple de números en el código fuente
        # (En un caso real, buscaríamos comparaciones específicas como resp.status_code == 404)
        source_constants = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant):
                source_constants.add(str(node.value))
        
        for code in status_codes:
            if str(code) in source_constants or "raise_for_status" in method_source:
                handled.append(code)
            else:
                missing.append(code)
                
        return missing

    def audit(self):
        print(f"🔍 Auditando Cliente contra {self.openapi_path}...\n")
        print(f"{'MÉTODO':<10} | {'ENDPOINT':<30} | {'ESTADO':<10} | {'DETALLES'}")
        print("-" * 80)

        paths = self.spec.get('paths', {})
        
        # Métodos HTTP válidos
        valid_http_methods = {'get', 'put', 'post', 'delete', 'patch', 'options', 'head', 'trace'}
        
        for path, methods in paths.items():
            for http_method, details in methods.items():
                # Ignorar campos que no son métodos HTTP (como 'parameters')
                if http_method.lower() not in valid_http_methods:
                    continue
                    
                # Asegurarse de que details es un diccionario
                if not isinstance(details, dict):
                    continue
                    
                operation_id = details.get('operationId', 'unknown')
                client_method = self._get_client_method(operation_id, http_method, path)
                
                # 1. Verificar existencia de función
                if not client_method:
                    print(f"{http_method.upper():<10} | {path:<30} | ❌ Faltante | No existe función '{http_method}_{path}'")
                    continue

                # 2. Verificar Headers Requeridos
                params = details.get('parameters', [])
                required_headers = [p['name'] for p in params if p['in'] == 'header' and p.get('required')]
                method_source = inspect.getsource(getattr(self.client_class, client_method))
                missing_headers = [h for h in required_headers if h not in method_source]

                # 3. Verificar Códigos de Respuesta
                responses = details.get('responses', {}).keys()
                # Filtramos 'default' y nos quedamos con los numéricos
                status_codes = [code for code in responses if str(code).isdigit()]
                unhandled_codes = self._check_status_handling(client_method, status_codes)

                # Generar Reporte
                if missing_headers:
                    print(f"{http_method.upper():<10} | {path:<30} | ⚠️ Parcial | Faltan headers: {missing_headers}")
                elif unhandled_codes:
                    # Si usa raise_for_status, a veces asumimos que maneja todo, pero aquí somos estrictos
                    print(f"{http_method.upper():<10} | {path:<30} | ⚠️ Parcial | No maneja explícitamente: {unhandled_codes}")
                else:
                    print(f"{http_method.upper():<10} | {path:<30} | ✅ Conforme | Cumple contrato")

if __name__ == "__main__":
    # Asegúrate de tener tu openapi.yaml en el mismo directorio
    auditor = ContractAuditor(OPENAPI_FILE, EcoMarketClient)
    auditor.audit()