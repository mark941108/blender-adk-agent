---
name: asset_fetcher
description: "Fetches and imports a 3D model (GLTF) from Poly Haven. CRITICAL: DO NOT use this for ground, floors, or textures. DO NOT combine multiple objects with commas; call this tool multiple times in parallel instead."
---

# Asset Fetcher Skill

This skill fetches CC0 3D models from Poly Haven and imports them into Blender.

### Instructions for the Agent
- Use this skill when the user requests a specific physical object, prop, or furniture (e.g. "table", "chair", "plant").
- `asset_query` should be a short, comma-separated string of descriptive tags (e.g., "wood,table", "chair,leather").
- **IMPORTANT**: The script automatically handles the network requests to Poly Haven and the import process in Blender. It returns a success message to you. Do NOT attempt to read the Poly Haven API JSON yourself.

### ⚠️ CRITICAL INSTRUCTIONS (MUST FOLLOW)
1. **Parallel Tool Calling**: If the user asks for multiple distinct items (e.g. "a barrel, a tire, and a fence"), you **MUST** call this tool multiple times concurrently, once for each item. Do **NOT** combine distinct items into a single `asset_query`.
   - ❌ **Incorrect**: `asset_fetcher(asset_query="barrel, tire, fence")`
   - ✅ **Correct**: `asset_fetcher(asset_query="barrel")` AND `asset_fetcher(asset_query="tire")` AND `asset_fetcher(asset_query="fence")`
2. **Auto Layout Required**: After you successfully finish all your `asset_fetcher` calls, you **MUST** call the `auto_layout` tool to arrange the newly imported objects cleanly in the scene.

### Execution
The underlying script is `scripts/asset_fetcher.py`. When you invoke this skill, the ADK will execute the script in the Blender MCP context with the provided `{{asset_query}}`.
