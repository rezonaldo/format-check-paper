import re
from typing import List, Dict, Any, Tuple, Optional
import pymupdf
from difflib import SequenceMatcher

import re
from typing import List, Dict, Any, Tuple, Optional
import pymupdf
from difflib import SequenceMatcher

ACADEMIC_STOPWORDS = {
    # Title / Research / Scientific domain words
    "accuracy", "computational", "efficiency", "comparison", "svm", "lstm", "indobert",
    "indonesian", "railway", "review", "sentiment", "analysis", "study", "evaluation",
    "using", "based", "approach", "framework", "system", "model", "method", "deep",
    "learning", "machine", "neural", "network", "networks", "classification", "aspect",
    "paper", "title", "conference", "ieee", "international", "proceedings", "journal",
    "decision", "ranking", "sensitivity", "optimization", "perturbation", "pairwise",
    "spectral", "response", "polyethylene", "microplastics", "salinity", "variations",
    "excitation", "conditions", "syndrome", "facial", "phenotype", "membership",
    "function", "construction", "histogram", "interpolation", "fuzzy", "dashboard",
    "high", "performance", "computing", "characterization", "hybrid", "diabetes",
    "treatment", "planning", "synthetic", "data", "analytics", "payment", "handling",
    "imbalanced", "recommender", "systems", "attention", "heads", "resampling",
    "strategies", "credit", "card", "virtual", "reality", "walking", "tour", "cultural",
    "heritage", "lightweight", "ensemble", "differential", "search", "algorithm",
    "reliability", "integrating", "silico", "strain", "geostatistical", "peatland",
    "soil", "moisture", "feature", "selection", "impact", "arrival", "first", "lane",
    "airport", "security", "checkpoints", "slot", "median", "demand", "profiles",
    "investigation", "development", "application", "applications", "modeling", "survey",
    "implementation", "experimental", "theoretical", "empirical", "numerical",
    "gas", "chromatography", "mass", "spectrometry", "spectroscopy", "microscopy",
    "scanning", "electron", "fourier", "transform", "infrared", "raman", "kriging",
    "variogram", "semivariogram", "regression", "detection", "prediction", "estimator",
    
    # Affiliation / Structure / Location words
    "faculty", "department", "school", "college", "university", "universitas", "institut",
    "institute", "polytechnic", "center", "centre", "laboratory", "dept", "univ", "program",
    "study", "engineering", "technology", "science", "sciences", "computer", "informatics",
    "information", "creative", "electrical", "mechanical", "civil", "medical", "health",
    "economics", "business", "agriculture", "agricultural", "forestry", "pharmacy",
    "indonesia", "malaysia", "singapore", "bandung", "jakarta", "bogor", "tasikmalaya",
    "pontianak", "surabaya", "yogyakarta", "medan", "semarang", "email", "author", "authors",
    "line", "given", "name", "surname", "member", "student", "lecturer", "professor",
    "abstract", "keywords", "index", "terms", "introduction", "conclusion", "references",
    "table", "figure", "fig", "acknowledgment", "acknowledgements"
}

def extract_paper_authors(doc: pymupdf.Document) -> List[str]:
    """
    Extracts genuine author names and surnames from the manuscript with high precision.
    Uses AUTHORS CONTRIBUTIONS section if available, or analyzes the author grid on Page 1.
    Strictly filters out title words, scientific nouns, and institutional affiliations.
    """
    if len(doc) == 0:
        return []

    # Strategy 1: Check AUTHORS CONTRIBUTIONS section on last pages (gold standard)
    for p_idx in range(len(doc) - 1, -1, -1):
        txt = doc[p_idx].get_text("text")
        m_contrib = re.search(
            r'(?:AUTHORS?[\s’\']*CONTRIBUTIONS?)\s*\n+(.*?)(?=\n\s*(?:DATA\s+AVAILABILITY|ACKNOWLEDGMENT|REFERENCES|[A-Z\s]{4,}\b|\Z))', 
            txt, 
            re.DOTALL | re.IGNORECASE
        )
        if m_contrib:
            contrib_text = m_contrib.group(1)
            names = []
            for chunk in re.split(r'[:;]\s*', contrib_text):
                for part in re.split(r',\s*|\band\b', chunk):
                    cleaned = part.strip()
                    words = cleaned.split()
                    if 2 <= len(words) <= 4 and all(w[0].isupper() and w.isalpha() for w in words):
                        if not any(w.lower() in ACADEMIC_STOPWORDS for w in words):
                            names.append(" ".join(words))
            if names:
                return list(dict.fromkeys(names))

    # Strategy 2: Page 1 Author Block Analysis
    p1 = doc[0]
    p_dict = p1.get_text("dict")
    
    # Identify title font size: max font size on top half of page 1
    max_font_size = 0
    for b in p_dict.get("blocks", []):
        if b.get("bbox", [0, 0, 0, 0])[1] < 350:
            for l in b.get("lines", []):
                for s in l.get("spans", []):
                    if s.get("size", 0) > max_font_size:
                        max_font_size = s["size"]
                        
    author_candidates = []
    for b in p_dict.get("blocks", []):
        bbox = b.get("bbox", [0, 0, 0, 0])
        # Authors are in top half of page, below title and above abstract
        if 50 <= bbox[1] <= 380:
            for l in b.get("lines", []):
                line_spans = l.get("spans", [])
                line_text = "".join(s.get("text", "") for s in line_spans).strip()
                if not line_text:
                    continue
                if "abstract" in line_text.lower():
                    break
                    
                # Skip title lines
                line_font_size = max([s.get("size", 0) for s in line_spans], default=0)
                if line_font_size >= max_font_size - 1.0 and max_font_size > 14.0:
                    continue
                    
                # Skip lines containing email, affiliations, digits, or organization keywords
                if re.search(r'(@|\.ac\.id|\.edu|\.com|\.org|\d{3,}|dept\.|faculty|univers|institut|school|college|laboratory|city|country)', line_text, re.IGNORECASE):
                    continue
                    
                # Strip ordinal labels like '1st', '2nd'
                cleaned_line = re.sub(r'\b(1st|2nd|3rd|4th|5th|6th)\b', '', line_text).strip()
                words = cleaned_line.split()
                
                # An author name has 2 to 4 capitalized words, with NO academic stopwords
                if 2 <= len(words) <= 4:
                    if all(w[0].isupper() and (w.isalpha() or w.endswith('.')) for w in words):
                        if not any(w.lower() in ACADEMIC_STOPWORDS for w in words):
                            author_candidates.append(" ".join(words))

    return list(dict.fromkeys(author_candidates))

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
    
    # Extract author surnames (distinctive names only, no common stopwords)
    author_surnames = set()
    for a in paper_authors:
        parts = a.split()
        if parts:
            surname = parts[-1].lower()
            if len(surname) >= 3 and surname not in ACADEMIC_STOPWORDS:
                author_surnames.add(surname)
            if len(parts) > 1:
                first = parts[0].lower()
                if len(first) >= 4 and first not in ACADEMIC_STOPWORDS:
                    author_surnames.add(first)

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
    # In standard IEEE references, authors strictly precede the first title quotation mark.
    # We only inspect the authors segment to prevent false positives against title/journal words.
    self_cited_refs = []
    for num, content in parsed_refs:
        m_q = re.search(r'[“"\'\`]', content)
        if m_q:
            author_segment = content[:m_q.start()]
        else:
            parts = content.split(',')
            author_segment = parts[0] if len(parts) == 1 else ",".join(parts[:2])
            
        matched_authors = []
        for surname in author_surnames:
            if len(surname) >= 4 and re.search(r'\b' + re.escape(surname) + r'\b', author_segment, re.IGNORECASE):
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

        # 6. BibTeX Acronym lowercasing (e.g. 'cnn', 'lstm' in lowercase; 'IoT' is valid mixed case)
        m_title = re.search(r'["“\']([^"”\']+)["”\']', content)
        if m_title:
            t_str = m_title.group(1)
            words = re.findall(r'\b[a-zA-Z-]+\b', t_str)
            corrupted = []
            for w in words:
                # 'IoT' is standard casing. Only flag if all-lowercase like 'iot' or 'cnn' or 'bert'
                if w.lower() in known_acronyms:
                    if w == "IoT":
                        continue  # Valid standard IEEE acronym casing
                    if w.islower() or (not w.isupper() and w.lower() != "iot"):
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
