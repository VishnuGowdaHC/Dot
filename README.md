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
- **No LangChain or LlamaIndex**: The orchestration loop is ~450 lines of Python I control entirely. I know exactly what is in my context window, how tokens are budgeted, and why.
- **No Electron**: The UI shell uses **NeutralinoJS** (~3MB runtime vs Electron's ~200MB). When running a quantized local model, every megabyte of RAM matters.
- **No cloud inference**: **llama.cpp** (`llama-server`) runs locally with full CUDA offloading. The Python backend talks to it over `localhost:11434` using an OpenAI-compatible API with zero network hops.

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
| **Direct Command Bypass** | < 50ms total dispatch | `all-MiniLM-L6-v2` embedding cosine similarity (> 0.45 threshold) |
| **ReAct Loop Step Budget** | Max 8 iterations | Hard ceiling preventing runaway model reasoning chains |
| **Context Compression Trigger** | 3,500 running tokens | Dynamic summarization of unpinned historical message turns |
| **Observation Token Ceiling** | 450 tokens / observation | Compact, high-density structured trimming preventing VRAM spikes |
| **Tool Deduplication** | State-aware signature hashing | Distinguishes inspection tools from state-changing mutations |
| **MCP Server Lifecycle** | 1 startup initialization | Persistent servers across lifespan (zero per-request process spawns) |

---

## Stack

| Layer | Choice | Why |
|---|---|---|
| **Frontend Shell** | NeutralinoJS | ~3MB runtime. Uses the native OS webview instead of bundling Chromium. The LLM needs the RAM, not the UI. |
| **Frontend Framework** | React 19 + Vite + Tailwind | Fast HMR during development. Renders markdown responses with streaming token animations. |
| **Backend Server** | Python FastAPI + Uvicorn | Async WebSocket server. Manages agent lifecycle, session memory, and MCP client connections. |
| **Agent Loop** | Custom ReAct (Pydantic-validated) | Hand-rolled Reason+Act loop with structured JSON output, sliding-window context compression, state-aware anti-loop circuit breakers, and guardrail enforcement. |
| **Tool Protocol** | Model Context Protocol (MCP) | Multi-server MCP client via `fastmcp`. Tool schemas are indexed in ChromaDB for vector-similarity discovery at runtime. |
| **Inference** | llama.cpp (`llama-server`) | Local GGUF inference with OpenAI-compatible API. Structured JSON output via `json_schema` response format. |
| **Models** | Gemma 4 (2B / 4B / 12B QAT Q4_0) | Multimodal local model. The setup wizard auto-probes GPU VRAM to pick the right tier. |
| **Intent Routing** | `all-MiniLM-L6-v2` | Cosine similarity against anchor phrases. Simple desktop commands bypass the LLM entirely for direct execution in <50ms. |
| **Voice Interaction** | Hold-Key / Global Hotkey Listener | Low-latency audio capture on a daemon thread. Triggers Whisper STT on release and streams audio state to UI. |
| **Vision** | Gemma 4 mmproj + EasyOCR | Multimodal projector for screenshot understanding. OCR for pixel-coordinate text location on screen. |
| **Memory** | ChromaDB + Session JSONL | Tool schemas vectorized for discovery. Session turns stored and embedded on disconnect. |

---

## How the Agent Loop Actually Works

The core of Dot is a hand-rolled [ReAct loop](dum-e/src/dot/core/engine.py) with no bloated framework dependencies:

1. **User query** enters via WebSocket, and the semantic intent router classifies it.
2. If it matches desktop app-launch anchors (cosine similarity $\ge$ 0.45), it **skips the LLM entirely** and routes to `routeAppOpener` for direct OS execution in <50ms.
3. Otherwise, the query enters the **ReAct loop** (maximum 8 steps):
   - LLM outputs a `Pydantic`-validated JSON action (`Tool`, `Tool-exec`, or `Final`).
   - `Tool`: vector search ChromaDB for matching MCP tool schemas (on-demand discovery for GitHub).
   - `Tool-exec`: dispatch to the appropriate MCP server (GitHub, Browser, or OS).
   - `Final`: stream the final structured answer token-by-token back over the WebSocket.
4. **State-Aware Anti-Loop Circuit Breaker**:
   - Distinguishes **Inspection Tools** (`browser_extract_text`, `browser_snapshot`, `os_take_screenshot`) from **State-Changing Tools** (`browser_ai_background_load_page`, `browser_search_web`, `browser_click`, etc.).
   - When the agent navigates or interacts, inspection signatures are cleared, allowing full multi-page comparison workflows without false-positive loop triggers.
   - Immediate consecutive duplicates receive an actionable guidance strike; if the circuit breaker trips, it **forces a final LLM synthesis** over collected observations rather than failing.
5. **Token Budget & History Compression**:
   - When running prompt tokens exceed **3,500 tokens**, older unpinned turns are automatically summarized to prevent local GPU VRAM / KV cache allocation crashes.
   - Observation outputs are capped at **450 tokens** to preserve dense, actionable context.
6. **Persistence**:
   - On WebSocket disconnect, the session is embedded into **ChromaDB** for persistent cross-session memory.

---

## Hardest Challenges Solved

### 1. State-Aware Anti-Loop & Multi-Page Browsing
Small local models easily get caught in loops, but naive deduplication breaks multi-page research. When an agent reads Article A, navigates to Article B, and attempts to extract text with empty arguments, standard hash deduplication flags it as an infinite loop and aborts. Dot solves this with:
- **Environmental State Tracking**: State-changing actions (`ai_background_load_page`, `search_web`, `click`) automatically invalidate inspection signatures so new pages can be read freely.
- **Active Webpage Identity Headers**: `browser_extract_text` injects `[Active Webpage: '<title>' | URL: <url>]` into observations, preventing the model from hallucinating multiple open browser tabs.
- **Forced Synthesis Fallback**: If the loop breaker ever trips or max steps are reached with observations in history, Dot forces a final synthesis pass so the user still receives an exhaustive, synthesized answer.

### 2. Guarding Against KV Cache / VRAM Spills on Local GPUs
Running multi-step agent reasoning with local models on an 8GB VRAM GPU is a tightrope walk. Multi-turn context quickly inflates token counts:
- Lowered `MAX_LOOP_TOKENS` to 3,500 and observation trim limits to 450 tokens.
- Quantized KV cache (`-ctk q8_0 -ctv q8_0`) cuts memory footprint by ~50%.
- Exception shielding around `llm()` calls catches connection or memory errors cleanly and triggers Playwright auto-cleanup instead of crashing the server process.

### 3. Sub-50ms Intent Bypass
Not every request needs a multi-step agent loop. A lightweight `all-MiniLM-L6-v2` semantic model compares user intent against pre-computed desktop action vectors. Commands like *"open chrome"*, *"launch spotify"*, or *"start notepad"* execute immediately with zero LLM generation latency.

### 4. MCP Multi-Server Lifecycle Management
All MCP servers (GitHub stdio, Playwright browser automation, and OS automation) boot once during FastAPI's `lifespan` context manager and persist across client sessions. WebSocket connections share the client pool, eliminating per-request process startup penalties.

---

## Project Structure

```text
Dot/
├── Dot.exe                     # Standalone silent desktop launcher (zero black terminal windows)
├── launcher.pyw                # Windowless background supervisor (manages server lifecycles & logging)
├── setup.py                    # Rig Analyzer + Setup Wizard GUI (hardware probing & model manager)
├── start_setup.bat             # Setup bootstrap & virtual environment creator
├── start_dot.bat               # Diagnostic launcher (keeps terminal windows open for inspection)
├── appConfig.json              # Model tiers, context sizes, allowed processes & active settings
├── requirements.txt            # Python dependencies (Torch, Transformers, FastMCP, FastAPI)
├── icon.ico                    # Windows application icon
├── bin/                        # Local inference runtime (llama-server.exe, CUDA DLLs, GGUF models)
│   ├── llama-server.exe        # llama.cpp HTTP server
│   ├── ggml-cuda.dll           # CUDA backend acceleration runtime
│   ├── cublas64_*.dll          # NVIDIA cuBLAS libraries
│   ├── gemma-4-E4B_q4_0-it.gguf# Quantized Gemma 4 multimodal model weights
│   └── gemma-4-E4B-it-mmproj.gguf # Vision projector
├── logs/                       # Server & inference logs (engine.log, backend.log)
│
└── dum-e/                      # Core application directory
    ├── server.py               # FastAPI/Uvicorn WebSocket server + MCP lifespan
    ├── neutralino.config.json  # NeutralinoJS shell configuration
    ├── package.json            # React 19 + Vite + Tailwind frontend
    │
    └── src/
        ├── index.css           # Design tokens, custom dark theme & accent utilities
        ├── App.jsx             # Chat interface with streaming & token animations
        │
        └── dot/
            ├── core/
            │   ├── engine.py       # ReAct agent loop, anti-loop breaker & synthesis fallback
            │   ├── router.py       # Semantic intent router (MiniLM cosine similarity)
            │   ├── llm.py          # Local llama.cpp / Cloud OpenAI-compatible client wrapper
            │   ├── prompts.py      # System prompt, browsing protocol & schema definitions
            │   ├── gaurdrails.py   # Action validation & dependency guardrails
            │   ├── intentOpener.py # Direct OS app launching
            │   └── utils.py        # Token counting, observation trimming & history compression
            │
            ├── config/
            │   ├── allowed_apps.yml# Whitelist of allowed OS automation processes
            │   └── mcp_servers.json# MCP server startup configurations
            │
            ├── mcp_files/
            │   ├── mcpClient.py    # Multi-server MCP client pool + sampling handler
            │   ├── registry.py     # Tool synchronization pipeline (MCP to ChromaDB)
            │   └── client_core.py  # MCP connection core & schema fetching
            │
            ├── automation_mcp/
            │   ├── os_automation.py       # FastMCP server: process management, screenshots, OCR, input
            │   └── browser_automation.py  # FastMCP server: Playwright browser control & organic web search
            │
            ├── memory/
            │   ├── vector_store.py        # ChromaDB tool schema discovery
            │   ├── session_memory/        # Session turn storage & sliding window context
            │   └── collections/           # ChromaDB collection handlers
            │
            └── voiceModel/
                ├── voiceListener.py       # Low-latency voice capture daemon
                └── voiceProcess.py        # Whisper STT transcription pipeline
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

## Installation & Setup

### 1. Initial Environment Setup
Run **`start_setup.bat`** to bootstrap the environment:
- Creates the Python virtual environment (`.venv`)
- Installs project dependencies (PyTorch, FastMCP, Uvicorn, Whisper)
- Installs Playwright Chromium browser binaries
- Boots the **Dot Setup Wizard GUI**

### 2. Setup Wizard Configuration
The GUI automatically adapts to your hardware and guides you through setup:
- **Hardware Detection**: Probes GPU VRAM, CUDA runtime version, and system RAM (supports NVIDIA CUDA, CPU AVX2, or Cloud API mode).
- **Effortless Model Setup (Non-Tech Friendly)**:
  - **1-Click Automatic Download**: Directly streams model weights and vision projector from HuggingFace to `bin/` with a live progress bar, speed tracker, and percentage.
  - **Smart Local Discovery**: Automatically scans your `Downloads` directory and local folders for existing models and offers a 1-click **Import (Instant)** button.
  - **File / Folder Picker**: Select downloaded `.gguf` files from anywhere on your PC without needing to find or copy into the `bin/` folder manually.
- **Engine Resolution**: Automatically downloads and pairs the exact CUDA-compiled `llama-server.exe` binary with matching `cudart` runtime DLLs for 100% GPU layer offloading.
- **Application Security**: Configures the whitelist of allowed OS automation processes (`appConfig.json`).

### 3. Launching Dot
You have two ways to run Dot:

- **Option A: Native Desktop App (Recommended)**:
  Double-click **`Dot.exe`**.
  - **Zero Terminal Windows**: Spawns all server processes completely hidden in the background.
  - **Clean Logging**: Streams output to `logs/engine.log` and `logs/backend.log`.
  - **Lifecycle Management**: Automatically shuts down `llama-server.exe` and background servers when you close the Dot window, releasing GPU VRAM.

- **Option B: Diagnostic / Dev Mode**:
  Run **`start_dot.bat`**.
  - Opens command windows showing live CUDA layer offload logs, token generation throughput, and backend traces.

> **Requirements:**
> - [Python 3.10+](https://www.python.org/downloads/) (must be added to PATH)
> - [Node.js](https://nodejs.org) (must be added to PATH)
> - NVIDIA GPU with CUDA support recommended (CPU mode supported with reduced context)

---

*Built on an RTX 3070 laptop. Designed to run on yours too.*