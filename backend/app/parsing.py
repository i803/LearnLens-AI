from __future__ import annotations
import fitz
from PIL import Image, ImageOps, ImageEnhance, ImageFilter
import io
import time
from .config import MAX_PDF_PAGES

IMAGE_TYPES = {"image/jpeg":"image/jpeg","image/jpg":"image/jpeg","image/png":"image/png","image/webp":"image/webp"}

def normalize_scalar(value, default):
    return default if value is None else value

def unit_interval(value, default: float = 0.0) -> float:
    """Coerce a model-supplied confidence to 0..1 (accepts 0-100 percentages)."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number:  # NaN
        return default
    if 1 < number <= 100:
        number /= 100
    return min(1.0, max(0.0, number))

def normalize_question(raw: dict, idx: int) -> dict:
    d = dict(raw)
    d["questionId"] = str(d.get("questionId") or f"ai-q-{idx}")
    d["questionNumber"] = str(d.get("questionNumber") or idx)
    d["questionText"] = str(d.get("questionText") or "")
    d["studentAnswer"] = str(d.get("studentAnswer") or "")
    d["correctAnswer"] = str(d.get("correctAnswer") or "")
    d["teacherFeedback"] = str(d.get("teacherFeedback") or "")
    d["conceptId"] = str(d.get("conceptId") or "unknown")
    d["conceptName"] = str(d.get("conceptName") or "Unknown concept")
    d["skill"] = str(d.get("skill") or "")
    d["errorType"] = normalize_scalar(d.get("errorType"), "unknown")
    d["extractionConfidence"] = unit_interval(d.get("extractionConfidence"))
    d["diagnosisConfidence"] = unit_interval(d.get("diagnosisConfidence"))
    d["marksAwarded"] = float(normalize_scalar(d.get("marksAwarded"), 0))
    d["marksPossible"] = float(normalize_scalar(d.get("marksPossible"), 0))
    source = str(normalize_scalar(d.get("marksSource"), "unknown"))
    d["marksSource"] = source if source in {"teacher", "estimated", "unknown"} else "unknown"
    d["gradingConfidence"] = unit_interval(d.get("gradingConfidence"))
    d["needsHumanReview"] = bool(normalize_scalar(d.get("needsHumanReview"), False))
    d["misconceptionTag"] = str(d.get("misconceptionTag") or "other")
    return d

def _render_page_jpeg(page: fitz.Page) -> bytes:
    pix = page.get_pixmap(matrix=fitz.Matrix(1.45, 1.45), alpha=False)
    # JPEG keeps multipart requests reasonably small while preserving handwriting.
    return pix.tobytes("jpeg", jpg_quality=78)

def pdf_to_inputs(data: bytes) -> tuple[str, list[tuple[str, bytes]]]:
    started = time.perf_counter()
    doc = fitz.open(stream=data, filetype="pdf")
    if len(doc) > MAX_PDF_PAGES:
        doc.close()
        raise ValueError(f"PDFs are limited to {MAX_PDF_PAGES} pages per file on the hosted demo. Split the PDF and upload fewer pages.")
    text_parts=[]; images=[]
    for page in doc:
        page_text = page.get_text("text")
        text_parts.append(page_text)
        # Always send a visual rendering. A PDF can have a text layer while the
        # student's handwriting/teacher marks live in the image layer.
        rendered = _render_page_jpeg(page)
        if len(rendered) <= 900_000:
            images.append(("image/jpeg", rendered))
    print(f"PDF_RENDER_END elapsed_ms={(time.perf_counter()-started)*1000:.1f} pages={len(doc)} images={len(images)}", flush=True)
    return "\n".join(text_parts), images

def image_to_input(data: bytes, content_type: str) -> tuple[str, list[tuple[str, bytes]]]:
    started = time.perf_counter()
    # Phone photos of handwritten work often have EXIF rotation, low resolution,
    # uneven lighting and soft pen strokes. Normalize these before multimodal AI.
    with Image.open(io.BytesIO(data)) as src:
        img = ImageOps.exif_transpose(src).convert("RGB")
        max_dim = max(img.width, img.height)
        if max_dim < 1800:
            scale = min(1.8, 1800 / max_dim)
            img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.Resampling.LANCZOS)
        elif max_dim > 2400:
            scale = 2400 / max_dim
            img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.Resampling.LANCZOS)
        img = ImageOps.autocontrast(img, cutoff=1)
        img = ImageEnhance.Sharpness(img).enhance(1.3)
        img = img.filter(ImageFilter.UnsharpMask(radius=1, percent=75, threshold=3))
        quality = 90
        while True:
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality, optimize=True)
            normalized = buf.getvalue()
            if len(normalized) <= 850_000 or quality <= 62:
                break
            quality -= 6
    print(f"IMAGE_PREPROCESS_END elapsed_ms={(time.perf_counter()-started)*1000:.1f} input_bytes={len(data)} output_bytes={len(normalized)}", flush=True)
    return "", [("image/jpeg", normalized)]
