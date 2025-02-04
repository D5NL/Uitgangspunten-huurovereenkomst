from flask import Flask, request, jsonify, send_file
import fitz  # PyMuPDF
import re
from fpdf import FPDF
import io
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_url_path='', static_folder='.')

class PDFProcessor:
    def __init__(self, pdf_file):
        self.pdf_file = pdf_file
        self.details = {}

    def extract_details(self):
        try:
            # Reset file pointer
            self.pdf_file.seek(0)
            pdf_data = self.pdf_file.read()
            
            # Open PDF with PyMuPDF
            doc = fitz.open(stream=pdf_data, filetype="pdf")
            
            # Extract text from all pages
            text = ""
            for page in doc:
                text += page.get_text()
            
            # Close the document
            doc.close()

            # Define patterns with more flexible matching
            patterns = {
                'Verhuurder': r'(?i)verhuurder\s*:?\s*(.*?)(?:\n|$)',
                'Huurder': r'(?i)huurder\s*:?\s*(.*?)(?:\n|$)',
                'Object': r'(?i)object\s*:?\s*(.*?)(?:\n|$)',
                'Huurprijs': r'(?i)huurprijs[^:]*:?\s*([\d.,]+)',
                'Huuringangsdatum': r'(?i)(?:huuringangsdatum|ingangsdatum)\s*:?\s*(\d{1,2}[-/\s]*(?:januari|februari|maart|april|mei|juni|juli|augustus|september|oktober|november|december|\d{1,2})[-/\s]*\d{2,4})',
                'Einddatum': r'(?i)(?:einddatum|eindigingsdatum)\s*:?\s*(\d{1,2}[-/\s]*(?:januari|februari|maart|april|mei|juni|juli|augustus|september|oktober|november|december|\d{1,2})[-/\s]*\d{2,4})'
            }

            # Extract information
            for field, pattern in patterns.items():
                match = re.search(pattern, text)
                if match:
                    self.details[field] = match.group(1).strip()
                    logger.info(f"Found {field}: {self.details[field]}")
                else:
                    self.details[field] = "Niet gevonden"
                    logger.warning(f"Field {field} not found in document")

            return self.details

        except Exception as e:
            logger.error(f"Error in extract_details: {str(e)}")
            raise Exception(f"Fout bij het extraheren van PDF gegevens: {str(e)}")

    def generate_summary(self):
        try:
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", "B", 16)
            
            # Title
            pdf.cell(190, 10, "Samenvatting Huurovereenkomst", 0, 1, "C")
            pdf.ln(10)
            
            # Add timestamp
            pdf.set_font("Arial", "", 10)
            pdf.cell(190, 10, f"Gegenereerd op: {datetime.now().strftime('%d-%m-%Y %H:%M')}", 0, 1, "R")
            pdf.ln(10)
            
            # Add details
            pdf.set_font("Arial", "", 12)
            for key, value in self.details.items():
                pdf.set_font("Arial", "B", 12)
                pdf.cell(60, 10, f"{key}:", 0)
                pdf.set_font("Arial", "", 12)
                pdf.cell(130, 10, str(value), 0, 1)
            
            # Save to BytesIO
            output = io.BytesIO()
            try:
                pdf.output(output)
                output.seek(0)
                return output
            except Exception as e:
                logger.error(f"Error in PDF output: {str(e)}")
                raise Exception("Fout bij het genereren van de PDF")

        except Exception as e:
            logger.error(f"Error in generate_summary: {str(e)}")
            raise Exception(f"Fout bij het maken van de samenvatting: {str(e)}")

@app.route("/")
def index():
    return app.send_static_file("index.html")

@app.route("/upload", methods=["POST"])
def upload_file():
    try:
        if 'file' not in request.files:
            return jsonify({"error": "Geen bestand geüpload"}), 400

        file = request.files['file']
        if file.filename == "":
            return jsonify({"error": "Geen bestand geselecteerd"}), 400

        if not file.filename.lower().endswith('.pdf'):
            return jsonify({"error": "Alleen PDF bestanden zijn toegestaan"}), 400

        # Process the PDF
        processor = PDFProcessor(file)
        details = processor.extract_details()
        output_pdf = processor.generate_summary()

        return send_file(
            output_pdf,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"voorblad_samenvatting_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        )

    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)
