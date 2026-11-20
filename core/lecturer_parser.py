import io
import re
from typing import List, Dict, Any, Optional
import docx
import pymupdf

def make_imperative_directive(comment: str) -> str:
    """
    Transforms a descriptive lecturer comment into a clean, active imperative directive (kata suruhan/instruktif).
    """
    text = comment.strip()
    if not text:
        return ""

    # Rule 1: Direct 'Please [verb]' -> '[Verb]'
    m_please = re.match(r'^Please\s+([a-z]+)(.*)', text, re.IGNORECASE)
    if m_please:
        verb = m_please.group(1).capitalize()
        rest = m_please.group(2)
        return f"{verb}{rest}".strip()

    # Rule 2: Pattern-specific transformations based on conference compliance standards
    lower = text.lower()
    
    # Page setup (US Letter vs A4)
    if "us letter" in lower and ("a4" in lower or "template" in lower):
        return "Change page setup from US Letter to official IEEE A4 template (210 x 297 mm); regenerate PDF via IEEE PDF eXpress."
        
    # Page count limit
    if "eight pages" in lower or "exceed" in lower and "page" in lower:
        return "Condense manuscript to regular length (6 pages) or confirm settlement of applicable extra page fee."
        
    # Copyright notice
    if "copyright notice is missing" in lower or "copyright" in lower and "missing" in lower:
        return "Insert official IEEE copyright notice at the bottom-left of Page 1; ensure IEEE Copyright Form is completed in EDAS."
        
    # Red font / revision markup
    if "red font" in lower or "revision mark" in lower or "coloured text" in lower:
        return "Convert all red font revision text to standard 100% black font; remove all review markers."
        
    # PDF document properties metadata
    if "pdf document properties" in lower or "metadata" in lower and ("placeholder" in lower or "title" in lower):
        return "Update PDF document properties (Title and Author) in file properties with genuine manuscript metadata."
        
    # Split tables / Mid-column floats
    if "split across columns" in lower or "middle of a column" in lower:
        return "Reposition figures and tables so they do not split across columns or pages; place floats strictly at the top or bottom of a column."
        
    # Conclusion unnumbered or orphan
    if "conclusion" in lower and ("not numbered" in lower or "orphan" in lower):
        return "Number the section heading as 'IV. CONCLUSION' (or appropriate Roman numeral) and avoid orphan headings isolated at column bottom."
        
    # Institution name inconsistency
    if "institution name" in lower or "ipb university" in lower and "inconsistent" in lower:
        return "Standardize institution affiliation: use official English name 'IPB University' consistently across all author blocks."
        
    # Subtitle in title
    if "subtitle" in lower or ("colon" in lower and "title" in lower):
        return "Revise title into a single declarative title line without a subtitle or colon (subtitles are not captured in IEEE Xplore)."
        
    # Fig vs Figure inconsistency
    if "fig" in lower and "figure" in lower and ("inconsistent" in lower or "abbreviation" in lower):
        return "Replace 'Figure' with standard abbreviation 'Fig.' consistently throughout the manuscript; do not spell out 'Figure'."
        
    # Table citation Arabic vs Roman
    if "table" in lower and "arabic" in lower or "roman" in lower and "cited" in lower:
        return "Cite tables using uppercase Roman numerals (e.g. 'Table II', 'Table IV') instead of Arabic numbers."
        
    # Fig not cited
    if "not cited in the text" in lower or "before it appears" in lower:
        return "Add in-text citation for all figures and tables before they appear in the manuscript."
        
    # Large blank space / Column balance
    if "blank space" in lower or "columns on the last page are not balanced" in lower or "equal length" in lower:
        return "Balance columns on the page to approximately equal length; eliminate large blank space by rearranging text or figures."
        
    # Ordinal labels (1st, 2nd, 3rd)
    if "ordinal labels" in lower or ("1st" in lower and "preceding" in lower):
        return "Remove template ordinal labels ('1st', '2nd', '3rd') preceding author names."
        
    # Incomplete references
    if "references are incomplete" in lower or "lack a doi" in lower:
        return "Complete bibliographic data for all reference entries (authors, title, journal/conference, volume, issue, pages, date, and DOI)."
        
    # Acronyms in reference titles (BibTeX lowercase)
    if "acronyms" in lower and ("lower case" in lower or "bibtex" in lower):
        return "Protect acronyms and proper nouns in BibTeX entries using curly braces (e.g., {CNN}, {PRISMA}) to preserve capitalization."
        
    # Duplicate references
    if "same work" in lower or "duplicate" in lower and "reference" in lower:
        return "Merge duplicate reference entries into a single entry and update in-text citation numbers."

    # Rule 3: Look for an imperative sentence inside the paragraph (e.g., "Please ...", "Ensure that ...")
    sentences = re.split(r'(?<=[.!?])\s+', text)
    for s in sentences:
        s_clean = s.strip()
        m_inner = re.match(r'^(Please\s+)?([A-Z][a-z]+)\s+(.+)', s_clean)
        if m_inner:
            verb = m_inner.group(2).lower()
            # Common imperative verbs
            if verb in ["change", "replace", "remove", "insert", "format", "balance", "condense", "update", "reposition", "renumber", "correct", "verify", "enlarge", "simplify", "add", "delete", "use", "standardize", "merge", "protect"]:
                directive = m_inner.group(2) + " " + m_inner.group(3)
                if not directive.endswith("."): directive += "."
                return directive

    return text

def infer_category(comment: str) -> str:
    """Classifies a lecturer comment into standard compliance categories."""
    lower = comment.lower()
    if "letter" in lower or "a4" in lower or "paper size" in lower:
        return "Page Setup"
    if "eight pages" in lower or "page count" in lower or "over-length" in lower or "pages" in lower and "limit" in lower:
        return "Page Count"
    if "copyright" in lower:
        return "IEEE Copyright Notice"
    if "red font" in lower or "colour" in lower or "color" in lower or "revision mark" in lower:
        return "Revision Markup (Red Font)"
    if "metadata" in lower or "document properties" in lower:
        return "PDF Metadata"
    if "fig" in lower and "figure" in lower:
        return "Figure Citation"
    if "table" in lower and ("roman" in lower or "arabic" in lower or "caption" in lower or "heading" in lower):
        return "Table Style"
    if "split" in lower or "orphan" in lower or "blank space" in lower or "balance" in lower:
        return "Page Layout & Column Balance"
    if "ordinal" in lower or "1st" in lower:
        return "Author Affiliation"
    if "institution" in lower or "affiliation" in lower or "ipb" in lower:
        return "Author Affiliation"
    if "subtitle" in lower or "colon" in lower and "title" in lower:
        return "Paper Title (Subtitle)"
    if "conclusion" in lower:
        return "Component Heading"
    if "acronym" in lower or "bibtex" in lower:
        return "Reference Formatting (Acronyms)"
    if "duplicate" in lower and "reference" in lower:
        return "Duplicate Reference"
    if "reference" in lower or "doi" in lower or "bibliographic" in lower:
        return "Reference Completeness"
    if "caption" in lower:
        return "Caption Formatting"
    if "font" in lower and "size" in lower:
        return "Font Size"
    return "General Format"

def parse_docx_comments(file_bytes: bytes) -> List[Dict[str, Any]]:
    """Parses committee comments table from a Word (.docx) file."""
    doc = docx.Document(io.BytesIO(file_bytes))
    comments = []
    
    for table in doc.tables:
        if not table.rows:
            continue
        headers = [c.text.strip().lower() for c in table.rows[0].cells]
        if any("comment" in h for h in headers):
            no_idx, comm_idx, loc_idx = 0, 1, 2
            for i, h in enumerate(headers):
                if "no" in h: no_idx = i
                elif "comment" in h: comm_idx = i
                elif "location" in h: loc_idx = i
                
            for r_idx, row in enumerate(table.rows[1:], start=1):
                cells = row.cells
                no_str = cells[no_idx].text.strip() if len(cells) > no_idx else str(r_idx)
                comm_text = cells[comm_idx].text.strip() if len(cells) > comm_idx else ""
                loc_text = cells[loc_idx].text.strip() if len(cells) > loc_idx else ""
                
                if comm_text:
                    directive = make_imperative_directive(comm_text)
                    cat = infer_category(comm_text)
                    comments.append({
                        "raw_no": no_str,
                        "category": cat,
                        "comment": directive,
                        "original_comment": comm_text,
                        "location": loc_text or "Entire manuscript",
                        "source": "Komite"
                    })
    return comments

def parse_pdf_comments(file_bytes: bytes) -> List[Dict[str, Any]]:
    """Parses committee comments table from a PDF file using text block analysis."""
    doc = pymupdf.open(stream=file_bytes, filetype="pdf")
    full_text = ""
    for page in doc:
        full_text += page.get_text("text") + "\n"

    # Find start after "Authors' Response"
    start_pos = 0
    m_start = re.search(r"Authors['’]?\s*Response", full_text, re.IGNORECASE)
    if m_start:
        start_pos = m_start.end()
        
    body_text = full_text[start_pos:]
    items = re.split(r'\n+(\d+)\s*\n+', "\n" + body_text)
    comments = []
    
    for i in range(1, len(items), 2):
        item_no = items[i]
        item_body = items[i+1].strip()
        lines = [ln.strip() for ln in item_body.split('\n') if ln.strip()]
        if not lines:
            continue
            
        loc_lines = []
        comm_lines = []
        is_loc = True
        for line in reversed(lines):
            # Check if line looks like location
            is_loc_indicator = bool(re.match(r'^(page|pages|entire|table|fig|section|references|pdf metadata|all)', line, re.IGNORECASE) or line.startswith('(') or len(line) < 35)
            if is_loc and is_loc_indicator:
                loc_lines.insert(0, line)
            else:
                is_loc = False
                comm_lines.insert(0, line)
                
        comm_text = " ".join(comm_lines).strip()
        loc_text = " ".join(loc_lines).strip() or "Entire manuscript"
        
        # If comm_text was empty because all lines looked like loc
        if not comm_text and loc_lines:
            comm_text = " ".join(loc_lines)
            loc_text = "Entire manuscript"
            
        if comm_text and len(comm_text) > 5 and not comm_text.lower().startswith("committee comments"):
            directive = make_imperative_directive(comm_text)
            cat = infer_category(comm_text)
            comments.append({
                "raw_no": item_no,
                "category": cat,
                "comment": directive,
                "original_comment": comm_text,
                "location": loc_text,
                "source": "Komite"
            })
            
    return comments

def parse_lecturer_file(file_bytes: bytes, filename: str) -> List[Dict[str, Any]]:
    """Parses lecturer committee comments from either .docx or .pdf."""
    fn = filename.lower()
    if fn.endswith(".docx") or fn.endswith(".doc"):
        try:
            return parse_docx_comments(file_bytes)
        except Exception:
            return []
    elif fn.endswith(".pdf"):
        try:
            return parse_pdf_comments(file_bytes)
        except Exception:
            return []
    return []
