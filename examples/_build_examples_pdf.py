"""One-off builder for the example-folder note. Not part of the checker."""

from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, Image

OUT = "examples/example-folders.pdf"

# Times is the face the source note is set in. Leading is a little opener than
# a two-column page, because this document is a single column.
BODY = "Times-Roman"
BOLD = "Times-Bold"
ITAL = "Times-Italic"
MONO = "Courier"


def styles():
    body = ParagraphStyle(
        "body",
        fontName=BODY,
        fontSize=11,
        leading=15,
        alignment=TA_JUSTIFY,
        textColor="#1a1a1a",
        spaceAfter=8,
        firstLineIndent=14,
    )
    first = ParagraphStyle("first", parent=body, firstLineIndent=0)
    h = ParagraphStyle(
        "h",
        fontName=BOLD,
        fontSize=12.5,
        leading=16,
        spaceBefore=14,
        spaceAfter=8,
        textColor="#111111",
    )
    caption = ParagraphStyle(
        "caption",
        fontName=BOLD,
        fontSize=9,
        leading=12,
        spaceBefore=10,
        spaceAfter=4,
        alignment=TA_LEFT,
    )
    cell = ParagraphStyle(
        "cell",
        fontName=BODY,
        fontSize=8.5,
        leading=11,
        alignment=TA_LEFT,
    )
    cell_b = ParagraphStyle("cellb", parent=cell, fontName=BOLD)
    code = ParagraphStyle(
        "code",
        fontName=MONO,
        fontSize=8,
        leading=10.5,
        leftIndent=12,
        spaceBefore=1,
        spaceAfter=1,
        textColor="#1a1a1a",
    )
    title = ParagraphStyle(
        "title",
        fontName=BOLD,
        fontSize=16,
        leading=20,
        spaceAfter=4,
        alignment=TA_LEFT,
    )
    dek = ParagraphStyle(
        "dek",
        fontName=ITAL,
        fontSize=11,
        leading=14,
        spaceAfter=12,
        textColor="#333333",
    )
    return {
        "body": body,
        "first": first,
        "h": h,
        "caption": caption,
        "cell": cell,
        "cell_b": cell_b,
        "code": code,
        "title": title,
        "dek": dek,
    }


def P(text, style):
    return Paragraph(text, style)


def ruled(data, widths):
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), BOLD),
                ("FONTNAME", (0, 1), (-1, -1), BODY),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("LEADING", (0, 0), (-1, -1), 11),
                ("TEXTCOLOR", (0, 0), (-1, -1), "#1a1a1a"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LINEABOVE", (0, 0), (-1, 0), 0.8, "#111111"),
                ("LINEBELOW", (0, 0), (-1, 0), 0.4, "#111111"),
                ("LINEBELOW", (0, -1), (-1, -1), 0.8, "#111111"),
                ("BACKGROUND", (0, 0), (-1, 0), "#f4f4f4"),
            ]
        )
    )
    return table


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont(BODY, 9)
    canvas.setFillColor("#444444")
    canvas.drawCentredString(letter[0] / 2, 0.5 * inch, str(doc.page))
    canvas.restoreState()


def build():
    s = styles()
    story = []

    story.append(P("Example folders for the folder check", s["title"]))
    story.append(
        P(
            "The specifications that were written, and the faults that were planted in the code.",
            s["dek"],
        )
    )

    story.append(
        P(
            "Two directories were added under examples so the folder upload can be tried by hand. "
            "Each holds a numbered specification and a Python implementation that only partly obeys it. "
            "The short folder is one module and two rules. The longer folder is a small clinic desk: "
            "twelve rules, five modules, a readme that is not the specification, and a test file the checker is meant to ignore. "
            "The faults were planted. They are not cases in the scored benchmark of eighty-six injections, and a verdict on them is not a measurement.",
            s["first"],
        )
    )

    story.append(P("1. What the checker keeps", s["h"]))
    story.append(
        P(
            "A chosen folder is not checked as a bag of every file inside it. The specification is the shallowest file named spec.md, specification.md, or specs.md. "
            "If none of those names is present, the markdown file that contains the most numbered rules is used instead. "
            "A line counts as a rule only when it is a list item whose rule id is written in bold, as in R01, and then the requirement. Headings are sections. Prose around the rules is not judged.",
            s["first"],
        )
    )
    story.append(
        P(
            "Python under src/ is preferred when that directory exists, because that is the layout of the three host projects and it keeps tests from being read as the implementation. "
            "Files under tests/, virtual environments, and hidden directories are dropped before any rule is checked. "
            "In the short folder the specification is spec.md and the only module is src/counter.py. "
            "In the longer folder the specification is again spec.md; README.md has no numbered rules, so it is not a candidate, and tests/test_schedule.py is skipped.",
            s["body"],
        )
    )

    story.append(P("2. The short folder", s["h"]))
    story.append(
        P(
            "The directory is examples/sample-project. The specification is short enough to quote in full. "
            "It introduces a counter, then states two requirements under the heading Limits.",
            s["first"],
        )
    )
    story.append(P("R01. The starting count MUST be 10.", s["code"]))
    story.append(P("R02. Adding past the maximum MUST raise Overflow.", s["code"]))
    story.append(
        P(
            "The implementation is a single class. START is set to 3, MAX is set to 10, and add raises Overflow once the next value would pass MAX. "
            "The exception named by R02 is therefore present and is actually raised. The constant named by R01 is not. "
            "A comment at the top of the file says that R01 is wrong on purpose; the checker is not supposed to treat that comment as behaviour.",
            s["first"],
        )
    )

    c = s["cell"]
    cb = s["cell_b"]
    story.append(P("Table 1. The short folder, rule by rule.", s["caption"]))
    story.append(
        ruled(
            [
                [P("Rule", cb), P("The specification says", cb), P("The code does", cb), P("Planted", cb)],
                [P("R01", c), P("The starting count must be 10.", c), P("START = 3 in src/counter.py.", c), P("Yes", c)],
                [
                    P("R02", c),
                    P("Adding past the maximum must raise Overflow.", c),
                    P("add raises Overflow when the next value would exceed MAX, and MAX is 10.", c),
                    P("No", c),
                ],
            ],
            [0.55 * inch, 2.15 * inch, 3.4 * inch, 0.7 * inch],
        )
    )
    story.append(Spacer(1, 8))
    story.append(
        P(
            "A check of this folder should come back as drift on R01 and compliant on R02, if the model compares the stated number with the assignment rather than with the comment. "
            "The overall status is then drift, because one accepted drift verdict is enough.",
            s["first"],
        )
    )

    story.append(P("3. The longer folder", s["h"]))
    story.append(
        P(
            "The directory is examples/clinic-desk. It registers patients, books clinician slots, and computes cancellation fees. "
            "The sources are split so that a fault in a constant, a fault in a missing check, and a fault in the order of two writes do not all sit in one function. "
            "limits.py holds the numbers. errors.py holds the exception types, including one that is never raised. models.py holds the records. "
            "schedule.py registers patients and books slots. fees.py computes the money. tests/test_schedule.py exercises registration and is excluded. README.md only points at spec.md.",
            s["first"],
        )
    )
    story.append(
        P(
            "The specification has four sections and twelve rules. Patients: a patient must be at least 16 (R01); registration below that age must raise UnderagePatient (R02); a repeated email must raise DuplicatePatient (R03). "
            "Appointments: a slot must be 30 minutes (R04); a patient must not hold more than 3 appointments on the same calendar day (R05); exceeding that cap must raise DailyLimitExceeded (R06); a taken slot must raise SlotTaken (R07); an unavailable clinician must raise ClinicianUnavailable (R08). "
            "Cancellation and fees: a cancellation inside 24 hours must cost 25.00 (R09); a cancellation at 24 hours or more must cost 0 (R10); the no-show fee must be 40.00 (R11). "
            "Records: the audit entry for a booking must be written only after the slot has been reserved (R12).",
            s["body"],
        )
    )

    story.append(P("Table 2. Faults planted in clinic-desk.", s["caption"]))
    story.append(
        ruled(
            [
                [P("Rule", cb), P("Required", cb), P("Written instead", cb), P("Where", cb)],
                [P("R01", c), P("Age at least 16.", c), P("MIN_AGE = 14.", c), P("limits.py", c)],
                [P("R04", c), P("A slot of 30 minutes.", c), P("SLOT_MINUTES = 45.", c), P("limits.py", c)],
                [P("R05", c), P("At most 3 appointments in a day.", c), P("MAX_PER_DAY = 5.", c), P("limits.py", c)],
                [
                    P("R08", c),
                    P("Refuse an unavailable clinician with ClinicianUnavailable.", c),
                    P("The exception is defined and never raised. book() does not read clinician.available.", c),
                    P("schedule.py", c),
                ],
                [P("R09", c), P("A late cancellation costs 25.00.", c), P("LATE_CANCEL_FEE = 10.00.", c), P("limits.py, used by fees.py", c)],
                [
                    P("R12", c),
                    P("Write the audit entry after the slot is reserved.", c),
                    P("The audit list is appended, and only then is the appointment stored.", c),
                    P("schedule.py", c),
                ],
            ],
            [0.5 * inch, 1.9 * inch, 3.15 * inch, 1.55 * inch],
        )
    )
    story.append(Spacer(1, 8))

    story.append(
        P(
            "Six rules were left in agreement with the code, so a report that flags everything is wrong in a different way. "
            "R02 raises UnderagePatient, R03 raises DuplicatePatient, R06 raises DailyLimitExceeded, and R07 raises SlotTaken. "
            "R10 returns the early-cancel fee of 0 when the cancellation is outside the 24-hour window. R11 returns the no-show fee of 40.00.",
            s["first"],
        )
    )
    story.append(
        P(
            "Two of the planted faults are easy to misread, which is why they were written this way. "
            "R02 names an exception the code does raise, but the age it treats as underage is 14, so a fifteen-year-old is accepted. The value fault is R01; R02 can look compliant if the reader only checks that the name UnderagePatient appears beside a raise. "
            "R06 is the same shape: DailyLimitExceeded is raised, against a cap of five rather than three, and the value fault is R05. "
            "R08 is an omitted check rather than a wrong constant. Putting the unused class in errors.py means a search for the word ClinicianUnavailable succeeds in a file that does not decide bookings. "
            "R12 is an ordering fault. Both writes exist. The audit entry is the first of them:",
            s["body"],
        )
    )
    story.append(
        P(
            "self.state.audit.append(AuditEntry(...))<br/>"
            "appointment = Appointment(...)<br/>"
            "self.state.appointments.append(appointment)",
            s["code"],
        )
    )
    story.append(Spacer(1, 8))
    story.append(
        P(
            "A comparison of literals will not see that reversal. It has to be read as a sequence.",
            s["first"],
        )
    )

    story.append(P("4. What the working check showed", s["h"]))
    story.append(
        P(
            "examples/clinic-desk was checked from the Your code page. Figure 1 is that run. "
            "The checker took spec.md and the six modules under src/clinic, and left the test file out.",
            s["first"],
        )
    )
    shot = Image(
        "examples/clinic-desk-check.png",
        width=6.35 * inch,
        height=6.35 * inch * (1337 / 1574),
    )
    story.append(Spacer(1, 6))
    story.append(shot)
    story.append(
        P(
            "Figure 1. The clinic-desk folder on the Your code page. The test file is not in the check. The banner is drift.",
            s["caption"],
        )
    )
    story.append(
        P(
            "Four of the six planted faults were flagged. R04 is the 45-minute slot against a rule of 30. "
            "R08 is the unused ClinicianUnavailable. R09 is the late fee of 10.00 against a rule of 25.00. "
            "R12 is the audit line written before the appointment exists. "
            "Two planted value faults were called compliant: R01, where the code registers from 14 against a rule of 16, and R05, where the daily cap is five against a rule of three. "
            "R06 does raise DailyLimitExceeded, and R11 does return 40.00; both were left uncertain. "
            "R10 was flagged even though a cancellation outside 24 hours returns 0, which is what that rule requires.",
            s["first"],
        )
    )
    story.append(
        P(
            "Opening R04 showed the further gap between a flag and a reading. The counterexample named SLOT_MINUTES as 15 and cited an import line in schedule.py. "
            "The assignment in limits.py is 45. The flag landed on the right rule. The number it offered is not the number in the file.",
            s["body"],
        )
    )
    story.append(
        P(
            "The short folder is unchanged. examples/sample-project says the starting count must be 10, and src/counter.py sets START to 3. "
            "Adding past the maximum must raise Overflow, and add does raise that exception once the next value would pass MAX.",
            s["body"],
        )
    )

    doc = SimpleDocTemplate(
        OUT,
        pagesize=letter,
        leftMargin=0.7 * inch,
        rightMargin=0.7 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.7 * inch,
        title="Example folders for the folder check",
        author="SpecDrift-Bench",
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(OUT)


if __name__ == "__main__":
    build()
