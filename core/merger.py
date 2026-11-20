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
    if "punctuation" in text and "citation" in text or "bracket" in text:
        return "citation_punctuation"
    if "equation" in text and ("(1)" in text or "eq." in text):
        return "equation_citation"
        
    return f"gen_{category.lower().replace(' ', '_')}"

def merge_locations(loc1: str, loc2: str) -> str:
    """Merges two location strings without duplicate parts."""
    parts = []
    seen = set()
    for s in [loc1, loc2]:
        for sub in re.split(r'[;\n]', s):
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
    """
    if not lecturer_comments:
        # Return student items tagged as 'Sistem'
        res = []
        for idx, it in enumerate(student_grouped, start=1):
            res.append({
                "no": idx,
                "category": it["category"],
                "comment": it["comment"],
                "location": it["location"],
                "severity": it.get("severity", "Warning"),
                "source": "Sistem",
                "count": it.get("count", 1)
            })
        return res

    merged_dict: Dict[str, Dict[str, Any]] = {}
    
    # 1. Index lecturer comments
    for l_item in lecturer_comments:
        key = get_topic_key(l_item["category"], l_item["comment"])
        merged_dict[key] = {
            "category": l_item["category"],
            "comment": l_item["comment"],
            "location": l_item["location"],
            "severity": "Warning",
            "source": "Komite",
            "count": 1,
            "matched": False
        }

    # 2. Match with student automated checks
    for s_item in student_grouped:
        key = get_topic_key(s_item["category"], s_item["comment"])
        if key in merged_dict:
            # Overlap found! Merge and deduplicate
            existing = merged_dict[key]
            existing["matched"] = True
            existing["source"] = "Komite & Sistem"
            # Combine locations
            existing["location"] = merge_locations(existing["location"], s_item["location"])
            # If student comment has more specific snippet, combine or keep the most directive
            if len(s_item["comment"]) > len(existing["comment"]) and "IEEE" in s_item["comment"]:
                existing["comment"] = s_item["comment"]
            if s_item.get("severity") == "Fatal":
                existing["severity"] = "Fatal"
            existing["count"] = s_item.get("count", 1) + 1
        else:
            # Student-only item
            merged_dict[key] = {
                "category": s_item["category"],
                "comment": s_item["comment"],
                "location": s_item["location"],
                "severity": s_item.get("severity", "Warning"),
                "source": "Sistem",
                "count": s_item.get("count", 1),
                "matched": False
            }

    # 3. Build ordered final merged list
    result = []
    # Priority ordering by category for professional committee layout
    priority_order = [
        "Page Setup", "Page Count", "IEEE Copyright Notice", "Revision Markup (Red Font)",
        "PDF Metadata", "Paper Title (Subtitle)", "Author Affiliation", "Font Size",
        "Figure Citation", "Table Style", "Page Layout & Column Balance",
        "Component Heading", "Citation Punctuation", "Equation Citation",
        "Reference Completeness", "Duplicate Reference", "Reference Formatting (Acronyms)"
    ]

    def sort_key(item):
        cat = item["category"]
        try:
            return (priority_order.index(cat), item["category"])
        except ValueError:
            return (99, item["category"])

    sorted_items = sorted(merged_dict.values(), key=sort_key)
    
    for idx, it in enumerate(sorted_items, start=1):
        result.append({
            "no": idx,
            "category": it["category"],
            "comment": it["comment"],
            "location": it["location"],
            "severity": it["severity"],
            "source": it["source"],
            "count": it["count"]
        })

    return result
