"""
Orchestrator Agent — Main ADK coordinator for the Scene Assembler.

Architecture: 
Takes fuzzy natural language intent from the user, uses the LLM to parse it into 
specific keywords, and calls the appropriate API-fetching skills via Blender MCP.
"""

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(name)s] %(message)s"
)
logger = logging.getLogger("Orchestrator")

@dataclass
class PipelineResult:
    """Final report returned to user."""
    actions_taken: list = None
    time_elapsed_seconds: float = 0.0
    error: str = None
    
    def __post_init__(self):
        if self.actions_taken is None:
            self.actions_taken = []

class SceneAssemblerOrchestrator:
    def __init__(self, mcp_client, llm_client):
        self.mcp = mcp_client
        self.llm = llm_client

    async def run(self, user_prompt: str) -> PipelineResult:
        start_time = time.perf_counter()
        logger.info(f"Parsing prompt: '{user_prompt}'")
        result = PipelineResult()
        
        # Step 1: Use LLM to classify intent and extract keywords
        # We ask LLM to output a JSON array of tasks: [{"tool": "hdri_setup", "args": {"environment_type": "evening"}}, ...]
        system_prompt = (
            "You are a 3D Scene Assembler Agent. Map the user's fuzzy request to specific tool calls.\n"
            "CRITICAL RULE: If the user asks for an outdoor scene or garden, you MUST actively call hdri_setup (e.g. 'clear sky') to provide light, unless they specify an HDRI.\n"
            "Available tools:\n"
            "1. hdri_setup: args={'environment_type': 'keyword'} (for lighting, mood, time of day)\n"
            "2. asset_fetcher: args={'asset_query': 'keyword'} (for specific 3D models like table, barrel. CRITICAL: Do NOT use commas to combine distinct objects. Call this multiple times in parallel for multiple objects. DO NOT use for floors/roads.)\n"
            "3. material_setup: args={'material_type': 'keyword'} (CRITICAL: Use ONLY for floors, ground, roads, or paving materials like asphalt or mud.)\n"
            "4. auto_layout: args={} (for organizing or arranging the scene)\n"
            "Return a JSON list of tasks."
        )
        
        try:
            # Simulated ADK 2.0 Graph Workflow Task Routing
            # Instead of hacking repair_code, we use a dedicated routing API
            if hasattr(self.llm, "generate_task_plan"):
                parsed_json = await self.llm.generate_task_plan(user_prompt, system_prompt)
            else:
                # Fallback for legacy clients
                parsed_json = await self.llm.repair_code("[]", "Map the prompt to tool calls: " + user_prompt, system_prompt)
                
            match = re.search(r'\[.*\]', parsed_json, re.DOTALL)
            tasks = json.loads(match.group(0)) if match else json.loads(parsed_json)
        except Exception as e:
            logger.warning(f"ADK Task Routing failed: {e}. Falling back to basic pattern matching.")
            tasks = self._fallback_parse(user_prompt)

        logger.info(f"Planned tasks: {tasks}")
        
        # --- 2026 SOTA: Group tasks by dependency type ---
        # Gemini may return any of: 'tool', 'tool_code', 'tool_name', 'name'
        # _tool_name() normalises all variants into one canonical string.
        def _tool_name(t: dict) -> str:
            return (t.get("tool") or t.get("tool_code") or
                    t.get("tool_name") or t.get("name") or "")

        sequential_pre  = [t for t in tasks if _tool_name(t) in ("hdri_setup", "material_setup")]
        parallel_assets = [t for t in tasks if _tool_name(t) == "asset_fetcher"]
        sequential_post = [t for t in tasks if _tool_name(t) == "auto_layout"]

        # Post-action hook: auto-inject auto_layout if assets were fetched but layout missing
        if parallel_assets and not sequential_post:
            logger.info("Post-Action Hook: Injecting mandatory auto_layout.")
            sequential_post = [{"tool": "auto_layout", "args": {}}]

        async def _run_task(task: dict) -> dict:
            """Execute a single MCP task and return a result dict."""
            name = _tool_name(task)
            args = task.get("args", {})
            logger.info(f"Executing: {name} with args {args}")
            try:
                mcp_res = await self.mcp.call_tool(name, arguments=args)
                if getattr(mcp_res, "is_error", False):
                    raise Exception(mcp_res.content[0].text if mcp_res.content else "Tool returned error")
                msg = mcp_res.content[0].text if mcp_res.content else "Success"
                logger.info(f"Result: {msg!r}")
                return {"tool": name, "status": "Success", "msg": msg, "args": args}
            except Exception as e:
                logger.error(f"Task {name} failed: {e}")
                return {"tool": name, "status": "Failed", "msg": str(e), "args": args}

        # Phase 1 — sequential pre-tasks
        for task in sequential_pre:
            result.actions_taken.append(await _run_task(task))

        # Phase 2 — parallel asset fetching (ADK 2.0 parallel execution)
        if parallel_assets:
            # --- 2026 SOTA: Concurrency Governance ---
            # Prevent socket exhaustion and PolyHaven 429 Rate Limits by capping concurrent tasks
            fetch_semaphore = asyncio.Semaphore(5)
            
            async def _run_with_semaphore(task):
                async with fetch_semaphore:
                    return await _run_task(task)

            logger.info(f"Parallel fetching {len(parallel_assets)} assets with max concurrency 5")
            gathered = await asyncio.gather(*[_run_with_semaphore(t) for t in parallel_assets], return_exceptions=True)
            for item in gathered:
                if isinstance(item, Exception):
                    result.actions_taken.append({"tool": "asset_fetcher", "status": "Failed", "msg": str(item), "args": {}})
                else:
                    result.actions_taken.append(item)

        # Phase 3 — sequential post-tasks
        for task in sequential_post:
            result.actions_taken.append(await _run_task(task))

        result.time_elapsed_seconds = time.perf_counter() - start_time
        return result

    def _fallback_parse(self, prompt: str) -> list:
        """Basic regex fallback if LLM fails."""
        tasks = []
        prompt_lower = prompt.lower()
        if "evening" in prompt_lower or "sunset" in prompt_lower or "lighting" in prompt_lower:
            tasks.append({"tool": "hdri_setup", "args": {"environment_type": "evening"}})
        if "table" in prompt_lower or "wood" in prompt_lower:
            tasks.append({"tool": "asset_fetcher", "args": {"asset_query": "wooden table"}})
        if "arrange" in prompt_lower or "layout" in prompt_lower or "organize" in prompt_lower:
            tasks.append({"tool": "auto_layout", "args": {}})
        return tasks
