"""
integrations/unreal.py
=======================
Unreal Engine 5 handoff adapter.

This web application cannot reach into a running UE5 editor, invoke
Nanite, or auto-generate LODs — that happens inside Unreal itself. What
this module DOES do honestly: package the verified image asset plus
metadata into a predictable folder structure with import instructions,
so a user can drag it into UE5's Content Browser as a texture and use it
however they like (material input, decal, UI, etc).
"""

import json
import shutil
from pathlib import Path

import config
from utils.file_utils import sanitize_filename

INSTRUCTIONS = """\
UNREAL ENGINE 5 IMPORT INSTRUCTIONS
====================================
1. Open your UE5 project.
2. In the Content Browser, navigate to (or create) a folder, e.g.
   Content/GeneratedAssets/.
3. Drag "{filename}" from this export folder into that Content Browser
   folder. UE5 will import it as a Texture2D asset.
4. To use it on a mesh: create or edit a Material, add a Texture Sample
   node wired to Base Color, and assign the imported texture to that
   node. Apply the material to your mesh.
5. Nanite and LOD generation are properties of the MESH you apply this
   texture to, not of the image itself — this export is a texture/image
   asset, not a 3D mesh, so there is no Nanite/LOD step to perform here.
   If you generate or import a high-poly mesh separately, UE5's Nanite
   pipeline can auto-handle its LODs as usual.

metadata.json in this folder contains the full generation record
(prompt, resolution, QA scores, checksum) for provenance tracking.
"""


def export_for_unreal(image_path: Path, metadata: dict, request_id: str) -> Path:
    export_dir = config.EXPORTS_DIR / "unreal" / request_id
    export_dir.mkdir(parents=True, exist_ok=True)

    dest_image = export_dir / sanitize_filename(image_path.name)
    shutil.copy2(image_path, dest_image)

    (export_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))
    (export_dir / "README.txt").write_text(INSTRUCTIONS.format(filename=dest_image.name))

    return export_dir
