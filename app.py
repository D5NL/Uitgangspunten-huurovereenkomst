from flask import Flask, request, jsonify, send_file
import fitz  # PyMuPDF
import re
from fpdf import FPDF
import io

app = Flask(__name__)

def extract_rental_details(pdf_file):
    details = {}
    doc = fitz.open(stream=pdf_file.read(), filetype="pdf")
    for page in doc:
        text = page.get_text("text")
        if text:
            if "Verhuurder" in text:
                match = re.search(r'Verhuurder\\s*:\\s*(.*)', text)
                if match:
                    details["Verhuurder"] = match.group(1)
            if "Huurder" in text:
                match = re.search(r'Huurder\\s*:\\s*(.*)', text)
                if match:
                    details["Huurder"] = match.group(1)
            if "Object" in text:
                match = re.search(r'Object\\s*:\\s*(.*)', text)
                if match:
                    details["Object"] = match.group(1)
            if "Huurprijs" in text:
                match = re.search(r'Huurprijs op maandbasis\\s*:\\s*(.*)', text)
                if match:
                    details["Huurprijs"] = match.group(1)
            if "Huuringangsdatum" in text:
                match = re.search(r'Huuringangsdatum\\s*:\\s*(.*)', text)
                if match:
                    details["Huuringangsdatum"] = match.group(1)
            if "Einddatum" in text:
                match = re.search(r'Einddatum\\s*:\\s*(.*)', text)
                if match:
                    details["Einddatum"] = match.group(1)
    return details

def generate_summary_pdf(details):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, "Samenvatting Huurovereenkomst", ln=True, align='C')
    pdf.ln(10)
    
    for key, value in details.items():
        pdf.cell(200, 10, f"{key}: {value}", ln=True)
    
    pdf_output = io.BytesIO()
    pdf.output(pdf_output)
    pdf_output.seek(0)
    return pdf_output

@app.route("/upload", methods=["POST"])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files['file']
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400
    
    rental_details = extract_rental_details(file)
    output_pdf = generate_summary_pdf(rental_details)
    
    return send_file(output_pdf, mimetype='application/pdf', as_attachment=True, download_name="voorblad_samenvatting.pdf")

if __name__ == "__main__":
    app.run(debug=True)
