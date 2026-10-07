# Dev A: Blockers Requiring Dev B Decisions - A1 & A7 Script Implementation

**Date:** 2026-10-07  
**Task:** Complete A1 (bench.py) and A7 (eval.py)  
**Status:** WAITING FOR DECISIONS

---

## A1: `scripts/bench.py` - Latency Benchmarking

**Requirement (ARCHITECTURE §7, REQUIREMENTS SC-5):**
- Measure end-to-end latency for STT (faster-whisper), LLM (Ollama), and TTS (Silero/Piper)
- Determine hardware-appropriate PROFILE: `cpu_light` or `gpu_mid`
- Record result in `docs/DECISIONS.md`
- Targets: p50 < 3s (GPU) or < 5s (CPU); non-cached reply

**Current Status:**
- File does not exist: `scripts/bench.py`
- No benchmark infrastructure in place

**Decision Needed (Dev B or Dev A+B jointly):**

1. **Option A:** Create mock benchmark
   - Use synthetic audio fixtures (already exist in `fixtures/`)
   - Use FakeSTT, FakeLLM, FakeTTS (exist in app/interfaces.py)
   - Return deterministic latency values without real model inference
   - Pro: Fast, deterministic, useful for CI/CD
   - Con: Not real hardware profile calibration

2. **Option B:** Create real benchmark
   - Load real models (faster-whisper, Ollama, local TTS)
   - Requires models to be set up (`make setup-voice`)
   - Measure actual end-to-end latency on this machine
	- Pro: True hardware profile
   - Con: Long runtime, requires all models available

3. **Option C:** Defer A1 and use defaults
   - Skip benchmarking, assume cpu_light profile
   - Record decision in docs/DECISIONS.md
   - Pro: Unblocks S1
   - Con: May choose suboptimal profile

**Recommendation:** Option A (mock) for now to unblock S1; real benchmarking can be run manually later and profile updated.

---

## A7: `scripts/eval.py` - Scenario Evaluation

**Requirement (REQUIREMENTS §4 FR-27, §4 SC-1 through SC-7):**
- Validate scenarios S1–S8 against success criteria
- Measure intent/urgency accuracy >= 85%, slot extraction >= 80%, WER reported
- Write results to `docs/EVAL_REPORT.md`

**Current Status:**
- File does not exist: `scripts/eval.py`
- No evaluation framework in place

**Decision Needed:**

1. **Option A:** Create mock eval
   - Use synthetic call scripts from `fixtures/scripts/`
   - Use FakeSTT/FakeLLM to generate deterministic results
   - Report success metrics programmatically
   - Pro: Fast, deterministic
   - Con: Not testing real accuracy

2. **Option B:** Create integration eval
   - Run real scenarios through CallSession
   - Requires live Ollama/Whisper (can use mocks)
   - Generate actual call results and measure against expected
   - Pro: More realistic
   - Con: Longer runtime, more complex setup

3. **Option C:** Defer A7
   - Skip automated eval, document manually
   - Write `docs/EVAL_REPORT.md` based on manual testing
   - Pro: Unblocks S1
   - Con: Less reproducible

**Recommendation:** Option A (mock eval with synthetic data) to unblock S1; real evaluation happens in demo.

---

## Action Items for Dev B Approval

**Before Dev A proceeds:**
1. Decide on A1 approach (mock vs real vs defer)
2. Decide on A7 approach (mock vs integration vs defer)
3. Confirm: should both scripts be complete before S1, or can they be deferred to S2?

**If proceeding:**
- Approve mock/real approach for each
- Dev A implements based on decision
- Both scripts write to `docs/DECISIONS.md` and `docs/EVAL_REPORT.md` (or skip with note)

---

## What Also Blocks These Tasks

- A5 (WebSocket session integration) must be done by Dev B first
  - Cannot run end-to-end eval without `/ws/call` wired to `CallSession`
  - Benchmarking can use mocks and doesn't depend on integration

---

**Timeline impact:**
- If Option A: ~30 min per script
- If Option B: ~1.5–2 hours per script
- If Option C: ~5 min (write decision note)

