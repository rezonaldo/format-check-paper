import re
import os
from typing import Tuple, Dict, Any, List
import pymupdf

MAX_FILE_SIZE_MB = 25
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# Negative indicators: phrases strongly indicating non-academic paper documents
NEGATIVE_MANUSCRIPT_KEYWORDS = [
    r'\blatihan\s+soal\b',
    r'\bsoal\s+ujian\b',
    r'\bujian\s+(akhir|tengah)\s+semester\b',
    r'\blembar\s+(soal|jawaban)\b',
    r'\btugas\s+praktikum\b',
    r'\bkartu\s+tanda\s+mahasiswa\b',
    r'\btranskrip\s+nilai\b',
    r'\bsurat\s+(tugas|pengantar|keputusan|permohonan|peminjaman)\b',
    r'\bcurriculum\s+vitae\b',
    r'\bdaftar\s+(hadir|pemilih)\b',
    r'\bformulir\s+pendaftaran\b',
    r'\bpetunjuk\s+praktikum\b',
    r'\bexpense\s+tracker\b',
    r'\bkwitansi\b',
    r'\binvoice\b'
]

class DocumentSecurityError(Exception):
    pass

class NotAManuscriptError(Exception):
    pass

def validate_pdf_safety(file_bytes: bytes, filename: str) -> Tuple[bool, str]:
    """
    Validates file safety:
    1. Size limit
    2. Magic bytes (%PDF-)
    3. Basic format sanity
    """
    # 1. Check file size
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        return False, f"Ukuran berkas melebihi batas maksimal ({MAX_FILE_SIZE_MB} MB). Harap perkecil ukuran berkas Anda."
    
    if len(file_bytes) < 100:
        return False, "Berkas rusak atau terlalu kecil untuk menjadi dokumen PDF yang valid."

    # 2. Check Magic Bytes for PDF (%PDF-)
    if not file_bytes.startswith(b"%PDF-"):
        return False, "Format berkas tidak valid. Berkas bukan dokumen PDF asli (header file tidak valid)."

    return True, ""


def validate_manuscript_eligibility(doc: pymupdf.Document, filename: str = "") -> Tuple[bool, str, Dict[str, Any]]:
    """
    Gatekeeper that verifies if the document is genuinely an academic manuscript / IEEE paper.
    Prevents scanning random PDFs (exam sheets, slides, forms, scanned images, receipts).
    """
    # 1. Check Encryption / Password Protection
    if doc.is_encrypted or doc.needs_pass:
        return False, "Berkas PDF dilindungi kata sandi (password-protected). Harap unggah naskah yang tidak terkunci.", {}

    total_pages = len(doc)
    
    # 2. Check Extreme Page Limits
    # IEEE conference papers are practically between 3 and 12 pages maximum.
    if total_pages > 15:
        return False, (
            f"Dokumen memiliki {total_pages} halaman. Naskah konferensi IEEE standar memiliki 4-6 halaman "
            f"(maksimal 10 halaman). Berkas ini kemungkinan merupakan buku, modul kuliah, atau kumpulan soal."
        ), {"total_pages": total_pages}

    # 3. Check Text Layer Extractability (Blank / Pure Scanned Image Detection)
    total_text = ""
    for page in doc:
        total_text += page.get_text("text") + " "
        
    cleaned_total_text = total_text.strip()
    if len(cleaned_total_text) < 150:
        return False, (
            "Dokumen tidak memiliki lapisan teks yang dapat dibaca (kemungkinan berupa pindaian gambar/scan murni "
            "atau dokumen kosong). Sistem memerlukan naskah asli dalam format teks (bukan hasil scan kamera) "
            "agar dapat memeriksa kepatuhan format IEEE."
        ), {"text_length": len(cleaned_total_text)}

    # 4. Check First Two Pages for Academic Anchors
    first_two_pages_text = ""
    for i in range(min(2, total_pages)):
        first_two_pages_text += doc[i].get_text("text") + "\n"
        
    lower_first_text = first_two_pages_text.lower()
    lower_full_text = total_text.lower()

    # Check for prominent negative indicators (soal latihan, ujian, tugas kuliah, dll)
    combined_name_text = (filename + " " + lower_first_text[:1000]).lower()
    for neg_pattern in NEGATIVE_MANUSCRIPT_KEYWORDS:
        if re.search(neg_pattern, combined_name_text):
            match = re.search(neg_pattern, combined_name_text).group(0)
            return False, (
                f"Dokumen terdeteksi sebagai non-naskah ilmiah (ditemukan kata penanda: \"{match}\"). "
                "Sistem ini khusus digunakan untuk memeriksa naskah final paper ilmiah IEEE (ICoDMI)."
            ), {"negative_match": match}

    # Academic Anchor Detection:
    # 1. Abstract
    has_abstract = bool(re.search(r'\b(abstract|abstrak)\b', lower_first_text))
    
    # 2. Keywords / Index Terms
    has_keywords = bool(re.search(r'\b(keywords|index\s+terms|kata\s+kunci)\b', lower_first_text))
    
    # 3. Introduction
    has_introduction = bool(re.search(r'(\b\d+\.|\b[ivxlcdm]+\.)?\s*(introduction|pendahuluan)\b', lower_first_text))
    
    # 4. References / Bibliography
    has_references = bool(re.search(r'\b(references|bibliography|daftar\s+pustaka)\b', lower_full_text))

    # Calculate Confidence Score (0 to 4)
    anchors_found = []
    if has_abstract: anchors_found.append("Abstract")
    if has_keywords: anchors_found.append("Keywords")
    if has_introduction: anchors_found.append("Introduction")
    if has_references: anchors_found.append("References")

    score = len(anchors_found)

    # An academic paper MUST have at least 2 key structural anchors:
    # (e.g. Abstract + Introduction, or Abstract + References, or Keywords + References)
    if score < 2:
        missing = [a for a in ["Abstract", "Introduction", "Keywords", "References"] if a not in anchors_found]
        return False, (
            "Dokumen yang diunggah tidak terdeteksi sebagai naskah paper ilmiah/konferensi IEEE. "
            f"Sistem tidak menemukan struktur naskah ilmiah penting seperti: {', '.join(missing)}. "
            "Pastikan berkas yang diunggah adalah naskah artikel ilmiah yang memuat Judul, Penulis, Abstrak, dan Referensi."
        ), {"anchors_found": anchors_found, "score": score}

    return True, "", {
        "anchors_found": anchors_found,
        "score": score,
        "total_pages": total_pages
    }
