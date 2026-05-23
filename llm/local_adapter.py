"""Local LLM adapter to provide an async-compatible chat completions API.

This adapter wraps Hugging Face transformers text-generation pipelines and
exposes a minimal async interface compatible with the rest of the codebase
which expects `client.chat.completions.create(**params)` to be awaitable and
return an object with `choices[0].message.content`.

Usage:
  client = LocalLLMClient(model_path="gpt2", device='cpu')
  await client.chat.completions.create(messages=[{"role":"system","content":"..."}, ...], max_tokens=256)

Note: transformers and torch must be installed to use this adapter.
"""
from types import SimpleNamespace
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class LocalLLMClient:
    """Simple local LLM client using Hugging Face transformers pipeline.

    Provides a `chat.completions.create(**params)` async method that roughly
    mimics the structure used by the AsyncAzureOpenAI client in this project.
    """

    def __init__(self, model_path: Optional[str] = None, device: str = 'cpu'):
        self.model_path = model_path or "gpt2"
        self.device = device
        self._pipeline = None
        self._init_lock = asyncio.Lock()

        # Nested objects to match expected attribute access in LLMProvider
        class _Chat:
            def __init__(self, outer):
                self._outer = outer

            async def create(self, **params):
                return await self._outer._create_completion(**params)

        class _Completions:
            def __init__(self, outer):
                self._outer = outer
                self.create = _Chat(outer).create

        class _ChatRoot:
            def __init__(self, outer):
                self.completions = _Completions(outer)

        self.chat = _ChatRoot(self)

    async def _ensure_pipeline(self):
        async with self._init_lock:
            if self._pipeline is not None:
                return

            try:
                # Import lazily to avoid hard dependency unless used
                from transformers import pipeline, AutoTokenizer, AutoModelForCausalLM
            except Exception as e:
                logger.error("transformers is required for LocalLLMClient: %s", e)
                raise

            # Initialize pipeline in thread to avoid blocking the event loop
            def init():
                # Device handling: -1 for CPU, 0+ for CUDA
                device_arg = -1 if self.device == 'cpu' else 0
                # Create text-generation pipeline
                pl = pipeline('text-generation', model=self.model_path, device=device_arg)
                return pl

            self._pipeline = await asyncio.to_thread(init)

    async def _create_completion(self, **params):
        """Create a completion.

        Expected params include 'messages' (list of {role, content}) and either
        'max_tokens' or 'max_completion_tokens'.
        """
        await self._ensure_pipeline()

        messages = params.get('messages', [])
        # Build a simple prompt by concatenating system + user messages
        prompt_parts = []
        for m in messages:
            role = m.get('role', '')
            content = m.get('content', '')
            if role:
                prompt_parts.append(f"[{role}] {content}")
            else:
                prompt_parts.append(content)
        prompt = "\n\n".join(prompt_parts).strip()

        max_tokens = params.get('max_tokens') or params.get('max_completion_tokens') or 512

        # Call the pipeline in a thread
        def gen():
            # Use conservative generation parameters; user can tune via env vars
            try:
                outputs = self._pipeline(prompt, max_new_tokens=int(max_tokens), do_sample=False, num_return_sequences=1)
                return outputs
            except TypeError:
                # Some older pipelines expect max_length instead of max_new_tokens
                outputs = self._pipeline(prompt, max_length=int(max_tokens), do_sample=False, num_return_sequences=1)
                return outputs

        outputs = await asyncio.to_thread(gen)

        # outputs is a list of dicts with 'generated_text'
        if not outputs:
            text = ""
        else:
            text = outputs[0].get('generated_text', '')

        # Try to remove prompt prefix if pipeline echoed it
        if prompt and text.startswith(prompt):
            text = text[len(prompt):].lstrip()

        # Return an object with the attributes used by LLMProvider
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])
