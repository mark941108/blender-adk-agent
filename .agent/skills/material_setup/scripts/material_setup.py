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
    ALLOWED_EXTENSIONS = ['.gltf', '.glb', '.bin', '.jpg', '.png', '.exr', '.hdr']
    def require_valid_path(path: str):
        if not any(path.endswith(ext) for ext in ALLOWED_EXTENSIONS):
            raise ValueError(f"Security: Extension not allowed: {path}")

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
        return json.loads(response.read().decode('utf-8'))

def download_file(url: str, dest_dir: str, file_name: str) -> str:
    parsed = urlparse(url)
    if parsed.netloc not in ALLOWED_DOMAINS:
        raise ValueError(f"Security: Network egress to {parsed.netloc} is blocked.")
    
    safe_name = os.path.basename(file_name)
    dest_path = os.path.abspath(os.path.join(dest_dir, safe_name))
    require_valid_path(dest_path)
    
    req = urllib.request.Request(url, headers={'User-Agent': 'BlenderSceneAssembler/1.0 (Kaggle2026)'})
    with urllib.request.urlopen(req) as response, open(dest_path, 'wb') as out_file:
        out_file.write(response.read())
        
    return dest_path

def setup_ground_material(query: str):
    print(f"[Material Setup] Searching Poly Haven for: {query}")
    
    catalog_url = "https://api.polyhaven.com/assets?type=textures"
    try:
        assets = secure_request(catalog_url)
    except Exception as e:
        print(f"Error connecting to Poly Haven: {e}")
        return

    query_words = [q.lower() for q in query.replace(',', ' ').split()]
    best_match_id = None
    best_score = -1
    
    for asset_id, data in assets.items():
        score = 0
        tags = [t.lower() for t in data.get("tags", [])]
        categories = [c.lower() for c in data.get("categories", [])]
        search_corpus = " ".join([asset_id.lower()] + tags + categories)
        
        for qw in query_words:
            if qw in search_corpus:
                score += 1
                
        if score > best_score and score > 0:
            best_score = score
            best_match_id = asset_id

    if not best_match_id:
        print("Error: Poly Haven does not contain textures matching this query.")
        return
        
    # Strict Validation (Solution A)
    best_data = assets[best_match_id]
    best_corpus = " ".join([best_match_id.lower()] + [t.lower() for t in best_data.get("tags", [])] + [c.lower() for c in best_data.get("categories", [])])
    core_noun = query_words[-1]
    meaningful_match = any(qw in best_corpus for qw in query_words if len(qw) >= 4)
    if core_noun not in best_corpus and not meaningful_match:
        print(f"Error: Found '{best_match_id}' but it failed strict validation. Missing core keyword '{core_noun}'.")
        return

    asset_id = best_match_id
    print(f"[Material Setup] Found matching texture: {asset_id}")
    
    files_url = f"https://api.polyhaven.com/files/{asset_id}"
    files_data = secure_request(files_url)
    
    if "blend" not in files_data:
        print(f"Error: Asset {asset_id} format not supported.")
        return
        
    # Get 2k or fallback
    res_data = files_data["blend"].get("2k", list(files_data["blend"].values())[0])
    if "include" not in res_data["blend"]:
        print("Error: Texture files not found.")
        return
        
    temp_dir = os.path.abspath(os.path.join(os.environ.get("TEMP_ASSETS_DIR", "./temp_assets"), asset_id))
    os.makedirs(temp_dir, exist_ok=True)
    
    # Download diffuse, roughness, normal
    textures = {}
    for path, info in res_data["blend"]["include"].items():
        lname = path.lower()
        if "diff" in lname or "col" in lname:
            textures['diffuse'] = download_file(info["url"], temp_dir, os.path.basename(path))
        elif "rough" in lname or "arm" in lname:
            textures['roughness'] = download_file(info["url"], temp_dir, os.path.basename(path))
        elif "nor_gl" in lname or "normal" in lname:
            textures['normal'] = download_file(info["url"], temp_dir, os.path.basename(path))

    # Blender Setup
    try:
        # Check if Ground_Plane already exists, if not create it
        if "Ground_Plane" not in bpy.data.objects:
            bpy.ops.mesh.primitive_plane_add(size=50, location=(0, 0, 0))
            plane = bpy.context.active_object
            plane.name = "Ground_Plane"
        else:
            plane = bpy.data.objects["Ground_Plane"]

        # Create Material
        mat_name = f"{asset_id}_Mat"
        if mat_name in bpy.data.materials:
            mat = bpy.data.materials[mat_name]
        else:
            mat = bpy.data.materials.new(name=mat_name)
            mat.use_nodes = True
        
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        nodes.clear()

        # 1. Texture Coordinate & Mapping
        tex_coord = nodes.new(type='ShaderNodeTexCoord')
        tex_coord.location = (-1200, 0)
        
        mapping = nodes.new(type='ShaderNodeMapping')
        mapping.location = (-1000, 0)
        mapping.inputs['Scale'].default_value = (25.0, 25.0, 25.0)
        links.new(tex_coord.outputs['UV'], mapping.inputs['Vector'])

        # 2. Principled BSDF & Output
        bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
        bsdf.location = (0, 0)
        
        # 強制非金屬防護網 (Dielectric Guard)
        bsdf.inputs['Metallic'].default_value = 0.0
        if 'Roughness' in bsdf.inputs:
            bsdf.inputs['Roughness'].default_value = 0.8
            
        output = nodes.new(type='ShaderNodeOutputMaterial')
        output.location = (300, 0)
        links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])

        y_offset = 0
        
        if 'diffuse' in textures:
            tex_node = nodes.new('ShaderNodeTexImage')
            tex_node.image = bpy.data.images.load(textures['diffuse'])
            tex_node.location = (-600, y_offset)
            links.new(mapping.outputs['Vector'], tex_node.inputs['Vector'])
            links.new(tex_node.outputs['Color'], bsdf.inputs['Base Color'])
            y_offset -= 300

        if 'roughness' in textures:
            tex_node = nodes.new('ShaderNodeTexImage')
            tex_node.image = bpy.data.images.load(textures['roughness'])
            tex_node.image.colorspace_settings.name = 'Non-Color'
            tex_node.location = (-600, y_offset)
            links.new(mapping.outputs['Vector'], tex_node.inputs['Vector'])
            
            # ARM 貼圖防護網 (Separate Green Channel for Roughness)
            if 'arm' in textures['roughness'].lower():
                sep_color = nodes.new('ShaderNodeSeparateColor')
                sep_color.location = (-300, y_offset)
                links.new(tex_node.outputs['Color'], sep_color.inputs['Color'])
                links.new(sep_color.outputs['Green'], bsdf.inputs['Roughness'])
            else:
                links.new(tex_node.outputs['Color'], bsdf.inputs['Roughness'])
            y_offset -= 300
            
        if 'normal' in textures:
            tex_node = nodes.new('ShaderNodeTexImage')
            tex_node.image = bpy.data.images.load(textures['normal'])
            tex_node.image.colorspace_settings.name = 'Non-Color'
            tex_node.location = (-600, y_offset)
            links.new(mapping.outputs['Vector'], tex_node.inputs['Vector'])
            
            norm_map = nodes.new('ShaderNodeNormalMap')
            norm_map.location = (-300, y_offset)
            links.new(tex_node.outputs['Color'], norm_map.inputs['Color'])
            links.new(norm_map.outputs['Normal'], bsdf.inputs['Normal'])

        # Assign material
        if plane.data.materials:
            plane.data.materials[0] = mat
        else:
            plane.data.materials.append(mat)
            
        print(f"已成功建立 50x50 的 Ground_Plane，並鋪上 {asset_id} 材質！")
    except Exception as e:
        print(f"Error setting up material in Blender: {e}")

if __name__ == "__main__":
    try:
        MATERIAL_TYPE = MCP_PARAMS.get("MATERIAL_TYPE", "")
    except NameError:
        MATERIAL_TYPE = "{{material_type}}"
        
    cleaned_query = ",".join([q.strip() for q in MATERIAL_TYPE.split(",") if q.strip()])
    if cleaned_query:
        setup_ground_material(cleaned_query)
    else:
        print("Error: No material query provided.")
