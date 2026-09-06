import logging
import os

from smolagents import CodeAgent, LiteLLMModel
from src.settings import settings
from src.prompts import get_system_prompt
from src.client import DiffusionClient
from src.tools import (
    DocsSearchTool,
    VideoEditorTool,
    VisualFeedbackTool,
)

# Every LiteLLM call (model, api_base, tokens) logged to disk -- evidence that
# inference is actually routed through the CADIS gateway rather than direct
# to a provider.
os.environ.setdefault("LITELLM_LOG", "DEBUG")
os.makedirs("logs", exist_ok=True)
_litellm_file_handler = logging.FileHandler("logs/litellm_calls.log")
_litellm_file_handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(message)s"))
logging.getLogger("LiteLLM").addHandler(_litellm_file_handler)
logging.getLogger("LiteLLM").setLevel(logging.DEBUG)

client = DiffusionClient()

agent = CodeAgent(
    tools=[
        DocsSearchTool(),
        VideoEditorTool(client=client),
        VisualFeedbackTool(client=client),
    ],
    # Routed through the CADIS gateway (OpenAI-compatible; see
    # /root/devvy/projects/cadis-ai-gateway) instead of a direct Anthropic call, so this
    # agent's inference is metered and rate-limited the same way as every other CADIS
    # consumer on this host. Model id and gateway URL are both env-configurable
    # (VIDEO_COMPOSER_MODEL, CADIS_GATEWAY_URL) rather than pinned here.
    model=LiteLLMModel(
        model_id=f"openai/{settings.video_composer_model}",
        api_base=settings.cadis_gateway_url,
        api_key=settings.cadis_api_key or "unused",
        temperature=0.0,
    ),
    system_prompt=get_system_prompt(),
)

if __name__ == "__main__":
    asset_path = os.path.abspath("assets/big_buck_bunny_1080p_30fps.mp4")
    agent.run(
        "Trim the video at "
        f"{asset_path} to 5 seconds and add a centered white text overlay reading "
        "'Vidzs Composer'."
    )
