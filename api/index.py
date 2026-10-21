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
from core.report_generator import generate_word_report

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
    min_pages: int = Form(4),
    max_pages: int = Form(6),
    target_size: str = Form("A4"),
    conf_name: str = Form("ICoDMI 2026 (SSMI IPB)")
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
        
    try:
        content = await file.read()
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")
            
        # Open PDF in memory
        doc = pymupdf.open(stream=content, filetype="pdf")
        
        # Cast parameters
        min_p = int(min_pages)
        max_p = int(max_pages)
        
        # Check compliance
        checker = IEEEComplianceChecker(
            min_pages=min_p,
            max_pages=max_p,
            target_size=target_size
        )
        violations, metadata = checker.check_pdf(doc)
        metadata.filename = file.filename
        
        # Annotate PDF (Auto-stabilo)
        # We write to a temporary buffer
        temp_annotated = io.BytesIO()
        temp_annot_path = os.path.join(os.environ.get("TEMP", "/tmp"), f"annot_{os.urandom(8).hex()}.pdf")
        annotate_pdf(doc, violations, temp_annot_path)
        with open(temp_annot_path, "rb") as f:
            annotated_pdf_bytes = f.read()
        try:
            os.remove(temp_annot_path)
        except Exception:
            pass
            
        annotated_pdf_base64 = base64.b64encode(annotated_pdf_bytes).decode("utf-8")
        
        # Generate Word (.docx) report
        temp_word_path = os.path.join(os.environ.get("TEMP", "/tmp"), f"report_{os.urandom(8).hex()}.docx")
        generate_word_report(violations, metadata, temp_word_path, conference_name=conf_name)
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
            "metadata": {
                "total_pages": metadata.total_pages,
                "paper_size_name": metadata.paper_size_name,
                "is_a4": metadata.is_a4,
                "is_page_count_valid": metadata.is_page_count_valid,
                "has_copyright_notice": metadata.has_copyright_notice,
                "fonts_count": len(metadata.fonts)
            },
            "summary": {
                "total_violations": len(violations),
                "fatal_count": sum(1 for v in violations if v.severity == "Fatal"),
                "warning_count": sum(1 for v in violations if v.severity == "Warning")
            },
            "violations": violations_data,
            "annotated_pdf_base64": annotated_pdf_base64,
            "word_docx_base64": word_docx_base64
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")
