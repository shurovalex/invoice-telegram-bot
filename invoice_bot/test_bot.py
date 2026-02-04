#!/usr/bin/env python3
"""
Unit tests for the Invoice Collection Bot.
"""

import pytest
import asyncio
from datetime import datetime

from invoice_data import InvoiceData, WorkItem
from document_processor import DocumentProcessor, MockDocumentProcessor
from invoice_generator import InvoiceGenerator, MockInvoiceGenerator
from message_templates import MessageTemplates


class TestInvoiceData:
    """Test InvoiceData model."""
    
    def test_invoice_creation(self):
        """Test creating an invoice."""
        invoice = InvoiceData(
            contractor_name="Test Contractor",
            contractor_email="test@example.com",
            invoice_number="INV-001",
            subtotal=1000.00,
            vat_amount=200.00,
            cis_amount=0.00,
        )
        
        assert invoice.contractor_name == "Test Contractor"
        assert invoice.subtotal == 1000.00
    
    def test_calculate_total(self):
        """Test total calculation."""
        invoice = InvoiceData(
            subtotal=1000.00,
            vat_amount=200.00,
            cis_amount=200.00,
        )
        
        total = invoice.calculate_total()
        assert total == 1000.00
        assert invoice.total == 1000.00
    
    def test_work_items(self):
        """Test adding work items."""
        invoice = InvoiceData()
        
        item1 = WorkItem(
            property_address="123 Test St",
            plot="A1",
            description="Test work",
            amount=500.00,
        )
        
        invoice.work_items.append(item1)
        
        assert len(invoice.work_items) == 1
        assert invoice.work_items[0].amount == 500.00
    
    def test_to_dict(self):
        """Test serialization to dict."""
        invoice = InvoiceData(
            contractor_name="Test",
            invoice_number="INV-001",
        )
        
        data = invoice.to_dict()
        
        assert data["contractor_name"] == "Test"
        assert data["invoice_number"] == "INV-001"
    
    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "contractor_name": "Test Contractor",
            "contractor_email": "test@example.com",
            "invoice_number": "INV-001",
            "subtotal": 1000.00,
            "vat_amount": 200.00,
            "cis_amount": 200.00,
            "work_items": [
                {
                    "property_address": "123 Test St",
                    "plot": "A1",
                    "description": "Test work",
                    "amount": 500.00,
                }
            ],
        }
        
        invoice = InvoiceData.from_dict(data)
        
        assert invoice.contractor_name == "Test Contractor"
        assert len(invoice.work_items) == 1
        assert invoice.work_items[0].amount == 500.00


class TestMessageTemplates:
    """Test message templates."""
    
    def test_welcome_message(self):
        """Test welcome message."""
        templates = MessageTemplates()
        msg = templates.welcome_message("John")
        
        assert "John" in msg
        assert "Upload Document" in msg
        assert "Chat to Provide" in msg
    
    def test_help_message(self):
        """Test help message."""
        templates = MessageTemplates()
        msg = templates.help_message()
        
        assert "/start" in msg
        assert "/cancel" in msg
        assert "/help" in msg
    
    def test_full_summary(self):
        """Test summary message."""
        templates = MessageTemplates()
        
        data = {
            "contractor_name": "Test Contractor",
            "contractor_email": "test@example.com",
            "contractor_address": "123 Test St",
            "contractor_utr": "1234567890",
            "contractor_ni": "AB123456C",
            "bank_account": "12345678",
            "sort_code": "12-34-56",
            "cardholder_name": "John Doe",
            "invoice_number": "INV-001",
            "invoice_date": "15/01/2024",
            "work_start_date": "01/01/2024",
            "work_end_date": "14/01/2024",
            "work_items": [
                {"description": "Test work", "amount": 500.00},
            ],
            "operative_names": "John, Jane",
            "subtotal": 1000.00,
            "vat_amount": 200.00,
            "cis_amount": 200.00,
            "total": 1000.00,
        }
        
        msg = templates.full_summary(data)
        
        assert "Test Contractor" in msg
        assert "INV-001" in msg
        assert "£1000.00" in msg


class TestDocumentProcessor:
    """Test document processor."""
    
    @pytest.mark.asyncio
    async def test_mock_processor(self):
        """Test mock document processor."""
        processor = MockDocumentProcessor()
        
        invoice = await processor.process_document("test.pdf", "application/pdf")
        
        assert invoice.contractor_name == "ABC Construction Ltd"
        assert len(invoice.work_items) == 2
        assert invoice.total > 0


class TestInvoiceGenerator:
    """Test invoice generator."""
    
    @pytest.mark.asyncio
    async def test_mock_generator(self):
        """Test mock invoice generator."""
        generator = MockInvoiceGenerator()
        
        invoice = InvoiceData(
            contractor_name="Test",
            invoice_number="INV-001",
            subtotal=1000.00,
            vat_amount=200.00,
            cis_amount=200.00,
        )
        invoice.calculate_total()
        
        path = await generator.generate(invoice)
        
        assert path.endswith(".txt")
        
        # Clean up
        import os
        os.unlink(path)


def test_date_validation():
    """Test date format validation."""
    # Valid dates
    valid_dates = ["15/01/2024", "01/12/2023", "31/12/2024"]
    
    for date_str in valid_dates:
        try:
            datetime.strptime(date_str, "%d/%m/%Y")
            assert True
        except ValueError:
            assert False, f"{date_str} should be valid"
    
    # Invalid dates
    invalid_dates = ["32/01/2024", "15/13/2024", "invalid"]
    
    for date_str in invalid_dates:
        try:
            datetime.strptime(date_str, "%d/%m/%Y")
            assert False, f"{date_str} should be invalid"
        except ValueError:
            assert True


def test_email_validation():
    """Test email format validation."""
    import re
    
    pattern = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
    
    # Valid emails
    valid_emails = [
        "test@example.com",
        "user.name@domain.co.uk",
        "user+tag@example.org",
    ]
    
    for email in valid_emails:
        assert pattern.match(email), f"{email} should be valid"
    
    # Invalid emails
    invalid_emails = [
        "notanemail",
        "@nodomain.com",
        "spaces in@email.com",
    ]
    
    for email in invalid_emails:
        assert not pattern.match(email), f"{email} should be invalid"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
