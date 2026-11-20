import os
import re
from typing import List, Dict, Any, Optional
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import parse_xml, OxmlElement
from docx.oxml.ns import nsdecls, qn

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from .models import Violation, PaperMetadata

def set_cell_background(cell, fill_hex):
    """Sets background color of a Word table cell."""
    tcPr = cell._tc.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
    tcPr.append(shd)

def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    """Sets inner padding/margins for a Word table cell."""
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = parse_xml(f'''
        <w:tcMar {nsdecls("w")}>
            <w:top w:w="{top}" w:type="dxa"/>
            <w:bottom w:w="{bottom}" w:type="dxa"/>
            <w:left w:w="{left}" w:type="dxa"/>
            <w:right w:w="{right}" w:type="dxa"/>
        </w:tcMar>
    ''')
    tcPr.append(tcMar)

def group_violations(violations: List[Violation]) -> List[Dict[str, Any]]:
    """
    Groups individual violations by category and rule pattern.
    Produces clean, consolidated rows for Word (.docx) and Web view:
    - Merges repeated occurrences (e.g. 'Table 1', 'Table 2', and 'Table 3')
    - Consolidates locations (e.g. 'Page 3 (Right Col); Page 4 (Right Col)')
    - Writes the IEEE guideline explanation once
    - Provides a structured list of child violations for drill-down inspection
    """
    if not violations:
        return []

    grouped: Dict[str, List[Violation]] = {}
    for v in violations:
        key = v.category
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(v)

    result = []
    group_no = 1

    for category, items in grouped.items():
        if len(items) == 1:
            item = items[0]
            result.append({
                "no": group_no,
                "category": item.category,
                "comment": item.comment,
                "location": item.location,
                "severity": item.severity,
                "count": 1,
                "items": [{
                    "no": item.no,
                    "location": item.location,
                    "comment": item.comment,
                    "snippet": item.snippet
                }]
            })
            group_no += 1
            continue

        # Multiple items in this category
        snippets = []
        seen_snip = set()
        for it in items:
            s = it.snippet.strip(' "\'')
            if s and s not in seen_snip:
                seen_snip.add(s)
                snippets.append(f'"{s}"')

        # Format combined snippet text
        if len(snippets) == 1:
            snip_text = snippets[0]
        elif len(snippets) == 2:
            snip_text = f"{snippets[0]} and {snippets[1]}"
        elif len(snippets) > 2:
            snip_text = f"{', '.join(snippets[:-1])}, and {snippets[-1]}"
        else:
            snip_text = ""

        # Consolidate comment based on category (Action-oriented / Instructive verbs)
        first_comment = items[0].comment
        if category == "Table Style":
            comment = f"Change table numbering to uppercase Roman numerals in ALL CAPS: 'TABLE I. TABLE TYPE STYLES' centered above table ({snip_text}); do not use Arabic numerals."
        elif category == "Figure Citation":
            comment = f"Replace 'Figure' with the standard abbreviation 'Fig.' ({snip_text}), even at the beginning of a sentence."
        elif category == "Citation Punctuation":
            comment = f"Move sentence punctuation to follow after citation brackets (e.g. {snip_text}). IEEE rule: 'The sentence punctuation follows the bracket [2].' (e.g. write '...word [1].' instead of '...word.[1]')."
        elif category == "Equation Citation":
            comment = f"Refer to equations simply as '(1)' in mid-sentence ({snip_text}); use 'Equation (1)' only at the beginning of a sentence."
        elif category == "Template Guideline Text":
            comment = f"Remove leftover template placeholder text: {snip_text}. All IEEE template instruction text must be removed prior to camera-ready submission."
        elif category == "Reference Callout":
            comment = f"Refer directly to citation numbers as '[3]' in mid-sentence ({snip_text}); do not write 'Ref. [3]' or 'reference [3]'."
        elif category == "Number & Decimal Format":
            comment = f"Insert a leading zero before decimal points ({snip_text}). IEEE rule: 'Use a zero before decimal points: \"0.25\", not \".25\".'"
        elif category == "Units Format":
            comment = f"Use standard metric unit 'cm3' instead of deprecated unit ({snip_text}). IEEE rule: 'Use \"cm3\", not \"cc\".'"
        elif category == "Author Affiliation":
            if "ordinal" in first_comment.lower() or "1st" in first_comment.lower():
                comment = f"Delete template ordinal labels ({snip_text}) from author names."
            else:
                comment = first_comment
        elif category == "Keywords Heading":
            comment = "Change heading from 'Index Terms' to 'Keywords—' in bold/italic run-in format."
        elif category == "Abstract Content":
            comment = f"Remove percent symbols, mathematical equations, or formulas from abstract ({snip_text}); express findings in descriptive plain text."
        elif category == "DOI Format":
            comment = f"Standardize DOI prefix to lowercase 'doi: 10.xxxx/...' without capitalization or redundant prefixes ({snip_text})."
        elif category == "Figure Caption":
            comment = f"Format figure caption labels as 'Fig. X. Caption text' with a period and space ({snip_text}); remove stray colons."
        elif category == "Table Citation":
            comment = f"Cite tables using uppercase Roman numerals and capitalize table callouts ({snip_text}, e.g. 'Table I', 'Table II'); do not use Arabic numbers or lowercase 'table'."
        elif category == "Table Title Format":
            comment = f"Format table titles in ALL CAPS centered above table ({snip_text}); do not use lowercase or title case."
        elif category == "Caption Label Typo":
            comment = f"Standardize caption labels: format as 'Fig. X. Caption text' or 'TABLE X. TITLE' ({snip_text}); remove stray colons or punctuation typos."
        elif category == "Raw LaTeX Syntax":
            comment = f"Render raw LaTeX syntax properly ({snip_text}); compile all equations and citations into standard rendered text."
        elif category == "Review Annotation / Highlight":
            comment = f"Remove visible highlight annotations and review markup ({snip_text}) from camera-ready manuscript."
        elif category == "Non-Black Font Color" or category == "Revision Markup (Red Font)":
            comment = f"Convert all non-black and colored font text ({snip_text}) to standard 100% black font."
        elif category == "Drop Cap (Novel Style)":
            comment = f"Remove drop cap initial letter ({snip_text}) at the beginning of Introduction; write in standard 10 pt regular text."
        elif category == "Online Reference Format":
            comment = f"Format online references using standard IEEE prefix '[Online]. Available: URL' and include access dates ({snip_text})."
        elif category == "Font Size":
            if len(items) == 1:
                comment = first_comment
            else:
                comment = f"Adjust section font sizes to meet official IEEE specifications ({snip_text}): Paper Title 24 pt, Body Text 10 pt, Abstract/Keywords 9 pt, References and Captions 8 pt."
        else:
            if items[0].snippet and items[0].snippet in first_comment and snip_text:
                comment = first_comment.replace(f'"{items[0].snippet}"', snip_text)
            else:
                comment = f"Multiple occurrences ({len(items)} items): {first_comment}"

        # Consolidate locations
        locs = []
        seen_loc = set()
        for it in items:
            loc_str = it.location
            m = re.match(r'^(Page \d+)(?:,\s*([A-Za-z]+ Column))?', loc_str)
            if m:
                p = m.group(1)
                col = m.group(2)
                if col:
                    short_col = col.replace(" Column", " Col")
                    clean_loc = f"{p} ({short_col})"
                else:
                    clean_loc = p
            else:
                clean_loc = loc_str

            if clean_loc not in seen_loc:
                seen_loc.add(clean_loc)
                locs.append(clean_loc)

        merged_location = "; ".join(locs)
        severities = [it.severity for it in items]
        top_severity = "Fatal" if "Fatal" in severities else ("Warning" if "Warning" in severities else "Info")

        result.append({
            "no": group_no,
            "category": category,
            "comment": comment,
            "location": merged_location,
            "severity": top_severity,
            "count": len(items),
            "items": [{
                "no": it.no,
                "location": it.location,
                "comment": it.comment,
                "snippet": it.snippet
            } for it in items]
        })
        group_no += 1

    return result

def generate_word_report(
    violations: List[Violation], 
    metadata: PaperMetadata, 
    output_path: str,
    conference_name: str = "ICoDMI 2026 (SSMI IPB)",
    merged_items: Optional[List[Dict[str, Any]]] = None,
    forensics_data: Optional[Dict[str, Any]] = None
) -> str:
    """
    Generates a Microsoft Word (.docx) document with the official consolidated revision table:
    Columns: No | Format Comments | Location in Manuscript | Authors' Response
    Also appends Reference Integrity & Citation Forensics sheet if forensics findings exist.
    """
    doc = docx.Document()
    
    # Set page margins (0.8 inch for clean 4-column fit)
    sections = doc.sections
    for section in sections:
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)
        section.left_margin = Inches(0.8)
        section.right_margin = Inches(0.8)
        
    # Title Header (Matching official committee format)
    title_p = doc.add_paragraph()
    title_p.paragraph_format.space_after = Pt(2)
    run_title = title_p.add_run(f"Committee Comments & Author's Response")
    run_title.font.name = "Times New Roman"
    run_title.font.size = Pt(14)
    run_title.font.bold = True
    run_title.font.color.rgb = RGBColor(24, 43, 73)
    
    sub_p = doc.add_paragraph()
    sub_p.paragraph_format.space_after = Pt(12)
    run_sub = sub_p.add_run(f"Conference: {conference_name} • IEEE Manuscript Compliance Review")
    run_sub.font.name = "Times New Roman"
    run_sub.font.size = Pt(10.5)
    run_sub.font.italic = True
    
    # Metadata Info
    meta_p = doc.add_paragraph()
    meta_p.paragraph_format.space_after = Pt(12)
    meta_p.add_run("Manuscript Name: ").bold = True
    display_name = os.path.basename(metadata.filename) if metadata.filename else "manuscript.pdf"
    meta_p.add_run(f"{display_name}\n")
    meta_p.add_run("Page Count / Size: ").bold = True
    meta_p.add_run(f"{metadata.total_pages} pages ({metadata.paper_size_name})\n")
    meta_p.add_run("Total Findings: ").bold = True
    
    items_to_render = merged_items if merged_items is not None else group_violations(violations)
    run_status = meta_p.add_run(f"{len(items_to_render)} revision directive(s) consolidated from review")
    if len(items_to_render) > 0:
        run_status.font.color.rgb = RGBColor(180, 40, 40)
        run_status.bold = True
        
    # 4-Column Official Table:
    # No | Format Comments | Location in Manuscript | Authors' Response
    table = doc.add_table(rows=1, cols=4)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    
    # Header Row
    hdr_cells = table.rows[0].cells
    hdr_titles = ["No", "Format Comments", "Location in Manuscript", "Authors' Response"]
    col_widths = [Inches(0.45), Inches(3.3), Inches(1.5), Inches(1.5)]
    
    for i, title in enumerate(hdr_titles):
        cell = hdr_cells[i]
        cell.width = col_widths[i]
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        set_cell_background(cell, "F2F4F7")
        set_cell_margins(cell, top=140, bottom=140, left=120, right=120)
        
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER if i == 0 else WD_ALIGN_PARAGRAPH.LEFT
        run = p.add_run(title)
        run.font.name = "Times New Roman"
        run.font.size = Pt(10)
        run.font.bold = True
        run.font.color.rgb = RGBColor(30, 30, 30)
        
    # Populate rows using consolidated group data
    if not items_to_render:
        row_cells = table.add_row().cells
        for i in range(4):
            row_cells[i].width = col_widths[i]
            set_cell_margins(row_cells[i], top=120, bottom=120, left=120, right=120)
        row_cells[0].paragraphs[0].add_run("-")
        row_cells[1].paragraphs[0].add_run("All checked IEEE format rules are compliant! No revisions needed.")
        row_cells[2].paragraphs[0].add_run("-")
        row_cells[3].paragraphs[0].add_run("-")
    else:
        for idx, g in enumerate(items_to_render, start=1):
            row = table.add_row()
            cells = row.cells
            for i in range(4):
                cells[i].width = col_widths[i]
                set_cell_margins(cells[i], top=120, bottom=120, left=120, right=120)
                
            # Column 1: No
            p0 = cells[0].paragraphs[0]
            p0.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r0 = p0.add_run(str(g.get("no", idx)))
            r0.font.name = "Times New Roman"
            r0.font.size = Pt(9.5)
            
            # Column 2: Format Comments (Source + Category + Active Directive)
            p1 = cells[1].paragraphs[0]
            p1.alignment = WD_ALIGN_PARAGRAPH.LEFT
            
            if g.get("source"):
                r1_src = p1.add_run(f"[{g['source']}] ")
                r1_src.font.name = "Times New Roman"
                r1_src.font.size = Pt(8.5)
                r1_src.font.italic = True
                r1_src.font.color.rgb = RGBColor(70, 70, 150)
                
            r1_cat = p1.add_run(f"[{g['category']}] ")
            r1_cat.font.name = "Times New Roman"
            r1_cat.font.size = Pt(9.5)
            r1_cat.font.bold = True
            
            r1_comm = p1.add_run(g['comment'])
            r1_comm.font.name = "Times New Roman"
            r1_comm.font.size = Pt(9.5)
            
            if g.get('count', 1) > 1:
                p1_sub = cells[1].add_paragraph()
                p1_sub.paragraph_format.space_before = Pt(3)
                p1_sub.paragraph_format.space_after = Pt(0)
                r1_sub = p1_sub.add_run(f"(Total: {g['count']} occurrences detected)")
                r1_sub.font.name = "Times New Roman"
                r1_sub.font.size = Pt(8.5)
                r1_sub.font.italic = True
                r1_sub.font.color.rgb = RGBColor(100, 100, 100)
            
            # Column 3: Location in Manuscript
            p2 = cells[2].paragraphs[0]
            p2.alignment = WD_ALIGN_PARAGRAPH.LEFT
            r2 = p2.add_run(g['location'])
            r2.font.name = "Times New Roman"
            r2.font.size = Pt(9.0)
            
            # Column 4: Authors' Response (Empty paragraph for author notes)
            p3 = cells[3].paragraphs[0]
            p3.alignment = WD_ALIGN_PARAGRAPH.LEFT
            p3.paragraph_format.space_after = Pt(18)
            
    # Apply standard table borders
    tblPr = table._tbl.tblPr
    borders = parse_xml(f'''
        <w:tblBorders {nsdecls("w")}>
            <w:top w:val="single" w:sz="6" w:space="0" w:color="CCCCCC"/>
            <w:bottom w:val="single" w:sz="6" w:space="0" w:color="CCCCCC"/>
            <w:left w:val="single" w:sz="6" w:space="0" w:color="CCCCCC"/>
            <w:right w:val="single" w:sz="6" w:space="0" w:color="CCCCCC"/>
            <w:insideH w:val="single" w:sz="4" w:space="0" w:color="E0E0E0"/>
            <w:insideV w:val="single" w:sz="4" w:space="0" w:color="E0E0E0"/>
        </w:tblBorders>
    ''')
    tblPr.append(borders)

    # Append Table 2: Reference Integrity & Citation Forensics (if findings exist)
    if forensics_data and forensics_data.get("findings"):
        doc.add_page_break()
        f_p = doc.add_paragraph()
        f_p.paragraph_format.space_before = Pt(8)
        f_p.paragraph_format.space_after = Pt(2)
        run_f_title = f_p.add_run("Reference Integrity & Citation Forensics")
        run_f_title.font.name = "Times New Roman"
        run_f_title.font.size = Pt(13)
        run_f_title.font.bold = True
        run_f_title.font.color.rgb = RGBColor(180, 40, 40)

        sum_p = doc.add_paragraph()
        sum_p.paragraph_format.space_after = Pt(10)
        f_summary = forensics_data.get("summary", {})
        sum_text = (
            f"Total References: {f_summary.get('total_references', 0)} • "
            f"Self-Citations: {f_summary.get('self_citation_count', 0)} ({f_summary.get('self_citation_percentage', 0)}%) • "
            f"Suspicious/Incomplete Entries: {f_summary.get('suspicious_count', 0)} • "
            f"Duplicates: {f_summary.get('duplicate_count', 0)}"
        )
        r_sum = sum_p.add_run(sum_text)
        r_sum.font.name = "Times New Roman"
        r_sum.font.size = Pt(9.5)
        r_sum.font.italic = True

        f_table = doc.add_table(rows=1, cols=5)
        f_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        f_table.autofit = False

        f_hdr_cells = f_table.rows[0].cells
        f_hdr_titles = ["No", "Ref", "Check Type", "Evidence / Issue", "Directive Recommendation"]
        f_col_widths = [Inches(0.4), Inches(0.7), Inches(1.8), Inches(2.2), Inches(1.7)]

        for i, title in enumerate(f_hdr_titles):
            cell = f_hdr_cells[i]
            cell.width = f_col_widths[i]
            set_cell_background(cell, "FBEAE5")
            set_cell_margins(cell, top=120, bottom=120, left=100, right=100)
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER if i in [0, 1] else WD_ALIGN_PARAGRAPH.LEFT
            run = p.add_run(title)
            run.font.name = "Times New Roman"
            run.font.size = Pt(9.5)
            run.font.bold = True

        for f_idx, f_item in enumerate(forensics_data["findings"], start=1):
            f_row = f_table.add_row().cells
            for i in range(5):
                f_row[i].width = f_col_widths[i]
                set_cell_margins(f_row[i], top=100, bottom=100, left=100, right=100)

            f_row[0].paragraphs[0].add_run(str(f_item.get("no", f_idx))).font.size = Pt(9)
            f_row[1].paragraphs[0].add_run(str(f_item.get("ref_no", "-"))).font.size = Pt(9)

            p_type = f_row[2].paragraphs[0].add_run(f"[{f_item.get('severity', 'Warning')}]\n{f_item.get('type', '-')}")
            p_type.font.size = Pt(9)
            p_type.font.bold = True
            if f_item.get('severity') == 'Fatal':
                p_type.font.color.rgb = RGBColor(180, 30, 30)

            f_row[3].paragraphs[0].add_run(f_item.get("evidence", "-")).font.size = Pt(9)
            f_row[4].paragraphs[0].add_run(f_item.get("recommendation", "-")).font.size = Pt(9)

        f_tblPr = f_table._tbl.tblPr
        f_borders = parse_xml(f'''
            <w:tblBorders {nsdecls("w")}>
                <w:top w:val="single" w:sz="6" w:space="0" w:color="DDAAAA"/>
                <w:bottom w:val="single" w:sz="6" w:space="0" w:color="DDAAAA"/>
                <w:left w:val="single" w:sz="6" w:space="0" w:color="DDAAAA"/>
                <w:right w:val="single" w:sz="6" w:space="0" w:color="DDAAAA"/>
                <w:insideH w:val="single" w:sz="4" w:space="0" w:color="EEDDDD"/>
                <w:insideV w:val="single" w:sz="4" w:space="0" w:color="EEDDDD"/>
            </w:tblBorders>
        ''')
        f_tblPr.append(f_borders)
    
    doc.save(output_path)
    return output_path

def generate_excel_report(
    violations: List[Violation],
    metadata: PaperMetadata,
    output_path: str,
    conference_name: str = "ICoDMI 2026 (SSMI IPB)"
) -> str:
    """Generates an Excel workbook with both Consolidated and Itemized sheets."""
    wb = openpyxl.Workbook()
    
    # Sheet 1: Consolidated Review (Summary)
    ws_grouped = wb.active
    ws_grouped.title = "Review Summary"
    ws_grouped.views.sheetView[0].showGridLines = True
    
    # Headers
    headers_g = ["No", "Category", "Format Comments", "Location in Manuscript", "Authors' Response"]
    ws_grouped.append([f"{conference_name} - IEEE Manuscript Review Sheet"])
    ws_grouped.append([f"File: {os.path.basename(metadata.filename) if metadata.filename else 'manuscript.pdf'} | Pages: {metadata.total_pages} ({metadata.paper_size_name})"])
    ws_grouped.append([])
    ws_grouped.append(headers_g)
    
    grouped_items = group_violations(violations)
    for g in grouped_items:
        ws_grouped.append([
            g['no'],
            g['category'],
            g['comment'],
            g['location'],
            ""  # Empty for author response
        ])
        
    # Sheet 2: Raw Itemized Details
    ws_raw = wb.create_sheet(title="Raw Details")
    ws_raw.views.sheetView[0].showGridLines = True
    ws_raw.append(["No", "Severity", "Category", "Committee Comments", "Location in Manuscript"])
    for v in violations:
        ws_raw.append([v.no, v.severity, v.category, v.comment, v.location])
        
    wb.save(output_path)
    return output_path
