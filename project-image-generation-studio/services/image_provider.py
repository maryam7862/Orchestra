"""
services/image_provider.py
===========================
Abstract provider interface. The rest of the app talks to `generate_image()`
and never imports Hugging Face-specific code directly.

Architecture:

    Frontend -> Backend -> ImageProvider (this interface) -> HuggingFaceProvider

To add another provider later (Stability AI, Alibaba Wan, gpt-image, ...),
implement this interface in a new file under services/ and swap it in
get_active_provider(). No other code needs to change.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from PIL import Image


@dataclass
class ProviderResult:
    """What every provider must hand back, regardless of how it fetched
    the image internally (remote URL vs raw bytes vs PIL object)."""
    pil_image: Image.Image
    source_kind: str  # "pil_object" | "remote_url" | "raw_bytes"
    provider_name: str
    model_name: str


class ImageProvider(ABC):
    name: str = "abstract"

    @abstractmethod
    def supports_negative_prompt(self) -> bool:
        ...

    @abstractmethod
    def generate(
        self,
        prompt: str,
        negative_prompt: Optional[str],
        width: int,
        height: int,
        request_id: str,
    ) -> ProviderResult:
        ...


def get_active_provider() -> ImageProvider:
    from services.huggingface_provider import HuggingFaceProvider
    return HuggingFaceProvider()
