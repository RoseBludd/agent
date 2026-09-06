import base64

import instructor
from openai import OpenAI

from pydantic import BaseModel, Field
from smolagents import Tool
from typing import Any, List, Optional
from loguru import logger
from enum import Enum

from src.client import DiffusionClient
from src.settings import settings

VISUAL_FEEDBACK_SYSTEM_PROMPT = """
You are an advanced video editing assistant that reviews a **contact sheet** image: a grid of
frames sampled from a video composition, each cell labelled with its timecode (e.g. "01s12f" is
1 second 12 frames). Your job is to verify that the editing aligns with the given editing goal.

Your Task:
	•	Analyze each labelled cell to check if it meets the editing goal.
	•	If the sheet meets the goal, respond with "Everything checks out."
	•	If a cell reveals an issue, provide clear and actionable feedback, referencing its timecode.

Editing Mistakes to Detect:
	1.	Editing Goal Compliance:
	•	Text Positioning: Text should be centered but isn't.
	•	Missing Animation: An expected effect is absent.
	•	Trimming Issues: The clip wasn't trimmed correctly based on the goal.
	•	Positioning & Scaling Errors: Elements (video, text, graphics) aren't placed properly in the composition.
	2.	Common-Sense Issues (Even Without Explicit User Instruction):
	•	If a clip should be trimmed, but the subject is not centered or properly scaled in the composition.
	•	Visual artifacts or unnatural elements that would not appear in a polished video.

Important Clarifications:
    •	**Do NOT judge video quality** (e.g., resolution, lighting, camera work) unless the issue affects editing alignment.
	•	**Use the timecode labels burned into each cell**, not assumptions about frame spacing.
	•	**Variations in shot composition** (e.g., wide shots vs. close-ups) are only problematic if they contradict the user's goal.
	•	**Only point out clear violations of the editing goal.** If you're not certain, explain exactly why it's not aligned with the goal.

Response Format:

✅ If the sheet aligns with the editing goal:
	•	Approve the sheet

❌ If there's an issue:
	•	"Issue detected at <timecode>: The text is not centered. Adjust the alignment to match the goal."
	•	"Issue detected at <timecode>: The animation is missing. Ensure the transition effect is applied as specified."
	•	"Issue detected at <timecode>: The clip is not trimmed correctly. Adjust the start and end points as required."

Be concise, clear, and actionable in your feedback. Avoid unnecessary details or subjective judgments.
"""


class IssueType(str, Enum):
    TEXT_POSITIONING = "text_positioning"
    ANIMATION = "animation"
    TRIMMING = "trimming"
    POSITIONING_SCALING = "positioning_scaling"
    VISUAL_ARTIFACT = "visual_artifact"


class IssueSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CompositionIssue(BaseModel):
    type: IssueType = Field(..., description="Type of issue detected")
    description: str = Field(..., description="Detailed description of the issue")
    timecode: Optional[str] = Field(
        None, description="Timecode label of the cell where the issue occurs, e.g. '01s12f'"
    )
    suggested_fix: str = Field(
        ..., description="Actionable suggestion to fix the issue"
    )

    def format_message(self) -> str:
        return f"Issue detected at {self.timecode}: {self.description}. {self.suggested_fix}"


class SheetAnalysis(BaseModel):
    issues: List[CompositionIssue] = Field(default_factory=list)
    overall_decision: bool = Field(
        ..., description="Whether the composition, as shown in this contact sheet, meets requirements"
    )

    def format_message(self) -> str:
        if self.overall_decision:
            return "Everything checks out."
        return "\n".join(issue.format_message() for issue in self.issues)


class VisualFeedbackTool(Tool):
    name = "visual_feedback"
    description = """
    Analyzes video composition quality and makes render decisions taking into account the composition goal.
    Works in conjunction with VideoEditorTool to validate edits before rendering: captures a contact sheet
    of the current composition (via `dapi capture`) and reviews it with a vision model. Can point out issues
    with the video composition, which need to be fixed before rendering by the VideoEditorTool.
    """

    inputs = {
        "final_goal": {
            "type": "string",
            "description": "Quality criteria to evaluate (e.g. 'Ensure clip position are correct', 'Check for visual artifacts')",
            "nullable": False,
            "required": True,
        },
        "scene_id": {
            "type": "string",
            "description": "id of the <scene> to capture. Defaults to 'main'.",
            "nullable": True,
        },
        "times": {
            "type": "array",
            "description": "Timeline positions to sample, e.g. ['0', '2s', '4s']. Defaults to a spread across the scene if omitted.",
            "nullable": True,
        },
    }
    output_type = "object"

    def __init__(self, client: DiffusionClient):
        super().__init__()
        # CADIS gateway is OpenAI-compatible; "cadis" (glm-5.3-flash, the default
        # chat/tool-calling lane) is NOT vision-capable per cadis-ai-gateway.worker.js
        # -- "cadis-vision" (routed to @cf/meta/llama-4-scout-17b-16e-instruct) is,
        # and only for a single image per call, which is exactly what one capture
        # (a contact sheet bundling several timeline positions into one PNG) is.
        base_client = OpenAI(
            api_key=settings.cadis_api_key or "unused",
            base_url=settings.cadis_gateway_url,
        )
        self.openai_client = instructor.from_openai(base_client, mode=instructor.Mode.TOOLS)
        self.model = settings.video_composer_vision_model
        self.client = client

    def forward(
        self,
        final_goal: str = "The video should have a smooth transition between scenes without any glitches or artifacts.",
        scene_id: str = "main",
        times: Optional[List[str]] = None,
    ) -> Any:
        """Capture the current composition and get vision-model feedback on it."""
        try:
            captures = self.client.capture(scene_id, times=times)
            if not captures:
                return {"error": "No frames captured", "render_decision": False}

            prompt = f"Goal: **{final_goal}**"
            all_issues: List[str] = []
            is_ok_overall = True

            for capture in captures:
                path = capture["path"]
                with open(path, "rb") as f:
                    image_b64 = base64.b64encode(f.read()).decode("utf-8")

                logger.info(f"Analyzing contact sheet {path} with goal: {final_goal}")

                analysis: SheetAnalysis = self.openai_client.chat.completions.create(
                    model=self.model,
                    max_tokens=1024,
                    messages=[
                        {"role": "system", "content": VISUAL_FEEDBACK_SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                                },
                                {"type": "text", "text": prompt},
                            ],
                        },
                    ],
                    response_model=SheetAnalysis,
                )

                logger.debug(f"Sheet analysis: {analysis}")

                if not analysis.overall_decision:
                    all_issues.extend(issue.format_message() for issue in analysis.issues)
                is_ok_overall = is_ok_overall and analysis.overall_decision

            return {
                "issues": all_issues,
                "render_decision": is_ok_overall,
                "message": "; ".join(all_issues) if all_issues else "Everything checks out.",
            }

        except Exception as e:
            logger.error(f"Error processing frames: {str(e)}")
            return {"error": str(e), "render_decision": False}
