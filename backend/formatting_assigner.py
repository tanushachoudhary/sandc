"""
Use the LLM to assign which reference-document formatting (by paragraph index)
should apply to each blueprint section. This lets the model choose e.g. "Case Caption
→ use format from reference paragraph 0 (centered, 14pt)" and "Body sections → use
reference paragraph 1 (12pt, left, indented)".
"""
from typing import Any, Dict, List, Optional

from llm.client import LLMClient
from utils.text_utils import extract_json_from_llm


def _summarize_applyable(applyable: Dict[str, Any], index: int) -> str:
    """One-line summary of an applyable for the prompt."""
    font = applyable.get("font_name") or "Times New Roman"
    size = applyable.get("font_size_pt") or 12
    align = (applyable.get("alignment") or "left").lower()
    left_in = applyable.get("left_indent_in") or 0
    space_before = applyable.get("space_before_pt") or 0
    space_after = applyable.get("space_after_pt") or 0
    style = applyable.get("paragraph_style") or "Normal"
    parts = [f"{font} {size}pt", align]
    if left_in:
        parts.append(f"left indent {left_in}\"")
    if space_before or space_after:
        parts.append(f"space before {space_before}pt after {space_after}pt")
    parts.append(f"style {style}")
    return f"  {index}: " + ", ".join(parts)


def build_formatting_assignment_prompt(
    section_names: List[str],
    applyables: List[Dict[str, Any]],
) -> str:
    """Build prompt for LLM to map each section to a formatting option index."""
    options_text = "\n".join(
        _summarize_applyable(a, i) for i, a in enumerate(applyables)
    )
    sections_text = "\n".join(f"  - {name}" for name in section_names)
    return f"""You are assigning formatting styles to sections of a legal document.

Reference document has these formatting options (by paragraph index in the reference):

{options_text}

Document sections (in order):

{sections_text}

Task: For each section, choose the SINGLE option index (0 to {max(0, len(applyables) - 1)}) that best matches how that section should look. For example: case caption often uses centered, larger font (like option 0); body text often uses left-aligned, indented (like option 1). Use the same option for multiple sections if they should look the same.

Return ONLY valid JSON. Format: {{ "Section Name Exactly As Listed": <integer>, ... }}
Example: {{ "Case Caption": 0, "Summons Notice": 1, "Venue and Jurisdiction": 1 }}

JSON:"""


def assign_formatting_by_llm(
    section_names: List[str],
    applyables: List[Dict[str, Any]],
) -> Optional[Dict[str, int]]:
    """
    Call LLM to map each section name to an applyable index (0-based).
    Returns section_name -> index, or None on failure/empty.
    """
    if not section_names or not applyables:
        return None
    llm = LLMClient()
    prompt = build_formatting_assignment_prompt(section_names, applyables)
    try:
        response = llm.generate(
            prompt,
            max_tokens=1024,
            json_mode=True,
            temperature=0.1,
        )
        data = extract_json_from_llm(response)
        if not isinstance(data, dict):
            return None
        # Normalize: ensure keys match section names (exact or strip), values are int in range
        n = len(applyables)
        result = {}
        for name in section_names:
            val = data.get(name)
            if val is None:
                for k, v in data.items():
                    if str(k).strip() == name or k.strip().lower() == name.lower():
                        val = v
                        break
            if val is not None:
                try:
                    idx = int(val) if isinstance(val, int) else int(float(val))
                    result[name] = max(0, min(idx, n - 1))
                except (TypeError, ValueError):
                    result[name] = 0
            else:
                result[name] = 0
        return result
    except Exception:
        return None
