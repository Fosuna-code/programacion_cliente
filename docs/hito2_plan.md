# Plan — Hito 2 / Examen Práctico 2 (Semana 10 — Grand Deploy)

## Context

Final project of *Programación Distribuida del Lado del Cliente*. The activity in `Semana_10/semana10_cliente_aetl_ver2.html` bundles two instruments:

- **Examen Práctico 2** (12% of course, in-class artifacts)
- **Hito 2 — Cliente Seguro y Resiliente** (15% of course, formal delivery)

Teacher will only review the `.zip` (no deploy needed). The .zip must satisfy the **Hito 2 deliverable list** (12 required files) and also include the **Examen artifacts** because they share Retos 1-8.

**Constraints**
- Team of 2 (Cruz & Martínez or equivalent)
- < 1 day until submission
- Target: 100 base + Reto 9 bonus (+5) if time permits → ~105/100
- Existing semana 7-9 Python code (CB + TM + CR + SSE) has **not been verified end-to-end** → primary risk is the **Hard Gate** (broken code blocks the entrega).

**What's already done (reusable)**
- `semana_7/cliente_sse_multiplex.py`, `event_router_prioritizado.py`
- `semana_8/token_manager.py`, `sse_auth_design.md`
- `semana_9/circuit_breaker.py`, `cliente_robusto.py`, `demo_resiliencia.log`, `reporte_validacion.md`, `README.md` (already contains invariants INV-A1..A4, error-classification table, and Auth-Breaker Deadlock analysis — directly reusable in `checklist_invariantes.md` and `adr_decision_critica.md`)

## Strategy — Triage-first sprint (4 phases + bonus)

Time-boxed to ~7 hours of focused work for two people. De-risks the Hard Gate first.

### Phase 1 — Smoke test & mock (1h)
1. Build minimal `mock_server.py` (FastAPI or `http.server`) with endpoints:
   - `POST /auth/login` → returns JWT
   - `POST /auth/refresh` → returns new JWT (must stay outside breaker)
   - `GET /api/inventario` → controllable failure mode (env var or query param to force 500/503/timeout)
   - `GET /api/precios` → stable, for cross-regression test
2. Run `cliente_robusto.py` against mock. Confirm: login OK, inventario OK, force 5 failures → state transitions CERRADO→ABIERTO, wait 60s → SEMIABIERTO, success → CERRADO.
3. Fix any bugs found. Regenerate `demo_resiliencia.log` from actual run.

### Phase 2 — New code (2h)
4. `cliente_integrado.py` (Reto 4): script that performs login → 3 OK requests → triggers 5 failures → shows state transitions → recovers. Must (a) NOT log token in plaintext, (b) NOT block viewer role, (c) print observable UI state (`[UI] modo degradado`, `[UI] reconectando`, etc.).
5. `test_circuit_breaker.py`: pytest covering **INV-A2** (only ONE probe allowed in SEMIABIERTO; concurrent requests get `CircuitOpenError` instantly). This is the rubric's "prueba automatizada reproducible" (12 pts).

### Phase 3 — Markdown deliverables (3h) — split between partners

**Partner 1 (technical docs):**
- `checklist_invariantes.md` — 7 invariants (4 INV-A from semana_9 README + 3 INV-B from token_manager.py docstring), each with: state (✅/⚠️/❌), evidence (log line or test name), correction if applicable.
- `adr_decision_critica.md` — ADR Express on Auth-Breaker Deadlock decision (context → decision → consequences → adverse scenario). Material exists in semana_9 README §Evasión del Deadlock.
- `tc_cross_regression.md` — 3 cross-regression test cases:
  - TC-X1: token refresh succeeds while CB is open (manual protocol + log)
  - TC-X2: SEMIABIERTO admits exactly one probe (this is what `test_circuit_breaker.py` proves)
  - TC-X3: 401 does NOT increment fail counter (manual protocol + log)
- `diagrama_flujo.txt` — 5 nodes from Reto 2 (answers already in HTML retro section, just rewrite in own words).

**Partner 2 (process/meta docs):**
- `autopsia_bugs.md` — 3 deliberate bugs from Reto 3: (Bug A: SRP violation in ClienteRobusto, Bug B: token leak in logs, Bug C: corrupt state on partial failure). Each: Síntoma · Causa raíz · Corrección · Principio violado.
- `respuestas_reto1.md` — 5 fragment assignments + 1-sentence technical justification each (A→ReceptorAlertas, B→EventRouter, C→TokenManager, D→CircuitBreaker, E→ClienteRobusto).
- `bitacora_ia.md` — for each significant AI prompt: prompt summary, what AI suggested, what was accepted/rejected, technical justification. Quality > quantity (rubric demands curation, not transcripts).
- `contribucion_equipo.md` — split of work, individual contributions, one documented technical conflict and its resolution.

### Phase 4 — Assembly & final verification (1h)
6. Write `README.md` at root of zip: Python version, `pip install -r requirements.txt`, how to start `mock_server.py`, how to run `cliente_integrado.py`, how to run `pytest`, expected output.
7. Run the full chain ONE more time end-to-end. Capture fresh log.
8. Zip structure:
   ```
   hito2_cruz_martinez.zip
   ├── README.md
   ├── requirements.txt
   ├── src/
   │   ├── circuit_breaker.py
   │   ├── token_manager.py
   │   ├── cliente_robusto.py
   │   ├── cliente_integrado.py
   │   └── mock_server.py
   ├── tests/
   │   └── test_circuit_breaker.py
   ├── docs/
   │   ├── autopsia_bugs.md
   │   ├── checklist_invariantes.md
   │   ├── adr_decision_critica.md
   │   ├── tc_cross_regression.md
   │   ├── diagrama_flujo.txt
   │   ├── respuestas_reto1.md
   │   ├── bitacora_ia.md
   │   └── contribucion_equipo.md
   └── logs/
       └── demo_resiliencia.log
   ```
9. Tag git commit `hito2`. Verify integrity checklist boxes mentally:
   - Each member can verbally explain any function ✅
   - AI use documented with decisions, not transcripts ✅
   - Code was executed before delivery ✅
   - Contributions documented ✅

### Phase 5 — Bonus (only if Phase 1-4 finish on schedule)
10. **Reto 9 — Postmortem** (+5 pts, ~1h): Write `postmortem.md` simulating a production incident based on the demo log. Sections: timeline, root cause, contributing factors, action items.

**Skipped bonus:** Reto 6 (Árbitro SSE +7) requires significant SSE work; Reto 10 (Preview WS +3) requires a WebSocket spike. Not worth the time at our risk profile.

## Critical files to modify/create

| Path | Action |
|---|---|
| `Semana_10/hito2/mock_server.py` | CREATE |
| `Semana_10/hito2/cliente_integrado.py` | CREATE |
| `Semana_10/hito2/test_circuit_breaker.py` | CREATE |
| `Semana_10/hito2/circuit_breaker.py` | COPY from `semana_9/` (fix if smoke test fails) |
| `Semana_10/hito2/token_manager.py` | COPY from `semana_8/` (fix if smoke test fails) |
| `Semana_10/hito2/cliente_robusto.py` | COPY from `semana_9/` (fix if smoke test fails) |
| `Semana_10/hito2/docs/*.md` | CREATE 8 markdown files |
| `Semana_10/hito2/README.md` | CREATE |
| `Semana_10/hito2/requirements.txt` | CREATE (fastapi, uvicorn, pytest, httpx, pyjwt) |
| `Semana_10/hito2/logs/demo_resiliencia.log` | REGENERATE from fresh run |

Reuse pattern: anywhere the rubric asks for a design rationale that's already in `semana_9/README.md`, copy-paste-adapt rather than rewrite from scratch.

## Verification

End-to-end check before zipping:

```bash
cd Semana_10/hito2
pip install -r requirements.txt

# Terminal 1: mock server
python src/mock_server.py

# Terminal 2: demo
python src/cliente_integrado.py | tee logs/demo_resiliencia.log
# Expect to see: login OK, 3x inventario OK, 5x failure, [CB] CERRADO→ABIERTO,
# 60s wait, [CB] ABIERTO→SEMIABIERTO, success, [CB] SEMIABIERTO→CERRADO

# Terminal 3: test
pytest tests/test_circuit_breaker.py -v
# Expect: 1 passed (INV-A2 — concurrent probes blocked in SEMIABIERTO)
```

Pass conditions for Hard Gate:
- CB shows 3 states in log ✅
- ≥4 invariants verified in checklist ✅
- ≥2 bug diagnoses present ✅
- README has install/run/test commands that actually work ✅
- 1 automated test passes ✅

If all pass → zip and submit.
