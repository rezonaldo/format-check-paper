import re
from difflib import SequenceMatcher
from typing import List, Tuple, Dict, Any, Optional
import pymupdf
from .models import Violation, PaperMetadata

# Standard A4 size in points: 595.28 x 841.89 (72 points per inch, 210 x 297 mm)
A4_WIDTH = 595.28
A4_HEIGHT = 841.89
PT_TOLERANCE = 8.0  # Allow slight rounding variance (±8pt)

# US Letter in points: 612 x 792
LETTER_WIDTH = 612.0
LETTER_HEIGHT = 792.0

# 40+ known template placeholder phrases from official IEEE MS Word / LaTeX templates
TEMPLATE_PLACEHOLDER_PHRASES = [
    "Identify applicable funding agency here",
    "If none, delete this text box",
    "This electronic document is a \"live\" template",
    "This electronic document is a “live” template",
    "use style: paper title",
    "Sub-titles are not captured in Xplore and should not be used",
    "line 1: 1st Given Name Surname",
    "line 2: dept. name of organization",
    "line 3: name of organization",
    "line 4: City, Country",
    "line 5: email address or ORCID",
    "line 1: 2nd Given Name Surname",
    "line 1: 3rd Given Name Surname",
    "line 1: 4th Given Name Surname",
    "line 1: 5th Given Name Surname",
    "line 1: 6th Given Name Surname",
    "CRITICAL: Do Not Use Symbols, Special Characters, Footnotes, or Math in Paper Title or Abstract",
    "*CRITICAL: Do Not Use Symbols",
    "(Abstract)",
    "Keywords—component, formatting, style, styling, insert (key words)",
    "insert (key words)",
    "Word 97-2003 Document",
    "modified in MS Word 2007",
    "A. Selecting a Template (Heading 2)",
    "B. Maintaining the Integrity of the Specifications",
    "III. PREPARE YOUR PAPER BEFORE STYLING",
    "IV. USING THE TEMPLATE",
    "TABLE TYPE STYLES",
    "Table Column Head",
    "Table column subhead",
    "More table copy",
    "Sample of a Table footnote",
    "Example of a figure caption",
    "(figure caption)",
    "(bullet list)",
    "Title of paper if known",
    "IEEE conference templates contain guidance text for composing and formatting",
    "Please ensure that all template text is removed",
    "Failure to remove template text may result in your paper not being published",
    "We suggest that you use a text box to insert a graphic",
    "MSWord “Format” pull-down menu",
    "XXX-X-XXXX-XXXX-X/XX/$XX.00 ©20XX IEEE",
    "XXX-X-XXXX-XXXX-X/XX/$XX.00",
    "©20XX IEEE"
]

def get_location_description(page_num: int, rect: Optional[pymupdf.Rect], page_width: float = A4_WIDTH, page_height: float = A4_HEIGHT) -> str:
    """Generate precise human-readable manuscript location (Page, Column, Position, approx line)."""
    if not rect:
        return f"Page {page_num}"
    
    mid_x = page_width / 2.0
    x0, y0, x1, y1 = rect.x0, rect.y0, rect.x1, rect.y1
    
    # Column determination
    if (x1 - x0) > (page_width * 0.65) or (x0 < mid_x - 30 and x1 > mid_x + 30):
        col = "Full Width / Title Section"
    elif x1 <= mid_x + 10:
        col = "Left Column"
    elif x0 >= mid_x - 10:
        col = "Right Column"
    else:
        col = "Center / Spanning Column"
        
    # Vertical section determination
    if y0 < 100:
        vert = "Header / Top Margin"
    elif y0 < 220:
        vert = "Top Section"
    elif y0 < 450:
        vert = "Upper-Middle Section"
    elif y0 < 680:
        vert = "Lower-Middle Section"
    elif y0 < 770:
        vert = "Bottom Section"
    else:
        vert = "Footer Area"
        
    return f"Page {page_num}, {col}, {vert}"


class IEEEComplianceChecker:
    def __init__(
        self, 
        min_pages: int = 4, 
        max_pages: int = 6, 
        hard_max_pages: int = 8,
        target_size: str = "A4",
        expected_copyright: Optional[str] = None
    ):
        self.min_pages = min_pages
        self.max_pages = max_pages
        self.hard_max_pages = hard_max_pages
        self.target_size = target_size
        self.expected_copyright = expected_copyright
        self.violations: List[Violation] = []
        self.metadata: Optional[PaperMetadata] = None

    def check_pdf(self, doc: pymupdf.Document) -> Tuple[List[Violation], PaperMetadata]:
        self.violations = []
        total_pages = len(doc)
        
        # 1. Page Geometry & Metadata Check
        first_page = doc[0]
        p_width = first_page.rect.width
        p_height = first_page.rect.height
        
        is_a4 = (abs(p_width - A4_WIDTH) <= PT_TOLERANCE and abs(p_height - A4_HEIGHT) <= PT_TOLERANCE)
        is_letter = (abs(p_width - LETTER_WIDTH) <= PT_TOLERANCE and abs(p_height - LETTER_HEIGHT) <= PT_TOLERANCE)
        
        size_name = "A4" if is_a4 else ("US Letter" if is_letter else f"Custom ({p_width:.1f}x{p_height:.1f} pt)")
        
        # Check fonts used in document
        doc_fonts = set()
        for page in doc:
            for font in page.get_fonts():
                font_name = font[3] if len(font) > 3 else font[0]
                doc_fonts.add(font_name)
                
        is_regular_page_count = (self.min_pages <= total_pages <= self.max_pages)
        is_extra_pages = (self.max_pages < total_pages <= self.hard_max_pages)
        is_page_count_valid = (self.min_pages <= total_pages <= self.hard_max_pages)
                
        self.metadata = PaperMetadata(
            filename=doc.name,
            total_pages=total_pages,
            page_width_pt=p_width,
            page_height_pt=p_height,
            paper_size_name=size_name,
            fonts=sorted(list(doc_fonts)),
            has_copyright_notice=False,
            copyright_text="",
            is_a4=is_a4,
            is_page_count_valid=is_page_count_valid,
            is_extra_pages=is_extra_pages
        )
        
        # Rule 1.1: Paper Size Check
        if self.target_size == "A4" and not is_a4:
            if is_letter:
                msg = (
                    f"Paper size detected as US Letter ({p_width:.1f} x {p_height:.1f} pt). "
                    "IEEE ICoDMI (Region 10) proceedings require A4 size (210 x 297 mm / 595 x 842 pt) "
                    "in accordance with the official conference template. Please change Page Setup from Letter to A4 "
                    "so margins and column boundaries do not shift when compiled into the IEEE Xplore proceedings."
                )
            else:
                msg = (
                    f"Paper size detected as custom dimensions ({p_width:.1f} x {p_height:.1f} pt). "
                    "The official IEEE ICoDMI conference template mandates standard A4 size (210 x 297 mm / 595 x 842 pt). "
                    "Please adjust the document page setup to A4."
                )
            self.violations.append(Violation(
                no=len(self.violations) + 1,
                category="Page Setup",
                comment=msg,
                location=f"Document-wide (Current size: {p_width:.1f} x {p_height:.1f} pt)",
                page_num=1,
                rect=pymupdf.Rect(0, 0, p_width, 40),
                severity="Fatal"
            ))
            
        # Rule 1.2: Page Count Limit Check (Standard 4-6 pages, Extra Pages max 8 pages)
        if total_pages < self.min_pages:
            self.violations.append(Violation(
                no=len(self.violations) + 1,
                category="Page Count (Below Minimum)",
                comment=f"The manuscript has {total_pages} page(s). IEEE ICoDMI formatting policy requires a minimum of {self.min_pages} pages for regular conference papers.",
                location=f"Overall Document ({total_pages} pages)",
                page_num=total_pages,
                rect=pymupdf.Rect(0, p_height - 50, p_width, p_height),
                severity="Fatal"
            ))
        elif self.max_pages < total_pages <= self.hard_max_pages:
            self.violations.append(Violation(
                no=len(self.violations) + 1,
                category="Page Count (Extra Pages)",
                comment=(
                    f"The manuscript has {total_pages} pages, which exceeds the standard regular paper length ({self.max_pages} pages). "
                    f"This manuscript falls into the 'Extra Pages' category ({total_pages - self.max_pages} additional page(s), maximum {self.hard_max_pages} pages permitted). "
                    "The paper can proceed for publication, but authors must settle the applicable extra page fee according to ICoDMI conference guidelines."
                ),
                location=f"Overall Document ({total_pages} pages)",
                page_num=total_pages,
                rect=pymupdf.Rect(0, p_height - 50, p_width, p_height),
                severity="Warning"
            ))
        elif total_pages > self.hard_max_pages:
            self.violations.append(Violation(
                no=len(self.violations) + 1,
                category="Page Count (Exceeds Maximum Limit)",
                comment=(
                    f"The manuscript contains {total_pages} pages, which exceeds the absolute maximum length permitted by IEEE ICoDMI "
                    f"({self.hard_max_pages} pages including extra pages). "
                    f"The manuscript CANNOT be published unless it is condensed to at most {self.hard_max_pages} pages."
                ),
                location=f"Overall Document ({total_pages} pages)",
                page_num=total_pages,
                rect=pymupdf.Rect(0, p_height - 50, p_width, p_height),
                severity="Fatal"
            ))

        # Locate the References / Bibliography section start boundary
        # In-text style/grammar/citation rules must NOT run on the bibliography itself!
        ref_info = None
        for p_idx in range(total_pages):
            p = doc[p_idx]
            for b in p.get_text("blocks"):
                b_text = b[4].strip()
                if re.match(r'^(\b[IVXLCDM]+\.|\d+\.)?\s*(REFERENCES|References|DAFTAR PUSTAKA)\s*$', b_text, re.IGNORECASE):
                    ref_info = {
                        "page": p_idx + 1,
                        "x0": b[0],
                        "y0": b[1]
                    }
                    break
            if ref_info:
                break

        # Rule 1.3: PDF Document Properties Metadata Check
        self._check_pdf_metadata(doc)

        # Check pages one by one
        for page_idx in range(total_pages):
            page_num = page_idx + 1
            page = doc[page_idx]
            page_rect = page.rect
            page_text = page.get_text("text")
            
            # Rule 2: Template Placeholder Text Check
            self._check_template_placeholders(page, page_num)
            
            # Rule 3: Pagination / Page Numbers check ("Do not add any kind of pagination")
            self._check_pagination(page, page_num)
            
            # Rule 4: First Page Specific Checks (Copyright line, Abstract, Title)
            if page_num == 1:
                self._check_first_page(page, page_text)
                
            # Rule 5: Equations, Figures, Tables & Common Style Rules
            self._check_style_and_grammar(page, page_num, page_text, ref_info)
            
        # Rule 6: References Forensics (ChatGPT tracking, HTML tags, DOI formats, duplicate entries)
        self._check_references_forensics(doc, ref_info)
        
        # Rule 7: Final Page Column Balance Check
        self._check_last_page_column_balance(doc)
            
        return self.violations, self.metadata

    def _check_pdf_metadata(self, doc: pymupdf.Document):
        """Checks PDF document properties for leftover template placeholders."""
        meta = doc.metadata or {}
        title = (meta.get("title") or "").strip()
        author = (meta.get("author") or "").strip()

        # Check placeholder title
        if re.search(r'paper\s*title', title, re.IGNORECASE) or title == "use style: paper title":
            self.violations.append(Violation(
                no=len(self.violations) + 1,
                category="PDF Metadata",
                comment=f"PDF document properties contain template placeholder title: \"{title}\". IEEE template requires PDF metadata to reflect the actual paper title. Please update the Title in File > Info > Properties (in MS Word) or \\title (in LaTeX).",
                location="PDF Document Properties (Title)",
                page_num=1,
                rect=pymupdf.Rect(0, 0, 120, 20),
                severity="Warning",
                snippet=title
            ))

        # Check placeholder author
        if author == "IEEE" or re.search(r'\b(IEEE|line\s*1)\b', author, re.IGNORECASE):
            self.violations.append(Violation(
                no=len(self.violations) + 1,
                category="PDF Metadata",
                comment=f"PDF document properties contain template placeholder author: \"{author}\". Please update the Author property in File > Info > Properties with actual author names.",
                location="PDF Document Properties (Author)",
                page_num=1,
                rect=pymupdf.Rect(0, 0, 120, 20),
                severity="Warning",
                snippet=author
            ))

    def _check_template_placeholders(self, page: pymupdf.Page, page_num: int):
        """Scans page for leftover instructions or placeholder text from IEEE template."""
        for phrase in TEMPLATE_PLACEHOLDER_PHRASES:
            # Case-insensitive text search
            quads = page.search_for(phrase, flags=pymupdf.TEXT_DEHYPHENATE)
            if quads:
                for rect in quads:
                    loc = get_location_description(page_num, rect, page.rect.width, page.rect.height)
                    self.violations.append(Violation(
                        no=len(self.violations) + 1,
                        category="Template Guideline Text",
                        comment=f"Found leftover template placeholder text: \"{phrase}\". IEEE explicitly states: 'Please ensure that all template text is removed prior to submission. Failure to remove template text may result in your paper not being published.'",
                        location=loc,
                        page_num=page_num,
                        rect=rect,
                        severity="Fatal",
                        snippet=phrase
                    ))

    def _check_pagination(self, page: pymupdf.Page, page_num: int):
        """IEEE Rule: 'Do not add any kind of pagination anywhere in the paper.'"""
        p_width = page.rect.width
        p_height = page.rect.height
        
        # Check header area (y < 45) and footer area (y > 795 on A4)
        header_rect = pymupdf.Rect(0, 0, p_width, 45)
        footer_rect = pymupdf.Rect(0, p_height - 45, p_width, p_height)
        
        header_text = page.get_text("text", clip=header_rect).strip()
        footer_text = page.get_text("text", clip=footer_rect).strip()
        
        # Regex for page numbers like "1", "Page 2", "3 of 6", etc.
        page_num_regex = re.compile(r'^(page\s*)?\d+(\s*(of|/)\s*\d+)?$', re.IGNORECASE)
        
        # Check header
        if page_num_regex.match(header_text):
            rects = page.search_for(header_text, clip=header_rect)
            r = rects[0] if rects else header_rect
            self.violations.append(Violation(
                no=len(self.violations) + 1,
                category="Pagination",
                comment=f"Detected page numbering in header: \"{header_text}\". IEEE guideline explicitly states: 'Do not add any kind of pagination anywhere in the paper.'",
                location=f"Page {page_num}, Header Area",
                page_num=page_num,
                rect=r,
                severity="Fatal",
                snippet=header_text
            ))
            
        # Check footer (exclude copyright notice on page 1)
        if page_num > 1 and page_num_regex.match(footer_text):
            rects = page.search_for(footer_text, clip=footer_rect)
            r = rects[0] if rects else footer_rect
            self.violations.append(Violation(
                no=len(self.violations) + 1,
                category="Pagination",
                comment=f"Detected page numbering in footer: \"{footer_text}\". IEEE guideline explicitly states: 'Do not add any kind of pagination anywhere in the paper.'",
                location=f"Page {page_num}, Footer Area",
                page_num=page_num,
                rect=r,
                severity="Fatal",
                snippet=footer_text
            ))

    def _check_first_page(self, page: pymupdf.Page, page_text: str):
        """Checks for IEEE Copyright line, Abstract, and Keywords."""
        p_width = page.rect.width
        p_height = page.rect.height
        
        # 1. IEEE Copyright Notice Check in bottom left footer
        # Catatan: Pengecekan ketiadaan copyright notice dinonaktifkan atas permintaan panitia
        # karena IEEE copyright line biasanya disematkan secara terpusat oleh publisher / komite prosiding.
        footer_clip = pymupdf.Rect(30, p_height - 90, 350, p_height - 15)
        footer_text = page.get_text("text", clip=footer_clip).strip()
        
        has_copyright = bool(re.search(r'(©\s*20\d\d\s*IEEE|\bIEEE\b|97[89]-)', footer_text, re.IGNORECASE))
        if has_copyright:
            self.metadata.has_copyright_notice = True
            self.metadata.copyright_text = footer_text
            
        # 2. Abstract & Keywords format check
        if "abstract" not in page_text.lower():
            self.violations.append(Violation(
                no=len(self.violations) + 1,
                category="Abstract",
                comment="Abstract section heading not found on Page 1.",
                location="Page 1, Top Section",
                page_num=1,
                rect=pymupdf.Rect(40, 150, p_width - 40, 250),
                severity="Fatal"
            ))
        else:
            # Check for correct run-in format: "Abstract—" (with em-dash)
            abstract_rects = page.search_for("Abstract")
            if abstract_rects:
                # Check snippet
                abstract_line = page.get_text("text", clip=pymupdf.Rect(abstract_rects[0].x0, abstract_rects[0].y0 - 2, abstract_rects[0].x0 + 80, abstract_rects[0].y1 + 2))
                if "—" not in abstract_line and "-" not in abstract_line:
                    self.violations.append(Violation(
                        no=len(self.violations) + 1,
                        category="Abstract Formatting",
                        comment="Abstract heading should be formatted as a run-in head in bold/italic followed by an em-dash: 'Abstract—' (not followed by colon or on a separate line).",
                        location=get_location_description(1, abstract_rects[0], p_width, p_height),
                        page_num=1,
                        rect=abstract_rects[0],
                        severity="Warning",
                        snippet=abstract_line.strip()
                    ))
                    
        # Check Keywords presence
        has_keywords = bool(re.search(r'\b(keywords|index terms)\b', page_text, re.IGNORECASE))
        if not has_keywords:
            self.violations.append(Violation(
                no=len(self.violations) + 1,
                category="Keywords",
                comment="Keywords / Index Terms section not found on Page 1.",
                location="Page 1, Following Abstract",
                page_num=1,
                rect=pymupdf.Rect(40, 250, p_width - 40, 320),
                severity="Fatal"
            ))

        # 3. Subtitle / Colon in Paper Title Check
        for b in page.get_text("blocks"):
            if 40 <= b[1] <= 180 and b[3] <= 240:
                b_text = b[4].strip()
                if ":" in b_text and not b_text.startswith("XXX-") and not b_text.lower().startswith("line"):
                    colon_idx = b_text.find(":")
                    sub_snip = b_text[max(0, colon_idx - 15):min(len(b_text), colon_idx + 35)].replace('\n', ' ')
                    self.violations.append(Violation(
                        no=len(self.violations) + 1,
                        category="Paper Title (Subtitle)",
                        comment=f"The manuscript title contains a subtitle after a colon: \"{sub_snip}\". IEEE guidelines state: 'Sub-titles are not captured in IEEE Xplore and should not be used.' Please revise the title into a single coherent title without a colon.",
                        location="Page 1, Title Section",
                        page_num=1,
                        rect=pymupdf.Rect(b[0], b[1], b[2], b[3]),
                        severity="Warning",
                        snippet=sub_snip
                    ))
                    break

        # 4. Author Block Ordinal Placeholders ("1st Given Name", "2nd Author", etc.)
        p1_top_text = page.get_text("text")[:1500]
        for m_ord in re.finditer(r'\b(1st|2nd|3rd|4th|5th|6th)\b(?:\s+(?:Given|Author|Name|[A-Z][a-z]+))?', p1_top_text):
            ord_str = m_ord.group(0)
            rects = page.search_for(ord_str)
            for r in rects:
                if r.y0 < 320:
                    self.violations.append(Violation(
                        no=len(self.violations) + 1,
                        category="Author Affiliation",
                        comment=f"Author name is preceded by template ordinal label \"{ord_str}\". These are leftover template placeholders from the IEEE template and must be removed.",
                        location=get_location_description(1, r, p_width, p_height),
                        page_num=1,
                        rect=r,
                        severity="Warning",
                        snippet=ord_str
                    ))
                    break

        # 5. Keywords Heading check ("Index Terms" vs "Keywords")
        idx_terms_rects = page.search_for("Index Terms")
        if idx_terms_rects:
            r = idx_terms_rects[0]
            self.violations.append(Violation(
                no=len(self.violations) + 1,
                category="Keywords Heading",
                comment="The keyword list is introduced with \"Index Terms\". The IEEE A4 conference template used by ICoDMI prescribes the heading \"Keywords—\" (bold/italic run-in format). Please change \"Index Terms\" to \"Keywords—\".",
                location=get_location_description(1, r, p_width, p_height),
                page_num=1,
                rect=r,
                severity="Warning",
                snippet="Index Terms"
            ))

        # 6. Abstract Content Constraints (Percent, Math equations)
        m_abs = re.search(r'Abstract\b[-—\s]*(.*?)(?=Keywords\b|Index\s+Terms\b|\bI\.\s+|\b1\.\s+|$)', page_text, re.DOTALL | re.IGNORECASE)
        if m_abs:
            abs_text = m_abs.group(1)
            for m_pct in re.finditer(r'(\b\d+(?:\.\d+)?%)', abs_text):
                pct_str = m_pct.group(1)
                rects = page.search_for(pct_str)
                for r in rects:
                    self.violations.append(Violation(
                        no=len(self.violations) + 1,
                        category="Abstract Content",
                        comment=f"The abstract contains the percent symbol \"{pct_str}\". IEEE template states: 'The abstract should not contain symbols, special characters, or mathematical expressions, because they may not display correctly in IEEE Xplore.' Please rephrase using plain text (e.g., \"{pct_str.replace('%', ' percent')}\").",
                        location=get_location_description(1, r, p_width, p_height),
                        page_num=1,
                        rect=r,
                        severity="Warning",
                        snippet=pct_str
                    ))
                    break

            for m_math in re.finditer(r'\b(p\s*[<>=]\s*\d+(?:\.\d+)?|R\^?2\s*=\s*\d+(?:\.\d+)?|RMSE\s*=\s*\d+(?:\.\d+)?|MAE\s*=\s*\d+(?:\.\d+)?|WIS\s*=\s*\d+(?:\.\d+)?|NSE\s*=\s*\d+(?:\.\d+)?)\b', abs_text):
                math_str = m_math.group(1)
                rects = page.search_for(math_str)
                for r in rects:
                    self.violations.append(Violation(
                        no=len(self.violations) + 1,
                        category="Abstract Content",
                        comment=f"The abstract contains mathematical expression or metric formula \"{math_str}\". IEEE template states: 'The abstract must not contain mathematical equations or symbols.' Please express findings in descriptive plain text.",
                        location=get_location_description(1, r, p_width, p_height),
                        page_num=1,
                        rect=r,
                        severity="Warning",
                        snippet=math_str
                    ))
                    break

    def _is_in_references(self, page_num: int, rect: Optional[pymupdf.Rect], page_width: float, ref_info: Optional[dict]) -> bool:
        """Determines if a given rectangle on a page is inside the bibliography/references section."""
        if not ref_info or not rect:
            return False
        if page_num > ref_info["page"]:
            return True
        if page_num < ref_info["page"]:
            return False
            
        # Same page as references heading
        mid_x = page_width / 2.0
        ref_in_right = ref_info["x0"] >= mid_x - 30
        rect_in_right = rect.x0 >= mid_x - 30
        
        if ref_in_right:
            # References starts in right column; left column is body text
            return rect_in_right and rect.y0 >= ref_info["y0"] - 5
        else:
            # References starts in left column; right column is bibliography too
            if rect_in_right:
                return True
            return rect.y0 >= ref_info["y0"] - 5

    def _check_style_and_grammar(self, page: pymupdf.Page, page_num: int, page_text: str, ref_info: Optional[dict] = None):
        """Checks for specific IEEE editorial rules (Equations, Figures, Tables, Citations, Language)."""
        p_width = page.rect.width
        p_height = page.rect.height
        
        # 1. Equation Callout Style: "Eq. (1)" or "equation (1)" mid-sentence
        # IEEE rule: "Use '(1)', not 'Eq. (1)' or 'equation (1)', except at the beginning of a sentence: 'Equation (1) is...'"
        eq_matches = list(re.finditer(r'(?<![\.\?\!\n]\s)(Eq\.\s*\(\d+\)|equation\s*\(\d+\))', page_text))
        for match in eq_matches:
            target_str = match.group(1)
            rects = page.search_for(target_str)
            for r in rects:
                if self._is_in_references(page_num, r, p_width, ref_info):
                    continue
                loc = get_location_description(page_num, r, p_width, p_height)
                self.violations.append(Violation(
                    no=len(self.violations) + 1,
                    category="Equation Citation",
                    comment=f"Found \"{target_str}\" in middle of sentence. IEEE rule: 'Use \"(1)\", not \"Eq. (1)\" or \"equation (1)\", except at the beginning of a sentence: \"Equation (1) is...\"'",
                    location=loc,
                    page_num=page_num,
                    rect=r,
                    severity="Warning",
                    snippet=target_str
                ))
                break  # match first rect on this page
                
        # 2. Figure Citation Style: "Figure 1" or "fig 1"
        # IEEE rule: "Use the abbreviation 'Fig. 1', even at the beginning of a sentence."
        fig_matches = list(re.finditer(r'\b(Figure\s+\d+|fig\s+\d+)\b', page_text))
        for match in fig_matches:
            target_str = match.group(1)
            # Skip if inside table or code snippet if possible
            rects = page.search_for(target_str)
            for r in rects:
                if self._is_in_references(page_num, r, p_width, ref_info):
                    continue
                loc = get_location_description(page_num, r, p_width, p_height)
                self.violations.append(Violation(
                    no=len(self.violations) + 1,
                    category="Figure Citation",
                    comment=f"Found \"{target_str}\". IEEE rule prescribes: 'Use the abbreviation \"Fig. 1\", even at the beginning of a sentence.' (Do not spell out 'Figure').",
                    location=loc,
                    page_num=page_num,
                    rect=r,
                    severity="Warning",
                    snippet=target_str
                ))
                break

        # 3. Table Heading Format: "Table 1" or "Tabel 1" instead of "TABLE I."
        table_matches = list(re.finditer(r'\b(Table\s+\d+|Tabel\s+\d+)\b', page_text))
        for match in table_matches:
            target_str = match.group(1)
            rects = page.search_for(target_str)
            for r in rects:
                if self._is_in_references(page_num, r, p_width, ref_info):
                    continue
                loc = get_location_description(page_num, r, p_width, p_height)
                self.violations.append(Violation(
                    no=len(self.violations) + 1,
                    category="Table Style",
                    comment=f"Found \"{target_str}\". IEEE template prescribes uppercase Roman numerals for table titles: 'TABLE I. TABLE TYPE STYLES' centered above the table.",
                    location=loc,
                    page_num=page_num,
                    rect=r,
                    severity="Warning",
                    snippet=target_str
                ))
                break

        # 4. Heading 5: Numbered REFERENCES or ACKNOWLEDGMENT
        # IEEE rule: Component heads (Acknowledgment, References) are unnumbered.
        comp_matches = list(re.finditer(r'((\b[IVXLCDM]+\.|\d+\.)\s*(REFERENCES|ACKNOWLEDGMENT|ACKNOWLEDGEMENT))', page_text, re.IGNORECASE))
        for match in comp_matches:
            target_str = match.group(1)
            rects = page.search_for(target_str)
            for r in rects:
                loc = get_location_description(page_num, r, p_width, p_height)
                self.violations.append(Violation(
                    no=len(self.violations) + 1,
                    category="Component Heading",
                    comment=f"Found numbered component heading: \"{target_str}\". In IEEE style, Acknowledgments and References are Component Heads (Heading 5) and MUST NOT be numbered with Roman numerals or Arabic numbers.",
                    location=loc,
                    page_num=page_num,
                    rect=r,
                    severity="Warning",
                    snippet=target_str
                ))
                break

        # 5. Spelling: "ACKNOWLEDGEMENT" with 'e'
        # IEEE rule: "The preferred spelling of the word 'acknowledgment' in America is without an 'e' after the 'g'."
        ack_matches = list(re.finditer(r'\b(ACKNOWLEDGEMENT|Acknowledgement)\b', page_text))
        for match in ack_matches:
            target_str = match.group(1)
            rects = page.search_for(target_str)
            for r in rects:
                loc = get_location_description(page_num, r, p_width, p_height)
                self.violations.append(Violation(
                    no=len(self.violations) + 1,
                    category="Spelling / Language",
                    comment=f"Spelling error: \"{target_str}\". IEEE template notes: 'The preferred spelling of the word \"acknowledgment\" in America is without an \"e\" after the \"g\".'",
                    location=loc,
                    page_num=page_num,
                    rect=r,
                    severity="Warning",
                    snippet=target_str
                ))
                break

        # 6. Latin abbreviation "et. al." (period after et)
        # IEEE rule: "There is no period after the 'et' in the Latin abbreviation 'et al.'."
        etal_matches = list(re.finditer(r'\bet\.\s*al\b', page_text, re.IGNORECASE))
        for match in etal_matches:
            target_str = match.group(0)
            rects = page.search_for(target_str)
            for r in rects:
                loc = get_location_description(page_num, r, p_width, p_height)
                self.violations.append(Violation(
                    no=len(self.violations) + 1,
                    category="Latin Abbreviation",
                    comment=f"Found \"{target_str}\". IEEE rule: 'There is no period after the \"et\" in the Latin abbreviation \"et al.\".' (Use 'et al.').",
                    location=loc,
                    page_num=page_num,
                    rect=r,
                    severity="Warning",
                    snippet=target_str
                ))
                break

        # 7. Decimal without leading zero: ".25"
        # IEEE rule: "Use a zero before decimal points: '0.25', not '.25'."
        dec_matches = list(re.finditer(r'(?<=\s)(\.\d+)(?=[\s,;\)])', page_text))
        for match in dec_matches:
            target_str = match.group(1)
            rects = page.search_for(target_str)
            for r in rects:
                loc = get_location_description(page_num, r, p_width, p_height)
                self.violations.append(Violation(
                    no=len(self.violations) + 1,
                    category="Number & Decimal Format",
                    comment=f"Found decimal point without leading zero: \"{target_str}\". IEEE rule: 'Use a zero before decimal points: \"0.25\", not \".25\".'",
                    location=loc,
                    page_num=page_num,
                    rect=r,
                    severity="Warning",
                    snippet=target_str
                ))
                break

        # 8. Deprecated units: "cc" instead of "cm3"
        # IEEE rule: "Use 'cm3', not 'cc'."
        cc_matches = list(re.finditer(r'\b(\d+\s*cc)\b', page_text, re.IGNORECASE))
        for match in cc_matches:
            target_str = match.group(1)
            rects = page.search_for(target_str)
            for r in rects:
                loc = get_location_description(page_num, r, p_width, p_height)
                self.violations.append(Violation(
                    no=len(self.violations) + 1,
                    category="Units Format",
                    comment=f"Found deprecated unit: \"{target_str}\". IEEE rule: 'Use \"cm3\", not \"cc\".'",
                    location=loc,
                    page_num=page_num,
                    rect=r,
                    severity="Warning",
                    snippet=target_str
                ))
                break

        # 9. Citation punctuation before bracket: "word.[1]" or "word,[1]"
        # IEEE rule: "The sentence punctuation follows the bracket [2]."
        # Only flag if punctuation follows a word, NOT when separating citations like "[1], [2]"
        punct_matches = list(re.finditer(r'([a-zA-Z]+[\.\,]\s*\[\d+\])', page_text))
        for match in punct_matches:
            target_str = match.group(1)
            rects = page.search_for(target_str)
            for r in rects:
                if self._is_in_references(page_num, r, p_width, ref_info):
                    continue
                loc = get_location_description(page_num, r, p_width, p_height)
                self.violations.append(Violation(
                    no=len(self.violations) + 1,
                    category="Citation Punctuation",
                    comment=f"Found sentence punctuation placed before citation bracket: \"{target_str}\". IEEE rule: 'The sentence punctuation follows the bracket [2].' (e.g. use '...word [1].' instead of '...word.[1]').",
                    location=loc,
                    page_num=page_num,
                    rect=r,
                    severity="Warning",
                    snippet=target_str
                ))
                break

        # 10. In-text reference citation with "Ref. [1]" in middle of sentence
        # IEEE rule: "Refer simply to the reference number, as in [3], do not use 'Ref. [3]' or 'reference [3]' except at the beginning of a sentence."
        ref_mid_matches = list(re.finditer(r'(?<![\.\?\!\n]\s)(Ref\.\s*\[\d+\]|reference\s*\[\d+\])', page_text))
        for match in ref_mid_matches:
            target_str = match.group(1)
            rects = page.search_for(target_str)
            for r in rects:
                if self._is_in_references(page_num, r, p_width, ref_info):
                    continue
                loc = get_location_description(page_num, r, p_width, p_height)
                self.violations.append(Violation(
                    no=len(self.violations) + 1,
                    category="Reference Callout",
                    comment=f"Found \"{target_str}\" in middle of sentence. IEEE rule: 'Refer simply to the reference number, as in [3], do not use \"Ref. [3]\" or \"reference [3]\" except at the beginning of a sentence.'",
                    location=loc,
                    page_num=page_num,
                    rect=r,
                    severity="Warning",
                    snippet=target_str
                ))
                break

        # 11. Figure Caption Punctuation (stray colon or missing space in caption label)
        for match in re.finditer(r'\b(Fig\.\s*\d+\.\s*:\s*|Fig\.\s*\d+\s*:\s*|Fig\.\d+\.)', page_text):
            target_str = match.group(1)
            rects = page.search_for(target_str)
            for r in rects:
                loc = get_location_description(page_num, r, p_width, p_height)
                self.violations.append(Violation(
                    no=len(self.violations) + 1,
                    category="Figure Caption",
                    comment=f"Irregular punctuation in figure caption label: \"{target_str.strip()}\". IEEE caption style requires: 'Fig. 1. Caption text' (with period and space, without colon).",
                    location=loc,
                    page_num=page_num,
                    rect=r,
                    severity="Warning",
                    snippet=target_str.strip()
                ))
                break

        # 12. Red Font / Revision Markup Check (Camera-ready manuscripts must be black text)
        page_dict = page.get_text("dict")
        red_found = False
        for block in page_dict.get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    color = span.get("color", 0)
                    r_val = (color >> 16) & 0xFF
                    g_val = (color >> 8) & 0xFF
                    b_val = color & 0xFF
                    s_text = span.get("text", "").strip()
                    if len(s_text) > 8 and r_val > 180 and g_val < 60 and b_val < 60:
                        bbox = pymupdf.Rect(span.get("bbox"))
                        loc = get_location_description(page_num, bbox, p_width, p_height)
                        self.violations.append(Violation(
                            no=len(self.violations) + 1,
                            category="Revision Markup (Red Font)",
                            comment=f"Passage rendered in red font: \"{s_text[:50]}\". All text in camera-ready IEEE manuscripts must be in standard black font. Please remove all revision markers.",
                            location=loc,
                            page_num=page_num,
                            rect=bbox,
                            severity="Fatal",
                            snippet=s_text[:50]
                        ))
                        red_found = True
                        break
                if red_found: break
            if red_found: break

        # 13. Prohibited Section Headings in Conference Papers (Author Bio, Supplementary Materials)
        for match in re.finditer(r'\b(Author\s+Biograph(?:y|ies)|Author\s+Profile|Supplementary\s+Materials?|Data\s+and\s+Code\s+Availability)\b', page_text, re.IGNORECASE):
            target_str = match.group(1)
            rects = page.search_for(target_str)
            for r in rects:
                loc = get_location_description(page_num, r, p_width, p_height)
                self.violations.append(Violation(
                    no=len(self.violations) + 1,
                    category="Prohibited Section",
                    comment=f"Found \"{target_str}\". IEEE conference template does not permit author biographies or standalone supplementary sections (these are reserved for Transactions/Journals). Please integrate code/data links into the body text or footnotes.",
                    location=loc,
                    page_num=page_num,
                    rect=r,
                    severity="Warning",
                    snippet=target_str
                ))
                break

        # 14. Unnumbered Conclusion Heading
        for b in page.get_text("blocks"):
            b_text = b[4].strip()
            if re.match(r'^(CONCLUSION|CONCLUSIONS)$', b_text, re.IGNORECASE):
                loc = get_location_description(page_num, pymupdf.Rect(b[:4]), p_width, p_height)
                self.violations.append(Violation(
                    no=len(self.violations) + 1,
                    category="Component Heading",
                    comment="The heading \"CONCLUSION\" is not numbered, whereas other content sections use Roman numerals. Please format as \"V. CONCLUSION\" (or the appropriate Roman numeral).",
                    location=loc,
                    page_num=page_num,
                    rect=pymupdf.Rect(b[:4]),
                    severity="Warning",
                    snippet=b_text
                ))

    def _check_references_forensics(self, doc: pymupdf.Document, ref_info: Optional[dict]):
        """Inspects references section for AI tracking parameters, HTML tags, duplicate citations, and DOI formatting."""
        if not ref_info:
            return
        start_page = ref_info["page"] - 1
        ref_text = ""
        for p_idx in range(start_page, len(doc)):
            ref_text += doc[p_idx].get_text("text") + "\n"

        # 1. ChatGPT tracking parameters in reference URLs
        for m in re.finditer(r'(https?://[^\s]+(?:utm_source=chatgpt\.com|chatgpt\.com)[^\s]*)', ref_text, re.IGNORECASE):
            url_str = m.group(1)
            for p_idx in range(start_page, len(doc)):
                rects = doc[p_idx].search_for(url_str[:25])
                if rects:
                    loc = get_location_description(p_idx + 1, rects[0], doc[p_idx].rect.width, doc[p_idx].rect.height)
                    self.violations.append(Violation(
                        no=len(self.violations) + 1,
                        category="Reference Quality",
                        comment=f"Reference URL contains chatbot tracking parameter: \"{url_str}\". References must cite original academic sources directly without AI/chatbot tracking parameters.",
                        location=loc,
                        page_num=p_idx + 1,
                        rect=rects[0],
                        severity="Fatal",
                        snippet=url_str
                    ))
                    break

        # 2. HTML/XML markup tags in reference text (<scp>, </scp>, etc.)
        for m in re.finditer(r'(<[/]?[a-zA-Z]{2,6}>)', ref_text):
            tag_str = m.group(1)
            for p_idx in range(start_page, len(doc)):
                rects = doc[p_idx].search_for(tag_str)
                if rects:
                    loc = get_location_description(p_idx + 1, rects[0], doc[p_idx].rect.width, doc[p_idx].rect.height)
                    self.violations.append(Violation(
                        no=len(self.violations) + 1,
                        category="Reference Formatting",
                        comment=f"Reference entry contains raw HTML/XML markup tags: \"{tag_str}\". The reference list must be in plain text without markup tags.",
                        location=loc,
                        page_num=p_idx + 1,
                        rect=rects[0],
                        severity="Warning",
                        snippet=tag_str
                    ))
                    break

        # 3. Uppercase "DOI:" prefix in references
        for m in re.finditer(r'\b(DOI:\s*10\.\d{4,9}/[^\s,]+)', ref_text):
            doi_str = m.group(1)
            for p_idx in range(start_page, len(doc)):
                rects = doc[p_idx].search_for("DOI:")
                if rects:
                    for r in rects:
                        if self._is_in_references(p_idx + 1, r, doc[p_idx].rect.width, ref_info):
                            loc = get_location_description(p_idx + 1, r, doc[p_idx].rect.width, doc[p_idx].rect.height)
                            self.violations.append(Violation(
                                no=len(self.violations) + 1,
                                category="DOI Format",
                                comment="Reference uses uppercase \"DOI:\" prefix. IEEE style requires lowercase \"doi: 10.xxxx/...\" without capitalization.",
                                location=loc,
                                page_num=p_idx + 1,
                                rect=r,
                                severity="Warning",
                                snippet=doi_str
                            ))
                            break
                    break

        # 4. Redundant/doubled DOI prefixes ("doi: doi.org/" or "doi: https://doi.org/")
        for m in re.finditer(r'\b(doi:\s*(?:https?://)?doi\.org/[^\s,]+)', ref_text, re.IGNORECASE):
            doubled_doi = m.group(1)
            for p_idx in range(start_page, len(doc)):
                rects = doc[p_idx].search_for(doubled_doi[:20])
                if rects:
                    loc = get_location_description(p_idx + 1, rects[0], doc[p_idx].rect.width, doc[p_idx].rect.height)
                    self.violations.append(Violation(
                        no=len(self.violations) + 1,
                        category="DOI Format",
                        comment=f"Reference contains redundant or doubled DOI prefix: \"{doubled_doi}\". IEEE style prescribes bare \"doi: 10.xxxx/...\" (e.g. use 'doi: 10.1109/...' rather than 'doi: https://doi.org/...').",
                        location=loc,
                        page_num=p_idx + 1,
                        rect=rects[0],
                        severity="Warning",
                        snippet=doubled_doi
                    ))
                    break

        # 5. Duplicate references check in bibliography
        entries = list(re.finditer(r'\[(\d+)\]\s*([^,]+),\s*["“\']([^"”\']{15,})["”\']', ref_text))
        seen_titles = []
        for em in entries:
            num = int(em.group(1))
            entry_title = em.group(3).strip().lower()
            seen_titles.append((num, entry_title))

        for i in range(len(seen_titles)):
            for j in range(i + 1, len(seen_titles)):
                n1, t1 = seen_titles[i]
                n2, t2 = seen_titles[j]
                ratio = SequenceMatcher(None, t1, t2).ratio()
                if ratio > 0.85:
                    self.violations.append(Violation(
                        no=len(self.violations) + 1,
                        category="Duplicate Reference",
                        comment=f"References [{n1}] and [{n2}] appear to be duplicate entries for the same work (\"{t1.title()}\"). IEEE style does not allow duplicate entries in the reference list. Please merge them into a single entry and update in-text citations.",
                        location=f"References [{n1}] and [{n2}]",
                        page_num=start_page + 1,
                        rect=pymupdf.Rect(0, 0, 100, 20),
                        severity="Fatal",
                        snippet=f"[{n1}] and [{n2}]"
                    ))

    def _check_last_page_column_balance(self, doc: pymupdf.Document):
        """Checks if the columns on the final page are approximately balanced."""
        if len(doc) == 0:
            return
        p_last = doc[-1]
        page_num = len(doc)
        p_width = p_last.rect.width
        p_height = p_last.rect.height
        mid_x = p_width / 2.0

        blocks = p_last.get_text("blocks")
        content_blocks = [b for b in blocks if b[1] >= 50 and b[3] <= p_height - 35 and len(b[4].strip()) > 10]
        if not content_blocks:
            return

        left_blocks = [b for b in content_blocks if b[0] < mid_x]
        right_blocks = [b for b in content_blocks if b[0] >= mid_x - 20]

        left_y1 = max([b[3] for b in left_blocks] or [0])
        right_y1 = max([b[3] for b in right_blocks] or [0])

        diff = left_y1 - right_y1
        if left_y1 > 420 and (right_y1 == 0 or diff > 260):
            rect = pymupdf.Rect(mid_x, left_y1 - 60, p_width - 40, left_y1)
            self.violations.append(Violation(
                no=len(self.violations) + 1,
                category="Column Balance",
                comment="The columns on the final page are not balanced: the left column extends significantly lower than the right column. IEEE guidelines require the two columns on the final page to be of approximately equal length (e.g., using \\IEEEtriggeratref or the balance package in LaTeX, or inserting a column break in Word).",
                location=f"Page {page_num}, Column Area",
                page_num=page_num,
                rect=rect,
                severity="Warning",
                snippet="Unbalanced columns"
            ))
