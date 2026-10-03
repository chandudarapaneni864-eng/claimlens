"""A tiny dependency-free PDF writer used to generate realistic sample bills for the demo.
Text is real (not an image), so it can be read by pdfplumber without OCR."""


def _esc(text):
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").encode("latin-1", "replace").decode("latin-1")


def write_pdf(path, blocks):
    """blocks: list of (style, text). style in {'h1','h2','text','small','rule','gap','row'}.
    'row' text is a tuple (left, right) printed on one line with the value right-aligned."""
    y = 800
    ops = []
    for style, text in blocks:
        if style == "gap":
            y -= 10
            continue
        if style == "rule":
            ops.append(f"0.75 w 50 {y + 4} m 545 {y + 4} l S")
            y -= 12
            continue
        if style == "row":
            left, right = text
            ops.append(f"BT /F1 10.5 Tf 50 {y} Td ({_esc(left)}) Tj ET")
            ops.append(f"BT /F1 10.5 Tf {545 - len(right) * 5.6:.1f} {y} Td ({_esc(right)}) Tj ET")
            y -= 16
            continue
        font, size, lead = {"h1": ("F2", 18, 26), "h2": ("F2", 12, 18), "text": ("F1", 10.5, 15), "small": ("F1", 8.5, 12)}[style]
        ops.append(f"BT /{font} {size} Tf 50 {y} Td ({_esc(text)}) Tj ET")
        y -= lead
    stream = "\n".join(ops).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 6 0 R /Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    with open(path, "wb") as fh:
        fh.write(out)
    return path
