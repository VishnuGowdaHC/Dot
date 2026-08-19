# Dot

A local-first autonomous AI desktop assistant. No cloud APIs, no token billing, no data leaving your machine.

Built because I wanted an AI agent that actually runs on my hardware, not one that wraps three SaaS APIs in a trenchcoat and calls itself "local."

![Status](https://img.shields.io/badge/Status-Active%20Development-yellow)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)
![Inference](https://img.shields.io/badge/Inference-100%25%20Local-green)
![License](https://img.shields.io/badge/License-MIT-blue)

---

## Why Build This From Scratch?

Most "AI assistant" projects glue together LangChain, Electron, and an OpenAI key and call it a day. That stack is fat, slow, and expensive.

I wanted to solve a different problem: **run a multi-tool ReAct agent loop against a local LLM with sub-second tool dispatch, on a laptop with 8GB VRAM, without the UI eating half my RAM before inference even starts.**

That means:
- No LangChain/LlamaIndex. The orchestration loop is ~350 lines of Python I control entirely. I know exactly what's in my context window and why.
- No Electron. The UI shell uses **NeutralinoJS** (~3MB runtime vs Electron's ~200MB). When you're running a quantized 4B model, every MB of RAM matters.
- No cloud inference. **llama.cpp** (`llama-server`) runs locally with CUDA offloading. The Python backend talks to it over `localhost:11434` using the OpenAI-compatible API: zero network hops.

---

## Stack

| Layer | Choice | Why |
|---|---|---|
| **Frontend Shell** | NeutralinoJS | ~3MB runtime. Uses the OS webview instead of bundling Chromium. The LLM needs the RAM, not the UI. |
| **Frontend Framework** | React 19 + Vite + Tailwind | Standard, fast HMR during development. Renders markdown responses with syntax highlighting. |
| **Backend Server** | Python FastAPI + Uvicorn | Async WebSocket server. Manages agent lifecycle, session memory, and MCP client connections. |
| **Agent Loop** | Custom ReAct (Pydantic-validated) | Hand-rolled Reason+Act loop with structured JSON output, sliding-window context compression, anti-loop circuit breakers, and guardrail enforcement. |
| **Tool Protocol** | Model Context Protocol (MCP) | Multi-server MCP client via `fastmcp`. Tool schemas are indexed in ChromaDB for vector-similarity discovery at runtime. |
| **Inference** | llama.cpp (`llama-server`) | Local GGUF inference with OpenAI-compatible API. Structured JSON output via `json_schema` response format. |
| **Models** | Gemma 4 (2B/4B/12B QAT Q4_0) | Google's latest multimodal model. The setup wizard picks the right tier for your hardware. |
| **Intent Routing** | `all-MiniLM-L6-v2` | Cosine similarity against anchor phrases. Simple commands (e.g., "open Spotify") bypass the LLM entirely: direct execution in <50ms. |
| **Wake Word** | OpenWakeWord + custom ONNX model | Always-on mic listener on a daemon thread. Triggers `faster-whisper` STT on detection. |
| **Vision** | Gemma 4 mmproj + EasyOCR | Multimodal projector for screenshot understanding. OCR for pixel-coordinate text location on screen. |
| **Memory** | ChromaDB + Session JSONL | Tool schemas vectorized for discovery. Session turns stored and embedded on disconnect. |

---

## How the Agent Loop Actually Works

The core of Dot is a hand-rolled [ReAct loop](dum-e/src/dot/core/engine.py): no framework, just a structured prompt-parse-act cycle:

1. **User query** enters via WebSocket → intent router classifies it.
2. If it's a simple command (cosine sim > 0.3, < 6 words), it **skips the LLM entirely** and routes to `AppOpener` for direct OS execution.
3. Otherwise, the query enters the **ReAct loop** (max 8 steps):
   - LLM outputs a `Pydantic`-validated JSON action (`Tool`, `Tool-exec`, or `Final`).
   - `Tool` → vector search ChromaDB for matching MCP tool schemas.
   - `Tool-exec` → dispatch to the appropriate MCP server (GitHub/Browser/OS).
   - `Final` → send the answer back over the WebSocket.
4. **Anti-loop circuit breakers** track execution signatures. If the agent tries to call the same tool with the same args twice, it's force-exited with a graceful fallback message.
5. **Context compression** kicks in when the running prompt exceeds 6000 tokens, unpinned history gets summarized to keep the window lean.
6. On WebSocket disconnect, the session is **embedded into ChromaDB** for future context retrieval.

---

## Hardest Challenges Solved

### Keeping a 2B model on the rails
Small models hallucinate tool names, emit malformed JSON, and loop on the same action forever. The agent loop has multiple layers of defense:
- **Pydantic validation** with a `model_validator` that remaps legacy/malformed key names before validation fails.
- **Self-healing**: if the model says `action: "Tool"` but the payload contains a `name` field, the engine silently corrects it to `Tool-exec`.
- **Signature-based dedup**: every tool call gets a hash. Duplicates trigger a hard exit instead of infinite retries.
- **Guardrails**: placeholder detection (`<username>`) blocks execution before it hits the MCP server.

### MCP multi-server lifecycle
All MCP servers (GitHub stdio, Browser via Playwright, OS automation) boot once during FastAPI's `lifespan` context manager and stay alive for the entire app session. Every WebSocket connection shares the same active MCP client: no per-request server spawning, no connection storms.

---

## Project Structure

```
Dot/
├── test/
│   ├── setup.py              # Rig Analyzer + Setup Wizard (CustomTkinter)
│   ├── appConfig.json         # Model tiers, launcher templates, active settings
│   └── start_dot.bat          # Generated launcher script
│
└── dum-e/                     # Main application
    ├── server.py              # FastAPI/Uvicorn WebSocket server + MCP lifespan
    ├── neutralino.config.json # NeutralinoJS shell configuration
    ├── package.json           # React 19 + Vite + Tailwind frontend
    │
    └── src/dot/
        ├── core/
        │   ├── engine.py      # ReAct agent loop (the brains)
        │   ├── router.py      # Intent classification (MiniLM cosine sim)
        │   ├── llm.py         # llama.cpp OpenAI-compat client wrapper
        │   ├── prompts.py     # System prompt + tool context injection
        │   ├── guardrails.py  # Placeholder detection, action validation
        │   └── utils.py       # JSON extraction, observation trimming, context compression
        │
        ├── mcp_files/
        │   ├── mcpClient.py   # Multi-server MCP client + sampling handler
        │   ├── registry.py    # Tool sync pipeline (MCP → ChromaDB)
        │   └── client_core.py # Server connection + tool schema fetching
        │
        ├── automation_mcp/
        │   ├── os_automation.py      # FastMCP server: process mgmt, screenshots, OCR, keyboard/mouse
        │   └── browser_automation.py # FastMCP server: Playwright browser control, screenshots, navigation
        │
        ├── memory/
        │   ├── vector_store.py       # ChromaDB tool discovery (vector search + bypass for known services)
        │   ├── session_memory/       # Session turn storage + sliding window manager
        │   └── collections/          # ChromaDB collection managers (tools, sessions, native)
        │
        ├── voiceModel/
        │   ├── voiceListener.py      # OpenWakeWord daemon + silence-based recording
        │   └── voiceProcess.py       # faster-whisper STT transcription
        │
        ├── sandbox/                  # [WIP] Docker-based command execution sandbox
        │   ├── Dockerfile
        │   └── container_running.py
        │
        └── config/
            ├── mcp_servers.json      # MCP server registry (GitHub, Browser, OS)
            └── allowed_apps.yml      # OS automation process whitelist
```

---

## Pending / Exploring

Being honest: these are scaffolded but not shipped:

| Area | Status | What I'm working toward |
|---|---|---|
| **Docker Sandbox** | Scaffolded (empty Dockerfile + module) | Isolated container for agent shell command execution. The agent shouldn't run `rm -rf` on the host. Planning to use Docker SDK for Python with volume-mounted workspaces and execution timeouts. |
| **Hybrid Search RAG** | Partially built (ChromaDB session embedding exists) | Session turns already get embedded on disconnect. Next step is a retrieval pipeline that combines vector similarity with keyword/BM25 search for better personal context recall during the agent loop. |
| **Cloud Fallback** | Config-level support exists | The setup wizard collects an API key and the launcher can skip local inference. The actual fallback routing logic (local fails → cloud retry) isn't wired yet. |

---

will update the setup.py soon

*Built on a RTX 3070 laptop. Designed to run on yours too.*