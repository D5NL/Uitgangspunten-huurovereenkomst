from typing import Dict, Any, Optional
import spacy
from transformers import pipeline
import pytesseract
import cv2
import numpy as np
import fitz
import re
from dataclasses import dataclass
from datetime import datetime
import logging
from pathlib import Path

@dataclass
class ContractField:
    name: str
    value: str
    confidence: float
    source: str  # OCR, NLP, or REGEX
    page_number: int

class AdvancedPDFProcessor:
    def __init__(self):
        # Initialize NLP components
        self.nlp = spacy.load("nl_core_news_lg")
        self.ner = pipeline("ner", model="wietsedv/bert-base-dutch-cased")
        
        # Initialize logging
        self.logger = logging.getLogger(__name__)
        
        # Regex patterns with context awareness
        self.patterns = {
            'Verhuurder': [
                r'(?i)(?:verhuurder|eigenaar|verhurende\s+partij)\s*:?\s*(.*?)(?=\n|$)',
                r'(?i)(?<=hierna\s+te\s+noemen\s+["']?(?:de\s+)?verhuurder["']?[:\s])(.*?)(?=\n|$)'
            ],
            'Huurder': [
                r'(?i)(?:huurder|hurende\s+partij)\s*:?\s*(.*?)(?=\n|$)',
                r'(?i)(?<=hierna\s+te\s+noemen\s+["']?(?:de\s+)?huurder["']?[:\s])(.*?)(?=\n|$)'
            ],
            'Object': [
                r'(?i)(?:object|woning|pand|adres|gehuurde)\s*:?\s*(.*?)(?=\n|$)',
                r'(?i)(?:gelegen\s+(?:aan|op|te))\s+(.*?)(?=\n|$)'
            ],
            'Huurprijs': [
                r'(?i)(?:huurprijs|huur(?:som)?)\s*(?:per\s+maand)?\s*:?\s*[€\s]*(\d+(?:[,.]\d{2})?)',
                r'(?i)(?:maandelijkse\s+huur(?:prijs)?)\s*:?\s*[€\s]*(\d+(?:[,.]\d{2})?)'
            ],
            'Huuringangsdatum': [
                r'(?i)(?:huuringangsdatum|ingangsdatum|aanvang\s+huur)\s*:?\s*(\d{1,2}[-/\s]*(?:januari|februari|maart|april|mei|juni|juli|augustus|september|oktober|november|december|\d{1,2})[-/\s]*\d{2,4})',
                r'(?i)(?:de\s+huur(?:overeenkomst)?\s+gaat\s+in\s+op)\s*(\d{1,2}[-/\s]*(?:januari|februari|maart|april|mei|juni|juli|augustus|september|oktober|november|december|\d{1,2})[-/\s]*\d{2,4})'
            ],
            'Einddatum': [
                r'(?i)(?:einddatum|eindigingsdatum|einde\s+huur)\s*:?\s*(\d{1,2}[-/\s]*(?:januari|februari|maart|april|mei|juni|juli|augustus|september|oktober|november|december|\d{1,2})[-/\s]*\d{2,4})',
                r'(?i)(?:de\s+huur(?:overeenkomst)?\s+eindigt\s+op)\s*(\d{1,2}[-/\s]*(?:januari|februari|maart|april|mei|juni|juli|augustus|september|oktober|november|december|\d{1,2})[-/\s]*\d{2,4})'
            ]
        }

    def _extract_text_with_ocr(self, image: np.ndarray) -> str:
        """Extract text from image using OCR."""
        return pytesseract.image_to_string(image, lang='nld')

    def _preprocess_image(self, image: np.ndarray) -> np.ndarray:
        """Preprocess image for better OCR results."""
        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Apply thresholding
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # Remove noise
        denoised = cv2.fastNlMeansDenoising(binary)
        
        return denoised

    def _extract_info_with_nlp(self, text: str) -> Dict[str, ContractField]:
        """Extract information using NLP."""
        doc = self.nlp(text)
        entities = self.ner(text)
        
        fields = {}
        
        # Process named entities
        for ent in entities:
            if ent['entity'] == 'PER' and 'Huurder' not in fields:
                fields['Huurder'] = ContractField(
                    name='Huurder',
                    value=ent['word'],
                    confidence=ent['score'],
                    source='NLP',
                    page_number=-1
                )
            elif ent['entity'] == 'LOC' and 'Object' not in fields:
                fields['Object'] = ContractField(
                    name='Object',
                    value=ent['word'],
                    confidence=ent['score'],
                    source='NLP',
                    page_number=-1
                )

        return fields

    def _validate_field(self, field: str, value: str) -> tuple[bool, float]:
        """Validate extracted field values."""
        if field == 'Huurprijs':
            # Check if value is a valid number
            try:
                float(value.replace(',', '.').replace('€', '').strip())
                return True, 1.0
            except ValueError:
                return False, 0.0
        elif field in ['Huuringangsdatum', 'Einddatum']:
            # Check if value is a valid date
            try:
                # Add more date format parsing here
                datetime.strptime(value, '%d-%m-%Y')
                return True, 1.0
            except ValueError:
                return False, 0.0
        return True, 0.8  # Default validation for other fields

    def process_pdf(self, pdf_path: Path) -> Dict[str, ContractField]:
        """Process PDF and extract all relevant information."""
        doc = fitz.open(pdf_path)
        extracted_fields = {}
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            
            # Extract text directly from PDF
            text = page.get_text()
            
            # Extract text using OCR if page contains images
            for img in page.get_images():
                xref = img[0]
                base_image = doc.extract_image(xref)
                image_data = base_image["image"]
                
                # Convert to numpy array and preprocess
                nparr = np.frombuffer(image_data, np.uint8)
                img_np = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                processed_img = self._preprocess_image(img_np)
                
                # Extract text from image
                ocr_text = self._extract_text_with_ocr(processed_img)
                text += "\n" + ocr_text

            # Extract information using NLP
            nlp_fields = self._extract_info_with_nlp(text)
            
            # Extract information using regex patterns
            for field, patterns in self.patterns.items():
                if field not in extracted_fields:
                    for pattern in patterns:
                        match = re.search(pattern, text)
                        if match:
                            value = match.group(1).strip()
                            is_valid, confidence = self._validate_field(field, value)
                            
                            if is_valid:
                                extracted_fields[field] = ContractField(
                                    name=field,
                                    value=value,
                                    confidence=confidence,
                                    source='REGEX',
                                    page_number=page_num
                                )
                                break

            # Combine regex and NLP results, preferring higher confidence values
            for field, nlp_field in nlp_fields.items():
                if field not in extracted_fields or \
                   nlp_field.confidence > extracted_fields[field].confidence:
                    extracted_fields[field] = nlp_field
                    extracted_fields[field].page_number = page_num

        return extracted_fields

    def generate_report(self, fields: Dict[str, ContractField]) -> str:
        """Generate a detailed analysis report."""
        report = []
        report.append("Huurovereenkomst Analyse Rapport")
        report.append(f"Gegenereerd op: {datetime.now().strftime('%d-%m-%Y %H:%M')}\n")
        
        for field in fields.values():
            report.append(f"{field.name}:")
            report.append(f"  Waarde: {field.value}")
            report.append(f"  Betrouwbaarheid: {field.confidence:.2%}")
            report.append(f"  Bron: {field.source}")
            report.append(f"  Pagina: {field.page_number + 1}\n")
        
        return "\n".join(report)

    def validate_contract(self, fields: Dict[str, ContractField]) -> list[str]:
        """Validate contract for completeness and consistency."""
        issues = []
        
        # Check required fields
        required_fields = {'Verhuurder', 'Huurder', 'Object', 'Huurprijs', 'Huuringangsdatum'}
        missing_fields = required_fields - set(fields.keys())
        if missing_fields:
            issues.append(f"Ontbrekende verplichte velden: {', '.join(missing_fields)}")
        
        # Check confidence levels
        low_confidence_threshold = 0.7
        for field in fields.values():
            if field.confidence < low_confidence_threshold:
                issues.append(
                    f"Lage betrouwbaarheid voor {field.name} ({field.confidence:.2%})"
                )
        
        # Validate dates if present
        if 'Huuringangsdatum' in fields and 'Einddatum' in fields:
            try:
                start_date = datetime.strptime(
                    fields['Huuringangsdatum'].value, '%d-%m-%Y'
                )
                end_date = datetime.strptime(fields['Einddatum'].value, '%d-%m-%Y')
                if end_date <= start_date:
                    issues.append("Einddatum ligt voor of op de ingangsdatum")
            except ValueError:
                issues.append("Ongeldige datumformaten gevonden")
        
        return issues
