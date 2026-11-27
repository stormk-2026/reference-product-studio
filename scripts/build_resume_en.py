"""Build the public English resume PDF. Run with ReportLab installed."""

from pathlib import Path
from xml.sax.saxutils import escape

import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate

OUTPUT = (
    Path(__file__).resolve().parents[1] / "src/studio/web/static/portfolio/stormg-resume-en.pdf"
)
SITE = "https://stormstudio.top"
NAME = "Huikang Guo"

EXPERIENCE = [
    (
        "Independent / Remote Projects",
        "Mobile & Full-Stack Developer",
        "Oct 2025 - Present",
        "Build and ship mobile apps, AI tools, remote device controls, and a Farcaster mini app. "
        "Work with distributed teams on cross-platform architecture, messaging, real-time media, "
        "Web3 wallet flows, and backend deployment.",
    ),
    (
        "Hangzhou Shengmai Communications Technology Co., Ltd.",
        "Mobile Engineer",
        "Jun 2019 - Oct 2025",
        "Led mobile development for IPTV/OTT products across education, entertainment, and social "
        "features. Adapted, released, and supported apps for regional operators. Optimized memory, "
        "rendering, and lists on resource-constrained set-top boxes and introduced Flutter for new projects.",
    ),
    (
        "Tianjin Xingyu Weiye Technology Co., Ltd.",
        "Android Developer",
        "Nov 2018 - Jun 2019",
        "Owned core Android development, coordinated client releases, and evaluated technical options "
        "through prototypes and load testing.",
    ),
    (
        "Tianjin Tuohai Technology Co., Ltd.",
        "Android Developer",
        "Jun 2016 - Nov 2018",
        "Developed Android features for commerce, payments, messaging, enterprise operations, "
        "and digital asset products.",
    ),
]

SKILLS = [
    ("Mobile", "Android, Kotlin, Java, Flutter, Dart, GetX, Riverpod, Cocos, TypeScript"),
    (
        "Real-time & Web3",
        "OpenIM, Tencent TRTC, rich messages, offline push, wallet signatures, Farcaster",
    ),
    (
        "Backend & delivery",
        "Python, FastAPI, Linux, CI/CD, HTTPS, OSS, tenant isolation, rate limiting",
    ),
    ("AI & devices", "Kimi, Seedream, OpenClaw, agent tools, IPTV/OTT, infrared and LAN control"),
    (
        "Release & attribution",
        "Google Play, operator distribution, PWA, Adjust, AppsFlyer, deep links",
    ),
]

PROJECTS = [
    (
        "visual-workbench",
        "AI Visual Workbench",
        "Independent developer | 2026 - Present",
        "Built workflows for product imagery, reference scenes, and draft technical illustrations. "
        "Integrated Kimi and Seedream with review steps, usage limits, and private asset storage.",
    ),
    (
        "daqian",
        "Daqian Travel Preparation Assistant",
        "Independent developer | Nov 2026 | Xiaohongshu mini tool",
        "Built destination search over an offline policy dataset, source attribution, and trip checklists. "
        "Adapted the mobile UI and local storage and photo APIs for the Xiaohongshu container.",
    ),
    (
        "flow",
        "Flow",
        "Independent developer | May - Jul 2026 | Google Play",
        "Designed and shipped a focus timer and journal with session history, a Flutter client, "
        "and a Python API.",
    ),
    (
        "seek",
        "Seek",
        "Independent developer",
        "Built a personal map for saving locations with photos, notes, and coordinates, with local drafts.",
    ),
    (
        "trundertrack",
        "Trundertrack",
        "Independent developer | Aug 2025 - Feb 2026",
        "Built a Farcaster mini app for trade journaling, analytics, and sharing. Improved "
        "client-side streaming and long-list rendering.",
    ),
    (
        "okchat",
        "OkChat",
        "Mobile engineer | Jul 2026 - Present | Google Play",
        "Led TRTC integration and tuning on both mobile platforms. Integrated OpenIM messaging, "
        "offline push and state sync, plus wallet sign-in and on-chain interactions.",
    ),
    (
        "hangmaguan",
        "Hangmaguan",
        "Android / Cocos developer | Aug 2024 - Oct 2025 | App Store",
        "Led the game lobby and feature pages in Cocos and TypeScript. Built the bridge to Android "
        "for navigation and data synchronization.",
    ),
    (
        "remote-control",
        "Distributed Set-Top Box Control",
        "Independent developer | Feb - Jun 2026",
        "Exposed Android, infrared, and LAN controls as agent tools for remote operation and signal "
        "monitoring. Built diagnostics and recovery for asynchronous workflows.",
    ),
    (
        "xinxi",
        "Xinxi",
        "Flutter developer | May - Aug 2026",
        "Built the Android and iOS architecture with GetX and led core messaging UI and state sync. "
        "Worked with the backend team on AI matching and chat interactions.",
    ),
    (
        "igaming",
        "International Casual Gaming Platform",
        "Mobile developer | Jan - Oct 2025",
        "Implemented release variants, remote configuration, PWA delivery, attribution and deep links. "
        "Improved connection reliability on low-end devices and weak networks.",
    ),
    (
        "tv-suite",
        "IPTV/OTT Application Suite",
        "Core developer | Jun 2019 - Oct 2025",
        "Adapted billing and playback to operator specs, rebuilt remote-control navigation, "
        "and tuned UI and memory performance on low-power set-top boxes.",
    ),
]


def build_resume(output: Path) -> None:
    font_root = Path(reportlab.__file__).parent / "fonts"
    pdfmetrics.registerFont(TTFont("Resume Sans", str(font_root / "Vera.ttf")))
    pdfmetrics.registerFont(TTFont("Resume Sans Bold", str(font_root / "VeraBd.ttf")))
    pdfmetrics.registerFontFamily("Resume Sans", normal="Resume Sans", bold="Resume Sans Bold")
    ink = colors.HexColor("#22342F")
    muted = colors.HexColor("#4E6058")
    accent = colors.HexColor("#276348")
    body = ParagraphStyle(
        "Body",
        fontName="Resume Sans",
        fontSize=9.5,
        leading=13.1,
        textColor=ink,
        alignment=TA_LEFT,
        spaceAfter=5,
    )
    title = ParagraphStyle(
        "Name", parent=body, fontName="Resume Sans Bold", fontSize=28, leading=33, spaceAfter=5
    )
    section = ParagraphStyle(
        "Section",
        parent=body,
        fontName="Resume Sans Bold",
        fontSize=13,
        leading=17,
        textColor=accent,
        spaceBefore=13,
        spaceAfter=6,
        keepWithNext=True,
    )
    entry = ParagraphStyle(
        "Entry", parent=body, fontName="Resume Sans Bold", fontSize=10.2, leading=13.3, spaceAfter=1
    )
    meta = ParagraphStyle(
        "Meta", parent=body, fontSize=8.8, leading=12, textColor=muted, spaceAfter=2
    )
    contact = ParagraphStyle("Contact", parent=meta, spaceAfter=12)
    document = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        topMargin=39,
        bottomMargin=41,
        leftMargin=47,
        rightMargin=47,
        title=f"{NAME} - Resume",
        author=NAME,
        subject="Android, Flutter, and full-stack development",
        invariant=True,
    )
    flow = [
        Paragraph(NAME, title),
        Paragraph(
            "<b>Android / Flutter Engineer</b> | Mobile, Full-Stack &amp; AI Product Development",
            body,
        ),
        Paragraph(
            'Hangzhou, China | <link href="mailto:gg5605568@gmail.com" color="#276348">'
            'gg5605568@gmail.com</link> | <link href="https://stormstudio.top" color="#276348">'
            'stormstudio.top</link> | <link href="https://github.com/stormk-2026" color="#276348">'
            "github.com/stormk-2026</link>",
            contact,
        ),
        Paragraph("Profile", section),
        Paragraph(
            "Mobile engineer since 2016. Builds native Android and Flutter products and works across "
            "requirements, UI implementation, architecture, testing, and deployment. Experience includes "
            "real-time communication, IPTV/OTT, Web3, and AI tools.",
            body,
        ),
        Paragraph("Professional Experience", section),
    ]
    for company, role, period, description in EXPERIENCE:
        flow.append(
            KeepTogether(
                [
                    Paragraph(escape(company), entry),
                    Paragraph(escape(f"{role} | {period}"), meta),
                    Paragraph(escape(description), body),
                ]
            )
        )
    flow.append(Paragraph("Technical Skills", section))
    for category, skills in SKILLS:
        flow.append(Paragraph(f"<b>{escape(category)}:</b> {escape(skills)}", body))
    flow.extend(
        [
            Paragraph("Education", section),
            Paragraph("Bachelor's degree in Communications Engineering | 2012 - 2016", body),
            Paragraph("Ren'ai College, Tianjin University", meta),
            PageBreak(),
            Paragraph("Projects", section),
        ]
    )
    for slug, name, detail, description in PROJECTS:
        link = f'<link href="{SITE}/projects/{slug}">{escape(name)}</link>'
        flow.append(
            KeepTogether(
                [
                    Paragraph(link, entry),
                    Paragraph(escape(detail), meta),
                    Paragraph(escape(description), body),
                ]
            )
        )

    def footer(canvas, doc):
        canvas.setFont("Resume Sans", 8)
        canvas.setFillColor(muted)
        canvas.drawString(doc.leftMargin, 26, f"{NAME} | stormg")
        canvas.drawRightString(A4[0] - doc.rightMargin, 26, str(doc.page))

    document.build(flow, onFirstPage=footer, onLaterPages=footer)


if __name__ == "__main__":
    build_resume(OUTPUT)
