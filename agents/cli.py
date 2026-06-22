"""
CLI interface for Blender Scene Assembler Agent.

Usage:
    python -m agents.cli                               # Interactive mode
    python -m agents.cli --prompt "give me a wood table"  # Single command
"""

import argparse
import asyncio
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

console = Console()

def print_banner():
    console.print(Panel.fit(
        "[bold cyan]Blender Scene Assembler Agent[/bold cyan] [dim]v1.0[/dim]\n"
        "[dim]ADK + Blender MCP + Antigravity IDE[/dim]\n"
        "[yellow]Kaggle AI Agents Capstone — Freestyle Track[/yellow]",
        border_style="cyan"
    ))

def print_result(result):
    table = Table(title="Pipeline Results", border_style="green")
    table.add_column("Tool", style="cyan")
    table.add_column("Status", style="magenta")
    table.add_column("Message", style="white")

    for action in result.actions_taken:
        table.add_row(action["tool"], action["status"], action["msg"])

    console.print(table)
    console.print(f"[dim]Time Elapsed: {result.time_elapsed_seconds:.1f}s[/dim]")

async def run_interactive(agent):
    console.print("[dim]Type your instruction. Ctrl+C to exit.[/dim]\n")
    while True:
        try:
            prompt = console.input("[bold cyan]>[/bold cyan] ")
            if not prompt.strip():
                continue

            with Progress(
                SpinnerColumn(),
                TextColumn("[cyan]Thinking & Executing..."),
                console=console,
            ) as progress:
                progress.add_task("Running pipeline...", total=None)
                result = await agent.run(prompt)
                
            print_result(result)
            if result.error:
                console.print(f"[red]Error: {result.error}[/red]")

        except KeyboardInterrupt:
            console.print("\n[dim]Exiting.[/dim]")
            break

async def main_async(args):
    console.print("[yellow]Initializing Real LLM and MCP Connections...[/yellow]")
    
    from agents.orchestrator import SceneAssemblerOrchestrator
    import os
    from dotenv import load_dotenv
    from google import genai
    from google.genai.types import GenerateContentConfig
    from mcp.client.session import ClientSession
    from mcp.client.stdio import stdio_client, StdioServerParameters
    from pydantic import BaseModel, Field
    from typing import List, Optional
    import json

    # --- Pydantic Schema: enforces 'tool' key, Developer API compatible ---
    # Gemini Developer API does NOT support additionalProperties (dict type).
    # We define explicit optional fields matching all tool signatures.
    class ToolCall(BaseModel):
        tool: str = Field(description="Tool name: hdri_setup | asset_fetcher | material_setup | auto_layout")
        environment_type: Optional[str] = Field(default=None, description="For hdri_setup: e.g. 'evening', 'forest', 'beach'")
        asset_query: Optional[str] = Field(default=None, description="For asset_fetcher: e.g. 'wooden table', 'axe'")
        material_type: Optional[str] = Field(default=None, description="For material_setup: e.g. 'sand', 'grass'")

    class TaskPlan(BaseModel):
        tasks: List[ToolCall] = Field(description="Ordered list of tool calls to assemble the scene")
    
    # 1. Load environment variables
    load_dotenv()
    if not os.environ.get("GEMINI_API_KEY"):
        console.print("[red]Error: GEMINI_API_KEY not found in .env file.[/red]")
        return
        
    # 2. Setup Real LLM Client
    class GeminiLLMClient:
        def __init__(self):
            self.client = genai.Client()
            self.model_name = "gemini-2.5-flash"
            # response_schema: forces 'tool' key, eliminates tool_code/tool_name non-determinism
            self.config = GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=TaskPlan,
            )

        async def generate_task_plan(self, prompt: str, system_prompt: str) -> str:
            full_prompt = f"{system_prompt}\n\nUser Request: {prompt}"
            
            # --- 2026 SOTA: Socket Stall Mitigation ---
            # Gemini API can stall without HTTP timeouts. We force a 15-second cap.
            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.client.models.generate_content,
                        model=self.model_name,
                        contents=full_prompt,
                        config=self.config
                    ),
                    timeout=15.0
                )
            except asyncio.TimeoutError:
                raise Exception("Gemini API Timeout (Socket Stall prevented)")
            # Unwrap {"tasks": [...]} and reconstruct args dict from flat fields
            parsed = json.loads(response.text)
            raw_tasks = parsed.get("tasks", []) if isinstance(parsed, dict) else parsed
            tasks = []
            for t in raw_tasks:
                args = {}
                if t.get("environment_type"): args["environment_type"] = t["environment_type"]
                if t.get("asset_query"):      args["asset_query"]      = t["asset_query"]
                if t.get("material_type"):   args["material_type"]    = t["material_type"]
                tasks.append({"tool": t["tool"], "args": args})
            return json.dumps(tasks)

        async def repair_code(self, original_code, error_message, context) -> str:
            return await self.generate_task_plan(error_message, context)
            
    llm_client = GeminiLLMClient()
    
    # 3. Setup Real MCP Client inside Context Manager
    server_params = StdioServerParameters(
        command="python",
        args=["custom_blender_mcp.py"],
        env={**os.environ, "BLENDER_MCP_AUTH_TOKEN": "kaggle-secret-token"}
    )
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            console.print("[green][OK] Connected to Blender MCP Server[/green]")
            
            # Wrapper to adapt session.call_tool to what orchestrator expects
            class RealMCPClientAdapter:
                def __init__(self, session):
                    self.session = session
                async def call_tool(self, name: str, arguments: dict):
                    return await self.session.call_tool(name, arguments)
            
            mcp_client = RealMCPClientAdapter(session)
            agent = SceneAssemblerOrchestrator(mcp_client, llm_client)

            if args.prompt:
                result = await agent.run(args.prompt)
                print_result(result)
            else:
                await run_interactive(agent=agent)

def main():
    parser = argparse.ArgumentParser(description="Blender Scene Assembler Agent")
    parser.add_argument("--prompt", "-p", type=str, help="Natural language instruction")
    args = parser.parse_args()

    print_banner()
    asyncio.run(main_async(args))

if __name__ == "__main__":
    main()
