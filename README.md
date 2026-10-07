# Hermes Long Conversations

Preserve conversation state across session boundaries without degradation from lossy compression.

Monitors token usage, extracts structured handoff briefs before context limits hit, and injects state into fresh continuation sessions with lineage tracking.

---

## Why Use This: Standard Compaction vs. Long Conversations

| Dimension | Standard Compaction | Long Conversations Plugin |
| :--- | :--- | :--- |
| **Trigger Timing** | **Reactive:** Triggers after context is exhausted or hitting provider hard limits. | **Proactive:** `pre_llm_call` hook intercepts at a configurable watermark (e.g. 80%) before degradation. |
| **What is Saved** | **Conversation Dialogue:** Compresses chat transcripts (user/assistant banter, tool output logs). | **Execution State:** Extracts only operational facts (active files, key decisions, negative constraints, next step). |
| **Context Overhead** | **High Bloat (3k–6k+ tokens):** Multi-paragraph summaries + residual baggage linger in active memory. | **Zero Bloat (~250 tokens):** Fresh session starts with 99% context headroom available for execution. |
| **Attention & Drift** | **High Degradation:** Outdated tool logs and discarded paths distract attention heads. | **Zero Context Poisoning:** Clean slate eliminates transcript drift and prompt-length penalties. |
| **Failure Traps** | **Repeats Mistakes:** Free-form summaries rarely record what failed, leading to looped errors. | **Explicit Dead-Ends:** Dedicated `dead_ends` field prevents re-trying invalidated approaches. |
| **Session Provenance** | **Fragmented:** Starting `/new` breaks session continuity and loses history. | **Lineage DAG:** Auto-links parent $\rightarrow$ child sessions in `lineage.json` with inspectable history. |
| **Local Model Fit** | **Poor:** 3B–8B local LLMs struggle with bloated summaries and long attention spans. | **Optimized:** Tiny ~250-token payload fits effortlessly into 4k–16k local context windows. |

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
