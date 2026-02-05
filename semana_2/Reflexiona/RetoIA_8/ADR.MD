📜 ADR: Arquitectura del Cliente HTTP EcoMarket
Proyecto: Licenciatura en Sistemas Computacionales - UAN

Estatus: Aceptado (Fase de Prototipo)

Contexto: Construcción de un cliente CRUD robusto que no confíe ciegamente en el servidor.

🏗️ Decisión 01: Organización del Código mediante Funciones
Contexto: El desarrollo inicial de la Semana 2 requiere implementar las 6 operaciones CRUD básicas para EcoMarket. Se busca priorizar la simplicidad mientras se aprenden los fundamentos de comunicación.

Decisión: Utilizar funciones independientes (procedural) en lugar de una estructura de clases.

Alternativas: Crear una clase EcoMarketClient o ProductosClient para encapsular la lógica.

Consecuencias:

Positivas: Curva de aprendizaje baja y código fácil de seguir secuencialmente.

Negativas: Falta de encapsulamiento; la configuración como BASE_URL o TIMEOUT queda como variables globales o se repite, dificultando el mantenimiento a largo plazo.

🔍 Decisión 02: Estrategia de Validación de Datos Manual
Contexto: Un cliente robusto debe validar que la respuesta tenga el código de estado, tipo de contenido y esquema correctos antes de procesar los datos.

Decisión: Implementar validación manual mediante bloques if/else y lógica personalizada en un módulo de validadores.

Alternativas: Uso de bibliotecas de esquemas como Pydantic o JSON Schema.

Consecuencias:

Positivas: Comprensión profunda de las capas de validación (Estado -> Content-Type -> Parseo -> Esquema -> Semántica).

Negativas: El código se vuelve verboso y difícil de escalar si el modelo de datos de EcoMarket se vuelve más complejo (más de 20 endpoints).

🛡️ Decisión 03: Manejo de Excepciones Personalizadas
Contexto: Las excepciones estándar de las librerías (como requests.exceptions) no siempre capturan errores de lógica de negocio o fallos de validación específicos.

Decisión: Crear clases de excepción propias como ValidationError para fallos 4xx y ServerError para fallos 5xx.

Alternativas: Usar response.raise_for_status() de la librería requests y atrapar excepciones genéricas.

Consecuencias:

Positivas: Manejo de errores más claro y específico, permitiendo al cliente diferenciar entre un error del servidor reintentable y un error del cliente definitivo.

Negativas: Requiere un mapeo manual de códigos HTTP a excepciones dentro del flujo de verificación de cada función.

🔄 Decisión que cambiaría tras la reflexión
Decisión a cambiar: Ausencia de reintentos automáticos y Timeout fijo.

¿Por qué el cambio? Aunque para una demo un timeout fijo de 10 segundos y fallar al primer intento es aceptable, en un entorno real esto genera una mala experiencia de usuario ante errores transitorios del servidor.

Nueva Propuesta: Implementar un sistema de Exponential Backoff con Jitter para operaciones idempotentes (GET, PUT, DELETE).

Justificación: Esto permitiría que el cliente se recupere automáticamente de picos de carga en el servidor sin "bombardearlo" gracias al jitter, previniendo el problema de la thundering herd. Mantendría la restricción de no reintentar POST automáticamente para evitar la duplicación accidental de recursos (pedidos o productos).