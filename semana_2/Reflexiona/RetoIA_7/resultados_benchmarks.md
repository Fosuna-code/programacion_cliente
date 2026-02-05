# Validación manual
def validar_manual(data):
    # Verificación de campos requeridos
    if not all(k in data for k in ("id", "nombre", "precio", "categoria")):
        raise ValueError("Faltan campos requeridos")
    
    # Verificación de tipos y lógica de negocio
    if not isinstance(data["precio"], (int, float)) or data["precio"] <= 0:
        raise ValueError("Precio debe ser un número positivo")
    
    # Manejo de anidados manualmente
    if "productor" in data:
        if "id" not in data["productor"]:
            raise ValueError("ID de productor requerido")
    return data


# Validación con Pydantic
from pydantic import BaseModel, Field, field_validator
from typing import Optional

class Productor(BaseModel):
    id: int
    nombre: str

class Producto(BaseModel):
    id: int
    nombre: str
    precio: float = Field(gt=0)
    categoria: str
    productor: Optional[Productor] = None

    @field_validator('categoria')
    @classmethod
    def validar_cat(cls, v):
        validas = ['frutas', 'verduras', 'lacteos', 'miel', 'conservas']
        if v not in validas:
            raise ValueError(f"Categoría {v} no es válida")
        return v


# Validación con JSON Schema
from jsonschema import validate

schema_producto = {
    "type": "object",
    "properties": {
        "id": {"type": "integer"},
        "nombre": {"type": "string"},
        "precio": {"type": "number", "minimum": 0.01},
        "productor": {
            "type": "object",
            "properties": {"id": {"type": "integer"}},
            "required": ["id"]
        }
    },
    "required": ["id", "nombre", "precio"]
}

def validar_schema(data):
    validate(instance=data, schema=schema_producto)
    return data