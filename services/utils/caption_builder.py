## services/utils/caption_builder.py

from typing import Optional, List


def build_job_caption(
    position: Optional[str] = None,
    emails: Optional[List[str]] = None,
    gender_required: Optional[str] = None,
) -> str:
    """
    Build structured job vacancy caption for social media posting.
    
    Shared across Instagram and Facebook clients to ensure
    consistent caption formatting.
    
    Args:
        position: Job position title
        emails: List of contact emails
        gender_required: Gender requirement if any
        
    Returns:
        Formatted caption string
    """
    lines: list[str] = ["📢 INFO LOWONGAN KERJA", ""]

    if position:
        lines.append(f"🔹 Posisi: {position}")

    if gender_required:
        lines.append(f"🔹 Gender: {gender_required.upper()}")

    if emails:
        lines.append("")
        lines.append("📧 Kirim lamaran ke:")
        for email in emails:
            lines.append(f"  • {email}")

    lines.append("")
    lines.append("#lowongankerja #loker #jobvacancy")

    return "\n".join(lines)
