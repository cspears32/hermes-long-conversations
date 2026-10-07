# Hermes Long Conversations

> Keep conversations going across session boundaries without degradation from lossy context compression.

A lightweight Hermes Agent plugin that monitors token usage, generates structured handoff briefs before context limits hit, and transfers state cleanly into fresh sessions with lineage tracking.

---

## Is this for you?

- **Context limits bottleneck your work:** You hit token ceilings in long-running coding, research, or planning sessions.
- **Compaction degrades coherence:** Default summarization drops critical decisions, dead ends, or active file state.
- **Local model user:** You run 4k–32k context windows on local llama.cpp / vLLM / Ollama backends where context space is precious.
- **Crash / session recovery:** You want to resurrect lost context from an interrupted or crashed session.

---

## How It Works

1. **Token Monitor:** Watches token budget on each turn (`pre_llm_call`).
2. **Handoff Generation:** When threshold (default: 80%) is reached or on demand, extracts an operational brief:
   - Topic & core goals
   - Work in progress & next steps
   - Decisions made & rejected dead ends
   - Touched/active files & key constraints
3. **Clean Session Rollover:** Spawns a fresh session with ~200 prompt tokens instead of an unwieldy 100k history, injecting the structured brief into turn one.
4. **Lineage DAG:** Maintains parent $\rightarrow$ child links (`lineage.json`) so you can trace history back through Hermes's native `session_search`.

---

## Quick Start

### Installation

Clone into your Hermes plugins directory:

```bash
git clone https://github.com/cspears32/hermes-long-conversations.git ~/.hermes/plugins/long-conversations
hermes plugins enable long-conversations
```

### Usage

```bash
# Generate a handoff brief and prepare continuation
/long-conv handoff

# List available briefs across sessions
/long-conv list

# Load a specific ancestor session brief into current turn
/long-conv load <session_id>

# View or update configuration
/long-conv config get
/long-conv config set threshold_ratio 0.75
```

---

## Configuration

In `~/.hermes/long-conversations/config.yaml`:

```yaml
threshold_ratio: 0.80     # Trigger alert at 80% context utilization
aggressive_mode: false    # If true, auto-handoffs without manual confirmation
prune_days: 14            # Auto-prune local brief files older than 14 days
```

---

## Architecture at a Glance

```
Session A (Tokens at 80%)
  │
  ├──> [pre_llm_call monitor]
  ├──> Auto-extracts brief -> ~/.hermes/long-conversations/briefs/<session_a>.json
  └──> Updates lineage.json (A -> B)
          │
          ▼
Session B (Fresh context: ~228 tokens)
  └──> [on_session_start hook] Injects brief -> Zero context bloat, 100% decision retention
```
