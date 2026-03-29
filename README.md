# Dot

> A privacy-first, offline desktop AI companion with screen-aware automation and adaptive local inference.

![Status](https://img.shields.io/badge/Status-In%20Progress-yellow)
![License](https://img.shields.io/badge/License-MIT-blue)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)
![Local](https://img.shields.io/badge/Inference-100%25%20Local-green)

---

## What is Dot?

Most AI assistants send your data to the cloud. Dot doesn't.

Dot is a fully local AI system that can see your screen, control your applications, assist with code, and answer questions — entirely on your machine. No API keys burning money. No data leaving your PC. No token limits.

---

## Core Design Principles

- **Privacy by architecture** — every model runs locally. Nothing leaves your machine.
- **Efficiency by design** — not every query needs a 7B model. Dot routes simple commands directly to the automation engine, skipping LLM inference entirely. Heavy models only wake up when actually needed.
- **Memory that grows** — user interactions are vectorized and stored locally. Dot gets more useful over time.

---

## Architecture

```
![DUM-E Architecture](/architecture.png)
```

---

## Features

| Feature | Status |
|---|---|
| Voice + Text input pipeline | ✅ Done |
| Intent routing (all-MiniLM-L6-v2) | ✅ Done |
| Direct command execution | ✅ Done |
| Automation engine → system control | ✅ Done |
| Wake word detection (separate thread) | ✅ Done |
| Gemma 2 2B + Florence 2 vision layer | 🔄 In Progress |
| MCP context layer | 🔄 In Progress |
| RAG memory pipeline | 🔄 In Progress |
| Qwen2.5-VL-7B escalation layer | 🔄 In Progress |
| SQLite activity logging | 🔄 In Progress |

---

## Tech Stack

![Python](https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white)
![NeutralinoJS](https://img.shields.io/badge/NeutralinoJS-black?style=flat)
![Ollama](https://img.shields.io/badge/Ollama-local%20inference-black?style=flat)
![ChromaDB](https://img.shields.io/badge/ChromaDB-VectorDB-orange?style=flat)
![SQLite](https://img.shields.io/badge/SQLite-003B57?style=flat&logo=sqlite&logoColor=white)

**Models:** Gemma 2 2B · Florence 2 (.23B) · Qwen2.5-VL-7B (4-bit quantized) · all-MiniLM-L6-v2

---

## Why This Matters

Cloud AI has a ceiling — rate limits, costs, privacy risks, internet dependency.  
Local AI has a floor — hardware constraints, latency, model size.  
Dot is an attempt to push that floor down as far as possible on consumer hardware.

---

*Built on a RTX 3070 laptop. Designed to run on yours too.*
