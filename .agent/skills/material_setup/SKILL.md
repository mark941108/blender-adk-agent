---
name: material_setup
description: "CRITICAL: USE THIS TOOL EXCLUSIVELY for ANY request about floors, ground, roads, or paving materials. Fetches a PBR texture and applies it to a 50x50m Ground Plane."
---

# Material Setup Skill

This skill downloads CC0 textures from Poly Haven and automatically creates a ground plane with a Principled BSDF material in Blender.

### Instructions for the Agent
- Use this skill when the user requests a floor, ground, or a specific surface material (e.g. "asphalt road", "muddy ground", "wood floor").
- `material_type` should be a short, descriptive search query (e.g., "asphalt", "dirt", "wood").
- **IMPORTANT**: This script handles the API requests and node connections automatically.

### Execution
The underlying script is `scripts/material_setup.py`. When you invoke this skill, the ADK will execute the script in the Blender MCP context with the provided `{{material_type}}`.
