#!/usr/bin/env python
"""Direct test of the full pipeline bypassing Flask."""
import config

print("Config HF_TOKEN:", config.HF_TOKEN[:20] + "...")
print("Config HF_MODEL:", config.HF_MODEL)

from services import pipeline

result = pipeline.run_generation(
    raw_prompt="a cute robot",
    raw_negative_prompt=None,
    aspect_ratio="1:1",
    num_images=1,
    style_preset="none"
)

print(f"Success: {result.success}")
print(f"Request ID: {result.request_id}")
if not result.success:
    print(f"Error: {result.error_code} - {result.error_message}")
    print("\nEvents:")
    for e in result.events:
        print(f"  {e.stage} / {e.status}")
        if e.detail:
            for k, v in e.detail.items():
                print(f"    {k}: {v}")
else:
    print(f"Image: {result.image_url}")
