#!/usr/bin/env python3
"""
Invoice document generator.
Creates professional PDF invoices from invoice data.
"""

import os
import tempfile
import logging
from datetime import datetime
from typing import Optional

from invoice_data import InvoiceData

logger = logging.getLogger(__name__)


class InvoiceGenerator:
    """Generate professional invoice PDFs."""
    
    def __init__(self, template_path: Optional[str] = None):
        self.template_path = template_path or "templates/invoice_template.html"
    
    async def generate(self, invoice: InvoiceData) -> str:
        """
        Generate invoice PDF from invoice data.
        
        Args:
            invoice: InvoiceData object with all invoice information
            
        Returns:
            Path to generated PDF file
        """
        try:
            # Try to use modern libraries
            return await self._generate_with_html(invoice)
        except Exception as e:
            logger.warning(f"HTML generation failed: {e}, trying fallback")
            return await self._generate_with_reportlab(invoice)
    
    async def _generate_with_html(self, invoice: InvoiceData) -> str:
        """Generate PDF using HTML template and weasyprint/pdfkit."""
        try:
            from weasyprint import HTML, CSS
            
            html_content = self._build_html_invoice(invoice)
            
            # Create temporary file
            fd, output_path = tempfile.mkstemp(suffix=".pdf", prefix="invoice_")
            os.close(fd)
            
            HTML(string=html_content).write_pdf(output_path)
            
            return output_path
            
        except ImportError:
            logger.warning("weasyprint not available")
            raise
    
    async def _generate_with_reportlab(self, invoice: InvoiceData) -> str:
        """Generate PDF using ReportLab (fallback method)."""
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch, mm
        from reportlab.platypus import (
            SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
            Image, PageBreak, KeepTogether
        )
        from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
        
        # Create temporary file
        fd, output_path = tempfile.mkstemp(suffix=".pdf", prefix="invoice_")
        os.close(fd)
        
        # Create document
        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            rightMargin=20*mm,
            leftMargin=20*mm,
            topMargin=20*mm,
            bottomMargin=20*mm,
        )
        
        # Container for elements
        elements = []
        styles = getSampleStyleSheet()
        
        # Custom styles
        title_style = ParagraphStyle(
            'Title',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1a365d'),
            spaceAfter=20,
        )
        
        heading_style = ParagraphStyle(
            'Heading',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#2d3748'),
            spaceAfter=10,
        )
        
        normal_style = ParagraphStyle(
            'Normal',
            parent=styles['Normal'],
            fontSize=10,
            spaceAfter=6,
        )
        
        # Header
        elements.append(Paragraph("INVOICE", title_style))
        elements.append(Spacer(1, 10))
        
        # Invoice info table
        invoice_info = [
            ["Invoice Number:", invoice.invoice_number or "N/A"],
            ["Invoice Date:", invoice.invoice_date or "N/A"],
            ["Work Period:", f"{invoice.work_start_date or 'N/A'} to {invoice.work_end_date or 'N/A'}"],
        ]
        
        info_table = Table(invoice_info, colWidths=[40*mm, 60*mm])
        info_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(info_table)
        elements.append(Spacer(1, 20))
        
        # Contractor section
        elements.append(Paragraph("Contractor Information", heading_style))
        contractor_data = [
            ["Name:", invoice.contractor_name or "N/A"],
            ["Address:", invoice.contractor_address or "N/A"],
            ["Email:", invoice.contractor_email or "N/A"],
            ["UTR:", invoice.contractor_utr or "N/A"],
            ["NI Number:", invoice.contractor_ni or "N/A"],
        ]
        
        contractor_table = Table(contractor_data, colWidths=[30*mm, 120*mm])
        contractor_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(contractor_table)
        elements.append(Spacer(1, 20))
        
        # Bank details
        elements.append(Paragraph("Payment Details", heading_style))
        bank_data = [
            ["Bank Account:", invoice.bank_account or "N/A"],
            ["Sort Code:", invoice.sort_code or "N/A"],
            ["Cardholder:", invoice.cardholder_name or "N/A"],
        ]
        
        bank_table = Table(bank_data, colWidths=[35*mm, 80*mm])
        bank_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(bank_table)
        elements.append(Spacer(1, 20))
        
        # Work items
        elements.append(Paragraph("Work Items", heading_style))
        
        if invoice.work_items:
            work_headers = ["#", "Property", "Plot", "Description", "Amount"]
            work_data = [work_headers]
            
            for i, item in enumerate(invoice.work_items, 1):
                work_data.append([
                    str(i),
                    item.property_address[:25] + "..." if len(item.property_address) > 25 else item.property_address,
                    item.plot,
                    item.description[:35] + "..." if len(item.description) > 35 else item.description,
                    f"£{item.amount:.2f}",
                ])
            
            work_table = Table(work_data, colWidths=[8*mm, 40*mm, 15*mm, 65*mm, 22*mm])
            work_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2d3748')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                ('ALIGN', (-1, 0), (-1, -1), 'RIGHT'),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
            ]))
            elements.append(work_table)
        else:
            elements.append(Paragraph("No work items recorded.", normal_style))
        
        elements.append(Spacer(1, 20))
        
        # Operatives
        if invoice.operative_names:
            elements.append(Paragraph(f"Operatives: {invoice.operative_names}", normal_style))
            elements.append(Spacer(1, 10))
        
        # Financial summary
        elements.append(Paragraph("Financial Summary", heading_style))
        
        financial_data = [
            ["Subtotal:", f"£{invoice.subtotal:.2f}"],
            ["VAT:", f"£{invoice.vat_amount:.2f}"],
            ["CIS Deduction:", f"-£{invoice.cis_amount:.2f}"],
            ["TOTAL:", f"£{invoice.total:.2f}"],
        ]
        
        financial_table = Table(financial_data, colWidths=[100*mm, 50*mm])
        financial_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -2), 'Helvetica'),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTNAME', (-1, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (-1, 0), (-1, -1), 'RIGHT'),
            ('LINEABOVE', (0, -1), (-1, -1), 1, colors.black),
            ('TOPPADDING', (0, -1), (-1, -1), 10),
            ('FONTSIZE', (0, -1), (-1, -1), 14),
        ]))
        elements.append(financial_table)
        
        # Footer
        elements.append(Spacer(1, 40))
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.grey,
            alignment=TA_CENTER,
        )
        elements.append(Paragraph(
            f"Generated on {datetime.now().strftime('%d/%m/%Y %H:%M')} | Invoice Collection Bot",
            footer_style
        ))
        
        # Build PDF
        doc.build(elements)
        
        return output_path
    
    def _build_html_invoice(self, invoice: InvoiceData) -> str:
        """Build HTML content for invoice."""
        work_items_html = ""
        for i, item in enumerate(invoice.work_items, 1):
            work_items_html += f"""
            <tr>
                <td>{i}</td>
                <td>{item.property_address}</td>
                <td>{item.plot}</td>
                <td>{item.description}</td>
                <td class="amount">£{item.amount:.2f}</td>
            </tr>
            """
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                @page {{
                    size: A4;
                    margin: 2cm;
                }}
                body {{
                    font-family: Arial, sans-serif;
                    font-size: 11pt;
                    line-height: 1.4;
                    color: #333;
                }}
                .header {{
                    text-align: center;
                    border-bottom: 3px solid #1a365d;
                    padding-bottom: 20px;
                    margin-bottom: 30px;
                }}
                .header h1 {{
                    color: #1a365d;
                    font-size: 28pt;
                    margin: 0;
                }}
                .invoice-info {{
                    float: right;
                    text-align: right;
                    margin-bottom: 20px;
                }}
                .section {{
                    margin-bottom: 25px;
                }}
                .section h2 {{
                    color: #2d3748;
                    font-size: 14pt;
                    border-bottom: 1px solid #ccc;
                    padding-bottom: 5px;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                }}
                th, td {{
                    padding: 8px;
                    text-align: left;
                    border-bottom: 1px solid #ddd;
                }}
                th {{
                    background-color: #2d3748;
                    color: white;
                    font-weight: bold;
                }}
                .amount {{
                    text-align: right;
                }}
                .financial-summary {{
                    margin-top: 30px;
                    width: 50%;
                    margin-left: auto;
                }}
                .financial-summary td {{
                    padding: 10px;
                }}
                .total-row {{
                    font-weight: bold;
                    font-size: 14pt;
                    border-top: 2px solid #333;
                }}
                .footer {{
                    margin-top: 50px;
                    text-align: center;
                    font-size: 9pt;
                    color: #666;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>INVOICE</h1>
            </div>
            
            <div class="invoice-info">
                <p><strong>Invoice Number:</strong> {invoice.invoice_number or 'N/A'}</p>
                <p><strong>Invoice Date:</strong> {invoice.invoice_date or 'N/A'}</p>
                <p><strong>Work Period:</strong> {invoice.work_start_date or 'N/A'} to {invoice.work_end_date or 'N/A'}</p>
            </div>
            
            <div style="clear: both;"></div>
            
            <div class="section">
                <h2>Contractor Information</h2>
                <p><strong>Name:</strong> {invoice.contractor_name or 'N/A'}</p>
                <p><strong>Address:</strong> {invoice.contractor_address or 'N/A'}</p>
                <p><strong>Email:</strong> {invoice.contractor_email or 'N/A'}</p>
                <p><strong>UTR:</strong> {invoice.contractor_utr or 'N/A'}</p>
                <p><strong>NI Number:</strong> {invoice.contractor_ni or 'N/A'}</p>
            </div>
            
            <div class="section">
                <h2>Payment Details</h2>
                <p><strong>Bank Account:</strong> {invoice.bank_account or 'N/A'}</p>
                <p><strong>Sort Code:</strong> {invoice.sort_code or 'N/A'}</p>
                <p><strong>Cardholder Name:</strong> {invoice.cardholder_name or 'N/A'}</p>
            </div>
            
            <div class="section">
                <h2>Work Items</h2>
                <table>
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Property</th>
                            <th>Plot</th>
                            <th>Description</th>
                            <th class="amount">Amount</th>
                        </tr>
                    </thead>
                    <tbody>
                        {work_items_html or '<tr><td colspan="5">No work items</td></tr>'}
                    </tbody>
                </table>
            </div>
            
            {f'<p><strong>Operatives:</strong> {invoice.operative_names}</p>' if invoice.operative_names else ''}
            
            <div class="section">
                <h2>Financial Summary</h2>
                <table class="financial-summary">
                    <tr>
                        <td>Subtotal:</td>
                        <td class="amount">£{invoice.subtotal:.2f}</td>
                    </tr>
                    <tr>
                        <td>VAT:</td>
                        <td class="amount">£{invoice.vat_amount:.2f}</td>
                    </tr>
                    <tr>
                        <td>CIS Deduction:</td>
                        <td class="amount">-£{invoice.cis_amount:.2f}</td>
                    </tr>
                    <tr class="total-row">
                        <td>TOTAL:</td>
                        <td class="amount">£{invoice.total:.2f}</td>
                    </tr>
                </table>
            </div>
            
            <div style="clear: both;"></div>
            
            <div class="footer">
                <p>Generated on {datetime.now().strftime('%d/%m/%Y %H:%M')} | Invoice Collection Bot</p>
            </div>
        </body>
        </html>
        """
        
        return html


class MockInvoiceGenerator(InvoiceGenerator):
    """Mock generator for testing."""
    
    async def generate(self, invoice: InvoiceData) -> str:
        """Create a simple text file as mock PDF."""
        fd, output_path = tempfile.mkstemp(suffix=".txt", prefix="invoice_")
        with os.fdopen(fd, 'w') as f:
            f.write(f"MOCK INVOICE: {invoice.invoice_number}\n")
            f.write(f"Contractor: {invoice.contractor_name}\n")
            f.write(f"Total: £{invoice.total:.2f}\n")
        return output_path
