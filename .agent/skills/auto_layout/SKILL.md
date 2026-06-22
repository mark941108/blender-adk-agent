---
name: auto_layout
description: "Automatically arranges all top-level objects in the Blender scene into a neat grid layout to prevent overlapping. Usage: auto_layout()"
---

# Auto Layout Skill

This skill delegates deterministic grid math and spatial arrangement to a Python script, avoiding LLM coordinate hallucination.

### Instructions for the Agent
- Use this skill after you have fetched and imported multiple assets, or when the user asks you to "clean up", "arrange", or "organize" the scene.
- Takes no parameters.

### Execution
The underlying script is `scripts/layout_engine.py`. When you invoke this skill, the ADK will execute the script in the Blender MCP context.
