# Invoice Bot - Conversation Flow & State Machine

## State Machine Overview

The bot uses a finite state machine with 28 conversation states to manage the invoice collection process.

## State Definitions

```python
# Conversation States Enumeration
(
    SELECT_MODE,           # 0 - Initial mode selection (upload vs chat)
    UPLOAD_DOCUMENT,       # 1 - Waiting for document upload
    CONFIRM_EXTRACTED,     # 2 - Confirm extracted data from document
    CONTRACTOR_NAME,       # 3 - Contractor name input
    CONTRACTOR_ADDRESS,    # 4 - Contractor address input
    CONTRACTOR_EMAIL,      # 5 - Contractor email input
    CONTRACTOR_UTR,        # 6 - Contractor UTR input
    CONTRACTOR_NI,         # 7 - Contractor NI number input
    CONTRACTOR_BANK,       # 8 - Bank account number input
    CONTRACTOR_SORT,       # 9 - Sort code input
    CONTRACTOR_CARDHOLDER, # 10 - Cardholder name input
    INVOICE_NUMBER,        # 11 - Invoice number input
    INVOICE_DATE,          # 12 - Invoice date input
    WORK_START_DATE,       # 13 - Work start date input
    WORK_END_DATE,         # 14 - Work end date input
    ADD_WORK_ITEM,         # 15 - Ask to add work item
    WORK_PROPERTY,         # 16 - Work item property address
    WORK_PLOT,             # 17 - Work item plot number
    WORK_DESCRIPTION,      # 18 - Work item description
    WORK_AMOUNT,           # 19 - Work item amount
    MORE_WORK_ITEMS,       # 20 - Ask for more work items
    OPERATIVE_NAMES,       # 21 - Operative names input
    SUBTOTAL,              # 22 - Subtotal amount input
    VAT_AMOUNT,            # 23 - VAT amount input
    CIS_AMOUNT,            # 24 - CIS deduction input
    CONFIRM_SUMMARY,       # 25 - Final confirmation
    GENERATE_INVOICE,      # 26 - Generate invoice (transient)
) = range(27)
```

## Visual Flow Diagram

```
                                    ┌─────────────────┐
                                    │   USER STARTS   │
                                    │    (/start)     │
                                    └────────┬────────┘
                                             │
                                             ▼
                              ┌──────────────────────────────┐
                              │      STATE: SELECT_MODE      │
                              │  "Choose: Upload or Chat"    │
                              │                              │
                              │  [📄 Upload Document]        │
                              │  [💬 Chat to Provide]        │
                              └──────────────┬───────────────┘
                                             │
                    ┌────────────────────────┴────────────────────────┐
                    │                                                  │
                    ▼                                                  ▼
┌──────────────────────────────────┐                    ┌──────────────────────────────────┐
│    STATE: UPLOAD_DOCUMENT        │                    │    STATE: CONTRACTOR_NAME        │
│    "Send PDF/DOCX/Photo"         │                    │    "Enter contractor name"       │
│                                  │                    │                                  │
│  Handler: _process_document()    │                    │  Handler: _get_contractor_name() │
│  - Download file                 │                    │  - Validate name                 │
│  - Extract text (OCR)            │                    │  - Store in context              │
│  - Parse invoice data            │                    │  - Next: CONTRACTOR_ADDRESS      │
└──────────────┬───────────────────┘                    └──────────────┬───────────────────┘
               │                                                       │
               ▼                                                       ▼
┌──────────────────────────────────┐                    ┌──────────────────────────────────┐
│   STATE: CONFIRM_EXTRACTED       │                    │   STATE: CONTRACTOR_ADDRESS      │
│   "Review extracted data"        │                    │   "Enter address"                │
│                                  │                    │                                  │
│  [✅ Confirm & Continue]         │                    │  Handler: _get_contractor_addr() │
│  [🔄 Re-upload]                  │                    │  Next: CONTRACTOR_EMAIL          │
│  [✏️ Enter Manually] → Chat      │                    └──────────────────────────────────┘
└──────────────┬───────────────────┘                                   │
               │                                                        │
               │         ┌──────────────────────────────────────────────┘
               │         │
               │         ▼
               │  ┌──────────────────────────────────┐
               │  │   STATE: CONTRACTOR_EMAIL        │
               │  │   "Enter email address"          │
               │  │                                  │
               │  │  Handler: _get_contractor_email()│
               │  │  - Validate email format         │
               │  │  - Next: CONTRACTOR_UTR          │
               │  └──────────────────────────────────┘
               │         │
               │         ▼
               │  ┌──────────────────────────────────┐
               │  │   STATE: CONTRACTOR_UTR          │
               │  │   "Enter UTR (or skip)"          │
               │  │                                  │
               │  │  Handler: _get_contractor_utr()  │
               │  │  Next: CONTRACTOR_NI             │
               │  └──────────────────────────────────┘
               │         │
               │         ▼
               │  ┌──────────────────────────────────┐
               │  │   STATE: CONTRACTOR_NI           │
               │  │   "Enter NI number (or skip)"    │
               │  │                                  │
               │  │  Handler: _get_contractor_ni()   │
               │  │  Next: CONTRACTOR_BANK           │
               │  └──────────────────────────────────┘
               │         │
               │         ▼
               │  ┌──────────────────────────────────┐
               │  │   STATE: CONTRACTOR_BANK         │
               │  │   "Enter bank account (or skip)" │
               │  │                                  │
               │  │  Handler: _get_contractor_bank() │
               │  │  Next: CONTRACTOR_SORT           │
               │  └──────────────────────────────────┘
               │         │
               │         ▼
               │  ┌──────────────────────────────────┐
               │  │   STATE: CONTRACTOR_SORT         │
               │  │   "Enter sort code (or skip)"    │
               │  │                                  │
               │  │  Handler: _get_contractor_sort() │
               │  │  Next: CONTRACTOR_CARDHOLDER     │
               │  └──────────────────────────────────┘
               │         │
               │         ▼
               │  ┌──────────────────────────────────┐
               │  │ STATE: CONTRACTOR_CARDHOLDER     │
               │  │ "Enter cardholder name (or skip)"│
               │  │                                  │
               │  │ Handler: _get_contractor_card()  │
               │  │ Next: INVOICE_NUMBER             │
               │  └──────────────────────────────────┘
               │         │
               │         ▼
               │  ┌──────────────────────────────────┐
               │  │   STATE: INVOICE_NUMBER          │
               │  │   "Enter invoice number"         │
               │  │                                  │
               │  │ Handler: _get_invoice_number()   │
               │  │ Next: INVOICE_DATE               │
               │  └──────────────────────────────────┘
               │         │
               │         ▼
               │  ┌──────────────────────────────────┐
               │  │   STATE: INVOICE_DATE            │
               │  │   "Enter invoice date (DD/MM/YY)"│
               │  │                                  │
               │  │ Handler: _get_invoice_date()     │
               │  │ - Validate date format           │
               │  │ Next: WORK_START_DATE            │
               │  └──────────────────────────────────┘
               │         │
               │         ▼
               │  ┌──────────────────────────────────┐
               │  │   STATE: WORK_START_DATE         │
               │  │   "Enter work start date"        │
               │  │                                  │
               │  │ Handler: _get_work_start_date()  │
               │  │ Next: WORK_END_DATE              │
               │  └──────────────────────────────────┘
               │         │
               │         ▼
               │  ┌──────────────────────────────────┐
               │  │   STATE: WORK_END_DATE           │
               │  │   "Enter work end date"          │
               │  │                                  │
               │  │ Handler: _get_work_end_date()    │
               │  │ Next: ADD_WORK_ITEM              │
               │  └──────────────────────────────────┘
               │         │
               │         ▼
               │  ┌──────────────────────────────────┐
               │  │   STATE: ADD_WORK_ITEM           │
               │  │   "Add work item?"               │
               │  │                                  │
               │  │ [➕ Add Work Item]               │
               │  │ [⏭️ Skip for Now]                │
               │  │                                  │
               │  │ Skip → OPERATIVE_NAMES           │
               │  │ Add → WORK_PROPERTY              │
               │  └──────────────────────────────────┘
               │         │
               │         ▼
               │  ┌──────────────────────────────────┐
               │  │   STATE: WORK_PROPERTY           │
               │  │   "Enter property address"       │
               │  │                                  │
               │  │ Handler: _get_work_property()    │
               │  │ Next: WORK_PLOT                  │
               │  └──────────────────────────────────┘
               │         │
               │         ▼
               │  ┌──────────────────────────────────┐
               │  │   STATE: WORK_PLOT               │
               │  │   "Enter plot number"            │
               │  │                                  │
               │  │ Handler: _get_work_plot()        │
               │  │ Next: WORK_DESCRIPTION           │
               │  └──────────────────────────────────┘
               │         │
               │         ▼
               │  ┌──────────────────────────────────┐
               │  │   STATE: WORK_DESCRIPTION        │
               │  │   "Enter work description"       │
               │  │                                  │
               │  │ Handler: _get_work_description() │
               │  │ Next: WORK_AMOUNT                │
               │  └──────────────────────────────────┘
               │         │
               │         ▼
               │  ┌──────────────────────────────────┐
               │  │   STATE: WORK_AMOUNT             │
               │  │   "Enter amount (£)"             │
               │  │                                  │
               │  │ Handler: _get_work_amount()      │
               │  │ - Validate numeric               │
               │  │ - Add to work_items list         │
               │  │ Next: MORE_WORK_ITEMS            │
               │  └──────────────────────────────────┘
               │         │
               │         ▼
               │  ┌──────────────────────────────────┐
               │  │   STATE: MORE_WORK_ITEMS         │
               │  │   "Add another work item?"       │
               │  │                                  │
               │  │ [➕ Add Another]                 │
               │  │ [✅ Done]                        │
               │  │                                  │
               │  │ More → WORK_PROPERTY             │
               │  │ Done → OPERATIVE_NAMES           │
               │  └──────────────────────────────────┘
               │         │
               │         ▼
               │  ┌──────────────────────────────────┐
               │  │   STATE: OPERATIVE_NAMES         │
               │  │   "Enter operative names"        │
               │  │                                  │
               │  │ Handler: _get_operative_names()  │
               │  │ Next: SUBTOTAL                   │
               │  └──────────────────────────────────┘
               │         │
               │         ▼
               │  ┌──────────────────────────────────┐
               │  │   STATE: SUBTOTAL                │
               │  │   "Enter subtotal amount"        │
               │  │                                  │
               │  │ Handler: _get_subtotal()         │
               │  │ - Validate numeric               │
               │  │ Next: VAT_AMOUNT                 │
               │  └──────────────────────────────────┘
               │         │
               │         ▼
               │  ┌──────────────────────────────────┐
               │  │   STATE: VAT_AMOUNT              │
               │  │   "Enter VAT amount"             │
               │  │                                  │
               │  │ Handler: _get_vat()              │
               │  │ Next: CIS_AMOUNT                 │
               │  └──────────────────────────────────┘
               │         │
               │         ▼
               │  ┌──────────────────────────────────┐
               │  │   STATE: CIS_AMOUNT              │
               │  │   "Enter CIS deduction"          │
               │  │                                  │
               │  │ Handler: _get_cis()              │
               │  │ - Calculate total                │
               │  │ Next: CONFIRM_SUMMARY            │
               │  └──────────────────────────────────┘
               │         │
               └─────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      STATE: CONFIRM_SUMMARY                          │
│                      "Review and confirm"                            │
│                                                                      │
│  Handler: _confirm_summary_callback()                                │
│                                                                      │
│  [✅ Generate Invoice]  → Generate PDF, send to user, END            │
│  [✏️ Edit Details]      → Restart from CONTRACTOR_NAME               │
│  [❌ Cancel]            → Clear data, END                            │
└──────────────────────────────────────────────────────────────────────┘
```

## State Transitions Summary

| Current State | User Input | Next State | Handler Method |
|--------------|------------|------------|----------------|
| SELECT_MODE | "upload" | UPLOAD_DOCUMENT | _select_mode_callback |
| SELECT_MODE | "chat" | CONTRACTOR_NAME | _select_mode_callback |
| UPLOAD_DOCUMENT | Document/Photo | CONFIRM_EXTRACTED | _process_document |
| CONFIRM_EXTRACTED | "confirm_data" | CONFIRM_SUMMARY | _confirm_extracted_callback |
| CONFIRM_EXTRACTED | "retry_upload" | UPLOAD_DOCUMENT | _confirm_extracted_callback |
| CONFIRM_EXTRACTED | "manual_entry" | CONTRACTOR_NAME | _confirm_extracted_callback |
| CONTRACTOR_NAME | Text | CONTRACTOR_ADDRESS | _get_contractor_name |
| CONTRACTOR_ADDRESS | Text | CONTRACTOR_EMAIL | _get_contractor_address |
| CONTRACTOR_EMAIL | Text | CONTRACTOR_UTR | _get_contractor_email |
| CONTRACTOR_UTR | Text | CONTRACTOR_NI | _get_contractor_utr |
| CONTRACTOR_NI | Text | CONTRACTOR_BANK | _get_contractor_ni |
| CONTRACTOR_BANK | Text | CONTRACTOR_SORT | _get_contractor_bank |
| CONTRACTOR_SORT | Text | CONTRACTOR_CARDHOLDER | _get_contractor_sort |
| CONTRACTOR_CARDHOLDER | Text | INVOICE_NUMBER | _get_contractor_cardholder |
| INVOICE_NUMBER | Text | INVOICE_DATE | _get_invoice_number |
| INVOICE_DATE | Text | WORK_START_DATE | _get_invoice_date |
| WORK_START_DATE | Text | WORK_END_DATE | _get_work_start_date |
| WORK_END_DATE | Text | ADD_WORK_ITEM | _get_work_end_date |
| ADD_WORK_ITEM | "add_work" | WORK_PROPERTY | _add_work_item_callback |
| ADD_WORK_ITEM | "skip_work" | OPERATIVE_NAMES | _add_work_item_callback |
| WORK_PROPERTY | Text | WORK_PLOT | _get_work_property |
| WORK_PLOT | Text | WORK_DESCRIPTION | _get_work_plot |
| WORK_DESCRIPTION | Text | WORK_AMOUNT | _get_work_description |
| WORK_AMOUNT | Text | MORE_WORK_ITEMS | _get_work_amount |
| MORE_WORK_ITEMS | "more_work" | WORK_PROPERTY | _more_work_items_callback |
| MORE_WORK_ITEMS | "done_work" | OPERATIVE_NAMES | _more_work_items_callback |
| OPERATIVE_NAMES | Text | SUBTOTAL | _get_operative_names |
| SUBTOTAL | Text | VAT_AMOUNT | _get_subtotal |
| VAT_AMOUNT | Text | CIS_AMOUNT | _get_vat |
| CIS_AMOUNT | Text | CONFIRM_SUMMARY | _get_cis |
| CONFIRM_SUMMARY | "confirm_all" | END (generate invoice) | _confirm_summary_callback |
| CONFIRM_SUMMARY | "edit_data" | CONTRACTOR_NAME | _confirm_summary_callback |
| CONFIRM_SUMMARY | "cancel_all" | END | _confirm_summary_callback |

## Fallback Handlers

| Command | Action |
|---------|--------|
| /cancel | Clear user data, end conversation |
| /start | Restart from SELECT_MODE |
| /help | Show help message |

## Error Recovery

Each state handler includes error handling:

1. **Validation Errors**: Invalid input triggers retry message, stays in same state
2. **Processing Errors**: User-friendly error message, option to retry or cancel
3. **Unexpected Errors**: Conversation ends gracefully, user can restart with /start

## Data Storage

User data is stored in `context.user_data`:

```python
{
    "user_id": 123456789,
    "mode": "upload" | "chat",
    "invoice": InvoiceData(),  # Main data object
    "current_work_item": WorkItem(),  # Temporary during work item entry
    "extracted_data": dict,  # From document upload
}
```
