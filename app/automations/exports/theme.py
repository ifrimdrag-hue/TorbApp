"""Tema corporate sobra — folosita in toate cele 3 export-uri (PPTX/DOCX/XLSX).

Paleta: Midnight Executive
- Navy puternic pentru titluri si accente principale
- Albastru deschis pentru charts si highlights secundare
- Gri inchis pentru text body
- Alb si gri foarte deschis pentru fundaluri
"""

# Hex strings (folosibile direct in openpyxl si docx)
NAVY = "1E2761"
LIGHT_BLUE = "5B9BD5"
DARK_GRAY = "404040"
MID_GRAY = "808080"
LIGHT_GRAY = "F5F5F5"
WHITE = "FFFFFF"
BLACK = "212121"
SUCCESS = "2E7D32"
WARN = "C77700"
DANGER = "C62828"

# Fonts
FONT_TITLE = "Cambria"
FONT_BODY = "Calibri"


def hex_to_rgb_tuple(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
