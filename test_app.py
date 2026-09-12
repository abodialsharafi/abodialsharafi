import os
from parser import CommercialInvoiceParser
from pdf_generator import SWIFTPDFGenerator

def test_full_pipeline():
    print("--- 1. Testing Commercial Invoice Parser ---")
    
    # نموذج نص فاتورة تجارية تجريبية لنفس المصطلحات المعطاة من العميل
    sample_invoice_text = """
    COMMERCIAL INVOICE
    Invoice No: INV-2026-8899
    PI No: PI-BL-554411
    Date: 2026-08-15
    Payment Terms: 30% T/T advance deposit
    Delivery Terms: FOB SHANGHAI
    
    Customer Name: Al-Qasemi Importing & Trading Ltd
    Customer Address: Sanaa, Yemen
    Tel: +967-771234567
    
    Beneficiary Name: Shenzhen Global Electronics Corp
    Beneficiary Address: Industrial Zone, Shenzhen, China
    Tel: +86-755-88889999
    
    Banking Details:
    Beneficiary Bank/Branch: Bank of China, Shenzhen Branch
    Beneficiary's Account No: 882910293847
    IBAN: CN880000882910293847
    Swift / BIC: BKCHCNBJ110
    Correspondent Bank: Citibank N.A. New York
    Correspondent Swift / BIC: CITIUS33XXX
    
    Description: High Quality Solar Panel Inverters 5KW
    Quantity(PCS): 500 PCS
    Amount (USD): 50000.00
    Port of Loading: Shanghai Port
    Port of Destination: Hodeidah Port, Yemen
    Pre-Carriage By: Sea Freight
    """
    
    test_txt_path = "sample_invoice.txt"
    with open(test_txt_path, "w", encoding="utf-8") as f:
        f.write(sample_invoice_text)
        
    parser = CommercialInvoiceParser()
    
    def mock_progress(val, msg):
        print(f"Progress [{int(val*100)}%]: {msg}")
        
    parsed_data = parser.parse_invoice(test_txt_path, progress_callback=mock_progress)
    
    print("\n--- Parsed Results ---")
    for k, v in parsed_data.items():
        if k != "raw_text":
            print(f"{k}: {v}")
            
    # التحقق من الشروط الأساسية
    assert parsed_data["invoice_no"] == "INV-2026-8899", f"Expected INV-2026-8899 but got {parsed_data['invoice_no']}"
    assert parsed_data["pi_no"] == "PI-BL-554411", f"Expected PI-BL-554411 but got {parsed_data['pi_no']}"
    assert "30%" in parsed_data["payment_terms"], "Expected 30% in payment terms"
    assert parsed_data["swift_code"] == "BKCHCNBJ110", f"Expected BKCHCNBJ110 but got {parsed_data['swift_code']}"
    assert parsed_data["total_amount"] == "50,000.00", f"Expected 50,000.00 but got {parsed_data['total_amount']}"
    assert parsed_data["transfer_amount"] == "15,000.00", f"Expected 15,000.00 but got {parsed_data['transfer_amount']}"
    
    print("\n--- 2. Testing PDF Generator ---")
    pdf_gen = SWIFTPDFGenerator()
    out_pdf = "SWIFT_Transfer_Test.pdf"
    pdf_gen.generate_pdf(parsed_data, out_pdf)
    assert os.path.exists(out_pdf), "PDF file was not created"
    print(f" PDF Successfully generated: {out_pdf} ({os.path.getsize(out_pdf)} bytes)")

def test_italian_invoice():
    print("\n--- 3. Testing Italian Invoice Keyword Extraction ---")
    italian_sample = """
    FAATTURA / INVOICE
    Numero documento: 292
    Data doc.: 24-08-2026
    Intestatario documento: ALOMAISI CLOTHES IMPORTING
    Sede legale: ADVANCE AQUA BIO TECHNOLOGIES ITALY SRL
    Beneficiary of the payment: ADVANCE AQUA BIO TECHNOLOGIES ITALY SRL
    Modalita di pagamento: 100% T/T ADVANCE
    Banca d'appoggio: INTESA SANPAOLO SPA
    Totale documento: 18,881.60 EUR
    """
    test_ita_path = "sample_italian_invoice.txt"
    with open(test_ita_path, "w", encoding="utf-8") as f:
        f.write(italian_sample)

    parser = CommercialInvoiceParser()
    parsed = parser.parse_invoice(test_ita_path)
    
    print("Numero documento (Invoice No):", parsed["invoice_no"])
    print("Data doc (Date):", parsed["date"])
    print("Intestatario documento (Customer Name):", parsed["customer_name"])
    print("Beneficiary / Sede (Beneficiary Name):", parsed["beneficiary_name"])
    print("Totale documento (Total Amount):", parsed["total_amount"])
    print("Banca (Beneficiary Bank):", parsed["beneficiary_bank"])
    print("Modalita di pagamento (Payment Terms):", parsed["payment_terms"])

    assert parsed["invoice_no"] == "292", f"Expected 292, got {parsed['invoice_no']}"
    assert parsed["date"] == "2026-08-24", f"Expected 2026-08-24, got {parsed['date']}"
    assert "18,881.60" in parsed["total_amount"], f"Expected 18,881.60, got {parsed['total_amount']}"
    assert "ADVANCE AQUA" in parsed["beneficiary_name"], f"Expected ADVANCE AQUA in beneficiary_name, got {parsed['beneficiary_name']}"
    print("[OK] All Italian Invoice Keyword Tests Passed!")

if __name__ == "__main__":
    test_full_pipeline()
    test_italian_invoice()
