import urllib.request
import json
import os
import sys
from urllib.parse import urlparse
try:
    import bpy
except ImportError:
    pass

# We import security rules from the agent's package if possible,
# otherwise we rely on the strict hardcoded rules below.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")))
try:
    from agents.security import require_valid_path
except ImportError:
    # Minimal fallback implementation if executed directly
    ALLOWED_EXTENSIONS = ['.gltf', '.glb', '.bin', '.jpg', '.png', '.exr', '.hdr']
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
    """Make an HTTP GET request to allowed domains only."""
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
            # timeout=(connect_s, read_s) — prevents hanging on a stalled CDN
            with urllib.request.urlopen(req, timeout=30) as response, \
                 open(dest_path, 'wb') as out_file:
                out_file.write(response.read())
            return dest_path
        except Exception as exc:
            last_exc = exc
            wait = 2 ** attempt  # exponential backoff: 1s, 2s, 4s
            print(f"[Asset Fetcher] Download attempt {attempt + 1}/{max_retries} failed: {exc}. Retrying in {wait}s...")
            time.sleep(wait)

    raise RuntimeError(f"Download failed after {max_retries} attempts: {last_exc}")

def fetch_and_import_asset(query: str):
    print(f"[Asset Fetcher] Searching Poly Haven for: {query}")
    
    # 1. Search Poly Haven API locally by fetching the catalog
    catalog_url = "https://api.polyhaven.com/assets?type=models"
    try:
        assets = secure_request(catalog_url)
    except Exception as e:
        print(f"Error connecting to Poly Haven: {e}")
        return

    # Comma Interceptor (Runtime Guardrail)
    if ',' in query:
        print("Error: Do not use commas to request multiple assets. Please call this tool multiple times, once for each distinct object.")
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
        print("Error: Poly Haven does not contain assets matching this query. Please try different keywords.")
        return
        
    # Strict Validation (Solution A)
    best_data = assets[best_match_id]
    best_corpus = " ".join([best_match_id.lower()] + [t.lower() for t in best_data.get("tags", [])] + [c.lower() for c in best_data.get("categories", [])])
    
    core_noun = query_words[-1] # Usually the last word is the main noun
    
    # Anti-Debris Guard
    negative_keywords = ["debris", "garbage", "rubble", "trash", "scatter", "litter"]
    if any(neg in best_match_id.lower() for neg in negative_keywords) and not any(neg in query.lower() for neg in negative_keywords):
        print(f"Error: Found '{best_match_id}' but it failed strict validation. Poly Haven likely doesn't have the full object, only debris. Please try a different query.")
        return

    # Dependency-Free strict validation to prevent substring hallucination in sandbox
    def is_exact_word(word, text):
        for char in ".,;:!?'\\\"()[]{}<>-=_+*&^%$#@`~|/\\\\":
            text = text.replace(char, ' ')
        words = text.split()
        return word in words or (word + 's') in words or (word + 'es') in words

    if not is_exact_word(core_noun, best_corpus):
        print(f"Error: Found '{best_match_id}' but it failed strict validation. It does not appear to be a '{core_noun}'. Please try a different query.")
        return
    asset_id = best_match_id
    print(f"[Asset Fetcher] Found matching asset: {asset_id}")
    
    # 2. Get file details
    files_url = f"https://api.polyhaven.com/files/{asset_id}"
    try:
        files_data = secure_request(files_url)
    except Exception as e:
        print(str(e))
        return
    
    if "gltf" not in files_data or not files_data["gltf"]:
        print(f"[Error] 資產 '{asset_id}' 不支援 GLTF 格式，無法匯入 Blender。請放棄此物件，或嘗試搜尋其他替代物品。")
        return
        
    gltf_resolutions = files_data["gltf"]
    # Prefer 2k resolution, fallback to the lowest available to save bandwidth
    res_key = "2k"
    if res_key not in gltf_resolutions:
        res_key = list(gltf_resolutions.keys())[0]
        
    target_data = gltf_resolutions[res_key]["gltf"]
    gltf_url = target_data["url"]
    
    # 3. Create sandbox directory
    temp_dir = os.path.abspath(os.path.join(os.environ.get("TEMP_ASSETS_DIR", "./temp_assets"), asset_id))
    os.makedirs(temp_dir, exist_ok=True)
    
    # 4. Download main gltf/glb file
    print(f"[Asset Fetcher] Downloading {asset_id} ({res_key})...")
    gltf_filename = os.path.basename(urlparse(gltf_url).path)
    local_gltf_path = download_file(gltf_url, temp_dir, gltf_filename)
    
    # 5. Download included textures (Dependencies)
    if "include" in target_data:
        includes = target_data["include"]
        for include_path, include_info in includes.items():
            inc_url = include_info["url"]
            # Preserve relative paths (e.g. textures/diffuse.jpg) for GLTF to find them
            inc_dest_dir = os.path.abspath(os.path.join(temp_dir, os.path.dirname(include_path)))
            os.makedirs(inc_dest_dir, exist_ok=True)
            download_file(inc_url, inc_dest_dir, os.path.basename(include_path))
            
    print(f"[Asset Fetcher] Download complete. Importing into Blender...")
    
    # 6. Import into Blender
    try:
        # Pre-import: Clean up default objects (Double Redundancy)
        for obj_name in ["Cube", "Camera", "Light"]:
            if obj_name in bpy.data.objects:
                bpy.data.objects.remove(bpy.data.objects[obj_name], do_unlink=True)
                
        # Pre-import: Record existing objects
        existing_objs = set(bpy.context.scene.objects)
        
        bpy.ops.import_scene.gltf(filepath=local_gltf_path)
        
        # Post-import: Group new objects under an Empty
        new_objs = set(bpy.context.scene.objects) - existing_objs
        if new_objs:
            bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0, 0, 0))
            group_empty = bpy.context.active_object
            group_empty.name = f"{asset_id}_Group"
            
            for obj in new_objs:
                if not obj.parent and obj != group_empty:
                    obj.parent = group_empty
                    obj.matrix_parent_inverse = group_empty.matrix_world.inverted()
                    
        print(f"已成功匯入 {asset_id}，位於座標 (0,0,0)")
    except Exception as e:
        print(f"Error importing GLTF into Blender: {e}")

if __name__ == "__main__":
    try:
        ASSET_QUERY = MCP_PARAMS.get("ASSET_QUERY", "")
    except NameError:
        # Fallback if run directly outside of the secure bridge
        ASSET_QUERY = "{{asset_query}}"
        
    cleaned_query = ",".join([q.strip() for q in ASSET_QUERY.split(",") if q.strip()])
    if cleaned_query:
        fetch_and_import_asset(cleaned_query)
    else:
        print("Error: No asset query provided.")
