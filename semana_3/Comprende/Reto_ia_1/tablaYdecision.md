### 📊 Tabla Comparativa de Modelos de Concurrencia - EcoMarket

| Característica | 1. Callbacks (Legacy) | 2. Futures (Thread Pool) | 3. Async/Await (Moderno) |
| :--- | :--- | :--- | :--- |
| **Biblioteca** | `concurrent.futures` + `callback` | `concurrent.futures` + `as_completed` | `asyncio` + `aiohttp` |
| **Mecanismo** | Hilos (Threads) + Función de retorno | Hilos (Threads) + Polling de estado | **Event Loop** (Hilo único) |
| **Tiempo Medido** | ~1.02 segundos | ~1.05 segundos | **~1.01 segundos** |
| **Bloqueo de Main** | No bloquea (asíncrono puro) | Bloquea esperando `.result()` | **No bloqueante** (usa `await`) |
| **Manejo de Errores** | Fragmentado (por cada callback) | Centralizado en el bucle principal | **Robusto** (`return_exceptions=True`) |
| **Legibilidad** | Baja ("Callback Hell") | Alta (Lineal) | **Muy Alta** (Estructura clara) |
| **Uso de Recursos** | Alto (Hilos del SO) | Alto (Hilos del SO) | **Bajo** (Cooperativo) |
| **Escalabilidad** | Media | Media | **Muy Alta** |


## Para el cliente de EcoMarket, la arquitectura elegida es **Async/Await (Modelo 3)**.

¿Por qué? Aunque los tres modelos reducen el tiempo de carga de 3s a ~1s, Async/Await es la única opción que escala eficientemente para un sistema I/O-bound (intensivo en red) como nuestro dashboard. A diferencia de Futures o Callbacks, que dependen de hilos del sistema operativo costosos en memoria y gestión, asyncio utiliza un Event Loop en un solo hilo, eliminando el overhead del cambio de contexto. Además, la capacidad de usar asyncio.gather(..., return_exceptions=True) es crítica para la resiliencia del dashboard: permite que si el endpoint de /categorias falla por timeout, el usuario aún pueda ver /productos y /perfil sin que la aplicación entera colapse o se congele, cumpliendo con el requisito de robustez definido en la arquitectura de la Semana 3.