import sys
import json
import ast
import traceback
import io
import contextlib
import struct
import threading
import queue
import os

# Phase 9: SafeASTVisitor to prevent __subclasses__ escape
class SafeASTVisitor(ast.NodeVisitor):
    def visit_Attribute(self, node):
        if node.attr in ('__class__', '__subclasses__', '__bases__', '__mro__', '__globals__'):
            raise Exception(f"SecurityError: Blocked AST Sandbox Escape vector: {node.attr}")
        self.generic_visit(node)
        
    def visit_Name(self, node):
        if node.id in ('eval', 'exec', 'compile', 'getattr', 'setattr', 'delattr'):
            raise Exception(f"SecurityError: Blocked dynamic execution function: {node.id}")
        self.generic_visit(node)

# Phase 8: Mute Blender OS-level stdout completely to prevent C-level warnings corrupting JSON IPC
try:
    original_stdout_fd = os.dup(1)
    real_stdout = os.fdopen(original_stdout_fd, 'wb')
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull_fd, 1)
    os.dup2(devnull_fd, 2)
except Exception:
    real_stdout = sys.__stdout__.buffer

sys.stdout = open(os.devnull, 'w')
sys.stderr = open(os.devnull, 'w')

stdout_lock = threading.Lock()

def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    allowed_modules = ["bpy", "bmesh", "mathutils", "mathutils.bvhtree", "json", "math", "typing", 
                       "urllib", "urllib.request", "urllib.parse", "urllib.error", "os", "sys"]
    if name in allowed_modules:
        return __import__(name, globals, locals, fromlist, level)
    raise ImportError(f"Security: Importing module '{name}' is forbidden by Zero Ambient Authority policy.")

def safe_stdout_write(response_bytes: bytes):
    with stdout_lock:
        try:
            real_stdout.write(struct.pack('>I', len(response_bytes)))
            real_stdout.write(response_bytes)
            real_stdout.flush()
        except Exception:
            pass

try:
    import bpy
except ImportError:
    bpy = None  # For testing outside Blender

class SecurityError(Exception):
    pass

def execute_securely(request: dict) -> dict:
    try:
        # 0. Ephemeral Sandboxing (Clear orphans to prevent cross-tenant pollution)
        if bpy:
            try:
                bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
            except Exception:
                pass
                
        # 1. Parameterized Tool Execution (CWE-94 Fix)
        tool = request.get("tool")
        params = request.get("params", {})
        
        import os
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if base_dir not in sys.path:
            sys.path.insert(0, base_dir)
        from agents.security import require_valid_path
        
        if tool == "fetch_scene_context":
            code_str = "import bpy\nimport json\nresult = {'objects': [o.name for o in bpy.data.objects], 'materials': [m.name for m in bpy.data.materials]}\nprint(json.dumps(result))"
            script_path = "<fetch_scene_context_skill>"
        elif tool == "hdri_setup":
            script_path = os.path.join(base_dir, ".agent", "skills", "hdri_setup", "scripts", "hdri_setup.py")
            require_valid_path(os.path.dirname(script_path)) # Validate agent skill directory is safe
            with open(script_path, "r", encoding="utf-8") as f:
                code_str = f.read()
        elif tool == "asset_fetcher":
            script_path = os.path.join(base_dir, ".agent", "skills", "asset_fetcher", "scripts", "asset_fetcher.py")
            require_valid_path(os.path.dirname(script_path)) # Validate agent skill directory is safe
            with open(script_path, "r", encoding="utf-8") as f:
                code_str = f.read()
        elif tool == "auto_layout":
            script_path = os.path.join(base_dir, ".agent", "skills", "auto_layout", "scripts", "layout_engine.py")
            require_valid_path(os.path.dirname(script_path)) # Validate agent skill directory is safe
            with open(script_path, "r", encoding="utf-8") as f:
                code_str = f.read()
        elif tool == "material_setup":
            script_path = os.path.join(base_dir, ".agent", "skills", "material_setup", "scripts", "material_setup.py")
            require_valid_path(os.path.dirname(script_path)) # Validate agent skill directory is safe
            with open(script_path, "r", encoding="utf-8") as f:
                code_str = f.read()
        else:
            return {"status": "error", "message": f"Unknown tool '{tool}'"}
            
        # Phase 8: Delete dangerous bpy attributes to prevent Sandbox Escape
        if bpy:
            try:
                if hasattr(bpy.ops, 'wm') and hasattr(bpy.ops.wm, 'url_open'):
                    delattr(bpy.ops.wm, 'url_open')
            except AttributeError:
                pass
            try:
                if hasattr(bpy.app, 'driver_namespace'):
                    bpy.app.driver_namespace.clear()
            except AttributeError:
                pass
            
        # 2. Build Safe Globalstricted globals
        safe_globals = {
            "__builtins__": {
                "print": print,
                "len": len,
                "range": range,
                "int": int,
                "float": float,
                "str": str,
                "bool": bool,
                "list": list,
                "dict": dict,
                "tuple": tuple,
                "set": set,
                "max": max,
                "min": min,
                "any": any,
                "all": all,
                "isinstance": isinstance,
                "open": open,
                "Exception": Exception,
                "ValueError": ValueError,
                "ImportError": ImportError,
                "enumerate": enumerate,
                "reversed": reversed,
                "sum": sum,
                "__import__": safe_import,
            },
            # Allow whitelisted modules to be accessed directly if imported
            "__name__": "__main__",
            "__file__": script_path,
            "bpy": __import__("bpy"),
            "bmesh": __import__("bmesh"),
            "mathutils": __import__("mathutils"),
            "json": __import__("json"),
            "math": __import__("math"),
            "typing": __import__("typing"),
            "MCP_PARAMS": params,  # CWE-94 & Template Injection Fix: Pass dict natively
        }
        
        # 3. Compile and exec inside a captured stdout context
        # Phase 9: Parse AST and strictly validate nodes to prevent Sandbox Escapes (CWE-94)
        tree = ast.parse(code_str, filename=script_path)
        SafeASTVisitor().visit(tree)
        
        compiled_code = compile(tree, filename=script_path, mode="exec")
        
        stdout_capture = io.StringIO()
        with contextlib.redirect_stdout(stdout_capture):
            exec(compiled_code, safe_globals)
            
        output = stdout_capture.getvalue()
        
        # Check if the script registered an async generator for yielding
        if "SKILL_GENERATOR" in safe_globals:
            return {
                "status": "async_generator",
                "generator": safe_globals["SKILL_GENERATOR"]
            }
        
        # The result from the script is often printed as a JSON string on the last line
        lines = [line.strip() for line in output.split('\n') if line.strip()]
        result_data = {}
        if lines:
            try:
                # Try to parse the last line as JSON result
                result_data = json.loads(lines[-1])
                stdout_text = "\n".join(lines[:-1])
            except json.JSONDecodeError:
                stdout_text = output
        else:
            stdout_text = ""
            
        return {
            "status": "ok",
            "result": result_data if result_data else stdout_text,
            "stdout": stdout_text,
            "stderr": ""
        }
        
    except SecurityError as e:
        return {"status": "error", "message": f"Security Exception: {str(e)}", "stdout": "", "stderr": traceback.format_exc()}
    except Exception as e:
        return {"status": "error", "message": f"Execution Exception: {str(e)}", "stdout": "", "stderr": traceback.format_exc()}


execution_queue = queue.Queue()
active_generator = None

def process_queue():
    global active_generator
    
    # Process the active async generator to yield to the UI main loop
    if active_generator is not None:
        try:
            # Execute one step of the generator
            result = next(active_generator)
            return 0.01  # Yield for 10ms to let Blender UI update and rotate viewport!
        except StopIteration as e:
            # Generator finished, get the final returned response
            final_response = e.value
            if not isinstance(final_response, dict):
                final_response = {"status": "error", "message": "Generator did not return a dict"}
            response_bytes = json.dumps(final_response).encode("utf-8")
            safe_stdout_write(response_bytes)
            active_generator = None
            return 0.1
        except Exception as e:
            err_response = {"status": "error", "message": f"Generator execution failed: {str(e)}", "stderr": traceback.format_exc()}
            safe_stdout_write(json.dumps(err_response).encode("utf-8"))
            active_generator = None
            return 0.1

    if not execution_queue.empty():
        request = execution_queue.get()
        try:
            response = execute_securely(request)
            if response.get("status") == "async_generator":
                active_generator = response["generator"]
                return 0.01  # Start processing generator next tick
        except Exception as e:
            response = {"status": "error", "message": f"Server error: {str(e)}"}
        
        # If it was a synchronous response, send it immediately
        if response.get("status") != "async_generator":
            response_bytes = json.dumps(response).encode("utf-8")
            safe_stdout_write(response_bytes)
            
    return 0.1  # Run again in 0.1 seconds

def stdin_listener():
    import os
    AUTH_TOKEN = os.environ.get("BLENDER_MCP_AUTH_TOKEN")
    while True:
        try:
            # 1. Read exactly 4 bytes for length prefix (Stdio Desync Fix)
            raw_msglen = sys.stdin.buffer.read(4)
            if not raw_msglen or len(raw_msglen) < 4:
                break  # EOF reached
            msglen = struct.unpack('>I', raw_msglen)[0]
            
            # 2. OOM DoS Protection (10MB Limit) & Proper Drain (CWE-400)
            if msglen > 10 * 1024 * 1024:
                bytes_to_read = msglen
                while bytes_to_read > 0:
                    chunk = sys.stdin.buffer.read(min(bytes_to_read, 4096))
                    if not chunk:
                        break
                    bytes_to_read -= len(chunk)
                response = {"status": "error", "message": "SecurityError: Payload exceeds 10MB limit (OOM DoS Protection)"}
                safe_stdout_write(json.dumps(response).encode("utf-8"))
                continue
            
            # 3. Read exactly msglen bytes for payload
            buf = bytearray()
            while len(buf) < msglen:
                chunk = sys.stdin.buffer.read(min(4096, msglen - len(buf)))
                if not chunk:
                    break
                buf.extend(chunk)
                
            if len(buf) == msglen:
                request = json.loads(buf.decode("utf-8"))
                
                # 4. Authenticate (CWE-798 & CWE-306 Fix)
                if not AUTH_TOKEN or request.get("auth_token") != AUTH_TOKEN:
                    response = {"status": "error", "message": "Unauthorized: Invalid or missing auth_token"}
                    safe_stdout_write(json.dumps(response).encode("utf-8"))
                else:
                    execution_queue.put(request)
            else:
                pass  # Incomplete payload
        except json.JSONDecodeError:
            response = {"status": "error", "message": "Invalid JSON request"}
            safe_stdout_write(json.dumps(response).encode("utf-8"))
        except Exception:
            pass  # Silent fail on thread to keep it alive

def start_stdio_bridge():
    if bpy:
        bpy.app.timers.register(process_queue)
    
    # Write a sync token so the parent process can skip the Blender banner
    with stdout_lock:
        try:
            real_stdout.write(b"MCP_READY\n")
            real_stdout.flush()
        except Exception:
            pass
        
    # Start background listener thread
    listener_thread = threading.Thread(target=stdin_listener, daemon=True)
    listener_thread.start()
    
    if bpy and bpy.app.background:
        import time
        while listener_thread.is_alive():
            process_queue()
            time.sleep(0.01)

if __name__ == "__main__":
    start_stdio_bridge()
