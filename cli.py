import os
import sys
import argparse
import pymupdf
from colorama import init, Fore, Style

from core.rules import IEEEComplianceChecker
from core.highlighter import annotate_pdf
from core.report_generator import generate_word_report, generate_excel_report

init(autoreset=True)

def main():
    parser = argparse.ArgumentParser(description="IEEE Conference Manuscript Format Checker & Auto-Annotator")
    parser.add_argument("pdf_path", help="Path to manuscript PDF file to check")
    parser.add_argument("--output-dir", default="./reports", help="Directory to save annotated PDF and reports")
    parser.add_argument("--min-pages", type=int, default=4, help="Minimum page limit (default: 4)")
    parser.add_argument("--max-pages", type=int, default=6, help="Maximum page limit (default: 6)")
    parser.add_argument("--size", default="A4", choices=["A4", "Letter"], help="Target paper size (default: A4)")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.pdf_path):
        print(f"{Fore.RED}Error: File not found: {args.pdf_path}")
        sys.exit(1)
        
    os.makedirs(args.output_dir, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(args.pdf_path))[0]
    
    print(f"\n{Fore.CYAN}{'='*60}")
    print(f"{Fore.CYAN} IEEE MANUSCRIPT COMPLIANCE CHECKER - ICoDMI (SSMI IPB)")
    print(f"{Fore.CYAN}{'='*60}")
    print(f"File Target: {Style.BRIGHT}{args.pdf_path}")
    
    # Open document
    doc = pymupdf.open(args.pdf_path)
    
    # Run checker
    checker = IEEEComplianceChecker(
        min_pages=args.min_pages, 
        max_pages=args.max_pages, 
        target_size=args.size
    )
    violations, metadata = checker.check_pdf(doc)
    
    # Summary
    print(f"\n{Fore.YELLOW}[METADATA SCAN]")
    print(f"• Total Pages    : {metadata.total_pages} (Allowed: {args.min_pages}-{args.max_pages})")
    print(f"• Detected Size  : {metadata.paper_size_name} ({metadata.page_width_pt:.1f} x {metadata.page_height_pt:.1f} pt)")
    print(f"• Copyright Line : {'Found' if metadata.has_copyright_notice else 'Missing / Incomplete'}")
    print(f"• Fonts Count    : {len(metadata.fonts)} unique font subsets")
    
    fatal_count = sum(1 for v in violations if v.severity == "Fatal")
    warn_count = sum(1 for v in violations if v.severity == "Warning")
    
    print(f"\n{Fore.YELLOW}[EVALUATION RESULT]")
    print(f"• Total Violations Detected : {len(violations)}")
    print(f"• Critical / Fatal Errors   : {Fore.RED}{fatal_count}{Style.RESET_ALL}")
    print(f"• Editorial Warnings        : {Fore.YELLOW}{warn_count}{Style.RESET_ALL}")
    
    # Print sample violations table
    if violations:
        print(f"\n{Style.BRIGHT}{'No':<4} | {'Location in Manuscript':<38} | {'Committee Comments'}")
        print(f"{'-'*4}-+-{'-'*38}-+-{'-'*50}")
        for v in violations[:15]:  # print first 15 in console
            comment_snippet = (v.comment[:75] + '...') if len(v.comment) > 75 else v.comment
            color = Fore.RED if v.severity == "Fatal" else Fore.YELLOW
            print(f"{v.no:<4} | {v.location:<38} | {color}{comment_snippet}")
        if len(violations) > 15:
            print(f"... and {len(violations) - 15} more items (see generated report)")
    else:
        print(f"{Fore.GREEN}[OK] Document 100% compliant with checked IEEE format rules!")
        
    # Generate Output Files
    annotated_pdf_path = os.path.join(args.output_dir, f"{base_name}_annotated.pdf")
    word_report_path = os.path.join(args.output_dir, f"{base_name}_review_sheet.docx")
    excel_report_path = os.path.join(args.output_dir, f"{base_name}_review_sheet.xlsx")
    
    print(f"\n{Fore.CYAN}[GENERATING OUTPUTS]")
    annotate_pdf(doc, violations, annotated_pdf_path)
    print(f"{Fore.GREEN}[OK] Annotated PDF (Auto-stabilo) : {annotated_pdf_path}")
    
    generate_word_report(violations, metadata, word_report_path)
    print(f"{Fore.GREEN}[OK] Word Revision Sheet (.docx) : {word_report_path}")
    
    generate_excel_report(violations, metadata, excel_report_path)
    print(f"{Fore.GREEN}[OK] Excel Revision Sheet (.xlsx): {excel_report_path}")
    
    print(f"\n{Fore.CYAN}{'='*60}\n")

if __name__ == "__main__":
    main()
