# Estrategia de Seguridad: Sanitización de URLs en el Cliente
La implementación de un URLBuilder centralizado actúa como nuestra primera línea de defensa perimetral en la comunicación con la API. Su objetivo principal es garantizar la integridad de la estructura del recurso.

## Ataques que Neutraliza el URLBuilder
El uso de urllib.parse junto con validación de tipos protege contra los siguientes vectores:

### Inyección de Parámetros de Ruta (Path Traversal)
Ataque: Intentar acceder a archivos o endpoints fuera del scope usando ../.

Defensa: Al forzar el escape de caracteres y validar que el ID sea estrictamente un int o UUID, cualquier secuencia de puntos o diagonales maliciosas se convierte en un string inofensivo o dispara una excepción antes de realizar la petición.

### Inyección de Query String
Ataque: Manipular un parámetro para añadir instrucciones adicionales (ej. id=123&admin=true).

Defensa: urlencode trata el símbolo & y = como datos literales (%26 y %3D), por lo que el servidor recibirá un solo parámetro con un valor extraño en lugar de dos parámetros separados.

C. Ambigüedad de Delimitadores (Fragment Injection)
Ataque: El uso de # para truncar la URL en el servidor y confundir el enrutamiento.

Defensa: El builder escapa los caracteres reservados, asegurando que el delimitador sea interpretado como parte del valor del recurso y no como un comando de navegación.

## Lo que NO Defiende (Limitaciones)
Es vital entender que el URLBuilder solo asegura que la "dirección" esté bien escrita; no garantiza que el "viaje" sea seguro ni que el "destino" sea legítimo.

| Riesgo | Por qué el URLBuilder no es suficiente | Defensa Requerida |
| :--- | :--- | :--- |
| Man-in-the-Middle (MitM) | La URL es segura, pero viaja en texto plano si no hay cifrado. | TLS/HTTPS obligatorio y Certificate Pinning. |
| Falta de Autorización | Puedes construir una URL perfecta al producto de otro usuario. | JWT o API Keys validadas en el backend. |
| DDoS / Fuerza Bruta | Puedes generar millones de URLs válidas y seguras para inundar la API. | Rate Limiting y Throttling en el servidor. |
| SQL Injection / NoSQLi | El builder protege la URL, pero si el backend toma el ID y lo pega en una query sin usar ORM/Prepared Statements, el servidor cae. | Validación y Parameterized Queries en el backend. |