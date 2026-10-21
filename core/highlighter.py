import pymupdf
from typing import List
from .models import Violation

COLOR_FATAL = (1.0, 0.35, 0.35)    # Coral Red for Fatal / Blocker
COLOR_WARNING = (1.0, 0.88, 0.15)  # Bright Yellow for Editorial Warning
COLOR_INFO = (0.35, 0.75, 1.0)     # Sky Blue for Info

def annotate_pdf(doc: pymupdf.Document, violations: List[Violation], output_path: str) -> str:
    """
    Highlights (stabilo) exact error locations in the PDF and adds pop-up notes.
    """
    for v in violations:
        if v.rect is None:
            continue
            
        page_idx = v.page_num - 1
        if page_idx < 0 or page_idx >= len(doc):
            continue
            
        page = doc[page_idx]
        rect = pymupdf.Rect(v.rect)
        
        # Determine color based on severity
        if v.severity == "Fatal":
            color = COLOR_FATAL
        elif v.severity == "Warning":
            color = COLOR_WARNING
        else:
            color = COLOR_INFO
            
        # Add highlight annotation (Stabilo) or clean boxed outline
        try:
            is_region = (
                rect.height > 30 
                or rect.width > page.rect.width * 0.7 
                or v.category in ["IEEE Copyright Notice", "Page Setup", "Page Count", "Pagination", "Abstract", "Keywords"]
            )
            
            if is_region:
                annot = page.add_rect_annot(rect)
                annot.set_colors(stroke=color)
                annot.set_border(width=1.5, dashes=[3, 3])  # Dashed box for regional notes
            else:
                annot = page.add_highlight_annot(rect)
                annot.set_colors(stroke=color)
                
            # Add sticky note comment inside the annotation
            note_content = f"Item #{v.no}: [{v.category}]\n{v.comment}"
            annot.set_info(
                content=note_content,
                title=f"IEEE Reviewer ({v.severity})"
            )
            annot.update()
        except Exception:
            # Fallback to rect annotation if highlight fails
            try:
                annot = page.add_rect_annot(rect)
                annot.set_colors(stroke=color)
                annot.set_info(content=f"Item #{v.no}: {v.comment}", title="IEEE Reviewer")
                annot.update()
            except Exception:
                pass
                
    doc.save(output_path, garbage=4, deflate=True)
    return output_path
