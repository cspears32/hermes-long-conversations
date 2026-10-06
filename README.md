# Long Conversations — Product One-Pager

A lightweight Hermes general plugin that enables persistent, structured long-term conversations across session boundaries regardless of model backend, context limits, or deployment environment.

---

## 1. Problem Statement

Hermes compresses context when token budgets are exceeded — degrading conversation coherence and losing critical operational context. There is no pre-compression handoff mechanism, no structured session summary for continuation, and no clean way to resume a session after unexpected interruption. Local LLM users and those running constrained context models (4k/8k/32k) are hit hardest, where conversation depth is constrained by token limits.

## 2. Vision & Pitch

> **"Converse forever."** — Keep conversations going across session boundaries without degradation from lossy context compression.

A lean background plugin that monitors active session token usage, generates structured handoff briefs before compression triggers or upon session termination, and transitions context into a fresh session. Not a project tracker. Not Kanban. Focused purely on conversation continuity.

## 3. Core Principles

- **User-Controlled Handoffs via Slash Commands**: The plugin detects threshold crossing and alerts the user with actionable commands (`/long-conv handoff`). An optional aggressive mode auto-transitions.
- **Lineage Tracked**: Each brief records its source session ID in a persistent lineage graph (`lineage.json`), allowing traversal back to full transcripts via Hermes's built-in `session_search`.
- **Manual Override & Crash Recovery**: If an agent crashes or context is lost, users can generate a brief from a dead session transcript or resume from any saved brief.
- **Session Resilience**: The conversation thread outlives individual process or session lifespans.
- **Lean, Bounded Briefs**: Briefs follow a strict, bounded JSON schema to prevent context explosion.
- **Pruning by Design**: Local brief files and metadata on disk are pruned after N days (user-configurable). Canonical Hermes session records in `state.db` are never deleted.
- **Model & Backend Agnostic**: Operates at the Hermes session and prompt layer.

## 4. User Flows

### Primary Path: Threshold Handoff
1. Plugin monitors token utilization during active turns via `pre_llm_call`.
2. At threshold (default: 80% of model context limit), the plugin generates a structured handoff brief file under `$HERMES_HOME/long-conversations/briefs/{session_id}.json`.
3. The plugin posts an in-session notification: `Handoff brief ready. Run /long-conv handoff to continue in a fresh session.`
4. User runs `/long-conv handoff` (or auto-triggers if `aggressive_mode: true`).
5. A new session starts; `on_session_start` detects the pending brief, injects the handoff context into the initial turn, and records the lineage linkage.

### Manual Recovery Scenarios
| Scenario | User Action | Result |
|---|---|---|
| **Brief exists, active session** | `/long-conv handoff` | Generates/refreshes brief and spawns continuation session |
| **Brief exists, previous session closed** | `/long-conv load <session_id>` | Starts new session initialized with the target brief |
| **Session crashed / unbriefed** | `/long-conv recover <session_id>` | Reads transcript from `state.db`, synthesizes handoff brief, and prepares continuation |

## 5. Key Concepts

### Handoff Brief
A bounded, machine-readable JSON structure capturing:
- `source_session_id`: Parent session ID
- `topic`: Conversation core topic/objective
- `work_in_progress`: Current active task state
- `decisions_made`: Key decisions and architectural choices
- `active_state_files`: Files touched or referenced
- `key_assumptions`: Hypotheses and constraints
- `open_questions`: Unresolved points
- `dead_ends`: Rejected paths
- `next_step`: Concrete immediate next action

### Storage & Retention
Stored on disk under `$HERMES_HOME/long-conversations/`:
- `briefs/{session_id}.json`: Structured brief files.
- `lineage.json`: Session DAG mapping children to parent sessions.
- `config.yaml`: Plugin settings (threshold, pruning interval, aggressive toggle).

Pruning purges local brief files older than N days (default: 14 days) without mutating Hermes `state.db`.

## 6. Out of Scope
- Replacing Hermes built-in `ContextCompressor` (works alongside it as a pre-compression handoff).
- Multi-agent orchestration or task routing (handled by Kanban / `delegate_task`).
- Ephemeral in-memory only message channels (storage uses standard persistent files).
- Custom desktop GUI button injection (interacts via native slash commands and tools).

## 7. Status & Next Steps
- **Status**: Planning complete. All architectural issues from review resolved.
- **Immediate Next Step**: 2-day prototype testing to validate `pre_llm_call` token monitoring and `on_session_start` context injection.
