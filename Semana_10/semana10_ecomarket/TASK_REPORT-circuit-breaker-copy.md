# Task Report: Circuit Breaker Copy & Modification

## Summary
Copied `circuit_breaker.py` from Semana IX to Semana X with the required modifications to make it self-contained and add UI observability callbacks (`on_circuit_open`, `on_circuit_close`).

## Files Modified/Created
- **Created**: `/home/petucho/Documents/scul/FEND101/Semana X/semana10_ecomarket/circuit_breaker.py`
- **Source**: `/home/petucho/Documents/scul/FEND101/Semana IX/semana9_ecomarket/circuit_breaker.py`

## Changes Made
1. **Self-contained**: Verified that the module only uses stdlib imports (`asyncio`, `time`, `logging`, `enum`). No external dependencies from other weeks were introduced.
2. **Preserved design decisions**: All original design decisions, docstrings, thresholds, timeouts, error-classification logic, and `asyncio.Lock` SEMIABIERTO handling remain intact.
3. **Invariant compliance verified**:
   - **INV-A1**: CircuitBreaker never touches JWT fields — no token decoding logic exists.
   - **INV-A2**: SEMIABIERTO uses `asyncio.Lock`; concurrent test requests get `CircuitOpenError`.
   - **INV-A3**: `_fallos_consecutivos` is reset to `0` in `_registrar_exito()` before any state transition.
   - **INV-A4**: `_es_fallo_servidor()` explicitly returns `False` for 4xx-class errors (via `.status`/`.code` < 500 checks and exclusion of client errors).
4. **Added callback properties**:
   - `on_circuit_open` / `on_circuit_close` properties with getters/setters.
   - Private attributes `_on_circuit_open` and `_on_circuit_close` initialized to `None` in `__init__`.
   - Callback `_on_circuit_open` is fired inside `_registrar_fallo()` when the circuit transitions to `ABIERTO`.
   - Callback `_on_circuit_close` is fired inside `_registrar_exito()` when the circuit transitions from `SEMIABIERTO` → `CERRADO`.
   - Both callbacks are wrapped in `try/except` so a faulty UI callback cannot break the breaker logic.

## Self-Assessment
**DONE**
