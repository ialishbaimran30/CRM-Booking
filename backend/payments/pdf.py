"""Server-side invoice PDF rendering (ReportLab).

Reuses the existing Invoice/Payment models and InvoiceSerializer field set —
no new model, no change to invoice data. The layout mirrors the existing
frontend invoice modal (PaymentsView.js) field-for-field.
"""
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas


def render_invoice_pdf(invoice):
    """Render a single Invoice to PDF bytes."""
    buffer = BytesIO()
    page_width, page_height = A4
    c = canvas.Canvas(buffer, pagesize=A4)

    dark_text = HexColor("#1E2A3A")
    light_text = HexColor("#6B7A90")
    accent = HexColor("#3E7BFA")

    left = 20 * mm
    right = page_width - 20 * mm
    y = page_height - 25 * mm

    booking = invoice.booking
    client = booking.client

    c.setFillColor(dark_text)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(left, y, f"Invoice {invoice.invoice_number}")

    y -= 8 * mm
    c.setFillColor(light_text)
    c.setFont("Helvetica", 10)
    issued_date = invoice.issued_date.strftime("%Y-%m-%d") if invoice.issued_date else "-"
    c.drawString(left, y, f"Issued {issued_date}")

    y -= 12 * mm
    c.setStrokeColor(HexColor("#E3E8F0"))
    c.line(left, y, right, y)

    def field(label, value, bold_value=False, size=11):
        nonlocal y
        y -= 9 * mm
        c.setFillColor(dark_text)
        c.setFont("Helvetica-Bold", size)
        c.drawString(left, y, f"{label}:")
        c.setFont("Helvetica-Bold" if bold_value else "Helvetica", size)
        c.drawString(left + 35 * mm, y, str(value))

    field("Client", client.full_name)
    field("Service", booking.service_name)
    field("Subtotal", f"${invoice.subtotal}")

    discount_line = f"${invoice.discount_amount}"
    if invoice.coupon_code:
        discount_line += f" ({invoice.coupon_code})"
    field("Discount", discount_line)

    field("Tax", f"${invoice.tax_amount}")

    y -= 4 * mm
    c.setStrokeColor(HexColor("#E3E8F0"))
    c.line(left, y, right, y)

    field("Total", f"${invoice.total_amount}", bold_value=True, size=14)

    y -= 9 * mm
    c.setFillColor(accent)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(left, y, f"Status: {invoice.status}")

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer.getvalue()
