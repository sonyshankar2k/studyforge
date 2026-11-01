"""Generates samples/BREATHE-2_protocol_synopsis.pdf, a short FICTIONAL protocol synopsis
for demos and tests.   Run:  cd api && uv run python ../samples/make_sample_protocol.py
"""

from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

OUT = Path(__file__).with_name("BREATHE-2_protocol_synopsis.pdf")

SECTIONS = [
    ("title", "Protocol Synopsis: BREATHE-2 (FICTIONAL, for demonstration only)"),
    ("body", "A Phase 3, Randomized, Double-Blind, Placebo- and Active-Controlled Study "
             "of SF-202 in Adults with Moderate Persistent Asthma"),
    ("h", "1. Study Design"),
    ("body", "Participants will be randomized 2:2:1 to one of three treatment groups for "
             "24 weeks, followed by a 4-week safety follow-up."),
    ("h", "2. Treatment Arms"),
    ("line", "Arm A: SF-202 20 mg once daily (N=200)"),
    ("line", "Arm B: Active comparator fluticasone 250 mcg twice daily (N=200)"),
    ("line", "Arm C: Matching placebo once daily (N=100)"),
    ("h", "3. Objectives and Endpoints"),
    ("line", "Primary objective: Evaluate the efficacy of SF-202 compared with placebo"),
    ("line", "Endpoint: Change from baseline in pre-bronchodilator FEV1 at Week 24"),
    ("line", "Secondary objective: Compare SF-202 with the active comparator on asthma control"),
    ("line", "Endpoint: Change from baseline in ACQ-5 score at Week 24"),
    ("line", "Secondary objective: Evaluate the safety and tolerability of SF-202"),
    ("line", "Endpoint: Incidence of treatment-emergent adverse events through Week 28"),
    ("line", "Exploratory objective: Explore the effect of SF-202 on airway inflammation"),
    ("line", "Endpoint: Change from baseline in FeNO at Weeks 12 and 24"),
    ("h", "4. Key Eligibility Criteria"),
    ("body", "Adults aged 18 to 75 with a physician diagnosis of asthma for at least 12 months, "
             "pre-bronchodilator FEV1 between 50% and 85% of predicted, and an ACQ-5 score of "
             "1.5 or higher at screening. Current smokers are excluded."),
]


def main() -> None:
    styles = getSampleStyleSheet()
    style = {"title": styles["Title"], "h": styles["Heading2"],
             "body": styles["BodyText"], "line": styles["BodyText"]}
    story = []
    for kind, text in SECTIONS:
        story.append(Paragraph(text, style[kind]))
        story.append(Spacer(1, 4))
    SimpleDocTemplate(str(OUT), pagesize=LETTER, title="BREATHE-2 protocol synopsis").build(story)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
