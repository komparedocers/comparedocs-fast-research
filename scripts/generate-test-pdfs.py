#!/usr/bin/env python3
"""
Generate test PDF documents for performance testing
"""

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
import random
import os

def generate_test_pdf(filename, num_pages=10, variant="base"):
    """Generate a test PDF with specified number of pages"""

    c = canvas.Canvas(filename, pagesize=letter)
    width, height = letter

    for page_num in range(num_pages):
        # Add header
        c.setFont("Helvetica-Bold", 16)
        c.drawString(inch, height - inch, f"Test Document - Page {page_num + 1}")

        # Add content paragraphs
        c.setFont("Helvetica", 12)
        y_position = height - 2*inch

        paragraphs = [
            f"This is paragraph 1 on page {page_num + 1}. Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
            f"This is paragraph 2 on page {page_num + 1}. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
            f"This is paragraph 3 on page {page_num + 1}. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris.",
            f"This is paragraph 4 on page {page_num + 1}. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum.",
            f"This is paragraph 5 on page {page_num + 1}. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia.",
        ]

        # Add variant-specific changes
        if variant == "modified":
            paragraphs[2] = f"This is a MODIFIED paragraph on page {page_num + 1}. Different content here for anomaly detection."
            paragraphs.append(f"EXTRA paragraph added on page {page_num + 1}. This is new content not in the base version.")
        elif variant == "paraphrase":
            paragraphs[1] = f"On page {page_num + 1}, this represents the second paragraph. It performs temporary modification including work and significant effort."

        for para in paragraphs:
            # Wrap text if needed
            words = para.split()
            line = ""
            for word in words:
                if c.stringWidth(line + word, "Helvetica", 12) < width - 2*inch:
                    line += word + " "
                else:
                    c.drawString(inch, y_position, line.strip())
                    y_position -= 0.3*inch
                    line = word + " "

            if line:
                c.drawString(inch, y_position, line.strip())

            y_position -= 0.5*inch

            if y_position < inch:
                break

        # Add page number at bottom
        c.setFont("Helvetica", 10)
        c.drawString(width/2, 0.5*inch, f"Page {page_num + 1} of {num_pages}")

        c.showPage()

    c.save()
    print(f"Generated: {filename}")

def main():
    """Generate a set of test PDFs"""

    os.makedirs("test-pdfs", exist_ok=True)

    # Generate base documents
    print("Generating test PDFs...")

    # Small documents
    generate_test_pdf("test-pdfs/small-base.pdf", num_pages=5, variant="base")
    generate_test_pdf("test-pdfs/small-modified.pdf", num_pages=5, variant="modified")

    # Medium documents
    generate_test_pdf("test-pdfs/medium-base.pdf", num_pages=20, variant="base")
    generate_test_pdf("test-pdfs/medium-modified.pdf", num_pages=20, variant="modified")

    # Large documents
    generate_test_pdf("test-pdfs/large-base.pdf", num_pages=50, variant="base")
    generate_test_pdf("test-pdfs/large-modified.pdf", num_pages=50, variant="modified")

    # Paraphrase variant
    generate_test_pdf("test-pdfs/medium-paraphrase.pdf", num_pages=20, variant="paraphrase")

    print(f"\nGenerated {7} test PDFs in test-pdfs/ directory")
    print("\nUsage:")
    print("  1. Upload small-base.pdf and small-modified.pdf to test basic comparison")
    print("  2. Upload medium-base.pdf and medium-paraphrase.pdf to test paraphrase detection")
    print("  3. Upload large-*.pdf files to test performance with bigger documents")

if __name__ == "__main__":
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.units import inch
        main()
    except ImportError:
        print("Error: reportlab not installed")
        print("Install with: pip install reportlab")
        exit(1)
