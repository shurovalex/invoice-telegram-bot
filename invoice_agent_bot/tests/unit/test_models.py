"""
Unit tests for invoice models.
"""

import pytest
from decimal import Decimal
from datetime import date

from src.models.invoice import (
    InvoiceData,
    InvoiceItem,
    CustomerInfo,
    CompanyInfo,
    InvoiceStatus,
)


class TestInvoiceItem:
    """Tests for InvoiceItem model."""
    
    def test_item_creation(self):
        """Test creating an invoice item."""
        item = InvoiceItem(
            description="Test Service",
            quantity=Decimal("2"),
            unit_price=Decimal("100.00"),
        )
        
        assert item.description == "Test Service"
        assert item.quantity == Decimal("2")
        assert item.unit_price == Decimal("100.00")
        assert item.amount == Decimal("200.00")
    
    def test_item_with_tax(self):
        """Test item with tax rate."""
        item = InvoiceItem(
            description="Taxable Item",
            quantity=Decimal("1"),
            unit_price=Decimal("100.00"),
            tax_rate=Decimal("10"),
        )
        
        assert item.amount == Decimal("100.00")


class TestCustomerInfo:
    """Tests for CustomerInfo model."""
    
    def test_customer_creation(self):
        """Test creating customer info."""
        customer = CustomerInfo(
            name="Test Customer",
            email="test@example.com",
            phone="+1-555-123-4567",
        )
        
        assert customer.name == "Test Customer"
        assert customer.email == "test@example.com"
    
    def test_email_normalization(self):
        """Test email is normalized to lowercase."""
        customer = CustomerInfo(
            name="Test",
            email="TEST@EXAMPLE.COM",
        )
        
        assert customer.email == "test@example.com"


class TestInvoiceData:
    """Tests for InvoiceData model."""
    
    def test_invoice_creation(self):
        """Test creating an invoice."""
        customer = CustomerInfo(name="Test Customer")
        invoice = InvoiceData(
            customer=customer,
            currency="USD",
        )
        
        assert invoice.customer.name == "Test Customer"
        assert invoice.currency == "USD"
        assert invoice.status == InvoiceStatus.DRAFT
    
    def test_invoice_add_item(self):
        """Test adding items to invoice."""
        customer = CustomerInfo(name="Test Customer")
        invoice = InvoiceData(customer=customer)
        
        item = InvoiceItem(
            description="Service",
            quantity=Decimal("2"),
            unit_price=Decimal("50.00"),
        )
        
        invoice.add_item(item)
        
        assert len(invoice.items) == 1
        assert invoice.subtotal == Decimal("100.00")
        assert invoice.total == Decimal("100.00")
    
    def test_invoice_totals(self):
        """Test invoice total calculations."""
        customer = CustomerInfo(name="Test Customer")
        invoice = InvoiceData(customer=customer)
        
        # Add items
        invoice.add_item(InvoiceItem(
            description="Item 1",
            quantity=Decimal("2"),
            unit_price=Decimal("50.00"),
        ))
        invoice.add_item(InvoiceItem(
            description="Item 2",
            quantity=Decimal("1"),
            unit_price=Decimal("100.00"),
        ))
        
        assert invoice.subtotal == Decimal("200.00")
        assert invoice.total == Decimal("200.00")
    
    def test_invoice_serialization(self):
        """Test invoice to/from dict."""
        customer = CustomerInfo(name="Test Customer")
        invoice = InvoiceData(
            customer=customer,
            invoice_number="INV-001",
        )
        
        invoice.add_item(InvoiceItem(
            description="Service",
            quantity=Decimal("1"),
            unit_price=Decimal("100.00"),
        ))
        
        # Serialize
        data = invoice.to_dict()
        
        # Deserialize
        restored = InvoiceData.from_dict(data)
        
        assert restored.invoice_number == "INV-001"
        assert restored.customer.name == "Test Customer"
        assert len(restored.items) == 1
