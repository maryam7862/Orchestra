#!/usr/bin/env python
"""Direct test of the HuggingFace provider bypassing Flask."""
import config

print("Config HF_TOKEN:", config.HF_TOKEN[:20] + "...")
print("Config HF_MODEL:", config.HF_MODEL)

from services.huggingface_provider import HuggingFaceProvider
provider = HuggingFaceProvider()

try:
    result = provider.generate(
        prompt="a cute robot",
        negative_prompt=None,
        width=512,
        height=512,
        request_id="TEST-123"
    )
    print("✓ PROVIDER RESULT SUCCESS:", result.pil_image.size)
except Exception as e:
    print("✗ PROVIDER ERROR:", type(e).__name__)
    print("  Message:", str(e)[:300])
    import traceback
    traceback.print_exc()
