---
name: hdri_setup
description: "Fetches and applies an HDRI lighting setup from Poly Haven based on semantic environment search. Usage: hdri_setup(environment_type='evening')"
---

# HDRI Setup Skill

This skill fetches CC0 HDRIs from Poly Haven and automatically configures Blender's World nodes for PBR lighting.

### Instructions for the Agent
- Use this skill when the user requests a specific mood, time of day, or environment lighting (e.g. "sunset", "studio", "cloudy").
- `environment_type` should be a short, comma-separated string of tags (e.g. "sunset,outdoor", "studio").
- **IMPORTANT**: The script automatically handles the network requests to Poly Haven and the import process in Blender. It returns a success message to you. Do NOT attempt to read the Poly Haven API JSON yourself.

### Execution
The underlying script is `scripts/hdri_setup.py`. When you invoke this skill, the ADK will execute the script in the Blender MCP context with the provided `{{environment_type}}`.
