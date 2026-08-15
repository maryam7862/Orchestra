"""
services/huggingface_provider.py
==================================
The ONLY file that talks to Hugging Face directly.

Uses the official current interface documented at
https://huggingface.co/docs/inference-providers and the
huggingface_hub Python SDK:

    from huggingface_hub import InferenceClient
    client = InferenceClient(api_key=HF_TOKEN)
    image = client.text_to_image(prompt, model=..., **kwargs)

`InferenceClient.text_to_image()` returns a `PIL.Image.Image` object
directly (not a URL) for the routed-inference path used here — so the
"remote streaming download" code path in api_gateway.py is NOT exercised
for the primary flow. That is documented rather than pretended away
(see Project 3 slide 13/29 requirement). Local saving of the returned
PIL image still goes through the memory-safe integrity pipeline in
services/integrity.py.

IMPORTANT — verify before running:
Hugging Face's supported models / providers / free-tier credit policy
change over time. Before relying on this in production, check the
current docs:
  https://huggingface.co/docs/inference-providers
  https://huggingface.co/docs/huggingface_hub/guides/inference
If black-forest-labs/FLUX.1-schnell is no longer routed, set HF_MODEL
(and optionally HF_PROVIDER) in .env to a currently supported
text-to-image model/provider pair.
"""

from typing import Optional

import config
from services.image_provider import ImageProvider, ProviderResult
from services.retry import NonRetryableError, RetryableError
from utils.logging_utils import get_logger

logger = get_logger(__name__)


class HuggingFaceProvider(ImageProvider):
    name = "huggingface"

    def supports_negative_prompt(self) -> bool:
        return config.MODEL_SUPPORTS_NEGATIVE_PROMPT

    def _get_client(self):
        if not config.HF_TOKEN:
            raise NonRetryableError(
                "MISSING_HF_TOKEN",
                "No Hugging Face token configured. Set HF_TOKEN in your .env file.",
            )
        try:
            from huggingface_hub import InferenceClient
        except ImportError as exc:
            raise NonRetryableError(
                "MISSING_DEPENDENCY",
                "huggingface_hub is not installed. Run: pip install -r requirements.txt",
            ) from exc

        kwargs = {"api_key": config.HF_TOKEN}
        if config.HF_PROVIDER:
            kwargs["provider"] = config.HF_PROVIDER
        return InferenceClient(**kwargs)

    def generate(
        self,
        prompt: str,
        negative_prompt: Optional[str],
        width: int,
        height: int,
        request_id: str,
    ) -> ProviderResult:
        client = self._get_client()

        models_to_try = []
        seen = set()
        for model_name in [config.HF_MODEL, *config.HF_MODEL_FALLBACKS]:
            if model_name and model_name not in seen:
                seen.add(model_name)
                models_to_try.append(model_name)

        last_exc = None
        image = None

        for model_name in models_to_try:
            call_kwargs = {
                "model": model_name,
                "width": width,
                "height": height,
            }
            if negative_prompt and self.supports_negative_prompt():
                call_kwargs["negative_prompt"] = negative_prompt

            logger.info(
                "[%s] requesting generation from Hugging Face model=%s size=%dx%d",
                request_id, model_name, width, height,
            )

            try:
                image = client.text_to_image(prompt, **call_kwargs)
                break
            except Exception as exc:  # noqa: BLE001 - SDK raises varied exception types
                last_exc = exc
                status_code = getattr(getattr(exc, "response", None), "status_code", None)
                message = str(exc).lower()
                is_deprecated_or_unavailable = (
                    status_code in {400, 404, 410}
                    or "deprecated" in message
                    or "no longer supported" in message
                    or "unavailable" in message
                )
                if model_name == config.HF_MODEL and is_deprecated_or_unavailable:
                    logger.warning(
                        "[%s] model %s is unavailable/deprecated; trying next supported FLUX model",
                        request_id,
                        model_name,
                    )
                    continue
                if model_name != config.HF_MODEL and is_deprecated_or_unavailable:
                    logger.warning(
                        "[%s] fallback model %s is unavailable/deprecated; giving up",
                        request_id,
                        model_name,
                    )
                    self._classify_hf_exception(exc, request_id)
                    raise
                self._classify_hf_exception(exc, request_id)
                raise

        if image is None:
            if last_exc is not None:
                self._classify_hf_exception(last_exc, request_id)
            raise RetryableError("EMPTY_RESULT", "Hugging Face returned no image data.")

        return ProviderResult(
            pil_image=image,
            source_kind="pil_object",
            provider_name=self.name,
            model_name=config.HF_MODEL,
        )

    @staticmethod
    def _classify_hf_exception(exc: Exception, request_id: str):
        """
        huggingface_hub raises requests-derived exceptions and
        huggingface_hub.utils.HfHubHTTPError for HTTP-level failures.
        We inspect what's available without hard-depending on every
        possible exception class the SDK might raise across versions.
        """
        message = str(exc)
        status_code = getattr(getattr(exc, "response", None), "status_code", None)

        # Explicit timeout classes (requests-based)
        cls_name = type(exc).__name__
        if "ConnectTimeout" in cls_name:
            raise RetryableError("CONNECT_TIMEOUT", "Could not connect to Hugging Face in time.") from exc
        if "ReadTimeout" in cls_name:
            raise RetryableError("READ_TIMEOUT", "Hugging Face took too long to respond (model may be loading).") from exc
        if "ConnectionError" in cls_name:
            raise RetryableError("CONNECTION_ERROR", "Network error contacting Hugging Face.") from exc

        if status_code in config.RETRYABLE_STATUS_CODES:
            raise RetryableError(f"HTTP_{status_code}", f"Hugging Face returned {status_code}.") from exc

        if status_code == 402 or "depleted your monthly included credits" in message.lower() or "purchase pre-paid credits" in message.lower():
            raise NonRetryableError(
                "HF_CREDIT_EXHAUSTED",
                "Hugging Face free-tier inference credits are exhausted for this account. Create a new free token, use a different Hugging Face account, or add paid credits to continue generation.",
            ) from exc

        if status_code in (401, 403):
            raise NonRetryableError(
                "AUTH_FAILURE",
                "Hugging Face rejected the token (invalid or insufficient permissions).",
            ) from exc

        if status_code == 400 or "content_policy" in message.lower() or "sentinel_block" in message.lower():
            raise NonRetryableError(
                "CONTENT_POLICY_VIOLATION",
                "The request was rejected by Hugging Face's own content policy.",
            ) from exc

        # "Model is loading" style 503s from the classic Inference API
        if "loading" in message.lower() or status_code == 503:
            raise RetryableError("MODEL_LOADING", "The model is warming up on the provider side.") from exc

        logger.error("[%s] unclassified Hugging Face error: %s", request_id, message)
        raise NonRetryableError("PROVIDER_ERROR", "Hugging Face inference failed. See server logs for detail.") from exc
