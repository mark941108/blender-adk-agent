# AGENTS.md — Shared Cross-Tool Foundation
#
# This file provides instructions to all AI coding agents (Antigravity IDE,
# Cursor, Claude Code, etc.) about this project's architecture, constraints,
# and workflows. It replaces tool-specific files like .cursorrules or CLAUDE.md.
#
# Reference: https://agents.md — AGENTS.md cross-tool standard (2026)

## Project Overview

**Blender Scene Assembler Agent** — A multi-agent system that acts as a 3D Scene Decorator. It understands fuzzy natural language intents, automatically fetches CC0 assets (HDRIs, Models) from Poly Haven via REST API, and imports/arranges them into Blender 5.1 using Google ADK + Blender MCP.

- **Language**: Python 3.11+
- **Framework**: Google ADK (Agent Development Kit)
- **External Tool**: Blender 5.1 via official MCP Server (mcp-1.0.0)

## Architecture Constraints

### DO NOT:
- Import `mathutils`, `bpy`, or `bmesh` in the external Python environment
  (these are Blender built-ins; they must run inside Blender via MCP)
- Store API keys, passwords, or absolute local paths in any source file
- Modify `specs/scene_assembly.feature` without updating corresponding tests
- Allow LLM to perform complex grid/math calculations in prompts (use Python `auto_layout` scripts instead).

### ALWAYS:
- Add Docstrings to every function: describe Design, Behavior, Args, Returns
- Use `validate_path()` from `agents/security.py` before any file I/O
- Pass parameters to Blender skills as `{{PLACEHOLDER}}` template tokens
- Log orchestrator actions at INFO level for trajectory review

## Security Model (Day 4 Course — Zero Ambient Authority & Egress Governance)

- **File-tree Allowlist**: Only `/temp_assets/` (for downloading)
- **Egress Governance (Zero Trust Network)**: Agents and scripts are STRICTLY forbidden from making arbitrary web requests. The only allowed outbound domain is `https://api.polyhaven.com` and its associated CDNs (`https://cdn.polyhaven.com`). This MUST be hardcoded in the scripts.
- **JIT Downscoping**: Permissions are scoped per-operation, not session-wide
- **No Ambient Credentials**: Use `os.environ.get()` only, never hardcode

## Skill Structure (Progressive Disclosure)

All agent skills follow the 3-level progressive disclosure pattern:
```
.agent/skills/{skill_name}/
├── SKILL.md          # REQUIRED: YAML frontmatter + instructions (Level 1+2)
├── scripts/          # Blender Python scripts injected via MCP (Level 3)
└── references/       # Supporting docs, loaded only when needed (Level 3)
```

Do NOT put business logic in orchestrator.py — keep it in skill scripts.

## Evaluation (EDD — Eval-Driven Development)

Agent behavior is defined by `tests/eval_cases.json`. Before adding new
agent logic, add an eval case first (TDD for agents).

- Trajectory quality is more important than final output correctness
- Each eval case defines: input prompt, expected tool call sequence, success criteria
