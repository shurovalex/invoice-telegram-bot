#!/usr/bin/env python3
"""
Data models for invoice information.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime


@dataclass
class WorkItem:
    """Represents a single work item on an invoice."""
    property_address: str = ""
    plot: str = ""
    description: str = ""
    amount: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "property_address": self.property_address,
            "plot": self.plot,
            "description": self.description,
            "amount": self.amount,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkItem":
        """Create from dictionary."""
        return cls(
            property_address=data.get("property_address", ""),
            plot=data.get("plot", ""),
            description=data.get("description", ""),
            amount=float(data.get("amount", 0)),
        )


@dataclass
class InvoiceData:
    """Complete invoice data model."""
    
    # Contractor Information
    contractor_name: str = ""
    contractor_address: str = ""
    contractor_email: str = ""
    contractor_utr: str = ""
    contractor_ni: str = ""
    bank_account: str = ""
    sort_code: str = ""
    cardholder_name: str = ""
    
    # Invoice Details
    invoice_number: str = ""
    invoice_date: str = ""
    work_start_date: str = ""
    work_end_date: str = ""
    
    # Work Items
    work_items: List[WorkItem] = field(default_factory=list)
    
    # Operatives
    operative_names: str = ""
    
    # Financials
    subtotal: float = 0.0
    vat_amount: float = 0.0
    cis_amount: float = 0.0
    total: float = 0.0
    
    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    source: str = ""  # 'upload' or 'chat'
    
    def calculate_total(self) -> float:
        """Calculate total amount."""
        self.total = self.subtotal + self.vat_amount - self.cis_amount
        return self.total
    
    def calculate_subtotal_from_items(self) -> float:
        """Calculate subtotal from work items."""
        self.subtotal = sum(item.amount for item in work_items)
        return self.subtotal
    
    def is_complete(self) -> bool:
        """Check if all required fields are filled."""
        required_fields = [
            self.contractor_name,
            self.contractor_address,
            self.invoice_number,
            self.invoice_date,
        ]
        return all(required_fields) and len(self.work_items) > 0
    
    def get_missing_fields(self) -> List[str]:
        """Get list of missing required fields."""
        missing = []
        
        if not self.contractor_name:
            missing.append("Contractor Name")
        if not self.contractor_address:
            missing.append("Contractor Address")
        if not self.contractor_email:
            missing.append("Contractor Email")
        if not self.invoice_number:
            missing.append("Invoice Number")
        if not self.invoice_date:
            missing.append("Invoice Date")
        if not self.work_items:
            missing.append("Work Items")
        
        return missing
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "contractor_name": self.contractor_name,
            "contractor_address": self.contractor_address,
            "contractor_email": self.contractor_email,
            "contractor_utr": self.contractor_utr,
            "contractor_ni": self.contractor_ni,
            "bank_account": self.bank_account,
            "sort_code": self.sort_code,
            "cardholder_name": self.cardholder_name,
            "invoice_number": self.invoice_number,
            "invoice_date": self.invoice_date,
            "work_start_date": self.work_start_date,
            "work_end_date": self.work_end_date,
            "work_items": [item.to_dict() for item in self.work_items],
            "operative_names": self.operative_names,
            "subtotal": self.subtotal,
            "vat_amount": self.vat_amount,
            "cis_amount": self.cis_amount,
            "total": self.total,
            "created_at": self.created_at,
            "source": self.source,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InvoiceData":
        """Create from dictionary."""
        invoice = cls(
            contractor_name=data.get("contractor_name", ""),
            contractor_address=data.get("contractor_address", ""),
            contractor_email=data.get("contractor_email", ""),
            contractor_utr=data.get("contractor_utr", ""),
            contractor_ni=data.get("contractor_ni", ""),
            bank_account=data.get("bank_account", ""),
            sort_code=data.get("sort_code", ""),
            cardholder_name=data.get("cardholder_name", ""),
            invoice_number=data.get("invoice_number", ""),
            invoice_date=data.get("invoice_date", ""),
            work_start_date=data.get("work_start_date", ""),
            work_end_date=data.get("work_end_date", ""),
            operative_names=data.get("operative_names", ""),
            subtotal=float(data.get("subtotal", 0)),
            vat_amount=float(data.get("vat_amount", 0)),
            cis_amount=float(data.get("cis_amount", 0)),
            total=float(data.get("total", 0)),
            created_at=data.get("created_at", ""),
            source=data.get("source", ""),
        )
        
        # Load work items
        for item_data in data.get("work_items", []):
            invoice.work_items.append(WorkItem.from_dict(item_data))
        
        return invoice
    
    def format_for_display(self) -> str:
        """Format invoice data for display in chat."""
        lines = [
            f"👤 *Contractor:* {self.contractor_name}",
            f"📧 *Email:* {self.contractor_email}",
            f"🏠 *Address:* {self.contractor_address[:50]}..." if len(self.contractor_address) > 50 else f"🏠 *Address:* {self.contractor_address}",
            f"🆔 *UTR:* {self.contractor_utr}" if self.contractor_utr else "",
            f"🔢 *NI:* {self.contractor_ni}" if self.contractor_ni else "",
            f"💳 *Bank:* {self.bank_account} | Sort: {self.sort_code}" if self.bank_account else "",
            "",
            f"📄 *Invoice #:* {self.invoice_number}",
            f"📅 *Date:* {self.invoice_date}",
            f"📆 *Period:* {self.work_start_date} to {self.work_end_date}" if self.work_start_date else "",
            "",
            "🔨 *Work Items:*",
        ]
        
        for i, item in enumerate(self.work_items, 1):
            lines.append(f"  {i}. {item.description[:30]}... - £{item.amount:.2f}")
        
        if self.operative_names:
            lines.extend(["", f"👷 *Operatives:* {self.operative_names}"])
        
        lines.extend([
            "",
            "💰 *Financial Summary:*",
            f"  Subtotal: £{self.subtotal:.2f}",
            f"  VAT: £{self.vat_amount:.2f}",
            f"  CIS Deduction: £{self.cis_amount:.2f}",
            f"  *Total: £{self.total:.2f}*",
        ])
        
        return "\n".join(line for line in lines if line)
