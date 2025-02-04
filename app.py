from flask import Flask, request, jsonify, send_file, current_app
from werkzeug.utils import secure_filename
from functools import wraps
import fitz  # PyMuPDF
import re
from fpdf import FPDF
import io
import os
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_url_path='', static_folder='.')

# Configuration
app.config.update(
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16MB max file size
    UPLOAD_EXTENSIONS=['.pdf'],
    SECRET_KEY='your-secret-key-here'  # Change this in production
)

class PDFExtractionError(Exception):
    """Custom exception for PDF extraction errors"""
    pass

def validate_pdf_file(file):
    """Validate uploaded PDF file"""
    filename = secure_filename(file.filename)
    if not filename:
        raise ValueError("Invalid filename")
    
    file_ext = os.path.splitext(filename)[1].lower()
    if file_ext not in current_app.config['UPLOAD_EXTENSIONS']:
        raise ValueError(f"Invalid file extension: {file_ext}")
    
    return filename

def error_handler(f):
    """Decorator for consistent error handling"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ValueError as e:
            logger.warning(f"Validation error: {str(e)}")
            return jsonify({"error": str(e)}), 400
        except PDFExtractionError as e:
            logger.error(f"PDF extraction error: {str(e)}")
            return jsonify({"error": "Kon geen gegevens uit PDF extracteren"}), 422
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}", exc_info=True)
            return jsonify({"error": "Er is een interne fout opgetreden"}), 500
    return decorated_function

class RentalDocument:
    """Class to handle rental document operations"""
    REQUIRED_FIELDS = {
        "Verhuurder": r'Verhuurder\s*:\s*(.*?)(?=\n|$)',
        "Huurder": r'Huurder\s*:\s*(.*?)(?=\n|$)',
        "Object": r'Object\s*:\s*(.*?)(?=\n|$)',
        "Huurprijs": r'Huurprijs op maandbasis\s*:\s*(.*?)(?=\n|$)',
        "Huuringangsdatum": r'Huuringangsdatum\s*:\s*(.*?)(?=\n|$)',
        "Einddatum": r'Einddatum\s*:\s*(.*?)(?=\n|$)'
    }

    def __init__(self, pdf_file):
        self.pdf_file = pdf_file
        self.details = {}

    def extract_details(self):
        """Extract rental details from PDF"""
        try:
            self.pdf_file.seek(0)
            pdf_data = self.pdf_file.read()
            doc = fitz.open(stream=pdf_data, filetype="pdf")
            
            full_text = ""
            for page in doc:
                full_text += page.get_text("text")

            for field, pattern in self.REQUIRED_FIELDS.items():
                match = re.search(pattern, full_text, re.MULTILINE)
                if match:
                    self.details[field] = match.group(1).strip()
                else:
                    logger.warning(f"Field {field} not found in document")
                    self.details[field] = "Niet gevonden"

            doc.close()
            return self.details

        except Exception as e:
            raise PDFExtractionError(f"Error extracting PDF details: {str(e)}")

    def generate_summary(self):
        """Generate summary PDF"""
        try:
            pdf = FPDF()
            pdf.set_auto_page_break(auto=True, margin=15)
            pdf.add_page()
            
            # Add header
            pdf.set_font("Arial", "B", size=16)
            pdf.cell(200, 10, "Samenvatting Huurovereenkomst", ln=True, align='C')
            pdf.ln(10)
            
            # Add timestamp
            pdf.set_font("Arial", size=10)
            pdf.cell(200, 10, f"Gegenereerd op: {datetime.now().strftime('%d-%m-%Y %H:%M')}", ln=True)
            pdf.ln(10)
            
            # Add details
            pdf.set_font("Arial", size=12)
            for key, value in self.details.items():
                pdf.set_font("Arial", "B", size=12)
                pdf.cell(60, 10, f"{key}:", 0)
                pdf.set_font("Arial", size=12)
                pdf.cell(130, 10, value, ln=True)
            
            output = io.BytesIO()
            pdf.output(output)
            output.seek(0)
            return output
            
        except Exception as e:
            raise PDFExtractionError(f"Error generating summary PDF: {str(e)}")

@app.route("/")
def index():
    return app.send_static_file("index.html")

@app.route("/upload", methods=["POST"])
@error_handler
def upload_file():
    if 'file' not in request.files:
        raise ValueError("Geen bestand geüpload")

    file = request.files['file']
    if file.filename == "":
        raise ValueError("Geen bestand geselecteerd")

    # Validate file
    validate_pdf_file(file)
    
    # Process rental document
    rental_doc = RentalDocument(file)
    rental_details = rental_doc.extract_details()
    
    # Generate summary
    output_pdf = rental_doc.generate_summary()
    
    return send_file(
        output_pdf,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"voorblad_samenvatting_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    )

if __name__ == "__main__":
    app.run(debug=False)  # Set to False in production
