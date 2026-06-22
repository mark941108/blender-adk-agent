# Blender Scene Assembler Agent 🛋️

**AI-Powered Scene Decoration and Asset Automation**

> Using Google ADK + Blender MCP + Antigravity IDE to automatically build 3D environments from fuzzy natural language intents.

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![Blender](https://img.shields.io/badge/Blender-5.1+-orange.svg)](https://blender.org)
[![ADK](https://img.shields.io/badge/Google-ADK-green.svg)](https://google.github.io/adk-docs/)

---

## 🎯 The Pitch: Why Agents?

**The Problem**: Non-3D professionals (indie game devs, marketers, writers) often need high-quality 3D environments for rapid prototyping or concept art, but lack the technical modeling and layout skills to create them from scratch.

**Why Agents are the Unique Solution**:
Traditional automation scripts fail here because user intent is **non-deterministic**. A user asking for a "cozy sunset living room" or a "vintage wooden table" provides fuzzy semantic intent. A traditional script cannot translate "sunset" to a specific HDRI file, nor "vintage table" to the correct asset query.

Our **Scene Assembler Agent** solves this by using the LLM's reasoning capabilities to bridge the gap:
1. It parses the semantic meaning of the request.
2. It translates fuzzy descriptions into precise REST API queries against Poly Haven.
3. It fetches the assets and delegates deterministic tasks (like grid layout math) to dedicated Python scripts.

---

## ✨ Features (Progressive Disclosure)

The Agent architecture strictly follows the **Progressive Disclosure** pattern, shifting deterministic logic left to scripts while keeping decision-making in the Agent layer:

1. **`hdri_setup` Skill**: Downloads and applies 8K HDRI lighting based on mood/time-of-day requests.
2. **`asset_fetcher` Skill**: Uses the Poly Haven API to search, download, and import GLTF models based on semantic queries.
3. **`auto_layout` Skill**: A dedicated Python execution engine (`layout_engine.py`) that handles grid math and collision avoidance, completely removing coordinate hallucination from the LLM.

---

## 🔒 Security: Egress Governance (Zero Trust)

Following Day 4 Kaggle Best Practices, this agent implements strict **Egress Governance** to prevent malicious remote execution and typosquatting downloads:

- **Network Allowlist**: The MCP Server and all Python fetcher scripts contain hardcoded domain allowlists.
- **Allowed Endpoints**: 
  - `https://api.polyhaven.com` (Metadata and querying)
  - `https://cdn.polyhaven.com` (Asset downloads)
- **Zero Ambient Authority**: The Agent is sandboxed and cannot access arbitrary URLs or local files outside the `/temp_assets/` workspace.

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────┐
│        User (Natural Language) + Antigravity IDE      │
│   "Give me an evening living room with a wood table"  │
└──────────────────────┬───────────────────────────────┘
                       │ ADK Orchestration
┌──────────────────────▼───────────────────────────────┐
│              Orchestrator Agent (ADK)                  │
│   Reasons intent → Coordinates API Skills             │
└──────────┬───────────────────────┬────────────────────┘
           │ API Skill             │ Layout Script
┌──────────▼──────┐     ┌──────────▼──────────────────┐
│  Asset Fetcher  │     │       Auto Layout           │
│                 │     │                             │
│ Calls PolyHaven │     │ layout_engine.py inside     │
│ API, downloads  │     │ Blender. Places objects     │
│ GLTF & textures │     │ without LLM math.           │
└──────────┬──────┘     └──────────┬────────────────────┘
           └──────────┬────────────┘
                      │ MCP Protocol
┌─────────────────────▼────────────────────────────────┐
│           Blender MCP Server (v1.0.0)                 │
│   Imports GLTF, Sets up World Nodes, Runs Layout      │
└──────────────────────────────────────────────────────┘
```

---

## ⚙️ Setup Instructions

1. **Install Dependencies**:
   ```bash
   uv venv
   uv pip install -r requirements.txt
   ```
2. **Start the Agent**:
   ```bash
   python -m agents.cli --prompt "Build me a beach scene with a wooden chair"
   ```

---

## 🏆 Kaggle Capstone

This project was built for the [AI Agents: Intensive Vibe Coding Capstone Project](https://kaggle.com/competitions/vibecoding-agents-capstone-project) — **Freestyle Track**.
