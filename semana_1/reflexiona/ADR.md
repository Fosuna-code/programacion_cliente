ADR: Evolución de la Arquitectura del Cliente HTTP - EcoMarket
Estado: Aceptado

Contexto: Proyecto de integración frontend/backend para la plataforma EcoMarket.

ADR 001: Centralización del Manejo de Errores mediante Decoradores
Contexto: Inicialmente, el manejo de errores se realizaba mediante bloques try-catch individuales en cada función de petición (listar_productos, crear_producto, etc.). Esto generaba una alta duplicación de código y dificultaba la implementación de una estrategia de logging consistente.

Decisión: Se implementó una capa de intercepción utilizando decoradores de Python (@interceptar_errores). Esta capa se encarga de capturar excepciones de red (ConnectionError, Timeout) y de lanzar el proceso de traducción de errores HTTP.

Alternativas Consideradas: * Mantener try-catch locales (descartado por falta de mantenibilidad).

Uso de una función "wrapper" genérica (descartado por ser menos elegante/Pythonic que los decoradores).

Consecuencias: * Positivas: Reducción drástica de líneas de código duplicadas y centralización de la observabilidad.

Negativas: Introduce una ligera complejidad adicional para los desarrolladores que no estén familiarizados con el concepto de decoradores en Python.

ADR 002: Transición de Lógica Manual a Mapeo Semántico (Cambiado tras diálogo)
Contexto: Esta decisión cambió radicalmente. Al principio, se propuso distinguir manualmente entre errores 400 y 422 en cada método para orientar al usuario. El "abogado del diablo" señaló que esto era frágil ante cambios en el backend.

Decisión: Se creó una clase de excepción personalizada BusinessError y un componente error_parser. En lugar de depender de los códigos de estado HTTP para la lógica de usuario, el cliente ahora parsea el cuerpo de la respuesta (response.json()) y mapea códigos internos (ej. INSUFFICIENT_STOCK) a mensajes amigables.

Alternativas Consideradas: * Manejo de errores genérico basado puramente en familias de códigos 4xx/5xx (descartado por falta de precisión para el usuario final).

Consecuencias: * Positivas: Mayor resiliencia ante cambios de framework en el backend y una experiencia de usuario mucho más específica y útil.

Negativas: Existe un acoplamiento con la estructura del JSON de error que devuelve el servidor (contrato semántico).

ADR 003: Implementación de Capa de Servicio con Persistencia de Sesión
Contexto: La aplicación requiere múltiples llamadas a la API y el manejo manual de headers en cada función (enfoque stateless puro) se volvía propenso a errores y poco eficiente en términos de red.

Decisión: Se encapsuló la lógica en la clase APIservices utilizando requests.Session(). Esto permite inyectar headers base una sola vez y aprovechar el connection pooling para mejorar el rendimiento de la comunicación cliente-servidor.

Alternativas Consideradas: * Mantener funciones aisladas con inyección de parámetros (enfoque inicial, descartado por carga cognitiva alta para el desarrollador).

Consecuencias: * Positivas: Mejora del rendimiento (Keep-Alive) y facilidad para gestionar el estado de la conexión en un solo lugar.

Negativas: Requiere una gestión cuidadosa del ciclo de vida de la instancia para evitar "fugas" de tokens de sesión antiguos.

ADR 004: Autenticación Dinámica mediante BearerAuth
Contexto: Los tokens de seguridad en EcoMarket pueden expirar o cambiar, y actualizar la cabecera de la sesión manualmente es ineficiente.

Decisión: Se implementó una clase BearerAuth que utiliza un callback. Esto garantiza que el token se evalúe justo antes de enviar cada petición, permitiendo cierres de sesión o renovaciones de token de forma transparente para el resto de la aplicación.

Alternativas Consideradas: * Hardcodear el token en la sesión (descartado por ser poco dinámico).

Consecuencias: * Positivas: Desacoplamiento total entre la lógica de obtención de credenciales y la lógica de ejecución de peticiones.

Negativas: Añade una pequeña sobrecarga de procesamiento en cada llamada al ejecutar la función de callback.