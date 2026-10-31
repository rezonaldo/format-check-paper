import re
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
                    f"Ukuran kertas terdeteksi US Letter ({p_width:.1f} x {p_height:.1f} pt). "
                    "Prosiding IEEE ICoDMI (Region 10) mewajibkan ukuran A4 (210 x 297 mm / 595 x 842 pt) "
                    "sesuai template resmi. Harap ubah Page Setup dokumen dari Letter menjadi A4 agar format batas "
                    "margin dan kolom tidak bergeser saat digabungkan ke prosiding IEEE Xplore."
                )
            else:
                msg = (
                    f"Ukuran kertas terdeteksi kustom ({p_width:.1f} x {p_height:.1f} pt). "
                    "Template resmi IEEE ICoDMI mewajibkan standar ukuran A4 (210 x 297 mm / 595 x 842 pt). Harap atur ukuran kertas dokumen ke A4."
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
            
        # Rule 1.2: Page Count Limit Check (Standar 4-6 Hal, Extra Pages maks. 8 Hal)
        if total_pages < self.min_pages:
            self.violations.append(Violation(
                no=len(self.violations) + 1,
                category="Page Count",
                comment=f"Naskah hanya berjumlah {total_pages} halaman. Ketentuan IEEE ICoDMI mensyaratkan naskah minimal {self.min_pages} halaman.",
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
                    f"Naskah berjumlah {total_pages} halaman (melebihi batas standar reguler {self.max_pages} halaman). "
                    f"Naskah masuk kategori 'Extra Pages' ({total_pages - self.max_pages} halaman tambahan, maksimal diperbolehkan {self.hard_max_pages} halaman). "
                    "Naskah tetap dapat diproses, namun penulis wajib melunasi biaya tambahan (extra page fee) sesuai ketentuan konferensi ICoDMI."
                ),
                location=f"Overall Document ({total_pages} pages)",
                page_num=total_pages,
                rect=pymupdf.Rect(0, p_height - 50, p_width, p_height),
                severity="Warning"
            ))
        elif total_pages > self.hard_max_pages:
            self.violations.append(Violation(
                no=len(self.violations) + 1,
                category="Page Count (Melebihi Batas Maksimal)",
                comment=(
                    f"Naskah memiliki {total_pages} halaman. Melebihi batas maksimal absolut yang diperbolehkan di IEEE ICoDMI "
                    f"(maksimal {self.hard_max_pages} halaman termasuk extra pages). "
                    f"Naskah TIDAK DAPAT DITERBITKAN sebelum dipangkas maksimal menjadi {self.hard_max_pages} halaman."
                ),
                location=f"Overall Document ({total_pages} pages)",
                page_num=total_pages,
                rect=pymupdf.Rect(0, p_height - 50, p_width, p_height),
                severity="Fatal"
            ))

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
            self._check_style_and_grammar(page, page_num, page_text)
            
        return self.violations, self.metadata

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
                    
        # Check Keywords
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

    def _check_style_and_grammar(self, page: pymupdf.Page, page_num: int, page_text: str):
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
        # IEEE rule: "Refer simply to the reference number, as in [3]—do not use 'Ref. [3]' or 'reference [3]' except at the beginning of a sentence."
        ref_mid_matches = list(re.finditer(r'(?<![\.\?\!\n]\s)(Ref\.\s*\[\d+\]|reference\s*\[\d+\])', page_text))
        for match in ref_mid_matches:
            target_str = match.group(1)
            rects = page.search_for(target_str)
            for r in rects:
                loc = get_location_description(page_num, r, p_width, p_height)
                self.violations.append(Violation(
                    no=len(self.violations) + 1,
                    category="Reference Callout",
                    comment=f"Found \"{target_str}\" in middle of sentence. IEEE rule: 'Refer simply to the reference number, as in [3]—do not use \"Ref. [3]\" or \"reference [3]\" except at the beginning of a sentence.'",
                    location=loc,
                    page_num=page_num,
                    rect=r,
                    severity="Warning",
                    snippet=target_str
                ))
                break
