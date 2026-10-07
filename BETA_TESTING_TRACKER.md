# Beta Testing & Multi-Session Validation Tracker

**Target Version:** `0.1.0-beta`  
**Branch:** `feat/beta-testing-and-multi-session`  
**Purpose:** Prototype validation, multi-session continuation stress testing, local (llama.cpp) vs cloud model refinement, and ephemeral diagnostic tracking.

---

## 1. Multi-Session Support & Lineage Architecture

When multiple sessions run concurrently or branch off the same ancestor:
- **Session Identification:** Briefs are indexed by `source_session_id`.
- **Branching Lineage:** The DAG stores `child_session_id -> parent_session_id` relationships in `lineage.json`.
- **Targeted Resumption:** Users can select specific branch continuation using `/long-conv load <session_id>` or allow sequential handoff.
- **Collision Avoidance:** Multiple parallel sessions writing handoffs do not overwrite each other; each receives a unique brief file (`briefs/<session_id>.json`).

---

## 2. Beta Testing Matrix

| Scenario | Model Type | Expected Behavior | Status |
| :--- | :--- | :--- | :--- |
| **Basic Handoff** | Cloud (Gemini/Claude) | Saves brief, next session injects brief cleanly | [x] Verified |
| **Local Model Handoff** | Local (llama.cpp 3B/8B) | Compact prompt parsing, avoids prompt blowing | [ ] In Progress |
| **Multi-Session Branching** | Any | Session A spawns Session B & C independently | [ ] In Progress |
| **Token Monitor Trigger** | Local & Cloud | Correctly detects 80% context threshold | [x] Verified |
| **Stale Pruning** | Local Storage | Briefs older than 14 days cleaned automatically | [x] Verified |
| **A/B Durability Eval** | Cloud / Local | 100% factual retention vs 0% control across fresh session start | [x] Verified |

---

## 4. A/B Durability Evaluation Scorecard

Benchmarked across multiple conversation domains (Cloud Infra, ESP32 Firmware, FinTech Pipeline) via `eval_durability_multi_domain.py`:

| Metric | Test Arm (`long-conversations`) | Control Arm (Clean Session) |
| :--- | :--- | :--- |
| **Factual Retention Rate** | **15/15 (100%)** | **0/15 (0%)** |
| **Context Bloat Reduction** | **-98.7%** (~22,100 $\rightarrow$ ~275 tokens) | 0.0% (No context) |
| **Start Token Footprint** | ~275 tokens | ~14 tokens |
| **Lineage Traceability** | 100% Verified (`parent -> child` DAG) | None |
| **Handoff Serialization Latency** | 0.20ms avg | N/A |
| **Key Decision / Dead End Retention** | 100% | 0% |


---

## 3. Ephemeral Beta Telemetry (Opt-In / Local Only)

To prevent polluting the public upstream code while collecting real diagnostic logs:
- **Flag-Gated:** Enabled only when `HERMES_LONG_CONV_BETA_LOG=1`.
- **Location:** Writes locally to `~/.hermes/long-conversations/beta_events.jsonl`.
- **Captured Metrics:**
  - Token counts at handoff (`last_total_tokens`, `threshold_tokens`)
  - Latency of brief serialization & context injection
  - Model provider slug (distinguish local vs cloud engine behavior)
  - Validation outcome of handoff deserialization
- **Privacy:** No raw prompt or chat body is logged; only structural metadata.
