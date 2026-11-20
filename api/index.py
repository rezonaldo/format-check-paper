import os
import sys
import io
import base64
from pathlib import Path
from typing import Optional

# Ensure project root is in sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import pymupdf

from core.rules import IEEEComplianceChecker
from core.highlighter import annotate_pdf
from core.report_generator import generate_word_report, group_violations
from core.validator import validate_pdf_safety, validate_manuscript_eligibility
from core.lecturer_parser import parse_lecturer_file
from core.merger import merge_and_deduplicate
from core.reference_forensics import analyze_reference_forensics

app = FastAPI(title="IEEE Manuscript Compliance Checker API")

# Enable CORS for Vercel and local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "IEEE Manuscript Compliance Checker"}

@app.post("/api/check")
async def check_manuscript(
    file: UploadFile = File(...),
    lecturer_file: Optional[UploadFile] = File(None),
    min_pages: int = Form(4),
    max_pages: int = Form(6),
    hard_max_pages: int = Form(8),
    target_size: str = Form("A4"),
    conf_name: str = Form("ICoDMI 2026 (SSMI IPB)")
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF format files (.pdf) are supported.")
        
    try:
        content = await file.read()
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty (0 bytes).")
            
        # 1. Security & PDF Safety Validation
        ok_safety, msg_safety = validate_pdf_safety(content, file.filename)
        if not ok_safety:
            raise HTTPException(status_code=400, detail=msg_safety)
            
        # Open PDF in memory
        try:
            doc = pymupdf.open(stream=content, filetype="pdf")
        except Exception:
            raise HTTPException(status_code=400, detail="Failed to open PDF file. The file may be corrupted or invalid.")
            
        # 2. Gatekeeper: Academic Manuscript Eligibility Check
        ok_eligibility, msg_eligibility, info = validate_manuscript_eligibility(doc, file.filename)
        if not ok_eligibility:
            raise HTTPException(status_code=422, detail=msg_eligibility)
        
        # Cast parameters
        min_p = int(min_pages)
        max_p = int(max_pages)
        hard_max_p = int(hard_max_pages)
        
        # Check compliance
        checker = IEEEComplianceChecker(
            min_pages=min_p,
            max_pages=max_p,
            hard_max_pages=hard_max_p,
            target_size=target_size
        )
        violations, metadata = checker.check_pdf(doc)
        metadata.filename = file.filename

        # Grouped violations for automated student review
        grouped_data = group_violations(violations)
        
        # 3. Parse optional lecturer comments file (.docx or .pdf)
        lecturer_comments = []
        lecturer_filename = None
        if lecturer_file and lecturer_file.filename:
            try:
                l_bytes = await lecturer_file.read()
                if len(l_bytes) > 0:
                    lecturer_filename = lecturer_file.filename
                    lecturer_comments = parse_lecturer_file(l_bytes, lecturer_file.filename)
            except Exception as e:
                print(f"Warning: Failed to parse lecturer file: {e}")

        # 4. Merge and deduplicate (Komite + Mahasiswa/Sistem) into active directives
        merged_data = merge_and_deduplicate(grouped_data, lecturer_comments)

        # 5. Reference Forensics & Integrity Check (Self-citations, dummy, AI links, etc.)
        ref_info = getattr(checker, 'ref_info', None)
        forensics_data = analyze_reference_forensics(doc, ref_info)
        
        # Annotate PDF (Auto-stabilo)
        temp_annot_path = os.path.join(os.environ.get("TEMP", "/tmp"), f"annot_{os.urandom(8).hex()}.pdf")
        annotate_pdf(doc, violations, temp_annot_path)
        with open(temp_annot_path, "rb") as f:
            annotated_pdf_bytes = f.read()
        try:
            os.remove(temp_annot_path)
        except Exception:
            pass
            
        annotated_pdf_base64 = base64.b64encode(annotated_pdf_bytes).decode("utf-8")
        
        # Generate Word (.docx) report with merged items and forensics table
        temp_word_path = os.path.join(os.environ.get("TEMP", "/tmp"), f"report_{os.urandom(8).hex()}.docx")
        generate_word_report(
            violations, 
            metadata, 
            temp_word_path, 
            conference_name=conf_name,
            merged_items=merged_data,
            forensics_data=forensics_data
        )
        with open(temp_word_path, "rb") as f:
            word_docx_bytes = f.read()
        try:
            os.remove(temp_word_path)
        except Exception:
            pass
            
        word_docx_base64 = base64.b64encode(word_docx_bytes).decode("utf-8")
        
        # Prepare structured violations list matching user's table
        violations_data = []
        for v in violations:
            violations_data.append({
                "no": v.no,
                "category": v.category,
                "comment": v.comment,
                "location": v.location,
                "severity": v.severity
            })
            
        return JSONResponse(content={
            "success": True,
            "filename": file.filename,
            "lecturer_filename": lecturer_filename,
            "lecturer_merged": bool(lecturer_comments),
            "metadata": {
                "total_pages": metadata.total_pages,
                "paper_size_name": metadata.paper_size_name,
                "is_a4": metadata.is_a4,
                "is_page_count_valid": metadata.is_page_count_valid,
                "is_extra_pages": metadata.is_extra_pages,
                "has_copyright_notice": metadata.has_copyright_notice,
                "fonts_count": len(metadata.fonts)
            },
            "summary": {
                "total_violations": len(violations),
                "total_groups": len(grouped_data),
                "total_merged": len(merged_data),
                "lecturer_items_count": len(lecturer_comments),
                "fatal_count": sum(1 for v in violations if v.severity == "Fatal"),
                "warning_count": sum(1 for v in violations if v.severity == "Warning")
            },
            "violations": violations_data,
            "grouped_violations": grouped_data,
            "merged_violations": merged_data,
            "reference_forensics": forensics_data,
            "annotated_pdf_base64": annotated_pdf_base64,
            "word_docx_base64": word_docx_base64
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")
