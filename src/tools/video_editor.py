from smolagents import Tool
from typing import Any, Optional
from loguru import logger

from src.client import DiffusionClient


class VideoEditorTool(Tool):
    name = "video_editor_tool"
    description = """A tool that edits and renders a video composition using Diffusion Studio's
    JSX-based editor (driven via the `dapi` CLI -- see the docs_search_tool for the JSX reference:
    query "jsx elements", "video element", "text element", "timing" etc).

    The tool is designed to be used in conjunction with the VisualFeedbackTool.
    The VisualFeedbackTool will verify if the composition can be rendered based on the overall
    composition quality. Call this tool again with render=True once approved.

    Passing `jsx` overwrites the project's entire index.tsx (the project's source is the whole
    document -- there is no incremental patch). Reference existing assets by their absolute
    file path in a `src` prop, e.g. `<video src="/abs/path/clip.mp4" start={0} end={5} .../>`.
    Every `<scene>` needs an `id` to be captured/exported by id later.
    """
    inputs = {
        "jsx": {
            "type": "string",
            "description": "Full contents of the project's index.tsx (a Solid component default-exporting a <stage> of <scene>s). Omit to skip editing and only render/check the current state.",
            "nullable": True,
        },
        "render": {
            "type": "boolean",
            "description": "Set true to export the scene to a video file, once VisualFeedbackTool has approved the composition.",
            "nullable": True,
        },
        "scene_id": {
            "type": "string",
            "description": "id of the <scene> to check/export. Defaults to 'main'.",
            "nullable": True,
        },
        "output": {
            "type": "string",
            "description": "Output path for the rendered video (only used when render=True). Use output/video.mp4 by default.",
            "nullable": True,
        },
    }
    output_type = "object"

    def __init__(self, client: DiffusionClient):
        super().__init__()
        self.client: DiffusionClient = client
        logger.debug("DiffusionClient initialized")

    def forward(
        self,
        jsx: Optional[str] = None,
        render: bool = False,
        scene_id: str = "main",
        output: str = "output/video.mp4",
    ) -> Any:
        """Main execution method that processes the video editing task."""
        result: dict[str, Any] = {}

        if jsx:
            self.client.write_project(jsx)

        try:
            result["check"] = self.client.check(scene_id)
        except Exception as e:
            result["check_error"] = str(e)

        if render:
            result["export"] = self.client.export(scene_id, output)

        return result
