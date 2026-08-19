# Dot

A local-first autonomous AI desktop assistant powered by llama.cpp, custom ReAct loops, and multi-server MCP tool execution in a lightweight NeutralinoJS shell.

![Status](https://img.shields.io/badge/Status-Active%20Development-yellow)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)
![Inference](https://img.shields.io/badge/Inference-100%25%20Local-green)
![License](https://img.shields.io/badge/License-MIT-blue)

---

## Why Build This From Scratch?

Most "AI assistant" projects glue together LangChain, Electron, and an OpenAI key and call it a day. That stack is heavy, slow, and expensive.

I wanted to solve a different problem: **run a multi-tool ReAct agent loop against a local LLM with sub-second tool dispatch, on a laptop with 8GB VRAM, without the UI eating half my RAM before inference even starts.**

That means:
- No LangChain or LlamaIndex: The orchestration loop is ~350 lines of Python I control entirely. I know exactly what is in my context window and why.
- No Electron: The UI shell uses **NeutralinoJS** (~3MB runtime vs Electron's ~200MB). When running a quantized local model, every megabyte of RAM matters.
- No cloud inference: **llama.cpp** (`llama-server`) runs locally with full CUDA offloading. The Python backend talks to it over `localhost:11434` using an OpenAI-compatible API with zero network hops.

---

## Metrics & System Benchmarks

*Measured on an NVIDIA RTX 3070 Laptop GPU (8GB VRAM), 16GB System RAM, Windows 11.*

### Memory & Resource Overhead
| Component | Runtime Footprint | Optimization Technique |
|---|---|---|
| **Frontend Shell (NeutralinoJS)** | ~3 MB to 15 MB RAM | Native OS webview integration (no bundled Chromium) |
| **Electron Baseline (Comparison)** | ~180 MB to 300 MB RAM | Standard multi-process Chromium shell |
| **KV Cache Allocation** | Quantized 8-bit (`q8_0`) | Quantized key-value cache (`-ctk q8_0 -ctv q8_0`) saving ~50% context VRAM |
| **FastAPI Orchestrator** | ~45 MB RAM | Async Uvicorn daemon with shared lifespan MCP client pool |
| **Model Context Limit** | 4096 / 8192 tokens | Context window clamped per hardware tier via setup wizard |

### Inference & Token Throughput
| Model Tier | Quantization | Context Window | Target VRAM Usage | Offload Target |
|---|---|---|---|---|
| **Gemma 4 (2B)** | Q4_0 QAT | 8,192 tokens | ~2.2 GB | 100% GPU Offload (`-ngl 99`) |
| **Gemma 4 (4B)** | Q4_0 QAT | 8,192 tokens | ~4.6 GB | 100% GPU Offload (`-ngl 99`) |
| **Gemma 4 (12B)** | Q4_0 QAT | 4,096 tokens | ~7.8 GB | Partial GPU Offload (`-ngl 25`) + System RAM fallback |

### Routing & Agent Execution
| Execution Pipeline | Latency / Metric | Method / Detail |
|---|---|---|
| **Direct Command Bypass** | < 50ms total dispatch | `all-MiniLM-L6-v2` embedding cosine similarity (> 0.3 threshold, < 6 words) |
| **ReAct Loop Step Budget** | Max 8 iterations | Hard ceiling preventing runaway model reasoning chains |
| **Context Compression Trigger** | 6,000 running tokens | Dynamic summarization of unpinned historical message turns |
| **Tool Deduplication** | Hash-based exact matching | Signature hash comparison prevents re-executing identical tool args |
| **MCP Server Lifecycle** | 1 startup initialization | Persistent servers across lifespan (zero per-request process spawns) |

---

---

## Stack

| Layer | Choice | Why |
|---|---|---|
| **Frontend Shell** | NeutralinoJS | ~3MB runtime. Uses the OS webview instead of bundling Chromium. The LLM needs the RAM, not the UI. |
| **Frontend Framework** | React 19 + Vite + Tailwind | Fast HMR during development. Renders markdown responses with syntax highlighting. |
| **Backend Server** | Python FastAPI + Uvicorn | Async WebSocket server. Manages agent lifecycle, session memory, and MCP client connections. |
| **Agent Loop** | Custom ReAct (Pydantic-validated) | Hand-rolled Reason+Act loop with structured JSON output, sliding-window context compression, anti-loop circuit breakers, and guardrail enforcement. |
| **Tool Protocol** | Model Context Protocol (MCP) | Multi-server MCP client via `fastmcp`. Tool schemas are indexed in ChromaDB for vector-similarity discovery at runtime. |
| **Inference** | llama.cpp (`llama-server`) | Local GGUF inference with OpenAI-compatible API. Structured JSON output via `json_schema` response format. |
| **Models** | Gemma 4 (2B / 4B / 12B QAT Q4_0) | Multimodal local model. The setup wizard auto-probes GPU VRAM to pick the right tier. |
| **Intent Routing** | `all-MiniLM-L6-v2` | Cosine similarity against anchor phrases. Simple commands bypass the LLM entirely for direct execution in <50ms. |
| **Wake Word** | OpenWakeWord + custom ONNX model | Always-on mic listener on a daemon thread. Triggers `faster-whisper` STT on detection. |
| **Vision** | Gemma 4 mmproj + EasyOCR | Multimodal projector for screenshot understanding. OCR for pixel-coordinate text location on screen. |
| **Memory** | ChromaDB + Session JSONL | Tool schemas vectorized for discovery. Session turns stored and embedded on disconnect. |

---

## How the Agent Loop Actually Works

The core of Dot is a hand-rolled [ReAct loop](dum-e/src/dot/core/engine.py) with no bloated framework dependencies:

1. **User query** enters via WebSocket, and the intent router classifies it.
2. If it is a simple command (cosine similarity > 0.3, < 6 words), it **skips the LLM entirely** and routes to `AppOpener` for direct OS execution.
3. Otherwise, the query enters the **ReAct loop** (maximum 8 steps):
   - LLM outputs a `Pydantic`-validated JSON action (`Tool`, `Tool-exec`, or `Final`).
   - `Tool`: vector search ChromaDB for matching MCP tool schemas.
   - `Tool-exec`: dispatch to the appropriate MCP server (GitHub, Browser, or OS).
   - `Final`: stream the final structured answer back over the WebSocket.
4. **Anti-loop circuit breakers** track execution signatures. If the agent tries to call the same tool with identical arguments twice, it triggers a forced exit with a fallback response.
5. **Context compression** activates when the running prompt exceeds 6,000 tokens, summarizing unpinned turns to keep context lean.
6. On WebSocket disconnect, the session is **embedded into ChromaDB** for persistent memory.

---

## Hardest Challenges Solved

### Keeping a 2B model on the rails
Small parameter models can hallucinate tool names, output malformed JSON, and enter execution loops. The agent loop handles this with multiple layers of defense:
- **Pydantic validation**: A `model_validator` intercepts and remaps malformed keys before schema parsing fails.
- **Self-healing actions**: If the model emits `action: "Tool"` but includes a payload `name` field, the engine silently normalizes it to `Tool-exec`.
- **Signature-based deduplication**: Every tool execution receives an argument hash. Duplicates trigger an immediate exit instead of infinite retries.
- **Pre-execution guardrails**: Placeholder detection (such as `<username>`) blocks raw command execution before reaching MCP tools.

### MCP multi-server lifecycle management
All MCP servers (GitHub stdio, Browser automation via Playwright, OS automation) boot once during FastAPI's `lifespan` context manager and persist for the entire app session. Every WebSocket connection shares the active client, avoiding per-request server initialization delays.

---

## Project Structure

```text
Dot/
├── test/
│   ├── setup.py               # Rig Analyzer + Setup Wizard (CustomTkinter)
│   ├── appConfig.json          # Model tiers, launcher templates, active settings
│   └── start_dot.bat           # Generated launcher script
│
└── dum-e/                      # Main application
    ├── server.py               # FastAPI/Uvicorn WebSocket server + MCP lifespan
    ├── neutralino.config.json  # NeutralinoJS shell configuration
    ├── package.json            # React 19 + Vite + Tailwind frontend
    │
    └── src/dot/
        ├── core/
        │   ├── engine.py       # ReAct agent loop
        │   ├── router.py       # Intent classification (MiniLM cosine sim)
        │   ├── llm.py          # llama.cpp client wrapper
        │   ├── prompts.py      # System prompt + tool context injection
        │   ├── guardrails.py   # Placeholder detection, action validation
        │   └── utils.py        # JSON extraction, observation trimming, context compression
        │
        ├── mcp_files/
        │   ├── mcpClient.py    # Multi-server MCP client + sampling handler
        │   ├── registry.py     # Tool sync pipeline (MCP to ChromaDB)
        │   └── client_core.py  # Server connection + tool schema fetching
        │
        ├── automation_mcp/
        │   ├── os_automation.py       # FastMCP server: process mgmt, screenshots, OCR, input
        │   └── browser_automation.py  # FastMCP server: Playwright browser control, navigation
        │
        ├── memory/
        │   ├── vector_store.py        # ChromaDB tool discovery
        │   ├── session_memory/        # Session turn storage + sliding window manager
        │   └── collections/           # ChromaDB collection managers (tools, sessions)
        │
        ├── voiceModel/
        │   ├── voiceListener.py       # OpenWakeWord daemon + audio capture
        │   └── voiceProcess.py        # faster-whisper STT transcription
        │
        ├── sandbox/                   # [WIP] Docker command execution sandbox
        │   ├── Dockerfile
        │   └── container_running.py
        │
        └── config/
            ├── mcp_servers.json       # MCP server registry
            └── allowed_apps.yml       # OS automation process whitelist
```

---

## Pending / Exploring

Scaffolded components currently in active development:

| Area | Status | Target Implementation |
|---|---|---|
| **Docker Sandbox** | Scaffolded (`Dockerfile` + module setup) | Isolated container for agent shell command execution using the Docker Python SDK with volume-mounted workspaces and hard timeouts. |
| **Hybrid Search RAG** | Partially built (ChromaDB session storage active) | Expanding retrieval by combining vector cosine similarity with keyword/BM25 search for better recall of past session contexts. |
| **Cloud Fallback Routing** | Config-level schema defined | Implementing automated retry failover (local execution error triggering optional cloud API fallback). |

---

*Built on an RTX 3070 laptop. Designed to run on yours too.*