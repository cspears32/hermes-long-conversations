# Hermes Long Conversations

Preserve conversation state across session boundaries without degradation from lossy compression.

Monitors token usage, extracts structured handoff briefs before context limits hit, and injects state into fresh continuation sessions with lineage tracking.

---

## How It Works

```text
Standard Compaction (Lossy):
[Turn 1 ... 50] (16k tokens) ──► [Context Full] ──► [Lossy Summary] ──► Hallucinations / Lost State

With Long Conversations (Preserved):
[Session A] (16k tokens) ──► [Auto-Handoff Brief] ──► [Session B (/new)] (~250 tokens, 100% state)
                                  │
                                  └──► WIP / Modified Files / Decisions / Next Steps
```

---

## Features

- **Token Monitoring:** Triggers alerts or auto-handoffs at context threshold (default 80%).
- **Structured Briefs:** Captures goals, active files, decisions, dead ends, and next steps.
- **Clean Rollovers:** Fresh continuation sessions start with ~200 tokens of focused context.
- **Lineage DAG:** Traces session parentage in `lineage.json`.

---

## Installation

```bash
git clone https://github.com/cspears32/hermes-long-conversations.git ~/.hermes/plugins/long-conversations
hermes plugins enable long-conversations
```

---

## Commands & Tools

- `/long-conv handoff` (`long_conv_handoff`): Generate brief and stage continuation.
- `/long-conv list` (`long_conv_list`): List saved session briefs.
- `/long-conv load <id>` (`long_conv_load`): Load brief by session ID.
- `/long-conv config get` (`long_conv_config_get`): View active configuration.
- `/long-conv config set <key> <val>` (`long_conv_config_set`): Update configuration.

---

## Configuration

`~/.hermes/long-conversations/config.yaml`:

```yaml
threshold_ratio: 0.80     # Context utilization threshold (0.0–1.0)
aggressive_mode: false    # Auto-generate handoff on threshold
prune_days: 14            # Stale brief retention window
```

---

## Acknowledgments & Prior Art

Inspired by and adapted from the auto-handoff architecture pioneered by [`claude-auto-handoff`](https://github.com/alexknowshtml/claude-auto-handoff) by Alex MacCaw, re-engineered for the Hermes Agent plugin ecosystem and local model constraints.
