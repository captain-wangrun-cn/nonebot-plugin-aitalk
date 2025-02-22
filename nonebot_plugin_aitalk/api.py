from openai import AsyncOpenAI
from .config import plugin_config

async def gen(messages: dict, model_name: str, api_key: str, api_url: str) -> str|None:
    client = AsyncOpenAI(base_url=api_url, api_key=api_key)

    completion = await client.chat.completions.create(
        model=model_name,
        messages=messages,
        max_tokens=plugin_config.aichat_completion_config.max_token,
        temperature=plugin_config.aichat_completion_config.temperature,
        top_p=plugin_config.aichat_completion_config.top_p,
    )

    return completion.choices[0].message.content