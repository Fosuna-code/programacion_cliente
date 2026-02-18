# ADR: Decisiones de Concurrencia - Cliente EcoMarket Asíncrono

## ADR-001: Uso de gather() como Estrategia Principal de Coordinación

### Contexto
El cliente asíncrono necesita cargar múltiples endpoints en paralelo para el dashboard (productos, categorías, perfil de usuario, notificaciones). Necesitamos una estrategia que coordine estas peticiones concurrentes.

### Decisión
Usar `asyncio.gather()` con `return_exceptions=True` como estrategia principal para ejecutar peticiones concurrentes.

### Alternativas Consideradas

1. **asyncio.wait()**
   - Pros: Mayor control granular, puede retornar cuando la primera tarea complete
   - Contras: API más compleja, requiere manejar sets de tareas manualmente

2. **asyncio.as_completed()**
   - Pros: Permite procesar resultados conforme van llegando
   - Contras: No retorna todos los resultados a la vez, más complejo para casos simples

3. **Ejecutar secuencialmente**
   - Pros: Código más simple, predecible
   - Contras: Latencia total es la suma de todas las peticiones (inaceptable para UX)

### Consecuencias

**Positivas:**
- Código legible y fácil de mantener
- Todos los resultados disponibles simultáneamente
- Con `return_exceptions=True`, el fallo de una petición no afecta las demás
- Óptimo para el caso de "cargar todo antes de mostrar el dashboard"

**Negativas:**
- El usuario espera a que TODAS las peticiones terminen antes de ver datos
- No hay feedback progresivo durante la carga
- Si una petición es muy lenta, retrasa toda la UI

**Mitigaciones:**
- Implementar timeouts individuales por petición
- Considerar `as_completed()` para futuras mejoras de UX
- Agregar indicador de progreso basado en el número de peticiones completadas

---

## ADR-002: Sesión HTTP Compartida para Peticiones Relacionadas

### Contexto
El cliente realiza múltiples peticiones HTTP al mismo servidor (EcoMarket API). Cada petición requiere una conexión TCP y configuración de headers. Necesitamos decidir cómo gestionar las sesiones HTTP.

### Decisión
Usar una sola `aiohttp.ClientSession` compartida para todas las peticiones del dashboard, pasándola como parámetro a cada función.

### Alternativas Consideradas

1. **Crear sesión dentro de cada función**
   ```python
   async def listar_productos():
       async with aiohttp.ClientSession() as session:
           # hacer petición
   ```
   - Pros: Cada función es independiente
   - Contras: Overhead de crear/destruir sesión por cada petición, no reutiliza conexiones TCP

2. **Sesión global como singleton**
   ```python
   SESSION = aiohttp.ClientSession()
   ```
   - Pros: Fácil acceso desde cualquier función
   - Contras: Difícil de testear, no se cierra correctamente, estado compartido peligroso

3. **Pasar sesión como parámetro**
   ```python
   async def listar_productos(session: aiohttp.ClientSession):
       # usar sesión
   ```
   - Pros: Control explícito, testeable, reutiliza conexiones
   - Contras: Requiere pasar sesión a cada función

### Consecuencias

**Positivas:**
- **Reutilización de conexiones TCP:** Una sesión mantiene un pool de conexiones que se reutilizan (keep-alive)
- **Mejor rendimiento:** Evita el overhead del TCP handshake en cada petición
- **Testing simplificado:** Podemos inyectar mocks de sesión fácilmente
- **Control de lifecycle:** Sabemos exactamente cuándo se crea y cierra la sesión

**Negativas:**
- **Acoplamiento explícito:** Todas las funciones deben recibir `session` como parámetro
- **Gestión manual:** El código que llama debe crear y cerrar la sesión con `async with`

**Mitigaciones:**
- Usar `async with` para garantizar cierre automático
- Documentar claramente en cada función que requiere una sesión
- Crear funciones helper como `cargar_dashboard()` que manejen el ciclo de vida de la sesión

---

## ADR-003: Timeouts Individuales por Petición

### Contexto
Las peticiones HTTP pueden fallar o tardar indefinidamente. Necesitamos estrategia de timeout que proteja la UX sin perder trabajo útil.

### Decisión
Configurar timeout individual por petición usando `aiohttp.ClientTimeout`, con valores ajustados según la criticidad de cada endpoint.

### Alternativas Consideradas

1. **Timeout global para todo el dashboard**
   ```python
   async with asyncio.timeout(5):
       await cargar_dashboard()
   ```
   - Pros: Simple, protege contra waiting indefinido
   - Contras: Si se alcanza el timeout, se pierden TODAS las peticiones, incluso las completadas

2. **Sin timeouts**
   - Pros: Ninguna petición se cancela prematuramente
   - Contras: Una petición colgada bloquea indefinidamente la UI

3. **Timeout individual configurable**
   ```python
   timeout = aiohttp.ClientTimeout(total=10)
   session = aiohttp.ClientSession(timeout=timeout)
   ```
   - Pros: Cada petición tiene su límite, las demás continúan si una falla
   - Contras: Requiere tuning de valores apropiados

### Consecuencias

**Positivas:**
- **Resiliencia:** Una petición lenta no afecta las demás
- **UX predecible:** El usuario sabe que como máximo esperará X segundos
- **Flexibilidad:** Podemos ajustar timeouts por tipo de petición
  - Peticiones críticas (perfil): 2s
  - Peticiones de datos (productos): 5s
  - Peticiones secundarias (notificaciones): 3s

**Negativas:**
- **Complejidad de configuración:** Necesitamos conocer latencias típicas de cada endpoint
- **Falsos positivos:** Peticiones legítimas pero lentas pueden cancelarse
- **Debugging más difícil:** Timeouts pueden ocultar problemas de rendimiento del servidor

**Mitigaciones:**
- Loguear todos los timeouts para detectar patrones
- Implementar retry con backoff exponencial para timeouts transitorios
- Monitorear latencias del servidor para ajustar timeouts dinámicamente

---

## ADR-004: Límite de Concurrencia con Semáforo (10 peticiones)

### Contexto
El cliente puede necesitar crear múltiples recursos en paralelo (ej: importar 100 productos). Sin límites, podríamos:
- Saturar el servidor (límite de conexiones)
- Agotar file descriptors del cliente
- Violar rate limits del API

### Decisión
Implementar un semáforo de `asyncio.Semaphore(10)` para limitar peticiones concurrentes a 10.

### Alternativas Consideradas

1. **Sin límite de concurrencia**
   - Pros: Máxima velocidad posible
   - Contras: Puede colapsar servidor o cliente

2. **Límite de 5 peticiones**
   - Pros: Más conservador, menos riesgo
   - Contras: Throughput innecesariamente bajo si el servidor puede manejar más

3. **Límite de 20 peticiones**
   - Pros: Mayor throughput
   - Contras: Mayor riesgo de saturación

4. **Rate limiting (peticiones/segundo)**
   - Pros: Respeta límites del API más precisamente
   - Contras: Más complejo de implementar

### Consecuencias

**Positivas:**
- **Protección del servidor:** No enviamos más peticiones de las que puede manejar
- **Control de recursos:** El cliente no agota file descriptors del SO
- **Throughput predecible:** Sabemos que procesaremos ~10 peticiones en paralelo
- **Simple de implementar:**
  ```python
  semaphore = asyncio.Semaphore(10)
  async with semaphore:
      await hacer_peticion()
  ```

**Negativas:**
- **Throughput limitado:** Si el servidor puede manejar 50, estamos dejando capacidad sin usar
- **Valor arbitrario:** El 10 no está basado en métricas reales
- **No diferencia tipos de petición:** GET ligeras y POST pesadas comparten el mismo límite

**Configuración elegida: 10**
- Basado en regla general: `num_cores * 2` (asumiendo 4-6 cores en máquinas modernas)
- Valor conservador que funciona en la mayoría de APIs REST
- Fácil de ajustar según métricas de producción

**Próximos pasos:**
- Medir throughput real con el servidor en diferentes configuraciones (5, 10, 20, 50)
- Implementar rate limiting de peticiones/segundo si el API lo requiere
- Considerar semáforos separados para operaciones pesadas (POST) vs ligeras (GET)

---

## ADR-005: Sin Reintentos Automáticos en la Capa de Concurrencia

### Contexto
En Semana 2 implementamos retry con backoff exponencial para peticiones síncronas. Al migrar a async, debemos decidir si mantener reintentos y cómo interactúan con `gather()`.

### Decisión
NO implementar reintentos automáticos en la capa de coordinación asíncrona. Los reintentos se manejan a nivel de cada función individual si es necesario.

### Alternativas Consideradas

1. **Retry dentro de cada función CRUD**
   ```python
   async def listar_productos(session):
       for intento in range(3):
           try:
               return await _hacer_peticion()
           except ServerError:
               await asyncio.sleep(2 ** intento)
   ```
   - Pros: Encapsulado, transparente para el que llama
   - Contras: Aumenta tiempo total del `gather()`, dificulta depuración

2. **Retry a nivel de gather()**
   ```python
   for intento in range(3):
       resultados = await gather(...)
       if todos_exitosos(resultados):
           break
   ```
   - Pros: Reintentar solo las peticiones que fallaron
   - Contras: Muy complejo, puede reintentar peticiones ya exitosas

3. **Sin reintentos automáticos**
   - Pros: Lógica más simple, tiempos predecibles
   - Contras: Menos resiliente ante fallos transitorios

### Consecuencias

**Positivas:**
- **Tiempos predecibles:** `gather()` tarda como máximo el timeout configurado
- **Debugging simplificado:** Un error es un error, sin capas de retry que ocultan problemas
- **Control explícito:** El código que llama decide si reintentar o no
- **Evita amplificación de latencia:** Si productos tarda 5s + 3 reintentos = 15s+ dentro del gather

**Negativas:**
- **Menos resiliente:** Errores 5xx transitorios no se recuperan automáticamente
- **Inconsistencia con Semana 2:** El cliente síncrono tenía reintentos

**Estrategia de mitigación:**
```python
# El código que llama puede reintentar todo el dashboard si es necesario
async def cargar_dashboard_con_retry():
    for intento in range(3):
        try:
            return await cargar_dashboard()
        except ServerError:
            if intento == 2:
                raise
            await asyncio.sleep(2 ** intento)
```

**Cuándo SÍ implementar retry:**
- Operaciones individuales críticas (login, pago) → retry a nivel de función
- Operaciones batch no críticas (importación) → retry todo el lote

---

## Resumen de Decisiones

| Decisión | Alternativa Principal | Justificación |
|----------|---------------------|---------------|
| gather() | wait() / as_completed() | Simplicidad + manejo de errores con return_exceptions |
| Sesión compartida | Sesión por petición | Reutilización de conexiones TCP (performance) |
| Timeout individual | Timeout global | Resiliencia: una petición lenta no bloquea todas |
| Semáforo 10 | Sin límite | Protección del servidor + control de recursos |
| Sin retry automático | Retry por función | Tiempos predecibles + debugging simplificado |

**Principio guía:** Priorizar **simplicidad** y **observabilidad** sobre **optimización prematura**. Todas estas decisiones pueden revisarse con métricas de producción.
