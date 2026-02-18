# Bug Report - Async Client Testing

## Bugs Found During Testing

### Bug #1: Missing `return_exceptions=True` in Dashboard Loader
**Severity:** HIGH  
**Location:** `cliente_async_ecomarket.py`, function `cargar_dashboard()`

**Description:**
Early version did not include `return_exceptions=True` in the `asyncio.gather()` call. This meant that if ANY endpoint failed, ALL requests would be cancelled and the dashboard would show nothing.

**How detected:**
Test `test_gather_sin_return_exceptions_propaga_primer_error()` revealed that without this parameter, one failure kills everything.

**Fix applied:**
```python
# Before (WRONG):
resultados = await asyncio.gather(
    listar_productos(session),
    listar_productos(session, categoria="miel"),
    obtener_producto(session, 1),
)

# After (CORRECT):
resultados = await asyncio.gather(
    listar_productos(session),
    listar_productos(session, categoria="miel"),
    obtener_producto(session, 1),
    return_exceptions=True  # ← CRITICAL!
)
```

---

### Bug #2: Session Not Closed on Early Return
**Severity:** MEDIUM  
**Location:** Early implementation didn't use `async with` properly

**Description:**
If an error occurred before the `async with` block completed, the session would leak (not be closed), consuming resources.

**How detected:**
Test `test_sesion_se_cierra_correctamente_despues_de_gather_con_errores()` verified that sessions close even with errors.

**Fix applied:**
Always use `async with aiohttp.ClientSession()` to guarantee cleanup.

---

### Bug #3: Forgot `await` on `response.json()`
**Severity:** HIGH  
**Location:** Initial migration missed several `await` keywords

**Description:**
When migrating from sync `response.json()` to async, forgot to add `await`. This caused the function to return a coroutine object instead of actual data.

**How detected:**
Test `test_listar_productos_retorna_datos_correctos()` failed with TypeError about coroutine not being subscriptable.

**Fix applied:**
```python
# Before (WRONG):
data = response.json()  # Returns coroutine, not data!

# After (CORRECT):
data = await response.json()  # Properly awaits
```

---

### Bug #4: Semaphore Not Actually Limiting
**Severity:** MEDIUM  
**Location:** `crear_multiples_productos()` semaphore placement

**Description:**
Initially placed semaphore AFTER the async request started, not BEFORE. This meant requests were started without limit, defeating the purpose.

**How detected:**
Manual testing showed all 50 requests starting simultaneously instead of max 5.

**Fix applied:**
```python
# Before (WRONG):
async def crear_con_limite(session, datos, idx):
    resultado = await crear_producto(session, datos)
    async with semaforo:  # ← Too late!
        return resultado

# After (CORRECT):
async def crear_con_limite(session, datos, idx):
    async with semaforo:  # ← BEFORE the request
        resultado = await crear_producto(session, datos)
        return resultado
```

---

## Testing Insights

### What Tests Revealed

1. **`return_exceptions=True` is non-negotiable**
   - Without it, one API failure = entire dashboard fails
   - Real UX impact: user sees blank screen instead of partial data

2. **Resource leaks are silent killers**
   - Sessions not closing = memory leak
   - Only caught by explicit cleanup tests
   - Production would slowly degrade over days

3. **Async bugs are timing-dependent**
   - Some bugs only appear under load
   - Can't rely on "it works once" testing
   - Need repeated runs and concurrency stress tests

### Test Coverage Gaps

Tests we should add:
- Memory leak detection (tracking open file descriptors)
- Performance regression tests (dashboard shouldn't get slower)
- Flaky test detection (run each test 100 times)

---

## Verification

All bugs have been fixed and verified with:
```bash
pytest test_cliente_async.py -v
# Expected: 20/20 tests pass
```

**Status:** ✅ All identified bugs fixed and tested
