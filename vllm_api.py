from openai import OpenAI

_client = OpenAI(
    base_url="http://your_vllm_host:8000/v1",
    api_key="your_token_here"
)

def _resolve_model_id(preferred: str | None) -> str:
    mid = None
    if isinstance(preferred, str) and preferred.strip():
        mid = preferred.strip().rstrip("/")
    if not mid:
        try:
            models = _client.models.list()
            for m in getattr(models, "data", []) or []:
                _id = getattr(m, "id", None)
                if _id:
                    mid = _id
                    break
        except Exception:
            mid = None
    if not mid:
        raise RuntimeError("vLLM: no available model id; start server or provide model")
    return mid

def chat(messages, model=None, max_tokens=1024, thinking=False):
    model_id = _resolve_model_id(model)
    completion = _client.chat.completions.create(
        model=model_id,
        messages=messages,
        max_tokens=max_tokens,
        extra_body={"chat_template_kwargs": {"thinking": bool(thinking)}}
    )
    return completion.choices[0].message.content
