"""Document reading (PDF text / OCR) and field extraction.

Pipeline: file -> text (pdfplumber, then Tesseract OCR if installed) -> fields (regex rules,
optionally refined by Gemini). Every field records how it was found so reviewers can trust it.
"""
import hashlib
import logging
import re
from datetime import date, datetime
from pathlib import Path

from django.conf import settings

from . import llm

log = logging.getLogger(__name__)

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}

MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
MONEY = r"(?:₹|rs\.?|inr|\$)?\s*([0-9]{1,3}(?:,[0-9]{2,3})+(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)"
AMOUNT_KEYS = [
    r"grand\s*total", r"total\s*amount\s*(?:paid|payable)?", r"net\s*(?:amount|payable)", r"amount\s*paid",
    r"amount\s*payable", r"total\s*payable", r"total\s*fare", r"bill\s*amount", r"amount\s*debited",
    r"amount", r"total",
]
DATE_PATTERNS = [
    (r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", "ymd"),
    (r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b", "dmy"),
    (r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{2})\b", "dmy2"),
    (r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})[,]?\s+(\d{4})\b", "d_mon_y"),
    (r"\b([A-Za-z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b", "mon_d_y"),
]
CATEGORY_WORDS = {
    "accommodation": ["hotel", "room", "check-in", "check in", "stay", "lodge", "resort", "night"],
    "travel": ["flight", "airline", "boarding", "pnr", "train", "irctc", "cab", "taxi", "uber", "ola", "bus", "fare", "ticket"],
    "food": ["restaurant", "cafe", "food", "meal", "dining", "swiggy", "zomato", "dinner", "lunch", "breakfast"],
    "medical": ["hospital", "clinic", "pharmacy", "medical", "doctor", "patient", "diagnostic", "consultation"],
}
VENDOR_SKIP = re.compile(r"invoice|receipt|bill|tax|gst|date|total|amount|payment|ticket|page|original|copy|statement|transaction", re.I)


# --------------------------------------------------------------------------- text

def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def image_phash(path):
    """Perceptual hash for photos/scans only. Text PDFs are compared by file hash and text similarity,
    because mostly-white pages produce near-identical perceptual hashes."""
    try:
        import imagehash
        from PIL import Image

        ext = Path(path).suffix.lower()
        if ext in IMAGE_EXT:
            return str(imagehash.phash(Image.open(path)))
    except Exception as exc:
        log.info("phash failed for %s: %s", path, exc)
    return ""


def _tesseract():
    try:
        import pytesseract

        if settings.CLAIMS["TESSERACT_CMD"]:
            pytesseract.pytesseract.tesseract_cmd = settings.CLAIMS["TESSERACT_CMD"]
        pytesseract.get_tesseract_version()
        return pytesseract
    except Exception:
        return None


def read_text(path):
    """Return (text, method)."""
    ext = Path(path).suffix.lower()
    if ext == ".txt":
        return Path(path).read_text(encoding="utf-8", errors="ignore"), "text-file"
    if ext == ".pdf":
        import pdfplumber

        with pdfplumber.open(path) as pdf:
            text = "\n".join((page.extract_text() or "") for page in pdf.pages)
            if text.strip():
                return text, "pdf-text"
            ocr = _tesseract()
            if ocr:
                pages = [ocr.image_to_string(p.to_image(resolution=250).original) for p in pdf.pages[:5]]
                return "\n".join(pages), "pdf-ocr"
        return "", "pdf-scanned-no-ocr"
    if ext in IMAGE_EXT:
        ocr = _tesseract()
        if ocr:
            from PIL import Image

            return ocr.image_to_string(Image.open(path)), "image-ocr"
        return "", "image-no-ocr"
    return "", "unsupported"


# ------------------------------------------------------------------------- fields

def _to_number(raw):
    try:
        return float(raw.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def _make_date(kind, groups):
    try:
        if kind == "ymd":
            y, m, d = map(int, groups)
        elif kind == "dmy":
            d, m, y = map(int, groups)
        elif kind == "dmy2":
            d, m, y = int(groups[0]), int(groups[1]), 2000 + int(groups[2])
        elif kind == "d_mon_y":
            d, m, y = int(groups[0]), MONTHS.get(groups[1][:3].lower()), int(groups[2])
        else:
            m, d, y = MONTHS.get(groups[0][:3].lower()), int(groups[1]), int(groups[2])
        if not m:
            return None
        return date(y, m, d)
    except (ValueError, TypeError):
        return None


def find_dates(line):
    found = []
    for pattern, kind in DATE_PATTERNS:
        for match in re.finditer(pattern, line):
            parsed = _make_date(kind, match.groups())
            if parsed and 2000 <= parsed.year <= 2100:
                found.append(parsed)
    return found


def _amount(lines):
    for key in AMOUNT_KEYS:
        rx = re.compile(key, re.I)
        for line in reversed(lines):  # totals usually sit at the bottom
            if rx.search(line) and not re.search(r"sub\s*total|tax\s*amount|gst\s*amount|discount", line, re.I):
                numbers = [_to_number(n) for n in re.findall(MONEY, line, re.I)]
                numbers = [n for n in numbers if n and n >= 1]
                if numbers:
                    return numbers[-1], line.strip()
    currency_values = [_to_number(n) for n in re.findall(r"(?:₹|rs\.?|inr)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)", "\n".join(lines), re.I)]
    currency_values = [n for n in currency_values if n]
    if currency_values:
        return max(currency_values), "largest currency value"
    return None, ""


def _labelled(lines, label_rx, value_rx):
    rx = re.compile(rf"(?:{label_rx})\s*[:#\-]?\s*({value_rx})", re.I)
    for line in lines:
        m = rx.search(line)
        if m:
            return m.group(1).strip(), line.strip()
    return None, ""


def parse_fields(text):
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    fields, sources = {}, {}

    amount, src = _amount(lines)
    if amount is not None:
        fields["amount"], sources["amount"] = amount, src

    inv, src = _labelled(
        lines,
        r"invoice\s*(?:no\.?|number|#)|bill\s*(?:no\.?|number|#)|receipt\s*(?:no\.?|number|#)|ticket\s*(?:no\.?|number)|booking\s*(?:id|ref(?:erence)?)|pnr(?:\s*no\.?)?|folio\s*(?:no\.?)",
        r"[A-Z0-9][A-Z0-9\-/]{3,}",
    )
    if inv and re.search(r"\d", inv):
        fields["invoice_number"], sources["invoice_number"] = inv.upper(), src

    txn, src = _labelled(lines, r"utr(?:\s*no\.?)?|transaction\s*(?:id|no\.?|ref)|txn\s*(?:id|no\.?)|upi\s*ref(?:\s*no\.?)?|reference\s*(?:no\.?|number)", r"[A-Z0-9]{6,}")
    if txn:
        fields["transaction_id"], sources["transaction_id"] = txn.upper(), src

    name, src = _labelled(
        lines,
        r"employee\s*name|guest\s*name|passenger\s*name|patient\s*name|customer\s*name|billed\s*to|guest|passenger|patient|name",
        r"[A-Za-z][A-Za-z .]{2,40}?(?=\s{2,}|\s*$|\s+(?:room|seat|age|date|emp|id)\b)",
    )
    if name:
        fields["employee_name"], sources["employee_name"] = re.sub(r"^(mr|mrs|ms|dr)\.?\s+", "", name, flags=re.I).title(), src

    vendor, src = _labelled(lines, r"paid\s*to|merchant|vendor|hotel\s*name|hospital\s*name|restaurant|airline|sold\s*by", r"[A-Za-z0-9][A-Za-z0-9 &.,'\-]{2,60}")
    if not vendor:
        for line in lines[:6]:
            if len(line) > 3 and not VENDOR_SKIP.search(line) and sum(ch.isalpha() for ch in line) > len(line) * 0.6:
                vendor, src = line, "document heading"
                break
    if vendor:
        fields["vendor"], sources["vendor"] = vendor.strip(" .,-"), src

    gstin = re.search(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b", text or "")
    if gstin:
        fields["gstin"] = gstin.group(0)

    date_line_rx = re.compile(r"invoice\s*date|bill\s*date|date\s*of\s*(?:issue|travel|journey|payment)|travel\s*date|payment\s*date|txn\s*date|\bdate\b", re.I)
    for line in lines:
        if date_line_rx.search(line) and not re.search(r"check", line, re.I):
            ds = find_dates(line)
            if ds:
                fields["date"], sources["date"] = ds[0].isoformat(), line
                break
    for label, key in ((r"check[\s-]*in|arrival", "check_in"), (r"check[\s-]*out|departure\s*date", "check_out")):
        for line in lines:
            if re.search(label, line, re.I):
                ds = find_dates(line)
                if ds:
                    fields[key], sources[key] = ds[0].isoformat(), line
                    break
    if "date" not in fields:
        all_dates = [d for line in lines for d in find_dates(line)]
        if all_dates:
            fields["date"], sources["date"] = all_dates[0].isoformat(), "first date in document"

    lowered = (text or "").lower()
    scores = {cat: sum(lowered.count(w) for w in words) for cat, words in CATEGORY_WORDS.items()}
    best = max(scores, key=scores.get) if scores else None
    if best and scores[best] > 0:
        fields["category"] = best

    fields["_sources"] = sources
    return fields


LLM_PROMPT = """You extract data from an expense document for an employee reimbursement system.
Return only JSON with these keys (use null when absent):
employee_name, invoice_number, date (YYYY-MM-DD), vendor, amount (number, final total paid),
category (one of travel, accommodation, food, medical, other), transaction_id, check_in (YYYY-MM-DD), check_out (YYYY-MM-DD).

Document text:
---
{text}
---"""


def extract_document(doc):
    """Populate a ClaimDocument with text, fields, hashes. Safe to call repeatedly."""
    path = doc.file.path
    try:
        doc.file_hash = file_sha256(path)
        doc.image_hash = image_phash(path)
        text, method = read_text(path)
        fields = parse_fields(text)
        if text.strip() and llm.enabled():
            ai = llm.ask_json(LLM_PROMPT.format(text=text[:6000]))
            if isinstance(ai, dict):
                for key, value in ai.items():
                    if value not in (None, "", "null"):
                        fields[key] = value
                        fields["_sources"][key] = "Gemini"
                method += "+gemini"
        doc.extracted_text = text[:20000]
        doc.extracted_data = fields
        doc.extraction_method = method
        doc.extraction_status = "done" if text.strip() else "unreadable"
        doc.extraction_error = "" if text.strip() else _unreadable_reason(method)
    except Exception as exc:
        log.exception("Extraction failed for %s", path)
        doc.extraction_status = "failed"
        doc.extraction_error = str(exc)[:250]
    doc.save()
    return doc


def _unreadable_reason(method):
    if method in ("image-no-ocr", "pdf-scanned-no-ocr"):
        return "This is an image or scanned file and OCR (Tesseract) is not installed on the server."
    if method == "unsupported":
        return "File type is not supported for extraction."
    return "No text could be read from this file."


def parse_iso(value):
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
