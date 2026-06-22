"""
Blender Scene Assembler Agent — Security utilities.

Design: Implements Zero Ambient Authority principle from Day 4 of the
Kaggle AI Agents Vibe Coding Course. Agents must never inherit ambient
filesystem permissions; all access must be explicitly scoped.

All path validation must pass before any file I/O or Blender object access.
"""

import os
from pathlib import Path

# File-tree allowlist: ONLY these directories are accessible by any agent action.
# This prevents prompt injection attacks from directing the agent to read
# sensitive files (e.g., ~/.ssh, system configs, credential stores).
# Dynamically mapped to support both Linux and Windows environments (CWE Fix).
_model_dirs_env = os.environ.get("BLENDER_MODEL_DIRS", r"D:\blender\model;D:\blender\vmd;D:\blender\temp_assets;./temp_assets")
_sep = os.pathsep
_skills_dir = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".agent", "skills"))
ALLOWED_MODEL_PATHS: list[str] = [
    os.path.realpath(p.strip()) 
    for p in _model_dirs_env.split(_sep) 
    if p.strip()
] + [_skills_dir]


ALLOWED_EXTENSIONS = ['.gltf', '.glb', '.bin', '.jpg', '.png', '.exr', '.hdr']

def validate_path(path: str) -> bool:
    """
    Enforce Zero Ambient Authority: validate path is within allowed directories
    and enforce extension whitelisting to prevent malicious file writes.

    Behavior: Returns False for any path outside ALLOWED_MODEL_PATHS, even
    if the operating system would permit access. This is a defense-in-depth
    measure against prompt injection and path traversal attacks.

    Args:
        path: Absolute filesystem path to validate

    Returns:
        True if path is within an allowed directory and has a valid extension, False otherwise
    """
    try:
        resolved_target = Path(os.path.realpath(path))
        
        # Check if it's inside allowed directory
        is_allowed_dir = any(resolved_target.is_relative_to(Path(os.path.realpath(allowed))) for allowed in ALLOWED_MODEL_PATHS)
        if not is_allowed_dir:
            return False
            
        # Check if it's a file with an extension, then check whitelist
        if resolved_target.suffix:
            if resolved_target.suffix.lower() not in ALLOWED_EXTENSIONS:
                return False
                
        return True
    except Exception:
        return False


def require_valid_path(path: str) -> None:
    """
    Raise ValueError if path is outside the allowlist.

    Design: Use this as a guard at the entry point of any function that
    performs file I/O, so security enforcement is consistent and explicit.

    Args:
        path: Absolute filesystem path to check

    Raises:
        ValueError: If path is not within an allowed directory
    """
    if not validate_path(path):
        raise ValueError(
            f"Security: Path '{path}' is outside the allowed directories. "
            f"Allowed: {ALLOWED_MODEL_PATHS}"
        )

import re

def validate_object_name(name: str) -> bool:
    """
    Validate Blender object name to prevent CWE-94 code injection.
    
    Design: Secures the MCP Bridge against prompt injection and arbitrary
    code execution when object names are interpolated into Python scripts.
    
    Behavior: Ensures the name only contains alphanumeric characters,
    underscores, Chinese characters, Japanese (Hiragana/Katakana),
    periods, and dashes (to support asset naming conventions like table_01.L).
    
    Args:
        name: The name of the Blender object to validate.
        
    Returns:
        True if the object name is safe, False otherwise.
    """
    if not isinstance(name, str):
        return False
    # Strictly allow only standard safe characters
    return bool(re.match(r'^[\w\u4e00-\u9fa5\u3040-\u309f\u30a0-\u30ff\.\-]+$', name))

def require_valid_object_name(name: str) -> None:
    """
    Raise ValueError if object name contains illegal characters.
    
    Design: Acts as a security guard at the entry point of string interpolation.
    
    Behavior: Calls validate_object_name and raises an exception if it fails,
    terminating the MCP request before it reaches the Blender interpreter.
    
    Args:
        name: The name of the Blender object to validate.
        
    Raises:
        ValueError: If the object name is invalid.
    """
    if not validate_object_name(name):
        raise ValueError(f"Security: Object name '{name}' contains illegal characters.")
