import asyncio
import os
import json
import time
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

async def run():
    print("[1] Preparing MCP Server Parameters...")
    server_params = StdioServerParameters(
        command="python",
        args=["custom_blender_mcp.py"],
        env={**os.environ, "BLENDER_MCP_AUTH_TOKEN": "kaggle-secret-token"}
    )
    
    print("[2] Spawning custom_blender_mcp.py as Stdio Server... (This will launch Blender)")
    start_time = time.time()
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            print("[3] Initializing MCP Session...")
            await session.initialize()
            print(f"[+] MCP Session Ready in {time.time() - start_time:.2f}s")
            
            print("[4] Calling asset_fetcher tool via MCP...")
            result = await session.call_tool("asset_fetcher", {"asset_query": "wooden table"})
            
            print("[5] Raw Result from Blender MCP:")
            print(result)

if __name__ == "__main__":
    asyncio.run(run())
