from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

FONT_NAME = "NanumGothic"
FONT_PATH = Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf")

TEXT = colors.HexColor("#2F2F2F")
SUBTEXT = colors.HexColor("#6E6E6E")
BORDER = colors.HexColor("#D9D9D9")
LINE = colors.HexColor("#E9E9E9")
BG = colors.HexColor("#F7F8F7")
CARD = colors.white

PRIMARY = colors.HexColor("#6EDC5A")
PRIMARY_DARK = colors.HexColor("#34B233")
PRIMARY_LIGHT = colors.HexColor("#EAF8E6")

DANGER = colors.HexColor("#FF6B5E")
DANGER_LIGHT = colors.HexColor("#FFE9E6")
CAUTION = colors.HexColor("#F4BE41")
CAUTION_LIGHT = colors.HexColor("#FFF5DE")
SAFE = colors.HexColor("#39B54A")
SAFE_LIGHT = colors.HexColor("#EAF8E6")
UNKNOWN = colors.HexColor("#B6B6B6")
UNKNOWN_LIGHT = colors.HexColor("#F1F1F1")

RISK_COLORS = {
    "DANGER": DANGER,
    "CAUTION": CAUTION,
    "SAFE": SAFE,
    "UNKNOWN": UNKNOWN,
}

RISK_BG_COLORS = {
    "DANGER": DANGER_LIGHT,
    "CAUTION": CAUTION_LIGHT,
    "SAFE": SAFE_LIGHT,
    "UNKNOWN": UNKNOWN_LIGHT,
}

RISK_LABELS = {
    "DANGER": "위험",
    "CAUTION": "주의",
    "SAFE": "안정",
    "UNKNOWN": "미확인",
}


def register_pdf_font():
    if FONT_NAME not in pdfmetrics.getRegisteredFontNames():
        if not FONT_PATH.is_file():
            raise RuntimeError(
                f"한글 폰트를 찾을 수 없습니다: {FONT_PATH}"
            )

        pdfmetrics.registerFont(
            TTFont(FONT_NAME, str(FONT_PATH))
        )


def pdf_text(value):
    return escape(str(value if value is not None else "-"))


def format_number(value):
    if value is None:
        return "-"

    number = float(value)
    if number.is_integer():
        return f"{number:,.0f}"
    return f"{number:,.1f}"


def format_date(value):
    if value is None:
        return "-"
    return value.strftime("%Y.%m.%d")


def format_datetime(value):
    if value is None:
        return "-"
    return value.strftime("%Y.%m.%d %H:%M")


def footer(canvas, document):
    canvas.saveState()

    width, _ = landscape(A4)

    canvas.setStrokeColor(LINE)
    canvas.line(16 * mm, 12 * mm, width - 16 * mm, 12 * mm)

    canvas.setFont(FONT_NAME, 8)
    canvas.setFillColor(SUBTEXT)
    canvas.drawString(16 * mm, 7 * mm, "IEUM Simulation Report")
    canvas.drawRightString(width - 16 * mm, 7 * mm, str(document.page))

    canvas.restoreState()


def build_styles():
    return {
        "title": ParagraphStyle(
            "Title",
            fontName=FONT_NAME,
            fontSize=18,
            leading=24,
            textColor=TEXT,
            alignment=TA_LEFT,
            spaceAfter=4,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle",
            fontName=FONT_NAME,
            fontSize=9,
            leading=14,
            textColor=SUBTEXT,
            spaceAfter=10,
        ),
        "section": ParagraphStyle(
            "Section",
            fontName=FONT_NAME,
            fontSize=12,
            leading=18,
            textColor=TEXT,
            spaceBefore=10,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "Body",
            fontName=FONT_NAME,
            fontSize=9,
            leading=14,
            textColor=TEXT,
        ),
        "small": ParagraphStyle(
            "Small",
            fontName=FONT_NAME,
            fontSize=8,
            leading=12,
            textColor=SUBTEXT,
        ),
        "cell": ParagraphStyle(
            "Cell",
            fontName=FONT_NAME,
            fontSize=8,
            leading=12,
            textColor=TEXT,
            wordWrap="CJK",
        ),
        "cell_center": ParagraphStyle(
            "CellCenter",
            fontName=FONT_NAME,
            fontSize=8,
            leading=12,
            textColor=TEXT,
            alignment=TA_CENTER,
            wordWrap="CJK",
        ),
        "header_cell": ParagraphStyle(
            "HeaderCell",
            fontName=FONT_NAME,
            fontSize=8,
            leading=12,
            textColor=SUBTEXT,
            alignment=TA_CENTER,
            wordWrap="CJK",
        ),
        "metric_label": ParagraphStyle(
            "MetricLabel",
            fontName=FONT_NAME,
            fontSize=8,
            leading=12,
            textColor=SUBTEXT,
            alignment=TA_CENTER,
        ),
        "metric_value": ParagraphStyle(
            "MetricValue",
            fontName=FONT_NAME,
            fontSize=20,
            leading=24,
            textColor=TEXT,
            alignment=TA_CENTER,
        ),
        "metric_hint": ParagraphStyle(
            "MetricHint",
            fontName=FONT_NAME,
            fontSize=8,
            leading=11,
            textColor=SUBTEXT,
            alignment=TA_CENTER,
        ),
    }


def make_paragraph(value, style):
    return Paragraph(pdf_text(value), style)


def make_info_table(rows, widths):
    table = Table(rows, colWidths=widths, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CARD),
        ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return table


def make_metric_card(label, value, hint, color, styles):
    value_style = ParagraphStyle(
        f"MetricValue_{label}",
        parent=styles["metric_value"],
        textColor=color,
    )

    table = Table(
        [
            [Paragraph(pdf_text(label), styles["metric_label"])],
            [Paragraph(pdf_text(value), value_style)],
            [Paragraph(pdf_text(hint), styles["metric_hint"])],
        ],
        colWidths=[78 * mm],
    )

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CARD),
        ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
        ("LINEABOVE", (0, 0), (-1, 0), 2.5, color),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))

    return table


def risk_text(level):
    return RISK_LABELS.get(level, level or "-")


def make_risk_paragraph(level, styles, center=False):
    base = styles["cell_center"] if center else styles["cell"]

    risk_style = ParagraphStyle(
        f"Risk_{level}_{id(base)}",
        parent=base,
        textColor=RISK_COLORS.get(level, UNKNOWN),
    )

    return Paragraph(pdf_text(risk_text(level)), risk_style)


def make_stop_table(stop_rows):
    table = Table(
        stop_rows,
        colWidths=[
            42 * mm,  # 정류소명
            19 * mm,  # 중단 전
            19 * mm,  # 중단 후
            19 * mm,  # 남은 노선
            19 * mm,  # 대체 노선
            23 * mm,  # 추정 영향
            15 * mm,  # 고립
            95 * mm,  # 분석 근거
        ],
        repeatRows=1,
        hAlign="LEFT",
    )

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BG),
        ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BG]),
    ]))

    return table


def build_simulation_pdf(simulation, routes, summary, stops):
    register_pdf_font()
    styles = build_styles()

    routes = list(routes)
    stops = list(stops)

    buffer = BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
    )

    elements = []

    analysis = simulation.baseline_analysis
    route_names = ", ".join(
        change.route.route_number for change in routes
    ) or "-"

    # 제목 영역
    elements.append(
        Paragraph("노선 운행 중단 시뮬레이션 보고서", styles["title"])
    )
    elements.append(
        Paragraph(
            "이음 서비스의 시뮬레이션 결과를 기반으로 생성된 분석 보고서입니다.",
            styles["subtitle"],
        )
    )

    # 1. 기본 정보
    elements.append(Paragraph("1. 기본 정보", styles["section"]))

    basic_rows = [
        [
            make_paragraph("시뮬레이션 ID", styles["small"]),
            make_paragraph(simulation.pk, styles["body"]),
            make_paragraph("실행 상태", styles["small"]),
            make_paragraph(simulation.status, styles["body"]),
        ],
        [
            make_paragraph("제목", styles["small"]),
            make_paragraph(simulation.title, styles["body"]),
            make_paragraph("실행 일시", styles["small"]),
            make_paragraph(format_datetime(simulation.created_at), styles["body"]),
        ],
        [
            make_paragraph("중단 노선", styles["small"]),
            make_paragraph(route_names, styles["body"]),
            make_paragraph("분석 기준 기간", styles["small"]),
            make_paragraph(
                f"{format_date(analysis.period_start)} ~ {format_date(analysis.period_end)}",
                styles["body"],
            ),
        ],
    ]

    elements.append(
        make_info_table(
            basic_rows,
            [28 * mm, 104 * mm, 28 * mm, 105 * mm],
        )
    )
    elements.append(Spacer(1, 8 * mm))

    # 2. 요약
    elements.append(Paragraph("2. 분석 결과 요약", styles["section"]))

    danger_stop_count = (
        summary.get("danger_stop_count")
        if summary is not None else "-"
    )
    caution_stop_count = (
        summary.get("caution_stop_count")
        if summary is not None else "-"
    )
    estimated_affected_daily = (
        summary.get("estimated_affected_daily")
        if summary is not None else None
    )

    metric_table = Table(
        [[
            make_metric_card(
                "빨간불",
                f"{danger_stop_count}곳",
                "중단 후 위험 정류소",
                DANGER,
                styles,
            ),
            make_metric_card(
                "노란불",
                f"{caution_stop_count}곳",
                "중단 후 주의 정류소",
                CAUTION,
                styles,
            ),
            make_metric_card(
                "영향 승차",
                f"{format_number(estimated_affected_daily)}명/일",
                "추정 일평균 영향 규모",
                PRIMARY_DARK,
                styles,
            ),
        ]],
        colWidths=[84 * mm, 84 * mm, 84 * mm],
    )
    metric_table.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    elements.append(metric_table)
    elements.append(Spacer(1, 8 * mm))

    # 3. 정류소별 결과
    elements.append(Paragraph("3. 정류소별 분석 결과", styles["section"]))
    elements.append(
        Paragraph(
            "위험도 변경 여부와 변경 후 위험도를 기준으로 정렬된 결과입니다.",
            styles["small"],
        )
    )
    elements.append(Spacer(1, 3 * mm))

    stop_rows = [[
        make_paragraph("정류소명", styles["header_cell"]),
        make_paragraph("중단 전", styles["header_cell"]),
        make_paragraph("중단 후", styles["header_cell"]),
        make_paragraph("남은 노선", styles["header_cell"]),
        make_paragraph("대체 노선", styles["header_cell"]),
        make_paragraph("추정 영향", styles["header_cell"]),
        make_paragraph("고립", styles["header_cell"]),
        make_paragraph("분석 근거", styles["header_cell"]),
    ]]

    if not stops:
        stop_rows.append([
            make_paragraph("분석 결과가 없습니다.", styles["cell"]),
            make_paragraph("-", styles["cell_center"]),
            make_paragraph("-", styles["cell_center"]),
            make_paragraph("-", styles["cell_center"]),
            make_paragraph("-", styles["cell_center"]),
            make_paragraph("-", styles["cell_center"]),
            make_paragraph("-", styles["cell_center"]),
            make_paragraph("-", styles["cell"]),
        ])
    else:
        for result in stops:
            stop_rows.append([
                make_paragraph(result.stop.name, styles["cell"]),
                make_risk_paragraph(result.before_risk_level, styles, center=True),
                make_risk_paragraph(result.after_risk_level, styles, center=True),
                make_paragraph(result.remaining_route_count, styles["cell_center"]),
                make_paragraph(result.after_min_alternatives, styles["cell_center"]),
                make_paragraph(
                    format_number(result.estimated_affected_daily),
                    styles["cell_center"],
                ),
                make_paragraph(
                    "예" if result.is_isolated else "아니요",
                    styles["cell_center"],
                ),
                make_paragraph(result.reason, styles["cell"]),
            ])

    stop_table = make_stop_table(stop_rows)
    elements.append(stop_table)

    elements.append(Spacer(1, 6 * mm))
    elements.append(
        Paragraph(
            "※ 예상 영향 인원은 평균 승차량과 중단 노선 비율을 기반으로 계산한 추정값입니다.",
            styles["small"],
        )
    )

    document.build(
        elements,
        onFirstPage=footer,
        onLaterPages=footer,
    )

    return buffer.getvalue()