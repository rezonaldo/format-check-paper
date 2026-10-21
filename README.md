# IEEE Manuscript Format Checker & Auto-Annotator 📑
**Publication Division - ICoDMI (SSMI IPB)**

Aplikasi otomatis berbasis Python untuk memeriksa kepatuhan naskah (*final manuscript*) terhadap ketentuan template resmi IEEE, menentukan lokasi kesalahan secara presisi (Halaman, Kolom, Baris/Seksi), memberi **stabilo (highlight) otomatis** langsung pada file PDF, serta menghasilkan **formulir tabel revisi (*Committee Comments & Location in Manuscript*)** dalam format Word (`.docx`) dan Excel (`.xlsx`).

---

## 🚀 Cara Menjalankan

### Cara 1: Menggunakan Antarmuka Web (Paling Mudah)
Cukup **klik dua kali (*double-click*)** file:
```
Jalankan_IEEE_Checker.bat
```
Atau melalui terminal/PowerShell:
```bash
streamlit run app.py
```
Aplikasi web interaktif akan otomatis terbuka di browser Anda (`http://localhost:8501`). Anda cukup melakukan **drag-and-drop file PDF** naskah.

### Cara 2: Melalui Terminal (CLI Batch Mode)
Untuk memeriksa satu file PDF secara langsung:
```bash
python cli.py "path/to/paper.pdf"
```
Hasil file PDF ber-stabilo dan dokumen Word akan otomatis tersimpan di folder `./reports/`.

---

## 🔍 Ketentuan IEEE yang Diperiksa Secara Presisi

1. **Ukuran Halaman & Margin:** Validasi A4 ($210 \times 297\text{ mm}$ / $595 \times 842\text{ pt}$).
2. **Batas Jumlah Halaman:** Memastikan paper sesuai rentang yang ditentukan (default: 4–6 halaman).
3. **Larangan Nomor Halaman:** Deteksi otomatis penomoran halaman liar (*pagination*) di header maupun footer.
4. **Pembersihan Teks Panduan Template:** Memindai 40+ frasa teks bawaan template IEEE (seperti *"Identify applicable funding agency"*, *"live template"*, *"line 1: 1st Given Name"*).
5. **IEEE Copyright Clearance Code:** Memverifikasi kode hak cipta di footer pojok kiri bawah halaman 1.
6. **Judul & Abstrak:** Memeriksa keberadaan judul, gaya run-in `Abstract—`, kata kunci, serta larangan simbol/rumus di judul.
7. **Persamaan Matematika (Equations):** Memeriksa nomor persamaan `(1)` rata kanan dan cara sitasi rumus di dalam teks (melarang penggunaan `"Eq. (1)"` di tengah kalimat).
8. **Gambar & Tabel:**
   - Memastikan sitasi dalam teks menggunakan singkatan `"Fig. 1"` (bukan `"Figure 1"`).
   - Memastikan judul tabel menggunakan angka romawi kapital `"TABLE I."` (bukan `"Table 1"`).
9. **Penulisan Istilah & Tata Bahasa:**
   - Ejaan kata `ACKNOWLEDGMENT` tanpa huruf 'e' setelah 'g'.
   - Penulisan singkatan Latin `et al.` (tanpa titik setelah `et`).
   - Penulisan angka desimal dengan angka nol di depan (`0.25`, bukan `.25`).
   - Satuan volume `cm3` (bukan `cc`).
   - Tanda baca setelah kurung sitasi (misal `[1].` bukan `.[1]`).
10. **Heading 5 (Component Heads):** Memastikan `REFERENCES` dan `ACKNOWLEDGMENT` tidak dinomori dengan angka romawi/arab.

---

## 📦 Output yang Dihasilkan
1. **📄 `[Nama_Paper]_annotated.pdf`:** File PDF yang sudah diberi tanda stabilo digital (kuning untuk catatan editorial, merah untuk pelanggaran fatal) lengkap dengan catatan teks komentar saat stabilo diklik.
2. **📝 `[Nama_Paper]_review_sheet.docx`:** Formulir Microsoft Word dengan tabel berkolom `No` | `Committee Comments` | `Location in Manuscript` siap dikirimkan langsung ke penulis.
3. **📊 `[Nama_Paper]_review_sheet.xlsx`:** File spreadsheet Excel untuk rekapitulasi komite publikasi.

