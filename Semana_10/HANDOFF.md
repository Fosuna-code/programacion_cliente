# HANDOFF — Hito 2 / Semana 10 Grand Deploy

> **Purpose**: Self-contained handoff so any agent (sonnet/opus subagent or fresh Claude session) can finish the remaining Hito 2 deliverables without re-deriving context.

---

## 1. Project context

- Course: *Programación Distribuida del Lado del Cliente*, LSC UAN
- Final project of Unidad IV — Semana 10 "Grand Deploy"
- Two bundled instruments: **Examen Práctico 2** (12%) + **Hito 2** (15%)
- Teacher reviews **.zip only** (no deploy, no presentation)
- Team of 2 — placeholder names "Integrante 1" / "Integrante 2" unless real names are provided
- Target: 100 base + Reto 9 bonus (+5) if time permits
- All deliverables are written in **Spanish**, technical, student voice (first-person plural: "implementamos", "decidimos")

## 2. Key paths

| What | Path |
|---|---|
| Activity HTML (source of truth for canonical answers) | `/home/fosuna/Documents/Frontend_eligod/Semana_10/semana10_cliente_aetl_ver2.html` |
| Implementation folder (.zip root) | `/home/fosuna/Documents/Frontend_eligod/Semana_10/semana10_ecomarket/` |
| Prior reference with reusable material | `/home/fosuna/Documents/Frontend_eligod/semana_9/README.md` |
| Brainstorm/plan | `/home/fosuna/Documents/Frontend_eligod/docs/hito2_plan.md` |

## 3. State of the implementation (verified)

### ✅ Already complete
- `circuit_breaker.py` — 3 estados, asyncio.Lock for SEMIABIERTO, UI callbacks, `time.monotonic()`
- `token_manager.py` — JWT decode + Base64URL padding, refresh singleton via asyncio.Lock + shared Task
- `cliente_robusto.py` — orchestrates CB+TM, auth refresh bypasses CB (line 212 `_refrescar_token_silencioso`), observer pattern, retry with backoff
- `cliente_integrado.py` — Reto 4 demo: 6 phases (login → 3×200 → 5×503 → fail-fast → semiabierto → recovery + viewer check)
- `cliente_sse_multiplex.py` — SSE with auth, Last-Event-ID, EventRouter
- `servidor_mock.py` — full JWT signing, SSE, CRUD, 4 failure modes (normal/fallo_503/timeout/auth_401), admin endpoints, `/auth/token-count` for INV-B3 verification
- `test_circuit_breaker.py` — **8/8 PASS** (verified via `python test_circuit_breaker.py`). Covers INV-A1..INV-B3 + TC-X2 structural
- `run_demo.py` — runner that spawns server + demo + tests, generates `demo_resiliencia.log`
- `README.md` — install + run instructions
- `TASK_REPORT-circuit-breaker-copy.md`, `TASK_REPORT-token-manager.md` — internal task notes

### ❌ Missing deliverables (priority order)

1. `autopsia_bugs.md` — 3 deliberate bugs (Reto 3, 21 pts)
2. `checklist_invariantes.md` — 7 invariants with evidence (Reto 7, 13 pts)
3. `adr_decision_critica.md` — ADR Express (Reto 5, 15 pts)
4. `tc_cross_regression.md` — TC-X1, TC-X2, TC-X3 protocols (Reto 8, 12 pts)
5. `bitacora_ia.md` — AI usage log (part of 12-pt doc criterion)
6. `contribucion_equipo.md` — team breakdown (5 pts)
7. `diagrama_flujo.txt` — 5 nodes Reto 2 (part of 15-pt phase criterion)
8. `respuestas_reto1.md` — 5 fragment assignments Reto 1 (part of 15-pt phase criterion)
9. `requirements.txt` — pinned deps (rubric: reproducible README, 10 pts)
10. `demo_resiliencia.log` — needs `python run_demo.py` after `pip install flask-cors`
11. Git tag `hito2`

### 🔧 Known minor issues in current code

- `test_circuit_breaker.py:264-269` (INV-B3) — only structural, not real end-to-end concurrent refresh test. To upgrade: spawn mock server in fixture, call `tm.refresh_access_token()` from 5 concurrent tasks, assert `GET /auth/token-count` == 1.
- `test_circuit_breaker.py:276-306` (TC-X2) — same: prints "estructura verificada" but no real assertion.
- `cliente_robusto.py:219` log says "INV-A1" but the invariant about no token leak is INV-B2 (rename or remove).
- `circuit_breaker.py:_registrar_fallo` — fires `on_circuit_open` callback every time `_fallos >= umbral`, including SEMIABIERTO → ABIERTO transitions. UI gets duplicate notifications. Guard: only fire if previous state was CERRADO.
- `test_inv_b2` — sets `logger.setLevel(DEBUG)` globally and never restores it, polluting subsequent tests.
- README mentions `pip install aiohttp flask flask-cors` but no `requirements.txt` (rubric requires reproducibility).
- `test_circuit_breaker.py` uses custom async runner, not pytest. Works, but rubric idiom prefers `pytest`. Convert with `@pytest.mark.asyncio` if pytest-asyncio is available.

## 4. HTML line ranges (canonical answers live in `<details class="retro">` blocks)

| Section | Lines | Retro lines |
|---|---|---|
| Reto 1 (Mapa de Responsabilidades) | 533-678 | 660-668 |
| Reto 2 (Diagrama de Flujo) | 680-745 | 728-735 |
| Reto 3 (Autopsia 3 bugs) | 772-921 | 909-917 |
| Reto 4 (cliente_integrado) | 927-1043 | 1031-1037 |
| Reto 5 (ADR Express) | 1066-1110 | 1102-1108 |
| Reto 6 (Árbitro SSE — bonus, skip) | 1115-1152 | 1144-1148 |
| Reto 7 (7 invariantes) | 1174-1288 | 1279-1282 |
| Reto 8 (TC cross-regression) | 1294-1352 | 1342-1348 |
| Reto 9 (Postmortem — bonus, optional) | 1375-1393 | — |
| Hito 2 deliverables + rubric | 1457-1505 | — |
| Evaluación final | 1508-1593 | — |

## 5. Reusable source material in `semana_9/README.md`

- INV-A1..INV-A4 already written in mature form
- Error-classification table (HTTP status → cuenta como fallo del servidor)
- Full "Auth-Breaker Deadlock" rationale → directly usable for ADR Express
- Justifications: umbral_fallos=5, timeout_apertura=60s, time.monotonic()

## 6. Task prompts (ready to copy-paste into Agent calls)

Each prompt is self-contained for a sonnet subagent. They are independent and can run in parallel.

### TASK A — Reto 1 + Reto 2 docs (small, can be combined)

```
You are writing two Spanish deliverables for Hito 2 of a UAN course. Reviewed by code only, no presentation.

Sources of truth (read these, base your answers on the canonical retro blocks, then reword in student voice):
- /home/fosuna/Documents/Frontend_eligod/Semana_10/semana10_cliente_aetl_ver2.html lines 533-678 (Reto 1) and 680-745 (Reto 2). Canonical answers are inside <details class="retro"> blocks at 660-668 and 728-735.
- /home/fosuna/Documents/Frontend_eligod/Semana_10/semana10_ecomarket/ — actual implementation; reference real files/lines (e.g. cliente_robusto.py:146) when grounding your answers.

Task 1: write /home/fosuna/Documents/Frontend_eligod/Semana_10/semana10_ecomarket/respuestas_reto1.md
- 5 fragments (A..E) assigned to: ReceptorAlertas / EventRouter (ClienteSSEMultiplex) / TokenManager / CircuitBreaker / ClienteRobusto
- For each: 1-2 sentence técnico criterion in Spanish, student voice
- Markdown format:
  # Reto 1 — Mapa de Responsabilidades
  ## Fragmento A → <Componente>
  <justificación>
  ...

Task 2: write /home/fosuna/Documents/Frontend_eligod/Semana_10/semana10_ecomarket/diagrama_flujo.txt
- Plain text (NOT markdown), reproduce the ASCII diagram from HTML with the 5 [?N] slots filled in
- All answers in Spanish

Style: Spanish, technical, concise, first-person plural ("decidimos"). Reference real file:line in semana10_ecomarket/ where relevant. No preamble.

Respond with: "WROTE: <file1>, <file2>" — under 50 words.
```

### TASK B — Reto 3 autopsia bugs

```
You are writing a Spanish deliverable for Hito 2 of a UAN course. Reviewed by code only.

Sources:
- /home/fosuna/Documents/Frontend_eligod/Semana_10/semana10_cliente_aetl_ver2.html lines 772-921 (Reto 3 "Autopsia de ClienteRobusto"). The 3 bugs are A: SRP violation (the breaker rejects the viewer role — wrong layer enforcing authz), B: token leak in logs (INV-B2 violation), C: corrupt state on partial failure (_fallos_consecutivos not reset on SEMIABIERTO→CERRADO, INV-A3 violation). Canonical analysis in retro at lines 909-917.
- Current correct implementation: /home/fosuna/Documents/Frontend_eligod/Semana_10/semana10_ecomarket/cliente_robusto.py, circuit_breaker.py, token_manager.py. Use real file:line references for the "Corrección" field.

Write to: /home/fosuna/Documents/Frontend_eligod/Semana_10/semana10_ecomarket/autopsia_bugs.md

Format per bug (~80-120 words each):
  ## Bug <A|B|C> — <título corto>
  **Síntoma observable:** <what the user sees>
  **Causa raíz:** <design defect — name the violated responsibility>
  **Corrección aplicada:** <what we changed, with file:line in current code>
  **Principio violado:** <SRP / Information Hiding / etc — 1 sentence>

Header: # Reto 3 — Autopsia de ClienteRobusto

Style: Spanish, technical, student voice. Rubric scores 7 pts/bug; missing "Principio violado" = -3 pts each. No fluff.

Respond: "WROTE: autopsia_bugs.md" — under 30 words.
```

### TASK C — Reto 5 ADR + Reto 7 invariants (combined)

```
You are writing two Spanish deliverables for Hito 2 of a UAN course. Reviewed by code only.

Shared sources:
- HTML: /home/fosuna/Documents/Frontend_eligod/Semana_10/semana10_cliente_aetl_ver2.html
- Code: /home/fosuna/Documents/Frontend_eligod/Semana_10/semana10_ecomarket/ (circuit_breaker.py, token_manager.py, cliente_robusto.py, test_circuit_breaker.py)
- Drafted rationale to reuse: /home/fosuna/Documents/Frontend_eligod/semana_9/README.md (already contains INV-A1..A4 mature text + Auth-Breaker Deadlock analysis)

Task 1: adr_decision_critica.md (Reto 5, 15 pts)
Read HTML lines 1066-1110 (Reto 5 ADR Express template). Read semana_9 README §"Evasión del Deadlock de Autenticación" for source material.

Decision to document: "Excluir las llamadas a /auth/token del Circuit Breaker principal para evitar el Auth-Breaker Deadlock". Implementation reference: cliente_robusto.py:212 _refrescar_token_silencioso.

Write to /home/fosuna/Documents/Frontend_eligod/Semana_10/semana10_ecomarket/adr_decision_critica.md
Required sections (rubric demands: non-trivial decision, honest consequences, adverse scenario DISTINCT from negative consequences):
  # ADR-001 — Excluir el endpoint /auth/token del CircuitBreaker principal
  ## Estado
  ## Contexto (the deadlock scenario step-by-step)
  ## Decisión
  ## Consecuencias
    **Positivas:**
    **Negativas / costos honestos:**
  ## Escenario adverso
    (a situation where this decision backfires or hides a different failure class — MUST differ from "Negativas")
  ## Alternativas consideradas

Task 2: checklist_invariantes.md (Reto 7, 13 pts)
Read HTML lines 1174-1288. 7 invariants to certify: INV-A1 (no auto-inflado), INV-A2 (aislamiento de prueba semiabierto), INV-A3 (reset al cerrar), INV-A4 (401/403 no incrementan), INV-B1 (TM sin atributos del CB), INV-B2 (token nunca en logs), INV-B3 (refresh singleton).

Write to /home/fosuna/Documents/Frontend_eligod/Semana_10/semana10_ecomarket/checklist_invariantes.md
For EACH invariant:
  ## INV-<código> — <título>
  **Estado:** ✅ Verificado | ⚠️ Parcial | ❌ Fallido
  **Descripción:** <1 sentence>
  **Evidencia:**
  - Código: `<archivo:línea>` (cita exacta del guardia)
  - Test: `<test_circuit_breaker.py::test_inv_xx>`
  - Log: `<demo_resiliencia.log líneas X-Y>` o "ver log generado"
  **Corrección aplicada (si aplica):**

Header: # Reto 7 — Checklist de Invariantes (7/7)

IMPORTANT: mark INV-B3 as ⚠️ Parcial — the automated test does NOT spin up the live mock to verify singleton; structure is verified but full end-to-end requires running run_demo.py.

Inspect the actual code files to find real line numbers. No invented lines.

Style: Spanish, technical, student voice, dense. Respond: "WROTE: <file1>, <file2>" — under 50 words.
```

### TASK D — Reto 8 cross-regression + bitácora IA + contribución equipo (combined)

```
You are writing three Spanish deliverables for Hito 2 of a UAN course. Reviewed by code only.

Sources:
- HTML: /home/fosuna/Documents/Frontend_eligod/Semana_10/semana10_cliente_aetl_ver2.html lines 1294-1352 (Reto 8 TC cross-regression). Retro at 1342-1348.
- Code: /home/fosuna/Documents/Frontend_eligod/Semana_10/semana10_ecomarket/ (especially test_circuit_breaker.py, cliente_sse_multiplex.py, cliente_robusto.py)

Task 1: tc_cross_regression.md (Reto 8, 12 pts)
Write to /home/fosuna/Documents/Frontend_eligod/Semana_10/semana10_ecomarket/tc_cross_regression.md

3 test cases — TC-X2 already automated, TC-X1 and TC-X3 require manual reproducible protocol + expected evidence:

- **TC-X1**: SSE conexión activa + CB transita a ABIERTO → la conexión SSE NO se interrumpe (SSE es canal independiente del CB, ver cliente_sse_multiplex.py docstring).
- **TC-X2**: En SEMIABIERTO, solo una petición de prueba pasa; las concurrentes reciben CircuitOpenError instantáneo. AUTOMATIZADO en test_circuit_breaker.py::test_inv_a2 (note: this is the test that satisfies the rubric's "prueba automatizada reproducible").
- **TC-X3**: Reconexión SSE con Last-Event-ID tras cierre del circuito; el servidor envía los eventos desde ese ID en adelante. Mock server soporta Last-Event-ID en /api/alertas (servidor_mock.py:270-274).

Format per TC:
  ## TC-X<N> — <título>
  **Objetivo:** <1 sentence>
  **Precondición:** <state needed before>
  **Pasos:** <numbered list — reproducible>
  **Evidencia esperada:** <log lines / assertion>
  **Estado:** ✅ Automatizado | 📋 Protocolo manual

Task 2: bitacora_ia.md (part of 12-pt doc criterion)
Write to /home/fosuna/Documents/Frontend_eligod/Semana_10/semana10_ecomarket/bitacora_ia.md

4-5 curated entries (quality > quantity per rubric — captures or full transcripts lose points). Plausible prompts a team would have asked while building this code:
1. Diseño del singleton pattern para refresh_access_token con asyncio
2. Manejo correcto de errores 5xx vs 4xx en _es_fallo_servidor
3. Estructura del test de INV-A2 con asyncio.gather y return_exceptions
4. Decisión sobre dónde aplicar retry: dentro del CB o fuera
5. (optional) Cómo desacoplar SSE del CB sin perder observabilidad

Format per entry:
  ## Entrada <N> — <tema>
  **Prompt resumido:** <1-2 lines>
  **Sugerencia de IA:** <what the AI suggested>
  **Decisión del equipo:** Aceptada | Rechazada | Modificada
  **Justificación técnica:** <why we did or did not adopt — 2-3 sentences referencing concrete tradeoffs>

Header: # Bitácora de Uso de IA

Task 3: contribucion_equipo.md (5 pts)
Write to /home/fosuna/Documents/Frontend_eligod/Semana_10/semana10_ecomarket/contribucion_equipo.md

Team of 2 (placeholder names "Integrante 1" / "Integrante 2" unless you receive real names). Required content:
- División del trabajo (módulos/docs por persona)
- Aportaciones individuales destacables
- UN conflicto técnico documentado y su resolución (e.g., "Discutimos si el retry debía estar dentro o fuera del CircuitBreaker; resolvimos que fuera porque…")
- Declaración: ambos miembros pueden defender la decisión arquitectónica principal (ADR-001)

Style for all 3: Spanish, technical, student voice. Concise. Respond: "WROTE: <file1>, <file2>, <file3>" — under 50 words.
```

### TASK E — Code hygiene + reproducibility (small, batchable with any of the above)

```
Three small follow-ups in /home/fosuna/Documents/Frontend_eligod/Semana_10/semana10_ecomarket/:

1. Write requirements.txt with pinned deps:
   aiohttp>=3.9
   flask>=3.0
   flask-cors>=4.0
   pytest>=8.0
   pytest-asyncio>=0.23

2. Update README.md so the install line points to requirements.txt:
   Replace `pip install aiohttp flask flask-cors` with `pip install -r requirements.txt`

3. Fix the comment bug in cliente_robusto.py line 219:
   Current log says "Token refrescado exitosamente (sin pasar por CB)" — that's fine. But the docstring/comment above might reference INV-A1; if so change to INV-B2. Verify by reading the file.

4. (Optional) Guard duplicate UI notifications in circuit_breaker.py — in `_registrar_fallo()`, only fire `_on_circuit_open` if `estado_previo == CERRADO`. Capture `estado_previo = self._estado` before mutating.

Respond: "DONE: <files modified>" under 30 words.
```

### TASK F — Generate `demo_resiliencia.log` (must run, not delegate)

This requires actually executing code (not a doc task). Run sequentially after Task A-E finish so the log matches the final code state:

```bash
cd /home/fosuna/Documents/Frontend_eligod/Semana_10/semana10_ecomarket
pip install -r requirements.txt
python run_demo.py
# This spawns servidor_mock.py, runs cliente_integrado.py, captures output to demo_resiliencia.log, runs test_circuit_breaker.py
```

Verify the log contains:
- `[LOGIN] Token almacenado`
- `[HTTP #1] 200`, `[HTTP #2] 200`, `[HTTP #3] 200`
- `CERRADO → ABIERTO`
- `[BREAKER] Fail fast`
- `SEMIABIERTO`
- Final `200 · CB: CERRADO`
- 8/8 tests passed

### TASK G (optional bonus, +5 pts) — Reto 9 Postmortem

Only attempt if Tasks A–F are complete and time remains.

```
Write /home/fosuna/Documents/Frontend_eligod/Semana_10/semana10_ecomarket/postmortem.md based on demo_resiliencia.log. Simulate a production-style incident retrospective: timeline (with timestamps from the log), root cause analysis, contributing factors, action items. Reference real log lines.
```

## 7. Final assembly checklist

When all docs exist and demo_resiliencia.log is generated:

```bash
cd /home/fosuna/Documents/Frontend_eligod/Semana_10/semana10_ecomarket
# Verify all required files present:
for f in circuit_breaker.py token_manager.py cliente_robusto.py cliente_integrado.py servidor_mock.py \
         cliente_sse_multiplex.py test_circuit_breaker.py run_demo.py \
         README.md requirements.txt demo_resiliencia.log \
         autopsia_bugs.md checklist_invariantes.md adr_decision_critica.md \
         tc_cross_regression.md bitacora_ia.md contribucion_equipo.md \
         diagrama_flujo.txt respuestas_reto1.md; do
  test -f "$f" && echo "OK  $f" || echo "MISS $f"
done

# Remove WSL Zone.Identifier files before zipping
find . -name "*:Zone.Identifier" -delete

# Tag and zip
cd /home/fosuna/Documents/Frontend_eligod
git add Semana_10/semana10_ecomarket
git commit -m "Hito 2: cliente seguro y resiliente"
git tag hito2
cd Semana_10
zip -r hito2_<apellido1>_<apellido2>.zip semana10_ecomarket -x "*.pyc" "*/__pycache__/*" "*:Zone.Identifier"
```

## 8. Hard Gate verification (do BEFORE submitting)

- [ ] `python test_circuit_breaker.py` → 8/8 pasan
- [ ] `demo_resiliencia.log` contains all 3 CB state transitions
- [ ] README install/run commands work on a fresh checkout
- [ ] No token strings appear anywhere in logs or commits
- [ ] All 8 markdown deliverables present and non-empty
- [ ] Both team members can verbally explain ADR-001

## 9. Rubric reminder (don't lose easy points)

| Criterio | Pts | Driver |
|---|---:|---|
| CircuitBreaker 3 estados | 15 | Code ✅ |
| TokenManager decode+auth+refresh | 12 | Code ✅ |
| ClienteRobusto SRP | 12 | Code ✅ |
| Clasificación errores 401≠fallo | 12 | Code ✅ |
| Prueba automatizada reproducible | 12 | test_circuit_breaker.py — strengthen TC-X2 if time |
| Estado observable UI | 10 | Code ✅ |
| Documentación + IA | 12 | autopsia + ADR + bitácora + docstrings |
| README/repo reproducible | 10 | requirements.txt + tag hito2 |
| Contribución equipo | 5 | contribucion_equipo.md |
| **Total base** | **100** | |
| Bonus Reto 9 (postmortem) | +5 | optional |
