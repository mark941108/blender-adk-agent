import sys
import math

try:
    import bpy
    import mathutils
except ImportError:
    print("Error: layout_engine.py must be run within Blender.")
    sys.exit(1)

def auto_layout_grid(spacing=3.0):
    """
    Arranges all top-level mesh objects in the scene into a grid layout.
    Ignores lights, cameras, and hidden objects.
    """
    # Clean up default Blender startup objects to prevent them from interfering with the layout
    default_names = ["Cube", "Camera", "Light"]
    for obj_name in default_names:
        if obj_name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[obj_name], do_unlink=True)

    # Filter objects: top-level objects (no parent) that are not hidden, excluding default cameras, lights, and Ground_Plane
    objects = [obj for obj in bpy.context.scene.objects 
               if not obj.parent and not obj.hide_get() and obj.type not in ('CAMERA', 'LIGHT') and obj.name != "Ground_Plane"]
    
    if not objects:
        print("No mesh objects found to arrange.")
        return

    # Calculate grid size
    count = len(objects)
    grid_size = math.ceil(math.sqrt(count))
    
    print(f"[Auto Layout] Arranging {count} objects in a {grid_size}x{grid_size} grid...")

    def pseudo_random(seed):
        # A simple pseudo-random hash returning 0.0 to 1.0 using the allowed 'math' module
        return (math.sin(seed * 12.9898) * 43758.5453) % 1.0

    natural_keywords = ['flower', 'grass', 'rock', 'plant', 'tree', 'bush', 'celandine', 'heliophila', 'weed']

    for i, obj in enumerate(objects):
        is_natural = any(kw in obj.name.lower() for kw in natural_keywords)

        if is_natural:
            obj.location.x = (pseudo_random(i + count) * 10.0) - 5.0
            obj.location.y = (pseudo_random(i + count + 100) * 10.0) - 5.0
        else:
            row = i // grid_size
            col = i % grid_size
            
            # Center the grid around origin
            x = (col - (grid_size - 1) / 2.0) * spacing
            y = (row - (grid_size - 1) / 2.0) * spacing
            
            obj.location.x = x
            obj.location.y = y
            
        # We leave Z untouched to keep objects on the ground
        
        # Ensure object transforms are updated
        obj.matrix_world = obj.matrix_basis
        
    # Deselect all, then select the arranged objects
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        obj.select_set(True)
        
    print(f"已成功將 {count} 個物件排列整齊！")

    # --- 2026 SOTA: Memory Leak Fix ---
    # Purge orphan data-blocks (materials/meshes) left behind by deleted assets
    print("[Auto Layout] Purging orphan data-blocks to free memory...")
    bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)

if __name__ == "__main__":
    auto_layout_grid()
