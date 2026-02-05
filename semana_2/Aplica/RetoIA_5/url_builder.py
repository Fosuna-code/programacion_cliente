import uuid
from urllib.parse import quote, urlencode, urljoin

class URLBuilder:
    def __init__(self, base_url: str):
        # Aseguramos que la base termine en / para que urljoin funcione predeciblemente
        self.base_url = base_url if base_url.endswith('/') else f"{base_url}/"

    def _validate_id(self, value):
        """Valida que el ID sea un entero o un UUID válido."""
        if isinstance(value, int):
            return str(value)
        try:
            # Si es string, intentamos ver si es un UUID válido
            return str(uuid.UUID(str(value)))
        except (ValueError, TypeError):
            raise ValueError(f"ID inválido: {value}. Se esperaba int o UUID.")

    def build_url(self, path_template: str, path_params: list = None, query_params: dict = None) -> str:
        """
        Construye una URL segura.
        path_template: ej. "productos/{}"
        path_params: Lista de valores para los placeholders {}
        query_params: Diccionario para la query string
        """
        # 1. Escapar y validar path params
        safe_path_params = []
        if path_params:
            for param in path_params:
                validated = self._validate_id(param)
                # quote(safe='') asegura que incluso los / se escapen
                safe_path_params.append(quote(validated, safe=''))
        
        # 2. Formatear el path
        path = path_template.format(*safe_path_params)
        
        # 3. Construir la URL completa
        full_url = urljoin(self.base_url, path.lstrip('/'))
        
        # 4. Añadir query params de forma segura
        if query_params:
            # urlencode maneja caracteres especiales y espacios automáticamente
            query_string = urlencode(query_params)
            full_url = f"{full_url}?{query_string}"
            
        return full_url


if __name__ == "__main__":
    builder = URLBuilder("https://api.ecomarket.com/v1/")

    # Caso 1: Path Traversal
    try:
        # Fallará por la validación de tipo (no es int ni UUID)
        url = builder.build_url("productos/{}", ["../../../etc/passwd"])
    except ValueError as e:
        print(f"Bloqueado Traversal: {e}")

    # Caso 2: Inyección de Query (Incluso si permitiéramos strings, se escaparía)
    # Simulando que el ID es un UUID pero alguien intenta inyectar
    id_malicioso = "550e8400-e29b-41d4-a716-446655440000?admin=true"
    try:
        url = builder.build_url("productos/{}", [id_malicioso])
    except ValueError as e:
        print(f"Bloqueado Inyección: {e}")

    # Caso 3: Unicode y Caracteres Especiales en Query Params
    params_sucios = {"categoria": "electrónica & hogar", "busqueda": "café total"}
    url_segura = builder.build_url("productos", query_params=params_sucios)
    print(f"URL Segura: {url_segura}")
    # Salida: .../productos?categoria=electr%C3%B3nica+%26+hogar&busqueda=caf%C3%A9+total

    #Mi facking caso como no
    hacekrquery = {"id": "54687=admin=true"} # Intento de inyección (no jalo pero se intento)
    try:
        url = builder.build_url("productos",query_params=hacekrquery)
        print(f"URL Segura: {url}")
    except ValueError as e:
        print(f"Bloqueado Inyección: {e}")