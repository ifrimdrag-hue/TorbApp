"""Unit tests for the shared PPT layout primitive."""
import sys
import os

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app'))

from exports import ppt_export  # noqa: E402


def _tables():
    return [
        {'title': 'Clienți', 'left': 0.3, 'width': 6.9,
         'headers': ['Client', 'VN'],
         'rows': [{'Client': 'A', 'VN': '1.000 RON'},
                  {'Client': 'B', 'VN': '2.000 RON'}]},
        {'title': 'Branduri', 'left': 7.4, 'width': 5.6,
         'headers': ['Brand', 'VN'],
         'rows': [{'Brand': 'Basilur', 'VN': '3.000 RON'}]},
    ]


def test_slide_kpi_tables_renders_cards_and_tables():
    prs = ppt_export._prs()
    slide = ppt_export._slide_kpi_tables(
        prs, 'Client: Test', '2026 · Ianuarie',
        [('Val. Netă', '1.000 RON'), ('Marjă Brută %', '20,0%')],
        _tables(),
    )
    graphic_frames = [s for s in slide.shapes if s.has_table]
    assert len(graphic_frames) == 2
    assert graphic_frames[0].table.cell(0, 0).text == 'Client'
    assert graphic_frames[0].table.cell(1, 0).text == 'A'
    texts = [s.text_frame.text for s in slide.shapes if s.has_text_frame]
    assert 'Val. Netă' in texts
    assert '1.000 RON' in texts
    assert 'Clienți' in texts
    assert '2026 · Ianuarie' in texts


def test_slide_kpi_tables_skips_empty_tables():
    prs = ppt_export._prs()
    slide = ppt_export._slide_kpi_tables(
        prs, 'Brand: Gol', '2026', [('Val. Netă', '—')],
        [{'title': 'Clienți', 'left': 0.3, 'width': 6.9,
          'headers': ['Client'], 'rows': []}],
    )
    assert [s for s in slide.shapes if s.has_table] == []
    assert 'Clienți' not in [s.text_frame.text for s in slide.shapes if s.has_text_frame]


def test_slide_kpi_tables_caps_at_four_cards():
    prs = ppt_export._prs()
    slide = ppt_export._slide_kpi_tables(
        prs, 'X', 'Y',
        [('A', '1'), ('B', '2'), ('C', '3'), ('D', '4'), ('E', '5')], [])
    texts = [s.text_frame.text for s in slide.shapes if s.has_text_frame]
    assert 'D' in texts
    assert 'E' not in texts


def test_public_formatters_are_exported():
    assert ppt_export.fmt_ron(1500) == '1.500 RON'
    assert ppt_export.fmt_ron(None) == '—'
    assert ppt_export.fmt_pct(12.34) == '12.3%'
    assert ppt_export.fmt_pct(None) == '—'


def test_trend_slide_accepts_custom_title():
    prs = ppt_export._prs()
    slide = ppt_export._slide_chart_trend(
        prs, 2026, {2026: [1] * 12}, title='Trend — Basilur')
    texts = [s.text_frame.text for s in slide.shapes if s.has_text_frame]
    assert 'Trend — Basilur' in texts
