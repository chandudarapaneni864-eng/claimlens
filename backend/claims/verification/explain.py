"""Turn findings into a plain-language verification report."""
from . import llm

WEIGHTS = {"high": 25, "medium": 12, "low": 4}
RECOMMENDATION_LABELS = {
    "approve": "Looks fine to approve",
    "review": "Needs careful review",
    "reject": "Likely to be rejected",
}


def risk(findings):
    score = min(100, sum(WEIGHTS[f["severity"]] for f in findings))
    level = "high" if score >= 50 else "medium" if score >= 20 else "low"
    return score, level


def recommendation(findings):
    if any(f["kind"] == "DUPLICATE" and f["severity"] == "high" for f in findings):
        return "reject"
    if any(f["kind"] == "VIOLATION" and f["title"] == "No policy covers this expense" for f in findings):
        return "reject"
    if any(f["severity"] in ("high", "medium") for f in findings):
        return "review"
    return "approve"


def template_summary(claim, findings, applicable):
    policy_part = (
        "Checked against " + ", ".join(f"{p.code} v{p.version}" for p in applicable) + "."
        if applicable else "No matching policy was found."
    )
    if not findings:
        return f"All checks passed. The documents match the form and the amount is within policy. {policy_part}"
    high = [f for f in findings if f["severity"] == "high"]
    medium = [f for f in findings if f["severity"] == "medium"]
    low = [f for f in findings if f["severity"] == "low"]
    parts = [f"{len(findings)} issue{'s' if len(findings) != 1 else ''} found"]
    counts = []
    if high:
        counts.append(f"{len(high)} serious")
    if medium:
        counts.append(f"{len(medium)} moderate")
    if low:
        counts.append(f"{len(low)} minor")
    parts[0] += f" ({', '.join(counts)})."
    lead = (high or medium or low)[:3]
    parts.append("Most important: " + "; ".join(f["title"].rstrip(".") for f in lead) + ".")
    parts.append(policy_part)
    return " ".join(parts)


def summarise(claim, findings, applicable, retrieved):
    base = template_summary(claim, findings, applicable)
    if not llm.enabled():
        return base
    lines = "\n".join(f"- [{f['severity']}] {f['title']}: {f['explanation']}" for f in findings) or "- none"
    context = "\n\n".join(r["text"] for r in retrieved[:4])
    prompt = (
        "You are assisting an expense claim reviewer. Write a short, neutral summary (max 90 words) of the "
        "verification result for the reviewer. Mention the most important issues first and cite policy codes. "
        "Do not decide approval; only explain.\n\n"
        f"Claim: {claim.get_category_display()} claim of INR {claim.amount} by grade {claim.employee.grade} employee, "
        f"expense date {claim.expense_date}. Title: {claim.title}.\n\nFindings:\n{lines}\n\nRelevant policy text:\n{context}"
    )
    return llm.ask_text(prompt) or base
