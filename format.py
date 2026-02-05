import json
from docx import Document
from docx.shared import Length
from docx.enum.text import WD_ALIGN_PARAGRAPH

# ==========================================
#        HELPER FUNCTIONS
# ==========================================

def format_unit(value, unit_type="pt"):
    """
    Convert Word's internal length values into human-readable strings.

    Word stores lengths in EMUs (English Metric Units). This converts to
    points (pt) for font size / spacing, or inches (") for margins/indents.
    Accepts either python-docx Length objects or raw EMU integers.

    Args:
        value: Length in EMUs or a Length object; None is allowed.
        unit_type: "pt" for points (e.g. font size), "inch" for margins/indents.

    Returns:
        String like "11 pt" or "1.0\"", or None if value is None so the caller
        can substitute a default (e.g. "0 pt", "0\"").
    """
    if value is None:
        return None  # Caller uses this to apply defaults

    if unit_type == "pt":
        # 12700 EMU ≈ 1 pt
        pts = value.pt if isinstance(value, Length) else value / 12700
        return f"{round(pts, 1)} pt"
    elif unit_type == "inch":
        # 914400 EMU = 1 inch
        inches = value.inches if isinstance(value, Length) else value / 914400
        return f"{round(inches, 2)}\""
    return str(value)


def get_alignment_string(enum_val):
    """
    Map Word's paragraph alignment enum to a display-friendly label.

    Args:
        enum_val: WD_ALIGN_PARAGRAPH value (e.g. LEFT, CENTER, JUSTIFY).

    Returns:
        String such as "Left", "Center", "Justified", or "Left (Default)"
        when alignment is None or unrecognized.
    """
    alignments = {
        WD_ALIGN_PARAGRAPH.LEFT: "Left",
        WD_ALIGN_PARAGRAPH.CENTER: "Center",
        WD_ALIGN_PARAGRAPH.RIGHT: "Right",
        WD_ALIGN_PARAGRAPH.JUSTIFY: "Justified",
    }
    return alignments.get(enum_val, "Left (Default)")

def get_paragraph_formatting(doc, paragraph, index):
    """
    Extracts formatting and full text for a single paragraph.
    Returns a dict with paragraph_index, text (full content), text_preview, and
    "Formatting of selected text" (Font, Paragraph, Section).
    """
    # 1. Get the first run (text chunk) to analyze font. 
    # If paragraph is empty, we use a dummy object to safely get style defaults.
    run = paragraph.runs[0] if paragraph.runs else None
    
    # --- FONT RESOLUTION ---
    # We check the Run first (direct formatting), then the Paragraph Style
    style_font = paragraph.style.font
    
    if run:
        font_name = run.font.name if run.font.name else style_font.name
        font_size_val = run.font.size if run.font.size else style_font.size
    else:
        font_name = style_font.name
        font_size_val = style_font.size

    # Defaults
    font_name = font_name if font_name else "(Default) Body Text"
    font_size_str = format_unit(font_size_val, "pt") if font_size_val else "11 pt (Default)"

    # --- PARAGRAPH RESOLUTION ---
    pf = paragraph.paragraph_format
    
    # Indents & Spacing
    left_indent = format_unit(pf.left_indent, "inch") if pf.left_indent else "0\""
    right_indent = format_unit(pf.right_indent, "inch") if pf.right_indent else "0\""
    space_before = format_unit(pf.space_before, "pt") if pf.space_before else "0 pt"
    space_after = format_unit(pf.space_after, "pt") if pf.space_after else "0 pt"
    
    # Line Spacing
    if pf.line_spacing_rule == 0: # wdLineSpaceSingle
        line_spacing = "Single"
    elif pf.line_spacing:
        # If < 10, it's likely a multiple (e.g. 1.5 lines), otherwise it's exact points
        line_spacing = f"{round(pf.line_spacing, 2)} lines" if pf.line_spacing < 10 else format_unit(pf.line_spacing, "pt")
    else:
        line_spacing = "Single"

    # Breaks
    breaks = []
    if pf.keep_with_next: breaks.append("Keep with next")
    if pf.page_break_before: breaks.append("Page break before")
    break_str = ", ".join(breaks) if breaks else "None"

    # --- SECTION RESOLUTION ---
    # (Simplified: Uses the first section's layout for all paragraphs. 
    # Handling multi-section docs perfectly requires complex XML parsing)
    section = doc.sections[0]
    
    margin_str = (
        f"Left: {format_unit(section.left_margin, 'inch')}, "
        f"Right: {format_unit(section.right_margin, 'inch')}, "
        f"Top: {format_unit(section.top_margin, 'inch')}, "
        f"Bottom: {format_unit(section.bottom_margin, 'inch')}"
    )

    return {
        "paragraph_index": index,
        "text": paragraph.text,
        "text_preview": paragraph.text[:50] + "..." if len(paragraph.text) > 50 else paragraph.text,
        "Formatting of selected text": {
            "Font": {
                "FONT": f"{font_name}\n{font_size_str}",
                "LANGUAGE": "English (United States)" # Extraction requires OXML parsing
            },
            "Paragraph": {
                "PARAGRAPH STYLE": paragraph.style.name,
                "ALIGNMENT": get_alignment_string(pf.alignment),
                "INDENTATION": f"Left: {left_indent}\nRight: {right_indent}",
                "SPACING": f"Before: {space_before}\nAfter: {space_after}\nLine spacing: {line_spacing}",
                "LINE AND PAGE BREAKS": break_str
            },
            "Section": {
                "MARGINS": margin_str,
                "LAYOUT": f"Section start: {section.start_type}",
                "PAPER": f"Width: {format_unit(section.page_width, 'inch')}, Height: {format_unit(section.page_height, 'inch')}",
                "HEADER/FOOTER": f"Different first page: {section.different_first_page_header_footer}"
            }
        }
    }

def extract_formatting_from_file(file_path_or_stream):
    """
    Extract formatting data from a .docx file.
    Accepts a file path (str/pathlib.Path) or a file-like object (e.g. BytesIO).
    Returns a list of paragraph formatting dicts, or raises on error.
    """
    doc = Document(file_path_or_stream)
    full_doc_data = []
    for i, para in enumerate(doc.paragraphs):
        if not para.text.strip():
            continue
        data = get_paragraph_formatting(doc, para, i)
        full_doc_data.append(data)
    return full_doc_data


# ==========================================
#             MAIN EXECUTION
# ==========================================

if __name__ == "__main__":
    from config import FILE_PATH
    try:
        full_doc_data = extract_formatting_from_file(FILE_PATH)
        print(json.dumps(full_doc_data, indent=4))
    except Exception as e:
        print(f"Error processing file: {e}")