# Blender Scene Assembler Agent 🛋️

**Deterministic 3D Scene Assembly via MCP and ADK 2.0**

> A multi-agent system utilizing Google ADK and Blender MCP to translate unstructured semantic intents into deterministic 3D environment construction.

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![Blender](https://img.shields.io/badge/Blender-5.1+-orange.svg)](https://blender.org)
[![ADK](https://img.shields.io/badge/Google-ADK-green.svg)](https://google.github.io/adk-docs/)

---

## 🎯 Architecture Overview

In modern 3D production, the true bottleneck for indie game developers and artists is no longer layout or design, but the tedious process of "Asset Preparation." Sourcing high-quality 3D models, downloading GLTF files, unzipping textures, importing them into Blender, and linking PBR materials consumes hours of repetitive, non-creative labor. 

Our **Semantic Asset Retrieval & Preparation Assistant** solves this by employing the 2026 "Human-on-the-Loop" (HOTL) paradigm. Instead of attempting to fully automate artistic layout, an ADK 2.0 Orchestrator acts as an intelligent middleware. It maps fuzzy semantic requests (e.g., "sunset living room") to structured, idempotent REST API queries against the Poly Haven asset library, fetching and injecting assets directly into Blender 5.1 via the Model Context Protocol (MCP 1.0.0). This allows the human artist to bypass file I/O and instantly take creative control over the final aesthetic arrangement.

---

## ✨ Engineering Features (Day 3 & 5 Compliance)

### 1. Progressive Disclosure & Context Hygiene
To protect the LLM's token budget and prevent Context Rot, the agent's skills are architected using **Progressive Disclosure**.
*   All skills reside in `.agent/skills/`.
*   At boot, only `SKILL.md` (metadata) is exposed to the Orchestrator. The actual Python execution scripts (`scripts/`) are dynamically loaded only upon explicit tool invocation.
*   We utilize a strictly configured `.aiignore` to prevent context leakage or memory pollution by blocking agents from reading temporary execution state and environment variables.

### 2. Shifting Intelligence Left
The system explicitly prevents the LLM from attempting arithmetic operations (such as 3D coordinate mapping or collision detection), known to cause arithmetic hallucinations.
*   **Implementation**: We apply **Shifting Intelligence Left** by deferring all coordinate geometry to the deterministic execution layer. The LLM simply triggers `auto_layout`, and the `layout_engine.py` script calculates bounding boxes and applies `bpy.ops.outliner.orphans_purge` natively inside Blender.

### 3. Pydantic Structured Outputs & SDD
*   **Structured Outputs**: The Orchestrator enforces Pydantic schemas for all tool calls, replacing brittle Regex parsing with deterministic JSON compliance.
*   **Spec-Driven Development (SDD)**: System logic is defined as the absolute source of truth in `specs/scene_assembly.feature` using Gherkin BDD syntax, evaluated rigorously via automated Trajectory Evaluation (`run_evals.py`).

---

## 🔒 Security: Zero Trust & Egress Governance

Following Day 4 Kaggle Best Practices, this agent operates within a strict Zero Trust framework:

1.  **Egress Governance**: Agents and scripts are strictly forbidden from making arbitrary web requests. The outbound domains are hardcoded (`https://api.polyhaven.com` and `https://cdn.polyhaven.com`). All requests are sanitized using `urllib.parse` to prevent Slopsquatting.
2.  **Zero Ambient Authority**: 
    *   File I/O operations are strictly validated against Path Traversal vulnerabilities using `os.path.realpath` (`agents/security.py`). 
    *   Asset downloads are confined exclusively to the `/temp_assets/` workspace.
3.  **Concurrency Governance**: To prevent API rate limiting (HTTP 429) and socket exhaustion, the Orchestrator wraps all asynchronous HTTP tool calls in an `asyncio.Semaphore(5)`, throttling parallel downloads to a deterministic queue.

---

## 🏗️ Architecture Flow

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': { 'edgeLabelBackground': '#1E293B', 'lineColor': '#94A3B8'}}}%%
flowchart TD
    %% 企業級冷色調極簡配色 (Corporate Minimalist Theme)
    classDef user fill:#1E293B,stroke:#0F172A,stroke-width:2px,color:#fff,rx:10,ry:10
    classDef ai fill:#2563EB,stroke:#1D4ED8,stroke-width:2px,color:#fff,rx:5,ry:5
    classDef python fill:#059669,stroke:#047857,stroke-width:2px,color:#fff,rx:5,ry:5
    classDef security fill:#6D28D9,stroke:#4C1D95,stroke-width:2px,color:#fff,rx:5,ry:5
    classDef external fill:#D97706,stroke:#B45309,stroke-width:2px,color:#fff,rx:10,ry:10

    User(("👤 User Prompt")):::user --> Orchestrator

    subgraph "1. Agentic Layer (Google ADK)"
        Orchestrator["🧠 Gemini 2.5 Flash<br>(Intent Parsing & Router)"]:::ai
    end

    subgraph "2. Skill & Network Layer"
        direction LR
        Skills["📦 Python Skill Modules<br>(HDRI, Material, Asset, Layout)"]:::python
        PolyHaven[("☁️ Poly Haven API<br>(Zero-Trust Egress)")]:::external
        
        Skills -.->|  Fetch Assets  | PolyHaven
        PolyHaven -.->|  GLTF / EXR  | Skills
    end

    subgraph "3. Sandbox Execution Layer"
        direction LR
        AST{"🛡️ AST Validator<br>(Security)"}:::security
        MCP["🔌 MCP Bridge"]:::security
        Blender[("🧊 Blender 5.1")]:::external
        
        AST -->|  Validation  | MCP
        MCP -->|  Subprocess  | Blender
    end

    %% 資料流向 (由上至下依序傳遞)
    Orchestrator -->|  Parallel Calls  | Skills
    Skills -->|  Inject Script  | AST
```

---

## ⚙️ Setup Instructions

1. **Install Dependencies**:
   ```bash
   uv venv
   uv pip install -r requirements.txt
   ```
2. **Configure Environment Variables**:
   *   Copy `.env.example` to `.env`.
   *   **DO NOT INCLUDE REAL API KEYS IN CODE COMMITS.**

3. **Start the Agent**:
   ```bash
   python -m agents.cli --prompt "Build a beach scene with a wooden chair"
   ```

---

## 🏆 Kaggle Capstone

This project is submitted for the [AI Agents: Intensive Vibe Coding Capstone Project](https://kaggle.com/competitions/vibecoding-agents-capstone-project) — **Freestyle Track**.
