import re
from typing import List, Dict, Any

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
    """Merges two location strings without duplicate parts."""
    parts = []
    seen = set()
    for s in [loc1, loc2]:
        for sub in re.split(r'[;\n]', s or ""):
            clean = sub.strip()
            if clean and clean.lower() not in seen and clean.lower() != "entire manuscript":
                seen.add(clean.lower())
                parts.append(clean)
    if not parts:
        return "Entire manuscript"
    return "; ".join(parts)

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
