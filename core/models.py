from dataclasses import dataclass, field
from typing import Optional, List, Tuple

@dataclass
class Violation:
    no: int
    category: str
    comment: str
    location: str
    page_num: int
    rect: Optional[Tuple[float, float, float, float]] = None
    severity: str = "Warning"  # Fatal, Warning, Info
    snippet: str = ""

@dataclass
class PaperMetadata:
    filename: str
    total_pages: int
    page_width_pt: float
    page_height_pt: float
    paper_size_name: str
    fonts: List[str] = field(default_factory=list)
    has_copyright_notice: bool = False
    copyright_text: str = ""
    is_a4: bool = False
    is_page_count_valid: bool = False
    is_extra_pages: bool = False

