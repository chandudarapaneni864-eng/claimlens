import re

MAX_CHARS = 650


def split_into_chunks(text, max_chars=MAX_CHARS):
    """Split policy wording into paragraph-sized chunks for retrieval."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    chunks, current = [], ""
    for para in paragraphs:
        if len(para) > max_chars:
            sentences = re.split(r"(?<=[.!?])\s+", para)
        else:
            sentences = [para]
        for piece in sentences:
            if current and len(current) + len(piece) + 1 > max_chars:
                chunks.append(current.strip())
                current = ""
            current = f"{current}\n{piece}" if current else piece
        if len(current) > max_chars * 0.6:
            chunks.append(current.strip())
            current = ""
    if current.strip():
        chunks.append(current.strip())
    return chunks


def rebuild_chunks(policy):
    from .models import PolicyChunk

    policy.chunks.all().delete()
    header = f"{policy.title} ({policy.code} v{policy.version}, {policy.get_category_display()})"
    PolicyChunk.objects.bulk_create(
        [PolicyChunk(policy=policy, index=i, text=f"{header}\n{chunk}") for i, chunk in enumerate(split_into_chunks(policy.text))]
    )
