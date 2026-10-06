# Long Conversations — Technical Architecture One-Pager

## 1. Architectural Role & Extension Model

`long-conversations` is implemented as a standard **Hermes General Plugin** (`~/.hermes/plugins/long-conversations/` or standalone catalog repository).

### Critical Design Adjustments vs Prior Drafts
1. **No `request_only_messages`**: Fabricated API removed. Briefs are stored as structured JSON files under `$HERMES_HOME/long-conversations/briefs/` and injected into the first user turn of the new session or queried via tools.
2. **No `ContextEngine` ABC replacement**: Plugin does **not** replace `ContextCompressor`. Instead, it reads the active engine's public token tracking metrics (`last_total_tokens`, `threshold_tokens`, `context_length`) in `pre_llm_call`.
3. **No fabricated hook signatures**: Uses standard `on_session_start(ctx)` and `on_session_end(ctx)`. Session continuation detection is file-driven via a pending brief marker on disk.
4. **Slash Commands over GUI Buttons**: Plugin interactions use native slash commands (`/long-conv handoff`, `/long-conv list`, `/long-conv load`, `/long-conv recover`) and tool definitions rather than non-existent desktop button hooks.
5. **Persistent Storage over Ephemeral Rolling Windows**: Uses standard file-based brief storage pruned by age (N days) rather than complex rolling multi-session windows.

---

## 2. Component Architecture

```
┌────────────────────────────────────────────────────────┐
│                      Hermes Core                       │
│  (CLI / Gateway / Desktop Runtime - Hooks & Tools)      │
└──────────────────────────┬─────────────────────────────┘
                           │
       ┌───────────────────┴───────────────────┐
       ▼                                       ▼
┌───────────────────────────────┐   ┌─────────────────────────┐
│     Plugin Lifecycle Hooks    │   │  Registered Tools & CLI │
│                               │   │                         │
│  • pre_llm_call (Monitor)     │   │  • /long-conv handoff   │
│  • on_session_start (Inject)  │   │  • /long-conv load <id> │
│  • on_session_end (Crash/Rec) │   │  • /long-conv recover   │
│  • session:compress (Capture) │   │  • /long-conv list      │
└──────────────┬────────────────┘   └────────────┬────────────┘
               │                                 │
               └────────────────┬────────────────┘
                                ▼
         ┌──────────────────────────────────────────────┐
         │         Long Conversations Manager           │
         │  (Token Monitor, Brief Generator, Lineage)   │
         └──────────────────────┬───────────────────────┘
                                ▼
         ┌──────────────────────────────────────────────┐
         │ File Storage ($HERMES_HOME/long-conversations)│
         │  ├── briefs/{session_id}.json                │
         │  ├── lineage.json                            │
         │  └── config.yaml                             │
         └──────────────────────────────────────────────┘
```

---

## 3. Hook & Event Integration Contract

### Entry Point (`__init__.py`)
```python
def register(ctx):
    ctx.register_hook("pre_llm_call", handle_pre_llm_call)
    ctx.register_hook("on_session_start", handle_session_start)
    ctx.register_hook("on_session_end", handle_session_end)
    
    ctx.register_tool(
        name="long_conv_handoff",
        description="Generate a handoff brief and prepare a continuation session.",
        handler=tool_handoff,
        parameters=HANDOFF_PARAM_SCHEMA,
    )
    ctx.register_tool(
        name="long_conv_load",
        description="Load an existing handoff brief by session ID.",
        handler=tool_load,
        parameters=LOAD_PARAM_SCHEMA,
    )
    ctx.register_tool(
        name="long_conv_recover",
        description="Synthesize a handoff brief from a dead/crashed session transcript.",
        handler=tool_recover,
        parameters=RECOVER_PARAM_SCHEMA,
    )
```

### Hook Behaviors
- **`pre_llm_call(ctx)`**: Inspects current active engine token usage. If `current_tokens >= (context_length * threshold_ratio)` (default 0.80):
  1. Compiles structured brief via prompt/summary helper.
  2. Writes `$HERMES_HOME/long-conversations/briefs/{session_id}.json`.
  3. Writes `$HERMES_HOME/long-conversations/.pending_continuation`.
  4. Emits user notification recommending `/long-conv handoff` (or auto-triggers in aggressive mode).
- **`on_session_start(ctx)`**: Checks for `$HERMES_HOME/long-conversations/.pending_continuation`. If found:
  1. Reads target brief file.
  2. Injects brief context into initial prompt / turn state.
  3. Updates `$HERMES_HOME/long-conversations/lineage.json` (`child_session_id -> parent_session_id`).
  4. Clears `.pending_continuation`.
- **`on_session_end(ctx)`**: Checks if the session terminated with dirty context and without a handoff. If unbriefed, persists fallback recovery brief to allow seamless recovery.
- **`session:compress` (Secondary Listener)**: Catches compression events as telemetry / fallback to ensure no session context is permanently lost without a brief.

---

## 4. Data Structures & File Storage

### Storage Directory Layout
```
$HERMES_HOME/long-conversations/
├── config.yaml
├── lineage.json
└── briefs/
    ├── 20261005_120000_abc123.json
    └── 20261005_143000_def456.json
```

### Handoff Brief Schema (`briefs/{session_id}.json`)
```json
{
  "version": "1.0",
  "source_session_id": "20261005_120000_abc123",
  "timestamp": 1791258000.0,
  "topic": "Refactoring authentication middleware",
  "work_in_progress": "Migrating bearer token verification to JWT validator",
  "decisions_made": [
    "Use PyJWT with RS256",
    "Keep token revocation list in local SQLite"
  ],
  "active_state_files": [
    "auth/jwt.py",
    "tests/test_auth.py"
  ],
  "key_assumptions": [
    "Public keys available via JWKS endpoint"
  ],
  "open_questions": [
    "Token expiration TTL duration"
  ],
  "dead_ends": [
    "Symmetric HMAC shared secret approach rejected for security compliance"
  ],
  "next_step": "Implement token refresh test cases in test_auth.py"
}
```

### Lineage Graph (`lineage.json`)
```json
{
  "20261005_143000_def456": {
    "parent_session_id": "20261005_120000_abc123",
    "timestamp": 1791258000.0,
    "topic": "Refactoring authentication middleware"
  }
}
```

---

## 5. Plugin Catalog Submission Manifest

```yaml
name: long-conversations
repo: https://github.com/cspears32/hermes-long-conversations
sha: 0000000000000000000000000000000000000000 # To be pinned to exact 40-hex commit SHA
description: Persistent long-term conversations across session boundaries via structured handoff briefs.
maintainer: cspears32
tier: community
category: tools
requires_hermes: ">=0.19"
capabilities:
  hooks:
    - pre_llm_call
    - on_session_start
    - on_session_end
  tools:
    - long_conv_handoff
    - long_conv_load
    - long_conv_recover
    - long_conv_list
  cli_commands:
    - long-conv
```

---

## 6. Prototype Test Plan (2-Day Scope)

| Day | Focus | Validation Target |
|---|---|---|
| **Day 1** | **Hook Integration & Token Detection** | Verify `pre_llm_call` reads token counts across prompt turns and reliably triggers brief generation at 80% threshold without altering core agent flow. |
| **Day 2** | **Session Transition & Context Injection** | Test `/long-conv handoff` spawning a fresh session, `on_session_start` picking up `.pending_continuation`, verifying brief injection quality and lineage linkage in `lineage.json`. |
