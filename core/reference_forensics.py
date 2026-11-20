import re
from typing import List, Dict, Any, Tuple, Optional
import pymupdf
from difflib import SequenceMatcher

def extract_paper_authors(doc: pymupdf.Document) -> List[str]:
    """Extracts author names and surnames from the first page of the manuscript."""
    if len(doc) == 0:
        return []
    p1 = doc[0]
    p_dict = p1.get_text("dict")
    
    # Author block is typically between Title (y0 ~ 80-180) and Abstract (y0 ~ 220-350)
    author_text = ""
    for b in p_dict.get("blocks", []):
        bbox = b.get("bbox", [0, 0, 0, 0])
        if 80 <= bbox[1] <= 300:
            for l in b.get("lines", []):
                line_str = "".join(s.get("text", "") for s in l.get("spans", [])).strip()
                if "abstract" in line_str.lower():
                    break
                # Skip template line instructions like "line 1", "author name"
                if re.search(r'\b(line\s*\d+|dept\.|faculty|university|institute|email|@)\b', line_str, re.IGNORECASE):
                    continue
                author_text += " " + line_str

    # Extract potential author names (2-4 capitalized words)
    raw_names = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z]\.|\s+[A-Z][a-z]+){1,3})\b', author_text)
    authors = []
    seen = set()
    for name in raw_names:
        name_clean = name.strip()
        # Filter common words
        if name_clean.lower() in ["paper title", "conference name", "ieee", "table", "figure", "abstract", "index terms", "keywords"]:
            continue
        if len(name_clean) > 4 and name_clean.lower() not in seen:
            seen.add(name_clean.lower())
            authors.append(name_clean)
            
    return authors

def analyze_reference_forensics(doc: pymupdf.Document, ref_info: Optional[dict] = None) -> Dict[str, Any]:
    """
    Performs forensic inspection of the references/bibliography section:
    1. Excessive Self-Citation Detection (cross-referencing paper authors with bibliography)
    2. Suspicious / Dummy / Fictitious references (missing data, dummy markers [?], [X])
    3. AI / Chatbot tracking parameters (utm_source=chatgpt.com)
    4. BibTeX Acronym lowercasing ({CNN}, {LSTM})
    5. Inconsistent / Future publication dates
    6. Duplicate bibliography entries
    """
    results = {
        "summary": {
            "total_references": 0,
            "self_citation_count": 0,
            "self_citation_percentage": 0.0,
            "suspicious_count": 0,
            "duplicate_count": 0,
            "detected_authors": []
        },
        "self_citations": [],
        "findings": []
    }

    if len(doc) == 0:
        return results

    # 1. Extract paper authors
    paper_authors = extract_paper_authors(doc)
    results["summary"]["detected_authors"] = paper_authors
    
    # Extract author surnames
    author_surnames = set()
    for a in paper_authors:
        parts = a.split()
        if parts:
            author_surnames.add(parts[-1].lower())  # surname
            if len(parts) > 1 and len(parts[0]) > 2:
                author_surnames.add(parts[0].lower())

    # 2. Extract references text
    start_page = (ref_info["page"] - 1) if ref_info else 0
    if not ref_info:
        for p_idx in range(len(doc)):
            txt = doc[p_idx].get_text("text")
            if re.search(r'\b(REFERENCES|References|DAFTAR PUSTAKA)\b', txt):
                start_page = p_idx
                break

    ref_text = ""
    for p_idx in range(start_page, len(doc)):
        ref_text += doc[p_idx].get_text("text") + "\n"

    # Split into individual reference items [1], [2], ...
    ref_entries = re.split(r'(?=\[\d+\])', ref_text)
    parsed_refs = []
    
    for entry in ref_entries:
        entry_clean = entry.strip()
        m_num = re.match(r'^\[(\d+)\]\s*(.+)', entry_clean, re.DOTALL)
        if m_num:
            ref_num = int(m_num.group(1))
            ref_content = m_num.group(2).replace('\n', ' ').strip()
            parsed_refs.append((ref_num, ref_content))

    results["summary"]["total_references"] = len(parsed_refs)
    if not parsed_refs:
        return results

    # A. Check Self-Citations
    self_cited_refs = []
    for num, content in parsed_refs:
        matched_authors = []
        for surname in author_surnames:
            if len(surname) > 3 and re.search(r'\b' + re.escape(surname) + r'\b', content, re.IGNORECASE):
                matched_authors.append(surname.title())
        if matched_authors:
            self_cited_refs.append({
                "ref_num": num,
                "matched_authors": list(set(matched_authors)),
                "snippet": content[:120] + "..." if len(content) > 120 else content
            })

    results["self_citations"] = self_cited_refs
    results["summary"]["self_citation_count"] = len(self_cited_refs)
    if parsed_refs:
        pct = (len(self_cited_refs) / len(parsed_refs)) * 100
        results["summary"]["self_citation_percentage"] = round(pct, 1)

    finding_no = 1

    # Flag self-citation alert if >= 3 or > 20%
    if len(self_cited_refs) >= 3 or (len(parsed_refs) > 5 and pct >= 20.0):
        sev = "Fatal" if len(self_cited_refs) >= 8 or pct >= 35.0 else "Warning"
        all_matched = sorted(list(set([a for r in self_cited_refs for a in r["matched_authors"]])))
        ref_nums_str = ", ".join([f"[{r['ref_num']}]" for r in self_cited_refs])
        results["findings"].append({
            "no": finding_no,
            "ref_no": ref_nums_str,
            "type": "Excessive Self-Citation",
            "severity": sev,
            "evidence": f"Found {len(self_cited_refs)} self-citation(s) ({pct:.1f}% of total references) citing authors: {', '.join(all_matched)}.",
            "recommendation": "Review all self-citations to ensure they are scientifically necessary; IEEE reviewers strictly scrutinize citation stuffing and excessive self-references."
        })
        finding_no += 1

    # B. Forensics on individual references
    known_acronyms = ["cnn", "cnns", "resnet", "lstm", "svm", "ai", "bert", "pca", "vit", "dnn", "nlp", "iot", "rfid", "ann", "knn"]

    for num, content in parsed_refs:
        # 1. Dummy/placeholder references
        if re.search(r'(\[\?\]|\[X\]|\bTODO\b|Author\s+et\s+al\.|Title\s+of\s+Paper)', content, re.IGNORECASE):
            results["findings"].append({
                "no": finding_no,
                "ref_no": f"[{num}]",
                "type": "Dummy / Unresolved Citation",
                "severity": "Fatal",
                "evidence": f"Contains placeholder text: \"{content[:80]}\"",
                "recommendation": "Replace dummy placeholder citation with complete, genuine bibliographic data."
            })
            finding_no += 1
            results["summary"]["suspicious_count"] += 1

        # 2. AI / Chatbot tracking URL
        if re.search(r'(utm_source=chatgpt\.com|chatgpt\.com)', content, re.IGNORECASE):
            results["findings"].append({
                "no": finding_no,
                "ref_no": f"[{num}]",
                "type": "Chatbot / AI Tracking URL",
                "severity": "Fatal",
                "evidence": "Contains chatbot parameter: 'utm_source=chatgpt.com'",
                "recommendation": "Remove chatbot tracking parameters; cite original peer-reviewed academic sources directly."
            })
            finding_no += 1
            results["summary"]["suspicious_count"] += 1

        # 3. Missing critical publication data (No year or no venue)
        has_year = bool(re.search(r'\b(19\d\d|20[0-2]\d)\b', content))
        if not has_year:
            results["findings"].append({
                "no": finding_no,
                "ref_no": f"[{num}]",
                "type": "Incomplete Bibliographic Data (Missing Year)",
                "severity": "Warning",
                "evidence": f"No publication year found in reference: \"{content[:90]}\"",
                "recommendation": "Add publication year and complete bibliographic information according to IEEE format."
            })
            finding_no += 1
            results["summary"]["suspicious_count"] += 1

        # 4. Future publication year
        m_fut = re.search(r'\b(20[3-9]\d)\b', content)
        if m_fut:
            results["findings"].append({
                "no": finding_no,
                "ref_no": f"[{num}]",
                "type": "Inconsistent Future Publication Year",
                "severity": "Fatal",
                "evidence": f"Reference mentions future year '{m_fut.group(1)}' relative to current submission timeline.",
                "recommendation": "Verify and correct publication date; dates cannot be in the future."
            })
            finding_no += 1
            results["summary"]["suspicious_count"] += 1

        # 5. Raw markup tags
        if re.search(r'(<[/]?[a-zA-Z]{2,6}>)', content):
            tag_m = re.search(r'(<[/]?[a-zA-Z]{2,6}>)', content).group(1)
            results["findings"].append({
                "no": finding_no,
                "ref_no": f"[{num}]",
                "type": "Raw XML/HTML Markup Tag",
                "severity": "Warning",
                "evidence": f"Reference contains raw tag '{tag_m}'",
                "recommendation": f"Remove raw tag '{tag_m}' from reference entry; provide plain text only."
            })
            finding_no += 1

        # 6. BibTeX Acronym lowercasing
        m_title = re.search(r'["“\']([^"”\']+)["”\']', content)
        if m_title:
            t_str = m_title.group(1)
            words = re.findall(r'\b[a-zA-Z-]+\b', t_str)
            corrupted = []
            for w in words:
                if w.lower() in known_acronyms and not w.isupper():
                    corrupted.append(w)
            if corrupted:
                results["findings"].append({
                    "no": finding_no,
                    "ref_no": f"[{num}]",
                    "type": "BibTeX Acronym Lowercasing",
                    "severity": "Warning",
                    "evidence": f"Acronym(s) {corrupted} converted to lower/mixed case in title \"{t_str[:60]}\"",
                    "recommendation": f"Protect acronyms in BibTeX using curly braces (e.g. {{{corrupted[0].upper()}}}) to preserve capitalization."
                })
                finding_no += 1

    # C. Duplicate Reference Detection
    for i in range(len(parsed_refs)):
        for j in range(i + 1, len(parsed_refs)):
            n1, c1 = parsed_refs[i]
            n2, c2 = parsed_refs[j]
            # Compare titles if present
            m1 = re.search(r'["“\']([^"”\']{15,})["”\']', c1)
            m2 = re.search(r'["“\']([^"”\']{15,})["”\']', c2)
            if m1 and m2:
                sim = SequenceMatcher(None, m1.group(1).lower(), m2.group(1).lower()).ratio()
                if sim > 0.85:
                    results["findings"].append({
                        "no": finding_no,
                        "ref_no": f"[{n1}] & [{n2}]",
                        "type": "Duplicate Reference Entry",
                        "severity": "Fatal",
                        "evidence": f"References [{n1}] and [{n2}] cite the same work: \"{m1.group(1)[:60]}...\"",
                        "recommendation": f"Merge duplicate entries [{n1}] and [{n2}] into a single entry and update in-text citation numbers."
                    })
                    finding_no += 1
                    results["summary"]["duplicate_count"] += 1

    return results
