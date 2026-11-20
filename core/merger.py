import re
from typing import List, Dict, Any, Optional
import pymupdf

def resolve_lecturer_locations(
    lecturer_comments: List[Dict[str, Any]], 
    doc: pymupdf.Document
) -> List[Dict[str, Any]]:
    """
    Scans the manuscript PDF to replace generic 'Entire manuscript' or blank locations 
    with concrete pages, columns, and section markers (e.g. 'Page 2 (Right Col, Eq. 2)').
    """
    total_pages = len(doc)
    
    # 1. Index document elements page by page
    eq_locations = {}          # eq_num (int) -> dict
    indented_where_eqs = []    # equations followed by indented 'where'
    unpunctuated_eqs = []      # equations followed by 'where' without trailing comma
    ref_page = total_pages     # fallback page for references
    
    for p_idx, page in enumerate(doc, start=1):
        blocks = page.get_text("dict")["blocks"]
        width = page.rect.width
        height = page.rect.height
        
        lines = []
        for b in blocks:
            if "lines" not in b: 
                continue
            for l in b["lines"]:
                text = "".join(s["text"] for s in l["spans"]).strip()
                bbox = l["bbox"]
                first_span = l["spans"][0] if l["spans"] else None
                x0 = first_span["bbox"][0] if first_span else bbox[0]
                col = "Left Col" if bbox[0] < width / 2 else "Right Col"
                col_margin = 45.0 if bbox[0] < width / 2 else 306.0
                y_desc = "Top" if bbox[1] < height / 3 else ("Middle" if bbox[1] < 2 * height / 3 else "Bottom")
                lines.append({
                    "text": text,
                    "bbox": bbox,
                    "x0": x0,
                    "col": col,
                    "col_margin": col_margin,
                    "y_desc": y_desc,
                    "y0": bbox[1]
                })
                if re.search(r'^\s*(?:[I|V|X]+\.|\b)\s*REFERENCES\b', text, re.IGNORECASE):
                    ref_page = p_idx

        # Sort lines by column (Left first, then Right) then y-coordinate
        lines.sort(key=lambda item: (0 if item["col"] == "Left Col" else 1, item["y0"]))
        
        # Scan for display equation markers e.g. (1), (2), (4)
        for idx, l in enumerate(lines):
            m_eq = re.search(r'\(([1-9]\d?)\)\s*$', l["text"])
            if m_eq:
                eq_num = int(m_eq.group(1))
                eq_info = {
                    "eq_num": eq_num,
                    "page": p_idx,
                    "col": l["col"],
                    "y_desc": l["y_desc"],
                    "bbox": l["bbox"]
                }
                eq_locations[eq_num] = eq_info
                
                # Check following lines within same column for continuation ('where', 'here', 'with')
                for next_l in lines[idx+1 : idx+8]:
                    if next_l["col"] != l["col"]:
                        break
                    if next_l["y0"] - l["y0"] > 55.0:
                        break
                    n_text = next_l["text"].strip()
                    m_where = re.match(r'^(?:[\'\"\s]*)(where|here|with)\b', n_text, re.IGNORECASE)
                    if m_where:
                        # Check if 'where' is indented (tab before where)
                        if next_l["x0"] > next_l["col_margin"] + 8.0:
                            indented_where_eqs.append(eq_info)
                        
                        # Check comma punctuation on equation line or preceding formula span
                        has_comma = False
                        if idx > 0:
                            prev_text = lines[idx-1]["text"].strip()
                            if prev_text.endswith(",") or prev_text.endswith(", "):
                                has_comma = True
                        if l["text"][:m_eq.start()].strip().endswith(","):
                            has_comma = True
                            
                        if not has_comma:
                            unpunctuated_eqs.append(eq_info)
                        break

    # 2. Resolve locations for lecturer comments
    resolved_comments = []
    unpunctuated_cursor = 0
    indented_cursor = 0

    for item in lecturer_comments:
        it = dict(item)
        loc = it.get("location", "").strip()
        
        if not loc or loc.lower() == "entire manuscript":
            comm = (it.get("original_comment", "") + " " + it.get("comment", "")).strip()
            lower = comm.lower()
            
            # Rule 1: Specific Equation Number in text e.g. (2) or Eq. 4
            m_num = re.search(r'\b(?:eq(?:uation)?\.?\s*|\()([1-9]\d?)\)?\b', comm, re.IGNORECASE)
            if m_num and int(m_num.group(1)) in eq_locations:
                eq = eq_locations[int(m_num.group(1))]
                it["location"] = f"Page {eq['page']} ({eq['col']}, Eq. {eq['eq_num']})"
                resolved_comments.append(it)
                continue
                
            # Rule 2: Tab before 'where' / Equation continuation indent
            if "where" in lower and ("tab" in lower or "indent" in lower or "flush" in lower):
                if indented_where_eqs:
                    pick_idx = min(indented_cursor, len(indented_where_eqs) - 1)
                    eq = indented_where_eqs[pick_idx]
                    indented_cursor += 1
                    it["location"] = f"Page {eq['page']} ({eq['col']}, Eq. {eq['eq_num']})"
                elif eq_locations:
                    eq = list(eq_locations.values())[-1]
                    it["location"] = f"Page {eq['page']} ({eq['col']}, Eq. {eq['eq_num']})"
                else:
                    it["location"] = "Body Text (Equation Continuation)"
                resolved_comments.append(it)
                continue
                
            # Rule 3: Comma after equation / Equation punctuation
            if "equation" in lower and ("comma" in lower or "punctuate" in lower or "period" in lower):
                if unpunctuated_eqs:
                    pick_idx = min(unpunctuated_cursor, len(unpunctuated_eqs) - 1)
                    eq = unpunctuated_eqs[pick_idx]
                    unpunctuated_cursor += 1
                    it["location"] = f"Page {eq['page']} ({eq['col']}, Eq. {eq['eq_num']})"
                elif eq_locations:
                    eq = list(eq_locations.values())[0]
                    it["location"] = f"Page {eq['page']} ({eq['col']}, Eq. {eq['eq_num']})"
                else:
                    it["location"] = "Body Text (Equations)"
                resolved_comments.append(it)
                continue
                
            # Rule 4: Figure references (e.g. Fig. 4, Figure 2)
            m_fig = re.search(r'\b(?:fig(?:ure)?\.?\s*(\d+))\b', comm, re.IGNORECASE)
            if m_fig:
                f_num = m_fig.group(1)
                found_fig = False
                for p_idx, page in enumerate(doc, start=1):
                    hits = page.search_for(f"Fig. {f_num}") or page.search_for(f"Figure {f_num}")
                    if hits:
                        col = "Left Col" if hits[0].x0 < page.rect.width / 2 else "Right Col"
                        it["location"] = f"Page {p_idx} ({col}, Fig. {f_num})"
                        found_fig = True
                        break
                if found_fig:
                    resolved_comments.append(it)
                    continue
                    
            # Rule 5: Table references (e.g. Table II, TABLE I)
            m_tab = re.search(r'\b(?:table\s+([IVXLCDM\d]+))\b', comm, re.IGNORECASE)
            if m_tab:
                t_str = m_tab.group(1)
                found_tab = False
                for p_idx, page in enumerate(doc, start=1):
                    hits = page.search_for(f"Table {t_str}") or page.search_for(f"TABLE {t_str}")
                    if hits:
                        col = "Left Col" if hits[0].x0 < page.rect.width / 2 else "Right Col"
                        it["location"] = f"Page {p_idx} ({col}, Table {t_str})"
                        found_tab = True
                        break
                if found_tab:
                    resolved_comments.append(it)
                    continue
                    
            # Rule 6: Title, Authors, Affiliation, Metadata
            if any(k in lower for k in ["title", "subtitle", "colon in title", "author", "affiliation", "institution", "ordinal"]):
                it["location"] = "Page 1 (Title / Author Block)"
                resolved_comments.append(it)
                continue
                
            # Rule 7: Copyright Notice
            if "copyright" in lower:
                it["location"] = "Page 1 (Bottom Left Column)"
                resolved_comments.append(it)
                continue
                
            # Rule 8: References / BibTeX / DOI
            if any(k in lower for k in ["reference", "bibtex", "acronym", "doi", "duplicate reference"]):
                it["location"] = f"Page {ref_page} (References)"
                resolved_comments.append(it)
                continue
                
            # Rule 9: Column balance / blank space
            if any(k in lower for k in ["blank space", "column balance", "balance columns"]):
                it["location"] = f"Page {total_pages} (Last Page Columns)"
                resolved_comments.append(it)
                continue

            # Rule 10: Page count / Page setup
            if any(k in lower for k in ["page count", "eight pages", "extra page", "a4", "us letter"]):
                it["location"] = f"Overall Document ({total_pages} pages)"
                resolved_comments.append(it)
                continue
                
            it["location"] = loc or "Entire manuscript"
            resolved_comments.append(it)
        else:
            resolved_comments.append(it)
            
    return resolved_comments

def get_topic_key(category: str, comment: str) -> str:
    """Computes a normalized topic key to match equivalent student and lecturer comments."""
    text = (category + " " + comment).lower()
    
    if "letter" in text or "a4" in text or "paper size" in text:
        return "page_setup"
    if "eight pages" in text or "page count" in text or "exceed" in text and "page" in text:
        return "page_count"
    if "copyright" in text:
        return "copyright"
    if "red font" in text or "revision mark" in text or "non-black font" in text or "colour" in text or "color" in text:
        return "revision_markup"
    if "metadata" in text or "document properties" in text:
        return "pdf_metadata"
    if "figure" in text and "fig" in text:
        return "figure_citation"
    if "table" in text and ("roman" in text or "arabic" in text):
        return "table_roman_numbering"
    if "table" in text and "all caps" in text:
        return "table_all_caps"
    if "split" in text and "table" in text:
        return "table_split"
    if "ordinal" in text or "1st" in text:
        return "ordinal_labels"
    if "institution" in text or "ipb university" in text or "bogor agricultural" in text:
        return "author_institution"
    if "subtitle" in text or "colon" in text and "title" in text:
        return "paper_subtitle"
    if "conclusion" in text and ("number" in text or "roman" in text or "orphan" in text):
        return "conclusion_heading"
    if "blank space" in text or "balance" in text and "column" in text:
        return "column_balance"
    if "acronym" in text or "bibtex" in text:
        return "bibtex_acronyms"
    if "duplicate" in text and "reference" in text:
        return "duplicate_reference"
    if "font size" in text or "12 pt" in text or "9 pt" in text or "8 pt" in text:
        return "font_size"
    if "reference" in text and ("incomplete" in text or "doi" in text or "bibliographic" in text):
        return "incomplete_references"
    if "tab" in text and "where" in text:
        return "equation_tab_indent"
    if "comma" in text and "equation" in text or "period" in text and "equation" in text or "punctuate" in text and "equation" in text:
        return "equation_comma_punctuation"
    if "punctuation" in text and "citation" in text or "bracket" in text:
        return "citation_punctuation"
    if "equation" in text and ("(1)" in text or "eq." in text or "formula" in text):
        return "equation_citation"
        
    return f"gen_{category.lower().replace(' ', '_')}_{re.sub(r'[^a-z0-9]', '', comment[:15].lower())}"

def merge_locations(loc1: str, loc2: str) -> str:
    """Merges two location strings without duplicate or redundant parts."""
    raw_parts = []
    for s in [loc1, loc2]:
        for sub in re.split(r'[;\n]', s or ""):
            clean = sub.strip()
            if clean and clean.lower() != "entire manuscript":
                raw_parts.append(clean)
                
    unique_parts = []
    for p in raw_parts:
        covered = False
        m_curr_eq = re.search(r'Page\s+(\d+).*?(?:Col|Column).*?Eq\.?\s*\(?(\d+)\)?', p, re.IGNORECASE)
        m_curr_gen = re.match(r'^Page\s+(\d+)\s*\((Left|Right)\s+Col(?:umn)?\)$', p, re.IGNORECASE)
        
        for idx, u in enumerate(unique_parts):
            m_u_eq = re.search(r'Page\s+(\d+).*?(?:Col|Column).*?Eq\.?\s*\(?(\d+)\)?', u, re.IGNORECASE)
            m_u_gen = re.match(r'^Page\s+(\d+)\s*\((Left|Right)\s+Col(?:umn)?\)$', u, re.IGNORECASE)
            
            # Both point to same Page and Eq: keep more descriptive
            if m_curr_eq and m_u_eq:
                if m_curr_eq.group(1) == m_u_eq.group(1) and m_curr_eq.group(2) == m_u_eq.group(2):
                    if len(p) > len(u):
                        unique_parts[idx] = p
                    covered = True
                    break
            # One is generic Page X (Col Y) and the other is specific on the same Page and Col
            elif m_curr_gen and m_u_eq:
                if m_curr_gen.group(1) == m_u_eq.group(1):
                    covered = True
                    break
            elif m_u_gen and m_curr_eq:
                if m_u_gen.group(1) == m_curr_eq.group(1):
                    unique_parts[idx] = p
                    covered = True
                    break
            elif p.lower() in u.lower():
                covered = True
                break
            elif u.lower() in p.lower():
                unique_parts[idx] = p
                covered = True
                break
                
        if not covered:
            unique_parts.append(p)
            
    if not unique_parts:
        return "Entire manuscript"
    return "; ".join(unique_parts)

def merge_and_deduplicate(
    student_grouped: List[Dict[str, Any]], 
    lecturer_comments: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Merges student (automated compliance engine) grouped violations with lecturer committee comments.
    If both flag the same issue, deduplicates by selecting the active instructive directive,
    merging their location points, and assigning source 'Komite & Sistem'.
    Preserves all unique lecturer and student comments.
    """
    if not lecturer_comments:
        res = []
        for idx, it in enumerate(student_grouped, start=1):
            res.append({
                "no": idx,
                "category": it["category"],
                "comment": it["comment"],
                "location": it["location"],
                "severity": it.get("severity", "Warning"),
                "source": "Sistem",
                "source_tag": "Sistem",
                "count": it.get("count", 1),
                "items": it.get("items", [])
            })
        return res

    final_items = []
    matched_lecturer_indices = set()

    # Step 1: For each student item, check if there is an overlapping lecturer comment
    for s_item in student_grouped:
        s_key = get_topic_key(s_item["category"], s_item["comment"])
        match_idx = None
        for l_idx, l_item in enumerate(lecturer_comments):
            if l_idx in matched_lecturer_indices:
                continue
            l_key = get_topic_key(l_item["category"], l_item["comment"])
            if s_key == l_key:
                match_idx = l_idx
                break
        
        if match_idx is not None:
            matched_lecturer_indices.add(match_idx)
            l_item = lecturer_comments[match_idx]
            merged_loc = merge_locations(l_item.get("location", ""), s_item.get("location", ""))
            
            # Select most instructive directive
            chosen_comment = s_item["comment"] if len(s_item["comment"]) > len(l_item["comment"]) and "IEEE" in s_item["comment"] else l_item["comment"]
            
            final_items.append({
                "category": l_item.get("category") or s_item["category"],
                "comment": chosen_comment,
                "location": merged_loc,
                "severity": "Fatal" if (s_item.get("severity") == "Fatal" or l_item.get("severity") == "Fatal") else "Warning",
                "source": "both",
                "source_tag": "Komite & Sistem",
                "count": s_item.get("count", 1) + 1,
                "items": s_item.get("items", [])
            })
        else:
            final_items.append({
                "category": s_item["category"],
                "comment": s_item["comment"],
                "location": s_item["location"],
                "severity": s_item.get("severity", "Warning"),
                "source": "system",
                "source_tag": "Sistem",
                "count": s_item.get("count", 1),
                "items": s_item.get("items", [])
            })

    # Step 2: Add all unmatched lecturer comments
    for l_idx, l_item in enumerate(lecturer_comments):
        if l_idx not in matched_lecturer_indices:
            final_items.append({
                "category": l_item.get("category", "General Format"),
                "comment": l_item["comment"],
                "location": l_item.get("location", "Entire manuscript"),
                "severity": l_item.get("severity", "Warning"),
                "source": "lecturer",
                "source_tag": "Komite",
                "count": 1,
                "items": []
            })

    # Step 3: Priority sort
    priority_order = [
        "Page Setup", "Page Count", "IEEE Copyright Notice", "Revision Markup (Red Font)",
        "PDF Metadata", "Paper Title (Subtitle)", "Author Affiliation", "Font Size",
        "Figure Citation", "Table Style", "Equation Formatting", "Equation Punctuation",
        "Page Layout & Column Balance", "Component Heading", "Citation Punctuation",
        "Equation Citation", "Reference Completeness", "Duplicate Reference", "Reference Formatting (Acronyms)"
    ]

    def sort_key(item):
        cat = item["category"]
        try:
            return (priority_order.index(cat), cat)
        except ValueError:
            return (99, cat)

    sorted_items = sorted(final_items, key=sort_key)

    result = []
    for idx, it in enumerate(sorted_items, start=1):
        it["no"] = idx
        result.append(it)

    return result
