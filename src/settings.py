import os
from pydantic_settings import BaseSettings
from pydantic import Field
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    embedding_dim: int = 1024
    infinity_base_url: str = "https://muhtasham--infinity-serve.modal.run"
    infinity_api_key: str = Field(default="sk-dummy")
    infinity_embedding_model: str = "mixedbread-ai/mxbai-embed-large-v1"
    infinity_rerank_model: str = "mixedbread-ai/mxbai-rerank-base-v1"
    # https://operator.diffusion.studio (the original default) no longer resolves --
    # the hosted "operator" build it pointed at is gone. diffusion.studio's own docs
    # site is live and serves the same llms.txt shape DocsSearchTool expects.
    url: str = Field(default_factory=lambda: os.getenv("DIFFUSION_STUDIO_URL", "https://diffusion.studio"))
    hash_file: str = "docs/content_hash.txt"
    # The real JSX/dapi reference (elements, timing, capture, export, ...) lives in the
    # editor-fork repo, not on the marketing site's llms.txt (a link index, not content) --
    # see build_local_docs_corpus in utils.py.
    docs_reference_dir: str = Field(
        default_factory=lambda: os.getenv(
            "DOCS_REFERENCE_DIR", "/root/devvy/projects/editor-fork/reference"
        )
    )

    qdrant_path: str = "embeddings/vector_db"
    collection_name: str = "diffusion_studio_docs"

    anthropic_api_key: str = Field(
        default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", "")
    )

    # --- dapi / editor-fork integration ---
    # The editor's automation surface is a JSX project folder driven by the `dapi`
    # CLI over a local socket to a running app instance (no `window.core`/Playwright
    # `page.evaluate` surface exists in the open-sourced editor -- confirmed absent
    # from its entire git history). This client shells out to `dapi`; the app
    # process itself (Electron, headless under Xvfb on this Linux host) is a
    # separately-run host service this client connects to, not something it starts.
    dapi_cli_path: str = Field(
        default_factory=lambda: os.getenv(
            "DAPI_CLI_PATH",
            "/root/devvy/projects/editor-fork/apps/cli/dist/index.js",
        )
    )
    dapi_project_dir: str = Field(
        default_factory=lambda: os.getenv(
            "DAPI_PROJECT_DIR",
            "/root/devvy/projects/vidzs-composer-project",
        )
    )

    # --- CADIS gateway routing (replaces the hardcoded Anthropic call in main.py) ---
    # CADIS is an OpenAI-compatible router (see /root/devvy/projects/cadis-ai-gateway).
    # cadis_gateway_url is the OpenAI-compatible base (".../v1"); litellm is called as
    # "openai/<video_composer_model>" against that base, per the smolagents LiteLLMModel contract.
    cadis_gateway_url: str = Field(
        default_factory=lambda: os.getenv(
            "CADIS_GATEWAY_URL", "https://cadis.geniuzs.com/v1"
        )
    )
    cadis_api_key: str = Field(default_factory=lambda: os.getenv("CADIS_API_KEY", ""))
    # "cadis" resolves to the account's strongest general lane (glm-5.3-flash as of
    # this writing); kept as an alias rather than a pinned model id so upstream
    # re-routing (see cadis-ai-gateway MODEL_ALIASES) doesn't require a redeploy here.
    video_composer_model: str = Field(
        default_factory=lambda: os.getenv("VIDEO_COMPOSER_MODEL", "cadis")
    )
    # Separate alias for VisualFeedbackTool: confirmed (cadis-ai-gateway worker.js) that
    # "cadis"/glm-5.3-flash is not the vision-capable lane -- "cadis-vision" (routed to
    # @cf/meta/llama-4-scout-17b-16e-instruct) is. Single-image vision only, so the tool
    # sends one capture (frame or contact-sheet PNG) per call rather than a batch.
    video_composer_vision_model: str = Field(
        default_factory=lambda: os.getenv("VIDEO_COMPOSER_VISION_MODEL", "cadis-vision")
    )

    # --- DocsSearchTool embeddings ---
    # "cloudflare" reuses the CADIS gateway's own /v1/embeddings passthrough to Workers
    # AI's @cf/baai/bge-m3 (see cadis-ai-gateway.worker.js handleEmbedding) instead of
    # standing up a second direct-to-Cloudflare-API code path; "infinity" keeps the
    # original hosted-modal-endpoint default as a fallback if that gateway is ever
    # unreachable from this host.
    embedding_provider: str = Field(
        default_factory=lambda: os.getenv("EMBEDDING_PROVIDER", "cloudflare")
    )

    max_retries: int = 10
    retry_delay: int = Field(default=10, description="Retry delay in seconds")

    class Config:
        env_prefix = ""
        case_sensitive = False


settings = Settings()
