# AGENTS.md

This document defines the architecture standards, refactoring plan, and coding rules for the Dot codebase.
All agents and developers must follow these rules.

---

## 1. Tool Discovery & ReAct Loop Strategy

### 1.1 The Role of Tool Discovery
Dynamic tool discovery (`Tool` -> search -> `Tool-exec`) is designed for **unbounded, dynamic tool sets** (such as GitHub APIs, database connectors, or cloud MCP servers) where schemas cannot fit into the context window.

### 1.2 The Local Model Bottleneck
On local hardware, each model generation takes 1.5 to 5.0 seconds.
Requiring two inference turns for every single action doubles execution latency:
- Turn 1: Model outputs `action: "Tool"` with a search query.
- Turn 2: Engine searches vector store and returns schema.
- Turn 3: Model outputs `action: "Tool-exec"` with arguments.
- Turn 4: Tool executes and returns observation.
- Turn 5: Model outputs `action: "Final"`.

For core, high-frequency tools (`browser`, `os_tools`, `native`), this creates unnecessary delay.

### 1.3 The Hybrid Architecture Standard
To maximize speed without losing dynamic capabilities, follow this hybrid standard:

1. **Direct Execution for Known Tools (Zero Discovery Overhead)**:
   - Core tools (`browser`, `os_tools`, `native`) are fixed and known.
   - The model must execute known tools directly with `action: "Tool-exec"` on Turn 1.
   - Do not run discovery turns for tools that are already known.

2. **Pre-Turn Tool Retrieval (Speculative Tool RAG)**:
   - When the user sends a query, the intent router retrieves the top 3 relevant tools in Python (< 15 ms).
   - Inject only those 3 relevant tools into the Turn 1 prompt.
   - The model can then execute `Tool-exec` immediately on Turn 1.
   - This eliminates the intermediate LLM discovery turn while keeping the prompt small.

3. **Fallback Discovery for External MCP Servers**:
   - Keep `action: "Tool"` only for large, dynamic MCP servers (such as GitHub with 50+ endpoints).
   - When the tool is not found in the initial context, the model uses `action: "Tool"` to search.

---

## 2. ASD-STE100 Commenting Standard

All code comments, docstrings, and error messages must comply with **ASD-STE100 (Simplified Technical English)**.

### 2.1 Core Rules
1. **Sentence Length**: Keep sentences short. Do not write sentences with more than 25 words.
2. **One Thought Per Sentence**: Express only one instruction or description per sentence.
3. **Active Voice**: Write in the active voice.
   - *Correct*: "The function starts the browser process."
   - *Incorrect*: "The browser process is started by the function."
4. **Simple Present Tense & Imperative Mood**:
   - Use simple present tense for descriptions: "Returns the tool schema."
   - Use imperative mood for instructions: "Verify that the port is open."
5. **No Slang, Idioms, or Jargon**:
   - Do not use casual expressions (e.g., "let me cook", "under the hood", "kick off").
   - Keep internal reasoning and code comments professional and objective.
6. **Consistent Terminology**:
   - Use "start", not "spin up" or "fire up".
   - Use "stop" or "terminate", not "kill".
   - Use "send", not "dispatch" or "emit".
   - Use "receive", not "catch".
   - Use "remove", not "strip" or "drop".
   - Use "find", not "sniff out".

### 2.2 Examples

#### Non-Compliant Style:
```python
# crude but cheap: pull tool names + outcomes, skip full reasoning text
# unwrap common "results wrapper" shapes: {"items": [...], "total_count": N}
# Self-heal mislabeled actions
# Fallback: If port 9222 isn't open, launch a new browser
```

#### ASD-STE100 Compliant Style:
```python
# Extract tool names and outcomes from previous steps. Omit reasoning text.
# Normalize result dictionaries that contain an items list and total count.
# Correct the action type when the model provides tool arguments.
# If port 9222 is closed, start a new local browser instance.
```

---

## 3. Codebase Refactoring Blueprint

### 3.1 Target Directory Structure
Refactor the codebase into clean, decoupled layers to enable fast symbol search and modular testing:

```text
Dot/
├── appConfig.json
├── launcher.pyw
├── setup.py
├── start_dot.bat
├── AGENTS.md
└── dum-e/
    ├── server.py
    └── src/
        ├── App.jsx
        ├── index.css
        ├── main.jsx
        ├── utils/
        └── dot/
            ├── config/                 # Static configuration files
            │   ├── allowed_apps.yml
            │   └── mcp_servers.json
            │
            ├── core/                   # Agent orchestration & LLM interfaces
            │   ├── engine.py           # Clean ReAct loop
            │   ├── guardrails.py       # Input/output validation
            │   ├── llm.py              # AsyncOpenAI client with true streaming
            │   ├── prompts.py          # Static system prompts
            │   └── router.py           # Fast intent classification
            │
            ├── mcp/                    # MCP client & protocol management
            │   ├── client.py           # Unified client connection pool
            │   └── registry.py         # Tool catalog and fast in-memory indexing
            │
            ├── automation/             # Automation servers & handlers
            │   ├── browser.py          # Playwright browser controller
            │   ├── os_desktop.py       # Desktop OS actions
            │   └── intent_opener.py    # Direct application opener
            │
            ├── memory/                 # Storage & vector systems
            │   ├── client.py           # Shared ChromaDB client singleton
            │   ├── session.py          # Session history sliding window
            │   ├── tokenizer.py        # Shared tokenizer singleton
            │   └── search.py           # Fixed session and past turn search
            │
            └── voice/                  # Speech & audio subsystems
                ├── listener.py         # Alt-hold key listener
                └── transcriber.py      # Lazy-loaded faster-whisper worker
```

---

## 4. Key Performance Requirements

### 4.1 Asynchronous Execution
- Do not run blocking operations on the `asyncio` event loop.
- Use `AsyncOpenAI` for all LLM calls.
- Wrap synchronous CPU libraries (`sentence_transformers`, `easyocr`, `AppOpener`) in `asyncio.to_thread()`.
- Use `httpx.AsyncClient` for all outbound network requests.

### 4.2 Streaming
- Use genuine token streaming (`stream=True`) from `llama-server`.
- Stream tokens to the WebSocket as soon as the model generates them.
- Do not use artificial sleep delays (`asyncio.sleep`) to simulate streaming.

### 4.3 Memory & VRAM Conservation
- Always launch `llama-server` with quantized KV cache flags: `-ctk q8_0 -ctv q8_0`.
- Load heavy models (`WhisperModel`, `EasyOCR`) lazily on first use.
- Run EasyOCR on CPU by default to prevent VRAM competition with `llama-server`.
- Instantiate the HuggingFace `AutoTokenizer` once as a module-level singleton.

### 4.4 Startup Optimization
- Do not launch MCP subprocesses twice.
- Synchronize tools using the active client pool during application startup.
- Verify CDP port availability with a 50 ms socket check before attempting Playwright connection.

---

## 5. Hybrid BM25 RAG Standard (Future Scope)

The future memory recall system combines dense vector search with BM25 keyword search.
All implementations of this subsystem must follow ASD-STE100 rules.

### 5.1 Architecture Requirements
1. **Rank Fusion**: Merge vector distances and BM25 scores with Reciprocal Rank Fusion (RRF).
2. **In-Memory Index**: Store the BM25 inverted index in memory for sub-millisecond retrieval.
3. **Non-Blocking Compute**: Run BM25 tokenization and scoring in worker threads via `asyncio.to_thread()`.
4. **Token Compactness**: Compress retrieved conversation turns to fit within a 500-token limit.
5. **Pure Python Fallback**: Use `rank_bm25` or custom sparse matrix math without heavy dependencies.

