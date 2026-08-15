"""
integrations/polycam.py
========================
Polycam handoff adapter.

Polycam does not currently offer a public, self-serve API for
programmatically fusing AI-generated 2D images with 3D scan data from
this kind of server-side application. Rather than fake that
integration, this module documents the intended workflow and produces
a clean export package (image + metadata) that a user can manually bring
into the Polycam app/workflow as an AI-generated reference/texture
alongside their own real-world 3D scans.

`PolycamAdapter` is written as a real interface so that if/when a
suitable API becomes available, only this file needs to change — no
other part of the app depends on Polycam specifics.
"""

import json
import shutil
from pathlib import Path

import config
from utils.file_utils import sanitize_filename

INSTRUCTIONS = """\
POLYCAM HANDOFF INSTRUCTIONS
=============================
There is currently no public self-serve Polycam API this application can
call directly to fuse this generated image with your 3D scans
automatically. This export package is a manual handoff:

1. Open the Polycam app.
2. Import "{filename}" as a reference image or texture within your
   capture/project workflow (e.g. as a moodboard reference, or as a
   texture source when texturing a scanned mesh).
3. Use it alongside your real-world 3D scan(s) as inspiration or texture
   input, per Polycam's own in-app tools.

metadata.json in this folder documents the generation record (prompt,
resolution, QA scores, checksum) so you can trace which AI variation
was used in the fused asset.

FUTURE INTEGRATION POINT: implement PolycamAdapter.push_to_project() in
this file once/if Polycam exposes a suitable public API for this.
"""


class PolycamAdapter:
    """Documented future integration point. Not implemented today because
    no suitable public API currently exists — see INSTRUCTIONS above."""

    def push_to_project(self, *args, **kwargs):
        raise NotImplementedError(
            "Direct Polycam API integration is not available. "
            "Use export_for_polycam() for a manual handoff package instead."
        )


def export_for_polycam(image_path: Path, metadata: dict, request_id: str) -> Path:
    export_dir = config.EXPORTS_DIR / "polycam" / request_id
    export_dir.mkdir(parents=True, exist_ok=True)

    filename = sanitize_filename(image_path.name)
    dest_image = export_dir / filename
    shutil.copy2(image_path, dest_image)

    (export_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))
    (export_dir / "README.txt").write_text(INSTRUCTIONS.format(filename=filename))

    return export_dir
