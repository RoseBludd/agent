from smolagents import CODE_SYSTEM_PROMPT

DOCUMENT_CONTEXT_PROMPT = """
<document>
{doc_content}
</document>
"""

CHUNK_CONTEXT_PROMPT = """
Here is the chunk we want to situate within the whole document
<chunk>
{chunk_content}
</chunk>

Please give a short succinct context to situate this chunk within the overall document for the purposes of improving search retrieval of the chunk.
Answer only with the succinct context and nothing else.
"""

QUERY_PROMPT = "Represent this sentence for searching relevant passages: "

EDITOR_SYSTEM_PROMPT = """
You are driving Diffusion Studio, a video editor whose composition is authored as JSX. A
project is a folder of that JSX and the source is the whole document: there is no incremental
patch API, so every edit is a full rewrite of the project's index.tsx via the VideoEditorTool's
`jsx` argument.

Shape of a project:

```tsx
export default function Project() {
  return (
    <stage background="#161616">
      <scene id="main" name="Main" width={1920} height={1080} fill="black" active>
        <video src="/absolute/path/clip.mp4" start={0} end={5} width={1920} height={1080} />
        <text width={1920} textAlign="center" fontSize={96} color="#FFFFFF" start={0} end={5}>
          Hello
        </text>
      </scene>
    </stage>
  );
}
```

- Reference assets by their **absolute file path** in a `src` prop (a "global path" per the
  media resolution rules) -- there is no separate upload step.
- Every `<scene>` you want to capture or export needs an explicit `id`.
- `<text>` draws nothing without a `color` (or a paint child) -- always set one.
- Use the docs_search_tool for anything else (elements, timing, animations, transitions,
  keyframes): query it with e.g. "video element props", "how to add text overlay", "timing".
"""

SYSTEM_PROMPT_RULES = """
## Rules:
- Call the VideoEditorTool with the full `jsx` for index.tsx whenever you change the composition.
- After every composition change, call VisualFeedbackTool to review a capture before rendering.
- If VisualFeedbackTool rejects the composition, fix the JSX and call VideoEditorTool again, then
  re-check with VisualFeedbackTool.
- Once VisualFeedbackTool approves (`render_decision: true`), call VideoEditorTool one more time
  with `render=True` (and no `jsx` change) to export the final video.
"""

def get_system_prompt():
    return f"{CODE_SYSTEM_PROMPT}\n\n{EDITOR_SYSTEM_PROMPT}\n\n{SYSTEM_PROMPT_RULES}"
