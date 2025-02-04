from flask import Flask, request, jsonify, send_file
import fitz  # PyMuPDF
import re
from fpdf import FPDF
import io
import os
import logging
import tempfile
from datetime import datetime
from werkzeug.utils import secure_filename

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_url_path='', static_folder='.')

# Configuratie
UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', tempfile.gettempdir())
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
ALLOWED_EXTENSIONS = {'pdf'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

class PDFProcessor:
    def __init__(self):
        self.patterns = {
            'Verhuurder': [
                r'(?i)verhuurder\s*:?\s*(.*?)(?=\n|$)',
                r'(?i)(?<=hierna\s+te\s+noemen\s+["']?(?:de\s+)?verhuurder["']?[:\s])(.*?)(?=\n|$)'
            ],
            'Huurder': [
                r'(?i)huurder\s*:?\s*(.*?)(?=\n|$)',
                r'(?i)(?<=hierna\s+te\s+noemen\s+["']?(?:de\s+)?huurder["']?[:\s])(.*?)(?=\n|$)'
            ],
            'Object': [
                r'(?i)(?:object|woning|pand|adres)\s*:?\s*(.*?)(?=\n|$)',
                r'(?i)(?:gelegen\s+(?:aan|op|te))\s+(.*?)(?=\n|$)'
            ],
            'Huurprijs': [
                r'(?i)(?:huurprijs|huur(?:som)?)\s*(?:per\s+maand)?\s*:?\s*[€\s]*(\d+(?:[,.]\d{2})?)',
                r'(?i)(?:maandelijkse\s+huur(?:prijs)?)\s*:?\s*[€\s]*(\d+(?:[,.]\d{2})?)'
            ],
            'Huuringangsdatum': [
                r'(?i)(?:huuringangsdatum|ingangsdatum|aanvang)\s*:?\s*(\d{1,2}[-/\s]*(?:januari|februari|maart|april|mei|juni|juli|augustus|september|oktober|november|december|\d{1,2})[-/\s]*\d{2,4})'
            ],
            'Einddatum': [
                r'(?i)(?:einddatum|eindigingsdatum|einde)\s*:?\s*(\d{1,2}[-/\s]*(?:januari|februari|maart|april|mei|juni|juli|augustus|september|oktober|november|december|\d{1,2})[-/\s]*\d{2,4})'
            ]
        }

    def extract_details(self, pdf_file):
        try:
            # Sla het bestand tijdelijk op
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
                pdf_file.save(tmp_file)
                tmp_file_path = tmp_file.name

            # Open met PyMuPDF
            doc = fitz.open(tmp_file_path)
            
            # Verzamel alle tekst
            full_text = ""
            for page in doc:
                full_text += page.get_text()

            # Sluit en verwijder tijdelijk bestand
            doc.close()
            os.unlink(tmp_file_path)

            # Extraheer details
            details = {}
            for field, patterns in self.patterns.items():
                value = None
                for pattern in patterns:
                    match = re.search(pattern, full_text)
                    if match:
                        value = match.group(1).strip()
                        break
                details[field] = value if value else "Niet gevonden"

            return details

        except Exception as e:
            logger.error(f"Error in extract_details: {str(e)}")
            raise Exception(f"Fout bij het extraheren van PDF gegevens: {str(e)}")

    def generate_summary(self, details):
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
            for key, value in details.items():
                pdf.set_font("Arial", "B", 12)
                pdf.cell(60, 10, f"{key}:", 0)
                pdf.set_font("Arial", "", 12)
                pdf.cell(130, 10, str(value), 0, 1)
            
            # Save to BytesIO
            output = io.BytesIO()
            pdf.output(output)
            output.seek(0)
            return output

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

        if not allowed_file(file.filename):
            return jsonify({"error": "Alleen PDF bestanden zijn toegestaan"}), 400

        filename = secure_filename(file.filename)
        
        # Process the PDF
        processor = PDFProcessor()
        details = processor.extract_details(file)
        output_pdf = processor.generate_summary(details)

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
    # Use production server when deploying
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
