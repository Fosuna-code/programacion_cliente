# Recomendación de Estrategia de Coordinación para EcoMarket

## Resumen Ejecutivo

**Recomendación:** Usar **`asyncio.as_completed()`** como estrategia principal para el dashboard de EcoMarket.

**Puntuación final:** 23/25 puntos (la más alta)

---

## Contexto del Problema

El dashboard de EcoMarket necesita cargar datos desde 4 endpoints diferentes:
- **Productos** (latencia típica: 200ms)
- **Categorías** (latencia típica: 100ms)
- **Perfil de usuario** (latencia típica: 500ms)
- **Notificaciones** (latencia variable, puede hacer timeout)

**Requisitos de UX:**
- Mostrar datos lo más rápido posible
- No dejar al usuario mirando una pantalla en blanco
- Ser resiliente ante fallos parciales (una API caída no debe romper todo)

---

## Resultados de las Mediciones

### Diagrama Temporal Comparativo

```
Tiempo (ms) →
0ms         100ms       200ms       300ms       400ms       500ms       3000ms
│           │           │           │           │           │           │
├───────────┼───────────┼───────────┼───────────┼───────────┼───────────┼─────►

ESTRATEGIA 1: gather()
├───────────────────────────────────────────────────────────────────────┤
│                                                                       │
│ Espera a TODAS, incluso al timeout (3000ms)                          │
│ Usuario ve: [LOADING.................................................]  │
│                                                                       ✓ MOSTRAR TODO
│ Latencia percibida: 3000ms

ESTRATEGIA 2: wait(FIRST_COMPLETED)
├──────────►│
│ Categorías│           ├──────────►│
│ listas    │           │Productos  │           ├──────────────────────►│
│ (100ms)   │           │(200ms)    │           │      Perfil (500ms)   │         ├─X TIMEOUT
│ ✓MOSTRAR  │           │ ✓MOSTRAR  │           │      ✓MOSTRAR         │         │ (3000ms)
│                                                                                   ✓ ERROR
│ Latencia percibida: 100ms (primer dato)

ESTRATEGIA 3: as_completed()
├──────────►│           ├──────────►│           ├──────────────────────►│         ├─X
│ Cat(100ms)│           │Prod(200ms)│           │      Perfil (500ms)   │         │ Timeout
│ ✓PROCESAR │           │ ✓PROCESAR │           │      ✓PROCESAR        │         │ (3000ms)
│ ✓MOSTRAR  │           │ ✓MOSTRAR  │           │      ✓MOSTRAR         │         ✓ ERROR
│ Latencia percibida: 100ms (primer dato) + procesamiento incremental

ESTRATEGIA 4: wait(FIRST_EXCEPTION)
├──────────►│           ├──────────►│           ├──────────────────────►│         ├─X ABORT!
│ Cat(100ms)│           │Prod(200ms)│           │      Perfil (500ms)   │         │ (3000ms)
│ ✓OK       │           │ ✓OK       │           │      ✓OK              │         🚫 CANCELAR TODO
│                                                                                   
│ Latencia percibida: 3000ms (esperó al error), luego mostró NADA
```

---

## Análisis Detallado por Estrategia

### 1. `asyncio.gather()` - Esperar a Todas

**Qué hace:**
Lanza todas las peticiones en paralelo y espera a que TODAS terminen antes de retornar.

**Mediciones:**
- Primer dato disponible: **3000ms** (espera al timeout de notificaciones)
- Tiempo total: **3000ms**
- Resultado: 3 éxitos, 1 error (pero no puedes mostrar nada hasta que todo termine)

**Pros:**
- ✅ API muy simple (`await gather(...)`)
- ✅ Todos los resultados disponibles simultáneamente
- ✅ Con `return_exceptions=True`, maneja errores sin perder datos

**Contras:**
- ❌ **Latencia percibida altísima** (usuario espera 3 segundos viendo loading)
- ❌ No hay feedback progresivo
- ❌ Una petición lenta retrasa toda la UI

**Cuándo usar:**
- Cuando TODOS los datos son imprescindibles para mostrar algo
- Cuando la latencia total es aceptable (\<1s)
- Cuando la UI no soporta actualización incremental

---

### 2. `asyncio.wait(FIRST_COMPLETED)` - Procesar Conforme Llegan

**Qué hace:**
Procesa cada petición inmediatamente cuando completa, sin esperar a las demás.

**Mediciones:**
- Primer dato disponible: **100ms** (¡categorías!)
- Datos progresivos: 100ms → 200ms → 500ms → 3000ms (error)
- Tiempo total: **3000ms** (igual que gather, pero la UX es radicalmente diferente)

**Pros:**
- ✅ **Feedback inmediato** (usuario ve datos en 100ms)
- ✅ UI se va poblando progresivamente (mejor percepción de velocidad)
- ✅ Robusto: un error no afecta los datos ya mostrados

**Contras:**
- ❌ Código más verboso (bucle manual, manejo de sets de tareas)
- ❌ Requiere UI que soporte actualización incremental
- ❌ Más difícil de razonar sobre el flujo de datos

**Cuándo usar:**
- Dashboards con múltiples secciones independientes
- Feeds de noticias / redes sociales
- Cualquier UI donde "algo es mejor que nada"

---

### 3. `asyncio.as_completed()` - Iterar por Orden de Completación ⭐

**Qué hace:**
Similar a `wait(FIRST_COMPLETED)`, pero con sintaxis más simple: retorna un iterador que yielda tareas conforme completan.

**Mediciones:**
- Primer dato disponible: **100ms**
- Orden de procesamiento: categorías(100ms) → productos(200ms) → perfil(500ms) → error(3000ms)
- Tiempo total: **3000ms**

**Pros:**
- ✅ **Sintaxis más limpia** que `wait()` (loop simple)
- ✅ Feedback inmediato como `wait(FIRST_COMPLETED)`
- ✅ Fácil de agregar procesamiento por cada resultado
- ✅ Perfecto para pipelines: recibir → transformar → mostrar

**Contras:**
- ❌ No retorna todos los resultados juntos (pero eso es intencional)
- ❌ Requiere UI incremental (igual que wait)

**Cuándo usar:**
- Cuando querés procesar cada resultado inmediatamente
- Pipelines de datos (fetch → validate → display)
- **Dashboard de EcoMarket** ← ¡Nuestro caso!

---

### 4. `asyncio.wait(FIRST_EXCEPTION)` - Abortar ante Primer Error

**Qué hace:**
Espera a que la primera tarea lance una excepción, luego cancela todas las demás.

**Mediciones:**
- Tiempo hasta detectar error: **3000ms**
- Tareas canceladas: 1 (perfil, que todavía estaba en progreso)
- Resultado: **No mostró NADA** (abortó todo)

**Pros:**
- ✅ **Fail-fast** (falla rápido)
- ✅ Ahorra recursos cancelando tareas innecesarias
- ✅ Útil cuando un error invalida todo el flujo

**Contras:**
- ❌ **Pierde trabajo útil** (descarta datos ya obtenidos exitosamente)
- ❌ Mala UX: usuario esperó 3s para ver un error
- ❌ Solo apropiado en escenarios muy específicos

**Cuándo usar:**
- Autenticación fallida → no tiene sentido cargar datos
- Transacciones atómicas
- **NO usar en dashboard** (queremos mostrar datos parciales)

---

## Tabla Comparativa de Puntuación

| Criterio | gather() | wait(FC) | as_completed() ⭐ | wait(FE) |
|----------|----------|----------|-------------------|----------|
| **Latencia percibida** (1er dato) | 2/5<br>(3000ms) | 5/5<br>(100ms) | 5/5<br>(100ms) | 3/5<br>(3000ms, luego nada) |
| **Robustez ante errores** | 5/5<br>(no pierde datos) | 5/5<br>(resiliente) | 5/5<br>(resiliente) | 1/5<br>(descarta todo) |
| **Complejidad de código** | 5/5<br>(1 línea) | 2/5<br>(bucle + sets) | 4/5<br>(loop simple) | 2/5<br>(manejo de cancel) |
| **Mantenibilidad** | 5/5<br>(obvio) | 3/5<br>(tracking de estado) | 4/5<br>(legible) | 3/5<br>(lógica de abort) |
| **Feedback progresivo UX** | 1/5<br>(todo o nada) | 5/5<br>(incremental) | 5/5<br>(incremental) | 1/5<br>(abort = nada) |
| **TOTAL** | **18/25** | **20/25** | **23/25** ⭐ | **10/25** |

---

## Recomendación Final para EcoMarket

### Estrategia Elegida: `asyncio.as_completed()` 🏆

**Justificación:**

1. **Mejor UX percibida:**
   ```python
   # Usuario ve categorías en 100ms, no espera 3 segundos
   for coro in asyncio.as_completed(tareas):
       resultado = await coro
       actualizar_ui(resultado)  # ← Feedback inmediato
   ```

2. **Código mantenible:**
   - Más simple que `wait(FIRST_COMPLETED)` (sin manejo manual de sets)
   - Más expresivo que `gather()` (muestra intención de procesar incrementalmente)

3. **Resiliente:**
   ```python
   # Si notificaciones falla, el resto se muestra igual
   try:
       resultado = await coro
       mostrar_seccion(resultado)
   except TimeoutError:
       mostrar_error_parcial("Notificaciones no disponibles")
   ```

4. **Escalable:**
   - Fácil agregar más endpoints (simplemente añadir a la lista de tareas)
   - Fácil agregar prioridades (procesar críticos primero)

### Implementación Recomendada

```python
async def cargar_dashboard():
    """Carga el dashboard mostrando datos conforme llegan."""
    async with aiohttp.ClientSession() as session:
        # Definir tareas en orden de prioridad (las críticas primero)
        tareas = [
            obtener_perfil(session),      # Crítico (autenticación)
            obtener_productos(session),    # Crítico (contenido principal)
            obtener_categorias(session),   # Importante (navegación)
            obtener_notificaciones(session), # Secundario (puede fallar)
        ]
        
        resultados = {
            "perfil": None,
            "productos": None,
            "categorias": None,
            "notificaciones": None,
        }
        
        # Procesar conforme van llegando
        for coro in asyncio.as_completed(tareas):
            try:
                resultado = await coro
                endpoint = resultado['endpoint']
                resultados[endpoint] = resultado['data']
                
                # Actualizar UI inmediatamente
                print(f"✓ {endpoint} cargado → actualizar sección")
                
                # Lógica de negocio
                if endpoint == "perfil" and resultado['data'].get('rol') == 'invitado':
                    # Cancelar tareas secundarias si es usuario no autenticado
                    pass
                    
            except asyncio.TimeoutError as e:
                # Error no crítico, continuar con las demás
                print(f"⚠ Timeout en endpoint → mostrar placeholder")
            except Exception as e:
                # Loguear pero no abortar
                print(f"❌ Error: {e}")
        
        return resultados
```

### Alternativa: Estrategia Híbrida

Para casos avanzados, podemos combinar estrategias:

```python
async def cargar_dashboard_hibrido():
    """
    Estrategia híbrida:
    1. Esperar a peticiones críticas (gather)
    2. Mostrar datos secundarios conforme llegan (as_completed)
    """
    async with aiohttp.ClientSession() as session:
        # Paso 1: Esperar a datos críticos juntos (máximo 2s)
        try:
            perfil, productos = await asyncio.wait_for(
                asyncio.gather(
                    obtener_perfil(session),
                    obtener_productos(session),
                ),
                timeout=2.0
            )
            mostrar_dashboard_basico(perfil, productos)
        except asyncio.TimeoutError:
            mostrar_error("No se pudo cargar datos críticos")
            return
        
        # Paso 2: Cargar secundarios conforme llegan
        tareas_secundarias = [
            obtener_categorias(session),
            obtener_notificaciones(session),
        ]
        
        for coro in asyncio.as_completed(tareas_secundarias):
            try:
                resultado = await coro
                actualizar_seccion_secundaria(resultado)
            except:
                pass  # Errores secundarios no afectan la UI principal
```

---

## Conclusión

Para el dashboard de EcoMarket, **`asyncio.as_completed()`** ofrece el mejor balance entre:
- ✅ UX (latencia percibida de 100ms vs 3000ms)
- ✅ Robustez (maneja errores parciales)
- ✅ Mantenibilidad (código legible)

**Evitar:** `wait(FIRST_EXCEPTION)` - solo úsalo para flujos transaccionales donde un error invalida todo.

**Considerar `gather()`** solo si:
- Tu UI no soporta actualización incremental
- TODOS los datos son críticos
- La latencia total es \<1s

---

**Referencias:**
- Documentación oficial: https://docs.python.org/3/library/asyncio-task.html
- PEP 492: Coroutines with async and await syntax
- Real Python: Async IO in Python - A Complete Walkthrough
