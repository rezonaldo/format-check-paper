import os
import tempfile
import streamlit as st
import pymupdf
import pandas as pd

from core.rules import IEEEComplianceChecker
from core.highlighter import annotate_pdf
from core.report_generator import generate_word_report, generate_excel_report
from core.validator import validate_pdf_safety, validate_manuscript_eligibility

st.set_page_config(
    page_title="ICoDMI - IEEE Manuscript Format Checker",
    page_icon="📑",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for polished publication committee look
st.markdown("""
<style>
    .main-title {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E3A8A;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        font-size: 1.05rem;
        color: #4B5563;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background-color: #F8FAFC;
        border-radius: 8px;
        padding: 1rem;
        border: 1px solid #E2E8F0;
        text-align: center;
    }
    .fatal-badge {
        background-color: #FEE2E2;
        color: #991B1B;
        font-weight: 600;
        padding: 2px 8px;
        border-radius: 4px;
    }
    .warning-badge {
        background-color: #FEF3C7;
        color: #92400E;
        font-weight: 600;
        padding: 2px 8px;
        border-radius: 4px;
    }
</style>
""", unsafe_allow_html=True)

# Sidebar Configuration
with st.sidebar:
    st.image("https://conference-ssmi.ipb.ac.id/assets/images/logo.png", width=180) if False else None
    st.header("⚙️ Pengaturan Konferensi")
    conf_name = st.text_input("Nama Konferensi", value="ICoDMI 2026 (SSMI IPB)")
    target_size = st.selectbox("Ukuran Kertas Wajib", ["A4", "Letter"], index=0)
    
    col_min, col_max = st.columns(2)
    with col_min:
        min_pages = st.number_input("Min Halaman", value=4, min_value=1, max_value=20)
    with col_max:
        max_pages = st.number_input("Max Halaman Reguler", value=6, min_value=1, max_value=20)
        
    hard_max_pages = st.number_input("Batas Maksimal Extra Pages", value=8, min_value=6, max_value=20, help="Maksimal total halaman termasuk extra pages (halaman 7 & 8 dikenakan biaya tambahan). Dokumen > 8 halaman ditolak.")

    st.markdown("---")
    with st.expander("ℹ️ Ketentuan Kertas & Halaman (FAQ)"):
        st.markdown("""
        **1. Apakah harus A4 atau boleh Letter?**
        - Untuk **ICoDMI (IEEE Region 10 / Indonesia)**, naskah **WAJIB A4 (210 × 297 mm)** sesuai template resmi. Template Letter tidak diperbolehkan karena margin prosiding akan bergeser.
        
        **2. Arti 'Up to 8 Pages with Extra Pages':**
        - **Total MAKSIMAL adalah 8 Halaman** (bukan tambah 8 halaman lagi).
        - **1–6 Hal:** Standar registrasi reguler.
        - **Hal 7 & 8:** Extra pages (dikenakan biaya tambahan per halaman).
        - **> 8 Hal:** Wajib dipangkas / ditolak.
        """)
    st.markdown("---")
    st.markdown("### 📌 Fitur Utama:")
    st.markdown("""
    - **Pemeriksaan 100% Ketentuan IEEE**
    - **Auto-Stabilo (Highlight)** langsung di PDF
    - **Deteksi Presisi:** Halaman, Kolom & Baris
    - **Ekspor Otomatis Formulir Komite (.docx & .xlsx)**
    """)
    st.caption("Publication Division © ICoDMI")

# Header
st.markdown('<div class="main-title">📑 IEEE Manuscript Format Checker & Auto-Annotator</div>', unsafe_allow_html=True)
st.markdown(f'<div class="sub-title">Sistem Pengecekan Presisi Format Naskah Final IEEE untuk Tim Publikasi <b>{conf_name}</b></div>', unsafe_allow_html=True)

uploaded_file = st.file_uploader("Unggah File Paper Final (PDF)", type=["pdf"], help="Drag and drop file PDF naskah di sini")

if uploaded_file is not None:
    file_bytes = uploaded_file.getvalue()
    
    # 1. File Safety & Integrity Check
    ok_safety, msg_safety = validate_pdf_safety(file_bytes, uploaded_file.name)
    if not ok_safety:
        st.error(f"🛑 **Peringatan Keamanan Berkas:**\n\n{msg_safety}")
        st.stop()
        
    # Save uploaded file to temp directory
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        tmp_file.write(file_bytes)
        temp_input_path = tmp_file.name

    try:
        doc = pymupdf.open(temp_input_path)
    except Exception:
        st.error("🛑 Gagal membaca file PDF. Berkas mungkin korup atau tidak valid.")
        st.stop()

    # 2. Gatekeeper: Academic Manuscript Eligibility Check
    ok_eligibility, msg_eligibility, info = validate_manuscript_eligibility(doc, uploaded_file.name)
    if not ok_eligibility:
        st.warning(f"⚠️ **Berkas Bukan Naskah Paper Ilmiah:**\n\n{msg_eligibility}")
        doc.close()
        st.stop()
    
    with st.spinner("Sedang memindai kepatuhan template IEEE dan menghitung koordinat..."):
        checker = IEEEComplianceChecker(
            min_pages=min_pages,
            max_pages=max_pages,
            hard_max_pages=hard_max_pages,
            target_size=target_size
        )
        violations, metadata = checker.check_pdf(doc)
        
    # Metrics display
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        if metadata.is_extra_pages:
            st.metric("Total Halaman", f"{metadata.total_pages} Hal", delta=f"Extra ({metadata.total_pages-max_pages} Hal Tambahan)", delta_color="off")
        elif metadata.is_page_count_valid:
            st.metric("Total Halaman", f"{metadata.total_pages} Hal", delta="Standar Reguler", delta_color="normal")
        else:
            st.metric("Total Halaman", f"{metadata.total_pages} Hal", delta=f"Batas: {min_pages}-{hard_max_pages} Hal", delta_color="inverse")
    with col2:
        st.metric("Ukuran Kertas", metadata.paper_size_name, delta="A4 Valid" if metadata.is_a4 else "Bukan A4!", delta_color="normal" if metadata.is_a4 else "inverse")
    with col3:
        fatal_count = sum(1 for v in violations if v.severity == "Fatal")
        st.metric("Pelanggaran Fatal", fatal_count, delta="Perlu Tolak" if fatal_count > 0 else "Nol", delta_color="inverse" if fatal_count > 0 else "normal")
    with col4:
        warn_count = sum(1 for v in violations if v.severity == "Warning")
        st.metric("Catatan Editorial", warn_count)
    with col5:
        st.metric("Total Revisi", len(violations))

    st.markdown("---")
    
    # Prepare Output Files in temp
    base_name = os.path.splitext(uploaded_file.name)[0]
    temp_dir = tempfile.gettempdir()
    annotated_pdf_path = os.path.join(temp_dir, f"{base_name}_annotated.pdf")
    word_report_path = os.path.join(temp_dir, f"{base_name}_review_sheet.docx")
    excel_report_path = os.path.join(temp_dir, f"{base_name}_review_sheet.xlsx")
    
    annotate_pdf(doc, violations, annotated_pdf_path)
    generate_word_report(violations, metadata, word_report_path, conference_name=conf_name)
    generate_excel_report(violations, metadata, excel_report_path)

    # Action Download Section
    st.subheader("📥 Unduh Hasil Pemeriksaan")
    dl_col1, dl_col2, dl_col3 = st.columns(3)
    
    with dl_col1:
        with open(annotated_pdf_path, "rb") as f:
            st.download_button(
                label="📄 Unduh PDF Ber-Stabilo (Annotated)",
                data=f,
                file_name=f"{base_name}_annotated.pdf",
                mime="application/pdf",
                use_container_width=True
            )
            
    with dl_col2:
        with open(word_report_path, "rb") as f:
            st.download_button(
                label="📝 Unduh Formulir Revisi Word (.docx)",
                data=f,
                file_name=f"{base_name}_review_sheet.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True
            )
            
    with dl_col3:
        with open(excel_report_path, "rb") as f:
            st.download_button(
                label="📊 Unduh Tabel Revisi Excel (.xlsx)",
                data=f,
                file_name=f"{base_name}_review_sheet.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

    # Table Display (Matching User's Template Table)
    st.subheader("📋 Tabel Komentar Komite (*Committee Comments & Location*)")
    
    if violations:
        table_data = []
        for idx, v in enumerate(violations, start=1):
            table_data.append({
                "No": idx,
                "Committee Comments": f"[{v.category}] {v.comment}",
                "Location in Manuscript": v.location,
                "Severity": v.severity
            })
            
        df = pd.DataFrame(table_data)
        
        # Filter options
        col_f1, col_f2 = st.columns([1, 3])
        with col_f1:
            severity_filter = st.multiselect("Filter Tingkat Keparahan:", ["Fatal", "Warning"], default=["Fatal", "Warning"])
        with col_f2:
            search_query = st.text_input("Cari kata kunci dalam komentar atau lokasi:", "")
            
        filtered_df = df[df["Severity"].isin(severity_filter)]
        if search_query:
            filtered_df = filtered_df[
                filtered_df["Committee Comments"].str.contains(search_query, case=False) |
                filtered_df["Location in Manuscript"].str.contains(search_query, case=False)
            ]
            
        st.dataframe(
            filtered_df[["No", "Committee Comments", "Location in Manuscript"]],
            use_container_width=True,
            hide_index=True,
            height=400
        )
    else:
        st.success("🎉 Luar biasa! Dokumen ini 100% mematuhi seluruh ketentuan format IEEE yang diperiksa.")
        
    doc.close()
    
    # Cleanup temp input
    try:
        os.remove(temp_input_path)
    except Exception:
        pass
else:
    # Instructions card
    st.info("💡 **Petunjuk Penggunaan:** Silakan seret dan lepas (*drag & drop*) file naskah PDF pada kotak di atas. Sistem akan langsung memindai setiap baris, menandai stabilo kuning/merah pada teks yang salah, serta membuatkan formulir revisi Word (.docx) secara otomatis.")

