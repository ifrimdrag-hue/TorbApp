"""Orchestrator export sedinta — genereaza PPTX + DOCX + XLSX si le impacheteaza in ZIP."""

import zipfile
from datetime import date
from io import BytesIO
from typing import NamedTuple

from .pptx_builder import build_pptx
from .docx_builder import build_docx
from .xlsx_builder import build_xlsx


class ExportBundle(NamedTuple):
    zip_bytes: bytes
    pptx_filename: str
    docx_filename: str
    xlsx_filename: str
    zip_filename: str
    summary: dict


def _slug_today() -> str:
    return date.today().strftime("%Y-%m-%d")


def build_export_bundle(campaigns: list[dict]) -> ExportBundle:
    """Construieste cele 3 fisiere si le impacheteaza intr-un ZIP."""
    today = _slug_today()
    _month = date.today().strftime("%Y-%m")
    pptx_name = f"Plan-Campanii-{_month}__{today}.pptx"
    docx_name = f"Brief-Sedinta-{_month}__{today}.docx"
    xlsx_name = f"Tracker-Operational-{_month}__{today}.xlsx"
    zip_name = f"Export-Sedinta-Campanii-{_month}__{today}.zip"

    pptx_bytes = build_pptx(campaigns)
    docx_bytes = build_docx(campaigns)
    xlsx_bytes = build_xlsx(campaigns)

    zip_buf = BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(pptx_name, pptx_bytes)
        zf.writestr(docx_name, docx_bytes)
        zf.writestr(xlsx_name, xlsx_bytes)
        # README mic in zip
        readme = (
            f"Export pentru sedinta — {today}\n"
            f"=" * 50 + "\n\n"
            "1. PowerPoint (.pptx) — pentru proiectie pe ecran in sedinta\n"
            "   12 slide-uri: context, 3 campanii detaliate, buget, calendar,\n"
            "   KPI, riscuri, asks pentru director.\n\n"
            "2. Word (.docx) — handout pentru director\n"
            "   Brief executiv structurat. Tipareste 1-2 copii pentru masa.\n\n"
            "3. Excel (.xlsx) — tracker operational\n"
            "   5 sheet-uri: sumar buget, detalii campanii, task-uri,\n"
            "   KPI tracker (de actualizat saptamanal), riscuri.\n\n"
            f"Total campanii: {len(campaigns)}\n"
            f"Buget total alocat: {sum(c.get('budget_alloc') or 0 for c in campaigns):.0f} RON\n"
        )
        zf.writestr("README.txt", readme)

    summary = {
        "campaigns": len(campaigns),
        "total_budget": sum(c.get("budget_alloc") or 0 for c in campaigns),
        "files": [pptx_name, docx_name, xlsx_name, "README.txt"],
        "zip_size_kb": round(len(zip_buf.getvalue()) / 1024, 1),
    }

    return ExportBundle(
        zip_bytes=zip_buf.getvalue(),
        pptx_filename=pptx_name,
        docx_filename=docx_name,
        xlsx_filename=xlsx_name,
        zip_filename=zip_name,
        summary=summary,
    )
