import sys
import os
import json
import subprocess
import struct
import threading
import concurrent.futures
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("BlenderOfficialBridge")

# Global Process Manager
BLENDER_PROCESS = None
IPC_LOCK = threading.Lock()

def get_blender_process():
    """
    Get or create the secure Blender subprocess.
    
    Design: Implements an isolated IPC subprocess (Zero Ambient Authority sandbox)
    to safely interact with Blender via Stdio. Bypasses WebSocket vulnerabilities.
    
    Behavior: Spawns the Blender 5.1.1 executable in the background (or foreground based
    on config). Ensures only one process runs at a time and returns it.
    
    Args:
        None
        
    Returns:
        subprocess.Popen: The active Blender subprocess handle.
    """
    global BLENDER_PROCESS
    if BLENDER_PROCESS is None or BLENDER_PROCESS.poll() is not None:
        default_blender = r"D:\blender\blender-5.1.1-windows-x64\blender-5.1.1-windows-x64\blender.exe"
        if not os.path.exists(default_blender):
            default_blender = "blender"
        blender_exe = os.environ.get("BLENDER_BIN", default_blender)
        cmd_args = [blender_exe, "--factory-startup"]
        
        # Phase 7: Load config for --background flag and .blend file
        try:
            with open("blender_mcp_config.json", "r", encoding="utf-8") as f:
                config = json.load(f)
                for arg in config.get("args", []):
                    if arg not in cmd_args:
                        cmd_args.append(arg)
                if config.get("background", False):
                    if "--background" not in cmd_args:
                        cmd_args.append("--background")
        except (FileNotFoundError, json.JSONDecodeError):
            pass
            
        cmd_args.extend(['--python', 'blender_scripts/mcp_bridge.py'])
        
        with open("blender_launch_log.txt", "w") as lf:
            lf.write(f"Launch args: {cmd_args}\n")
            
        BLENDER_PROCESS = subprocess.Popen(
            cmd_args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Wait for MCP_READY token to bypass Blender's startup banner
        while True:
            line = BLENDER_PROCESS.stdout.readline()
            if not line:
                break
            if b"MCP_READY" in line:
                break
                
    return BLENDER_PROCESS

def send_to_blender(tool_name: str, params: dict) -> str:
    """
    Send an RPC request to the Blender subprocess securely over Stdio.
    
    Design: Implements custom message framing (4-byte length header + JSON payload)
    and uses a thread lock to prevent concurrent FastMCP calls from scrambling the IPC pipe.
    
    Behavior: Packages the tool name and arguments, writes to stdin, and waits
    up to 3600 seconds for the stdout response. Applies DoS protection via timeout.
    
    Args:
        tool_name: The target MCP tool identifier inside the Blender bridge.
        params: The JSON-serializable parameters dictionary.
        
    Returns:
        JSON string representing the tool result or an error trace.
    """
    AUTH_TOKEN = os.environ.get("BLENDER_MCP_AUTH_TOKEN")
    if not AUTH_TOKEN:
        return json.dumps({"status": "error", "message": "SecurityError: BLENDER_MCP_AUTH_TOKEN environment variable is missing (CWE-798)"})
        
    request = {
        "tool": tool_name,
        "params": params,
        "auth_token": AUTH_TOKEN,
    }
    req_json = json.dumps(request).encode("utf-8")
    req_bytes = struct.pack('>I', len(req_json)) + req_json
    
    # Phase 10: Serialize all stdio operations to prevent concurrency interleaving in FastMCP
    with IPC_LOCK:
        proc = get_blender_process()
        
        try:
            proc.stdin.write(req_bytes)
            proc.stdin.flush()
        except Exception as e:
            return json.dumps({"status": "error", "message": f"Failed to send command to Blender: {str(e)}"})
            
        def read_response():
            raw_len = proc.stdout.read(4)
            if not raw_len or len(raw_len) < 4:
                return None, b""
            mlen = struct.unpack('>I', raw_len)[0]
            b = bytearray()
            while len(b) < mlen:
                c = proc.stdout.read(min(4096, mlen - len(b)))
                if not c: break
                b.extend(c)
            return mlen, b
            
        # Phase 11: Deadlock Prevention via ThreadPoolExecutor Timeout
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            try:
                future = executor.submit(read_response)
                msglen, buf = future.result(timeout=3600) # 60 mins timeout
            except concurrent.futures.TimeoutError:
                proc.kill()
                global BLENDER_PROCESS
                BLENDER_PROCESS = None
                return json.dumps({"status": "error", "message": "TimeoutError: Blender process deadlocked or exceeded 3600s limit. IPC_LOCK released."})
                
        if msglen is None:
            return json.dumps({"status": "error", "message": "Failed to receive length header from Blender MCP over Stdio"})
        if len(buf) != msglen:
            return json.dumps({"status": "error", "message": "Incomplete response payload from Blender MCP over Stdio"})
            
        try:
            resp = json.loads(buf.decode("utf-8", errors="replace"))
        except json.JSONDecodeError as e:
            # Phase 7/9: FastMCP DoS Protection (CVE-2025-53366) - Return JSON instead of raising exception
            return json.dumps({"status": "error", "message": f"Failed to decode JSON from Blender MCP: {e}. Raw payload preview: {buf[:100]}..."})
                
        if resp.get("status") == "ok":
            return json.dumps(resp.get("result", {}))
        else:
            err = resp.get("message", "Unknown error")
            return json.dumps({"status": "error", "message": f"Blender Error: {err}\nStdout: {resp.get('stdout', '')}\nStderr: {resp.get('stderr', '')}"})

@mcp.tool()
def hdri_setup(environment_type: str) -> str:
    """
    Fetches and applies an HDRI lighting setup from Poly Haven.
    Args:
        environment_type: A short string of comma-separated tags (e.g. 'sunset,outdoor').
    """
    return send_to_blender("hdri_setup", {"ENV_QUERY": environment_type})

@mcp.tool()
def asset_fetcher(asset_query: str) -> str:
    """
    Fetches and imports a 3D model from Poly Haven based on query.
    CRITICAL: DO NOT use this for ground, floors, or textures (use material_setup instead).
    Args:
        asset_query: Keywords to search for. DO NOT combine multiple objects with commas. For multiple objects, call this tool multiple times in parallel.
    """
    return send_to_blender("asset_fetcher", {"ASSET_QUERY": asset_query})

@mcp.tool()
def auto_layout() -> str:
    """
    Arranges all top-level mesh objects in the scene into a grid.
    """
    return send_to_blender("auto_layout", {})

@mcp.tool()
def material_setup(material_type: str) -> str:
    """
    Fetches a PBR texture from Poly Haven and applies it to a 50x50m ground plane.
    CRITICAL: USE THIS TOOL for ANY request about floors, ground, roads, or paving materials.
    Args:
        material_type: A short string of comma-separated tags (e.g. 'asphalt', 'wood').
    """
    return send_to_blender("material_setup", {"MATERIAL_TYPE": material_type})

@mcp.tool()
def fetch_scene_context() -> str:
    """
    Fetch objects and materials from Blender scene for context.
    """
    return send_to_blender("fetch_scene_context", {})

if __name__ == "__main__":
    mcp.run(transport='stdio')
