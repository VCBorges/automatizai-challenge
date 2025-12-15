import io
import logging

import pymupdf

from src.exceptions import PDFExtractionError

logger = logging.getLogger(__name__)

# Threshold for minimum extracted text length to consider valid extraction.
# Below this, we assume the PDF might be scanned/image-based.
MIN_TEXT_LENGTH_THRESHOLD = 50


def _extract_text_with_ocr_fallback(pdf_path: str) -> str:
    """
    Fallback OCR extraction for scanned/image-based PDFs.

    DESIGN DECISION:
    ----------------
    This is a MOCK implementation. In production, this would integrate with
    an OCR service such as:

    - Tesseract OCR (open-source, can run locally)
    - AWS Textract (managed service, high accuracy for documents)
    - Google Cloud Vision OCR
    - Azure Computer Vision

    The choice depends on:
    - Cost constraints (Tesseract is free, cloud services charge per page)
    - Accuracy requirements (cloud services generally better for complex layouts)
    - Latency requirements (local Tesseract is faster, no network overhead)
    - Infrastructure preferences (self-hosted vs managed)

    For a legal document validation system like this one, AWS Textract or
    Google Cloud Vision would be recommended due to their specialized
    document parsing capabilities and high accuracy with Brazilian documents.

    Implementation with Tesseract would look like:
    ```python
    import pytesseract
    from PIL import Image

    images = convert_from_path(pdf_path)
    text = ""
    for image in images:
        text += pytesseract.image_to_string(image, lang="por")
    return text
    ```

    For now, we return an empty string and let the system handle it gracefully
    by registering an appropriate inconsistency during cross-document analysis.
    """
    logger.warning(
        "OCR fallback triggered but not implemented - PDF may be scanned/image-based",
        extra={"pdf_path": pdf_path},
    )
    # TODO: Implement actual OCR integration when needed
    return ""


def extract_text_from_pdf(pdf_path: str, *, use_ocr_fallback: bool = True) -> str:
    """
    Extract text content from a PDF file.

    Uses PyMuPDF for native text extraction. If the extracted text is below
    a minimum threshold (indicating a scanned/image-based PDF), optionally
    falls back to OCR extraction.

    Args:
        pdf_path: Path to the PDF file.
        use_ocr_fallback: Whether to attempt OCR if native extraction yields
                          insufficient text. Defaults to True.

    Returns:
        Extracted text content from the PDF.

    Raises:
        PDFExtractionError: If the PDF cannot be read or processed.
    """
    try:
        string_buffer = io.StringIO()
        with pymupdf.open(pdf_path) as doc:
            for page in doc:
                string_buffer.write(page.get_text())

        extracted_text = string_buffer.getvalue()

        # Check if we got meaningful text
        if len(extracted_text.strip()) < MIN_TEXT_LENGTH_THRESHOLD:
            logger.info(
                "PDF text extraction yielded minimal content, may be scanned PDF",
                extra={
                    "pdf_path": pdf_path,
                    "extracted_length": len(extracted_text.strip()),
                    "threshold": MIN_TEXT_LENGTH_THRESHOLD,
                },
            )

            if use_ocr_fallback:
                ocr_text = _extract_text_with_ocr_fallback(pdf_path)
                if ocr_text.strip():
                    return ocr_text

        return extracted_text

    except FileNotFoundError as e:
        raise PDFExtractionError(
            f"PDF file not found: {pdf_path}",
            file_path=pdf_path,
            original_error=e,
        ) from e
    except Exception as e:
        raise PDFExtractionError(
            f"Failed to extract text from PDF: {pdf_path}",
            file_path=pdf_path,
            original_error=e,
        ) from e
