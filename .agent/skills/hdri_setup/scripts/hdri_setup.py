import urllib.request
import json
import os
import sys
from urllib.parse import urlparse
try:
    import bpy
except ImportError:
    pass

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")))
try:
    from agents.security import require_valid_path
except ImportError:
    ALLOWED_EXTENSIONS = ['.gltf', '.glb', '.jpg', '.png', '.exr', '.hdr']
    def require_valid_path(path: str):
        if not any(path.endswith(ext) for ext in ALLOWED_EXTENSIONS):
            raise ValueError(f"Security: Extension not allowed: {path}")

# ==========================================
# Egress Governance: Network Allowlist
# ==========================================
ALLOWED_DOMAINS = [
    "api.polyhaven.com",
    "cdn.polyhaven.com",
    "dl.polyhaven.org"
]

def secure_request(url: str) -> dict:
    parsed = urlparse(url)
    if parsed.netloc not in ALLOWED_DOMAINS:
        raise ValueError(f"Security: Network egress to {parsed.netloc} is blocked by Zero Trust policies.")
    
    headers = {'User-Agent': 'BlenderSceneAssembler/1.0 (Kaggle2026)'}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as response:
        try:
            return json.loads(response.read().decode('utf-8'))
        except json.JSONDecodeError:
            raise ValueError("[Error] 外部 API 回傳無效的格式，可能伺服器正在維修或遇到網路阻擋。請告訴使用者稍後再試，或嘗試其他搜尋關鍵字。")

def download_file(url: str, dest_dir: str, file_name: str, max_retries: int = 3) -> str:
    """
    Download a file with retry/backoff and explicit timeout.
    Uses stdlib only (compatible with Blender's embedded Python).

    Design: Retry on transient network errors with exponential backoff.
    Args:
        url:         CDN URL (must be in ALLOWED_DOMAINS).
        dest_dir:    Target directory (must be inside temp_assets).
        file_name:   Final filename.
        max_retries: Number of retry attempts before giving up.
    Returns:
        Absolute path to the downloaded file.
    """
    import time
    parsed = urlparse(url)
    if parsed.netloc not in ALLOWED_DOMAINS:
        raise ValueError(f"Security: Network egress to {parsed.netloc} is blocked.")

    safe_name = os.path.basename(file_name)
    dest_path = os.path.abspath(os.path.join(dest_dir, safe_name))
    require_valid_path(dest_path)

    headers = {'User-Agent': 'BlenderSceneAssembler/1.0 (Kaggle2026)'}
    last_exc = None
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as response, \
                 open(dest_path, 'wb') as out_file:
                out_file.write(response.read())
            return dest_path
        except Exception as exc:
            last_exc = exc
            wait = 2 ** attempt  # exponential backoff: 1s, 2s, 4s
            print(f"[HDRI Setup] Download attempt {attempt + 1}/{max_retries} failed: {exc}. Retrying in {wait}s...")
            time.sleep(wait)

    raise RuntimeError(f"Download failed after {max_retries} attempts: {last_exc}")

def setup_blender_world(hdri_path: str):
    """Setup Blender world nodes to use the downloaded HDRI."""
    world = bpy.context.scene.world
    if not world:
        world = bpy.data.worlds.new("World")
        bpy.context.scene.world = world
    
    world.use_nodes = True
    tree = world.node_tree
    nodes = tree.nodes
    links = tree.links
    
    # Clear existing nodes
    nodes.clear()
    
    # Create required nodes
    node_background = nodes.new(type='ShaderNodeBackground')
    node_environment = nodes.new(type='ShaderNodeTexEnvironment')
    node_output = nodes.new(type='ShaderNodeOutputWorld')
    
    # Load HDRI image
    try:
        img = bpy.data.images.load(hdri_path)
        node_environment.image = img
    except Exception as e:
        print(f"Error loading HDRI image into Blender: {e}")
        return
        
    # Link nodes
    links.new(node_environment.outputs["Color"], node_background.inputs["Color"])
    links.new(node_background.outputs["Background"], node_output.inputs["Surface"])
    
    # Set viewport to rendered mode to see the effect (if in context)
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    space.shading.type = 'RENDERED'
    print("HDRI setup applied to World Node.")

def fetch_and_apply_hdri(query: str):
    print(f"[HDRI Setup] Searching Poly Haven for: {query}")
    
    # 1. Search Poly Haven API locally by fetching the catalog
    catalog_url = "https://api.polyhaven.com/assets?type=hdris"
    try:
        assets = secure_request(catalog_url)
    except Exception as e:
        print(f"Error connecting to Poly Haven: {e}")
        return

    # 1. 過濾停用詞 (Stop Words Filter)
    stop_words = {"a", "an", "the", "of", "in", "with", "pile", "large", "small", "old", "vintage", "some", "many"}
    all_query_words = [q.lower() for q in query.replace(',', ' ').split()]
    query_words = [q for q in all_query_words if q not in stop_words]
    
    # 防呆：如果全被過濾光了，就用原來的
    if not query_words:
        query_words = all_query_words

    core_noun = query_words[-1] if query_words else ""
    best_match_id = None
    best_score = -1
    
    def is_exact_match(word, corpus_list):
        word_s = word + 's'
        word_es = word + 'es'
        return any(word == item or word_s == item or word_es == item for item in corpus_list)

    for asset_id, data in assets.items():
        score = 0
        
        # 標籤拆詞處理
        raw_tags = data.get("tags", []) + data.get("categories", [])
        corpus_words = []
        for tag in raw_tags:
            corpus_words.extend(tag.lower().replace('-', ' ').replace('_', ' ').split())
        
        asset_id_lower = asset_id.lower()
        id_words = asset_id_lower.replace('-', ' ').replace('_', ' ').split()
        corpus_words.extend(id_words)
        
        # 2. 精確單字配對 (Exact Word Matching)
        for qw in query_words:
            if is_exact_match(qw, corpus_words):
                score += 1
                
        # 3. 核心名詞加權 (Core Noun Boosting)
        # 如果核心名詞直接出現在 asset_id 裡面，給予極大加權！
        if is_exact_match(core_noun, id_words):
            score += 5
                
        if score > best_score and score > 0:
            best_score = score
            best_match_id = asset_id

    if not best_match_id:
        print("Error: Poly Haven does not contain HDRI assets matching this query. Please try different keywords.")
        return
        
    asset_id = best_match_id
    print(f"[HDRI Setup] Found matching HDRI: {asset_id}")
    
    files_url = f"https://api.polyhaven.com/files/{asset_id}"
    try:
        files_data = secure_request(files_url)
    except Exception as e:
        print(str(e))
        return
    
    if "hdri" not in files_data or not files_data["hdri"]:
        print(f"[Error] 資產 '{asset_id}' 不支援 HDRI 格式，無法作為環境光源。請嘗試搜尋其他場景。")
        return
        
    hdri_resolutions = files_data["hdri"]
    res_key = "2k"
    if res_key not in hdri_resolutions:
        res_key = list(hdri_resolutions.keys())[0]
        
    # For HDRIs, prefer .hdr format
    target_data = hdri_resolutions[res_key]
    format_key = "hdr"
    if format_key not in target_data:
        format_key = list(target_data.keys())[0]
        
    hdri_url = target_data[format_key]["url"]
    
    temp_dir = os.path.abspath(os.path.join(os.environ.get("TEMP_ASSETS_DIR", "./temp_assets"), asset_id))
    os.makedirs(temp_dir, exist_ok=True)
    
    print(f"[HDRI Setup] Downloading {asset_id} ({res_key} {format_key})...")
    hdri_filename = os.path.basename(urlparse(hdri_url).path)
    local_hdri_path = download_file(hdri_url, temp_dir, hdri_filename)
    
    print(f"[HDRI Setup] Download complete. Applying to World...")
    setup_blender_world(local_hdri_path)
    print(f"已成功套用 HDRI {asset_id} 作為環境光源")

if __name__ == "__main__":
    try:
        ENV_QUERY = MCP_PARAMS.get("ENV_QUERY", "")
    except NameError:
        ENV_QUERY = "{{environment_type}}"
        
    cleaned_query = ",".join([q.strip() for q in ENV_QUERY.split(",") if q.strip()])
    if cleaned_query:
        fetch_and_apply_hdri(cleaned_query)
    else:
        print("Error: No environment query provided.")
