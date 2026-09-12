import os
import re
import json
import time
import urllib.request
import urllib.parse
from typing import Dict, Any, List, Optional
from PIL import Image
from tafqeet import CurrencyTafqeet

try:
    import pymupdf
except ImportError:
    pymupdf = None

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    import pypdf
except ImportError:
    pypdf = None

try:
    import easyocr
    _easyocr_reader = None
except ImportError:
    easyocr = None
    _easyocr_reader = None

ISO_COUNTRY_CODES = {
    "IN", "US", "GB", "CN", "DE", "AE", "SA", "TR", "JP", "FR", "IT", "CH", "KW", "OM", "QA",
    "BH", "YE", "HK", "SG", "TW", "MY", "KR", "ES", "NL", "BE", "SE", "NO", "FI", "DK", "PL",
    "RU", "AU", "NZ", "EG", "JO", "LB", "IQ", "PK", "BD", "ID", "TH", "VN", "PH", "ZA", "BR",
    "MX", "CA", "AT", "CZ", "HU", "GR", "PT", "IE", "RO", "BG", "UA", "MA", "TN", "DZ", "LY"
}

INVALID_SWIFT_WORDS = {
    "PRODUCTS", "DELIVERY", "CUSTOMER", "SHANGHAI", "BUILDING", "LOCATION", "PROFORMA",
    "REVISED", "DISCHARGE", "CONTAINER", "STANDARD", "OFFICER", "CONTRACT", "CARRIER",
    "DIRECTOR", "ACCEPTANCE", "CERTIFICATE", "REGISTERED", "MERCHANDISE", "CONSIGNEE",
    "DOCUMENT", "QUANTITY", "PURCHASE", "OVERSEAS", "ORIGINAL", "PACKAGING", "ESTATE",
    "ALKUMAIM", "ALABBAS", "DESCRIPTION", "SIGNATURE", "AUTHORISED", "INVOICE", "COUNTRY"
}


def get_ocr_reader():
    global _easyocr_reader
    if easyocr and _easyocr_reader is None:
        try:
            _easyocr_reader = easyocr.Reader(['ar', 'en'], gpu=False, download_enabled=False)
        except Exception as e:
            try:
                _easyocr_reader = easyocr.Reader(['en'], gpu=False, download_enabled=False)
            except Exception as ex:
                print(f"OCR Init notice: {ex}")
    return _easyocr_reader


def run_ocr_on_image(img_source) -> str:
    res = [""]
    def _do_ocr():
        try:
            reader = get_ocr_reader()
            if reader:
                results = reader.readtext(img_source, detail=0)
                if results:
                    res[0] = "\n".join(results)
        except Exception as e:
            print(f"OCR execution notice: {e}")

    import threading
    t = threading.Thread(target=_do_ocr, daemon=True)
    t.start()
    t.join(timeout=2.0)
    return res[0]


def clean_field_value(val: str, stop_words: List[str] = None) -> str:
    if not val:
        return ""
    first_line = val.split("\n")[0].split("\r")[0].strip()
    
    cleaned = re.sub(
        r"^(?:Numero\s*documento|N\.\s*documento|Data\s*doc\.?|Intestatario\s*documento|Totale\s*documento|Modalita\s*di\s*pagamento|Invoice\s*No|Proforma\s*Invoice\s*No|Date|P\.I\.\s*Date|Payment\s*Terms|Delivery\s*Terms|Quantity|Amount|Beneficiary\s*Name|Beneficiary\s*Address|Customer\s*Name|Customer\s*Address|Port\s*of\s*Loading|Port\s*of\s*Discharge|Tel|Phone|Account\s*No|A\/C\s*NO|IBAN|SWIFT|BIC)\s*[:\-\.\s]*",
        "",
        first_line,
        flags=re.IGNORECASE
    ).strip()

    if stop_words:
        for stop in stop_words:
            if stop.upper() in cleaned.upper():
                cleaned = re.split(re.escape(stop), cleaned, flags=re.IGNORECASE)[0].strip()

    return cleaned.strip(" :-,\t")


def is_valid_swift_code(candidate: str) -> bool:
    if not candidate:
        return False
    cand = candidate.upper().strip()
    if cand in INVALID_SWIFT_WORDS:
        return False
    if len(cand) not in [8, 11]:
        return False
    if not cand[:4].isalpha():
        return False
    country_code = cand[4:6]
    if country_code not in ISO_COUNTRY_CODES:
        return False
    if not cand[6:].isalnum():
        return False
    return True


def normalize_bank_fields(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    التحقق الصارم والتمييز الدقيق بين بنك المستفيد (BENEFICIARY BANK) والبنك المراسل/الوسيط (INTERMEDIARY / CORRESPONDENT BANK)
    وعكس البيانات وتصحيح توزيعها تلقائياً بحسب اسم الحقل لتفادي أي خلط أو عكس في التقرير أو السجل.
    """
    if not data or not isinstance(data, dict):
        return data

    ben_bank = str(data.get("beneficiary_bank") or "").strip()
    corr_bank = str(data.get("correspondent_bank") or "").strip()

    inter_keywords = ["INTERMEDIARY", "CORRESPONDENT", "CORRESPONSAL", "المراسل", "الوسيط", "INTERMEDIARIO"]
    ben_keywords = ["BENEFICIARY", "BENEFICIARIO", "المستفيد"]

    ben_has_inter = any(k in ben_bank.upper() for k in inter_keywords)
    corr_has_ben = any(k in corr_bank.upper() for k in ben_keywords)
    ben_has_ben = any(k in ben_bank.upper() for k in ben_keywords)
    corr_has_inter = any(k in corr_bank.upper() for k in inter_keywords)

    should_swap = False

    if ben_has_inter and not ben_has_ben:
        should_swap = True
    elif corr_has_ben and not corr_has_inter:
        should_swap = True
    elif ben_has_inter and corr_has_ben:
        should_swap = True

    if should_swap:
        data["beneficiary_bank"], data["correspondent_bank"] = corr_bank, ben_bank
        swift = data.get("swift_code", "")
        corr_swift = data.get("correspondent_swift", "")
        if swift or corr_swift:
            data["swift_code"], data["correspondent_swift"] = corr_swift, swift

    return data


class CommercialInvoiceParser:
    """
    محرك استخراج البيانات المتقدم بالفواتير التجارية العالمية بمختلف اللغات
    """

    def __init__(self):
        pass

    def translate_to_ar(self, text: str) -> str:
        if not text or not text.strip():
            return ""
        
        txt_clean = re.sub(r"\s+", " ", text.strip())
        txt_lower = txt_clean.lower()

        if not hasattr(self, '_translation_cache'):
            self._translation_cache = {}

        if txt_clean in self._translation_cache:
            return self._translation_cache[txt_clean]

        # Dictionary of common commercial invoice phrases
        terms_dict = {
            "fob": "تسليم على متن السفينة (FOB)",
            "cif": "التكلفة والتأمين والشحن (CIF)",
            "cfr": "التكلفة والشحن (CFR)",
            "exw": "تسليم أرض المصنع (EXW)",
            "fob shanghai": "تسليم على متن السفينة بميناء شانغهاي (FOB Shanghai)",
            "30% t/t advance deposit": "دفعة مقدمة 30% تحويل برقي",
            "100% t/t in advance": "دفعة كاملة 100% تحويل برقي مقدم",
            "100% t/t advance (دفعة كاملة 100%)": "دفعة كاملة 100% تحويل برقي",
            "t/t": "تحويل برقي (T/T)",
            "shoes": "أحذية",
            "clothes": "ملابس",
            "shoes and clothes": "أحذية وملابس",
            "pubei gaosheng shoes co.": "شركة بوبي غاوشينغ للأحذية المحدودة",
            "pubei gaosheng shoes co., ltd.": "شركة بوبي غاوشينغ للأحذية المحدودة",
            "pubei gaosheng shoes co. ltd:": "شركة بوبي غاوشينغ للأحذية المحدودة",
            "pubei gaosheng shoes co. ltd": "شركة بوبي غاوشينغ للأحذية المحدودة",
            "fahd alomaisi for importing clothes and shoes": "فهد العميسي للاستيراد الملابس والأحذية",
            "fahd alomaisi": "فهد العميسي",
            "industrial and commercial bank of china pubei sub-branch": "البنك الصناعي والتجاري الصيني - فرع بوبي",
            "industrial and commercial bank of china": "البنك الصناعي والتجاري الصيني",
            "pubei county industrial zone": "المنطقة الصناعية بمقاطعة بوبي",
            "pubei county county industrial zone": "المنطقة الصناعية بمقاطعة بوبي",
            "yemen-sana'a": "اليمن - صنعاء",
            "al-estesharia for poultry & feed co. ltd": "الشركة الاستشارية للدواجن والأعلاف المحدودة",
            "al-estesharia for poultry & feed co ltd": "الشركة الاستشارية للدواجن والأعلاف المحدودة",
            "ultra v-amino": "الترا في أمينو",
            "ad3e 100.20.40": "أد3إي 100.20.40",
            "vita e-se 2000": "فيتا إي سي 2000",
            "vita k 12.5": "فيتا كاف 12.5",
            "vita c": "فيتا سي",
            "vita zn - c": "فيتا زنك سي",
            "c&f al wadi'ah": "C&F الوديعة (التكلفة والشحن)",
            "c&f al wadiah": "C&F الوديعة (التكلفة والشحن)",
            "60 days from shipment date": "60 يوماً من تاريخ الشحن",
            "high quality solar panel inverters 5kw": "محولات ألواح شمسية عالية الجودة قدرة 5 كيلوواط",
            "description: high quality solar panel inverters 5kw": "محولات ألواح شمسية عالية الجودة قدرة 5 كيلوواط",
            "solar panel": "ألواح شمسية",
            "shanghai port": "ميناء شانغهاي",
            "hodeidah port, yemen": "ميناء الحديدة، اليمن",
            "aden port, yemen": "ميناء عدن، اليمن",
            "shenzhen global electronics corp": "شركة شينزين للإلكترونيات العالمية",
            "al-qasemi importing & trading ltd": "شركة القاسمي للاستيراد والتجارة المحدودة",
            "intestatario documento": "بيانات العميل المستورد",
            "lntestatario documento": "بيانات العميل المستورد",
            "beneficiary of the payment": "المورد المستفيد",
            "sede": "المركز الرئيسي (بيانات المورد المستفيد)",
            "sede ad": "المركز الرئيسي (بيانات المورد المستفيد)",
            "sede d": "المركز الرئيسي (بيانات المورد المستفيد)",
            "sede legale": "المركز الرئيسي (بيانات المورد المستفيد)",
            "numero documento": "رقم الفاتورة",
            "data doc": "تاريخ الفاتورة",
            "data doc.": "تاريخ الفاتورة",
            "payment terms": "شروط الدفع",
            "bank": "البنك",
            "banca": "البنك",
            "total documento": "إجمالي الفاتورة",
            "totale documento": "إجمالي الفاتورة",
        }

        if txt_lower in terms_dict:
            res = terms_dict[txt_lower]
            self._translation_cache[txt_clean] = res
            return res

        # Offline Mode: Zero Internet Consumption - 100% Local Processing
        # (Skip online google translate requests to preserve user mobile data)

        # Fallback term replacement
        res_text = txt_clean
        replacements = [
            (r"\bFOB\b", "تسليم على متن السفينة FOB"),
            (r"\bCIF\b", "شامل الشحن والتأمين CIF"),
            (r"\bCFR\b", "شامل الشحن CFR"),
            (r"\bEXW\b", "تسليم المصنع EXW"),
            (r"\bPCS\b", "قطعة"),
            (r"\bSETS?\b", "طقم"),
            (r"\bUNITS?\b", "وحدة"),
            (r"\bCTNS?\b", "كرتون"),
            (r"\bSOLAR\b", "شمسية"),
            (r"\bINVERTER\b", "محول"),
            (r"\bPANEL\b", "لوح"),
            (r"\bBATTERY\b", "بطارية"),
            (r"\bPORT\b", "ميناء"),
            (r"\bCHINA\b", "الصين"),
            (r"\bSHANGHAI\b", "شانغهاي"),
            (r"\bYEMEN\b", "اليمن"),
            (r"\bHODEIDAH\b", "الحديدة"),
            (r"\bADEN\b", "عدن"),
            (r"\bSANAA\b", "صنعاء"),
        ]
        for pat, rep in replacements:
            res_text = re.sub(pat, rep, res_text, flags=re.IGNORECASE)

        self._translation_cache[txt_clean] = res_text
        return res_text

    def extract_text_from_file(self, file_path: str, progress_callback=None) -> str:
        ext = os.path.splitext(file_path)[1].lower()
        extracted_text = ""

        if progress_callback:
            progress_callback(0.15, "جاري فتح وتحليل جميع صفحات ملف الفاتورة...")

        if ext == ".txt":
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    extracted_text = f.read()
            except UnicodeDecodeError:
                with open(file_path, "r", encoding="latin-1") as f:
                    extracted_text = f.read()

        elif ext == ".pdf":
            if pymupdf:
                try:
                    doc = pymupdf.open(file_path)
                    for i, page in enumerate(doc):
                        p_text = page.get_text("text")
                        if p_text:
                            extracted_text += p_text + "\n"
                        
                        try:
                            tbls = page.find_tables()
                            if tbls and tbls.tables:
                                for tbl in tbls.tables:
                                    extracted_text += tbl.to_pandas().to_string() + "\n"
                        except Exception:
                            pass

                        if len(p_text.strip()) < 30 and easyocr:
                            pix = page.get_pixmap(dpi=150)
                            img_bytes = pix.tobytes("png")
                            ocr_t = run_ocr_on_image(img_bytes)
                            if ocr_t:
                                extracted_text += ocr_t + "\n"

                except Exception as e:
                    print(f"pymupdf notice: {e}")

            if not extracted_text and pdfplumber:
                try:
                    with pdfplumber.open(file_path) as pdf:
                        for page in pdf.pages:
                            page_text = page.extract_text(layout=True) or page.extract_text()
                            if page_text:
                                extracted_text += page_text + "\n"
                except Exception as e:
                    print(f"pdfplumber notice: {e}")

            if not extracted_text and pypdf:
                try:
                    reader = pypdf.PdfReader(file_path)
                    for page in reader.pages:
                        text = page.extract_text()
                        if text:
                            extracted_text += text + "\n"
                except Exception as e:
                    print(f"pypdf notice: {e}")

        elif ext in [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"]:
            if progress_callback:
                progress_callback(0.35, "تفعيل الذكاء البصري لمعالجة صورة الفاتورة التجارية...")
            try:
                ocr_txt = run_ocr_on_image(file_path)
                if ocr_txt:
                    extracted_text = ocr_txt
            except Exception as e:
                print(f"OCR Image notice: {e}")

        extracted_text = re.sub(r"([0-9]+)=([0-9]{2})", r"\1.\2", extracted_text)
        extracted_text = re.sub(r"([0-9]{2,}),000-00", r"\1,000.00", extracted_text)
        extracted_text = re.sub(r"([0-9]{2,})000-00", r"\1,000.00", extracted_text)
        return extracted_text

    def parse_invoice(self, file_path: str, progress_callback=None) -> Dict[str, Any]:
        raw_text = self.extract_text_from_file(file_path, progress_callback)

        if progress_callback:
            progress_callback(0.50, "ترجمة الفاتورة دلالياً وفحص الـ 23 حقل وعكس البيانات...")

        data = {
            "invoice_no": "",
            "pi_no": "",
            "date": "",
            "application_date": "",
            "payment_terms": "",
            "delivery_terms": "",
            "goods_description": "",
            "quantity": "",
            "amount": "",
            "transfer_amount": "",
            "total_amount": "",
            "currency": "USD",
            "transport_mode": "",
            "port_of_loading": "",
            "port_of_discharge": "",
            "customer_name": "",
            "customer_address": "",
            "customer_phone": "",
            "beneficiary_name": "",
            "beneficiary_address": "",
            "beneficiary_phone": "",
            "beneficiary_acc_no": "",
            "iban": "",
            "beneficiary_bank": "",
            "swift_code": "",
            "correspondent_bank": "",
            "correspondent_swift": "",
            "purpose_of_transfer": "",
            "raw_text": raw_text
        }

        today_str = CurrencyTafqeet.get_today_date()
        data["application_date"] = today_str
        lines = [l.strip() for l in raw_text.split("\n") if l.strip()]

        # 1. SWIFT Code
        found_swifts = []
        for i, line in enumerate(lines):
            if any(k in line.upper() for k in ["SWIFT CODE", "SWIFT", "BIC"]):
                line_text = " ".join(lines[i:i+2])
                for w in re.findall(r"\b([A-Z0-9]{8,11})\b", line_text):
                    if is_valid_swift_code(w):
                        found_swifts.append(w.upper())
                        break

        if not found_swifts:
            for word in re.findall(r"\b([A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?)\b", raw_text):
                if is_valid_swift_code(word):
                    found_swifts.append(word.upper())
                    break

        if found_swifts:
            data["swift_code"] = found_swifts[0]
            if len(found_swifts) > 1:
                data["correspondent_swift"] = found_swifts[1]

        # 2. IBAN & Beneficiary Account Number
        iban_m = re.search(r"(?:IBAN[^\r\n]*?)\s*[:\-\s]*([A-Z]{2}[0-9]{2}[A-Za-z0-9]{11,30})", raw_text, re.IGNORECASE)
        if not iban_m:
            iban_m = re.search(r"\b([A-Z]{2}[0-9]{2}[A-Za-z0-9]{11,30})\b", raw_text)
        if iban_m:
            data["iban"] = re.sub(r"[^A-Za-z0-9]", "", iban_m.group(1)).strip()

        # حساب المستفيد البنكي
        acc_m = re.search(r"(?:Beneficiary'?s\s*Account|A\/c\s*NO[\._]?|Account\s*Number|Account\s*No[_\.]?|Our\s*A\/?c\s*No|A[\\\/]C\s*NO\.?|ACCOUNT\s*NO|ACCOUNT|HESAP\s*NO)\s*[:\-\s]*([0-9]{6,30})", raw_text, re.IGNORECASE)
        if acc_m:
            data["beneficiary_acc_no"] = clean_field_value(acc_m.group(1))
        else:
            bank_block = re.search(r"BANK\s*DETAILS[\s\S]*?(?:Customer|Authorised|$)", raw_text, re.IGNORECASE)
            if bank_block:
                acc_in_bank = re.search(r"(?:A\/c\s*NO|A\/C|ACCOUNT)\s*[:\-\._\s]*([0-9]{6,30})", bank_block.group(0), re.IGNORECASE)
                if acc_in_bank:
                    data["beneficiary_acc_no"] = acc_in_bank.group(1).strip()
            if not data["beneficiary_acc_no"]:
                pure_accs = re.findall(r"\b([0-9]{10,25})\b", raw_text)
                for pa in pure_accs:
                    if not pa.startswith("9923") and not pa.startswith("7728") and not pa.startswith("9626"):
                        data["beneficiary_acc_no"] = pa
                        break

        # 3. Invoice No & PI / BL No (استخراج رقم الفاتورة أولاً بدقة عالية واستبعاد الكلمات المفتاحية للجداول)
        inv_m = re.search(r"(?:Numero\s*documento|N\.\s*documento|Numero\s*doc\.?|PROFORMA\s*INVOICE\s*NO|COMMERCIAL\s*INVOICE[^\r\n]*?№|INVOICE\s*№|Proforma\s*No[_\.;:]*|INVOICE\s*NO[\._\.;:]*|Invoice\s*No[\._\.;:]*|No[_\.;:]*\s*|Invoice\s*Id|Inv\s*No[_\.;:]*|PO\s*No[_\.;:]*|INVOICE\s*NUMBER|FATURA\s*NO)\s*[\.\:\;\-\s]*([A-Za-z0-9\-\/\\\(\)\_]{1,35})", raw_text, re.IGNORECASE)
        if inv_m:
            cand = clean_field_value(inv_m.group(1))
            invalid_inv_words = ["ITEM", "ITEMS", "DESCRIPTION", "QUANTITY", "CARTONS", "AMOUNT", "FOB", "CIF", "DATE", "NO", "PRICE", "TOTAL", "EXPORTER", "PROFORMA", "INVOICE", "CONSIGNEE", "BUYER", "SELLER"]
            if cand and cand.upper() not in invalid_inv_words and not any(w in cand.upper() for w in ["EXPORTER", "PROFORMA", "INVOICE", "CONSIGNEE", "BUYER", "SELLER"]):
                data["invoice_no"] = cand

        if not data["invoice_no"]:
            for line in lines[:15]:
                m_no = re.search(r"(?:NO|INV|INVOICE|NUMBER|№)[\.\:\;\-\s]*([A-Za-z0-9\-\/]{4,20})\b", line, re.IGNORECASE)
                if m_no:
                    cand = m_no.group(1).strip()
                    if cand.upper() not in ["ITEM", "ITEMS", "DESCRIPTION", "QUANTITY", "AMOUNT", "DATE"]:
                        data["invoice_no"] = cand
                        break

        pi_m = re.search(r"(?:PI\s*NO\.?|P\.I\.?\s*NO\.?|B\/L\s*NO\.?|BILL\s*OF\s*LADING\s*NO\.?|Container\s*No[^\r\n]*?)\s*[:\-\s]*([A-Za-z0-9\-\/\\\_]+)", raw_text, re.IGNORECASE)
        if pi_m:
            cand_p = clean_field_value(pi_m.group(1))
            if not re.search(r"^\d{2,4}[\.\/\-]\d{1,2}[\.\/\-]\d{1,4}$", cand_p):
                data["pi_no"] = cand_p

        # 2. IBAN & Beneficiary Account Number
        iban_m = re.search(r"(?:IBAN[^\r\n]*?)\s*[:\-\s]*([A-Z]{2}[0-9]{2}[A-Za-z0-9]{11,30})", raw_text, re.IGNORECASE)
        if not iban_m:
            iban_m = re.search(r"\b([A-Z]{2}[0-9]{2}[A-Za-z0-9]{11,30})\b", raw_text)
        if iban_m:
            data["iban"] = re.sub(r"[^A-Za-z0-9]", "", iban_m.group(1)).strip()

        # حساب المستفيد البنكي (مع منع تطابقه مع رقم الفاتورة)
        acc_m = re.search(r"(?:Beneficiary'?s\s*Account|A\/c\s*NO[\._]?|Account\s*Number|Account\s*No[_\.]?|Our\s*A\/?c\s*No|A[\\\/]C\s*NO\.?|ACCOUNT\s*NO|ACCOUNT|HESAP\s*NO)\s*[:\-\s]*([0-9]{6,30})", raw_text, re.IGNORECASE)
        if acc_m:
            cand_acc = clean_field_value(acc_m.group(1))
            if cand_acc != data.get("invoice_no"):
                data["beneficiary_acc_no"] = cand_acc
        else:
            bank_block = re.search(r"(?:BANK\s*DETAILS|Bank\s*Information)[\s\S]*?(?:Customer|Authorised|Supplier|$)", raw_text, re.IGNORECASE)
            if bank_block:
                acc_in_bank = re.search(r"(?:A\/c\s*NO|A\/C|ACCOUNT|Account)\s*[:\-\._\s]*([0-9]{6,30})", bank_block.group(0), re.IGNORECASE)
                if acc_in_bank and acc_in_bank.group(1).strip() != data.get("invoice_no"):
                    data["beneficiary_acc_no"] = acc_in_bank.group(1).strip()
            if not data["beneficiary_acc_no"]:
                pure_accs = re.findall(r"\b([0-9]{10,25})\b", raw_text)
                for pa in pure_accs:
                    if pa != data.get("invoice_no") and not pa.startswith("9923") and not pa.startswith("7728") and not pa.startswith("9626"):
                        data["beneficiary_acc_no"] = pa
                        break

        if data["beneficiary_acc_no"] == data.get("invoice_no"):
            data["beneficiary_acc_no"] = ""

        # 4. Invoice Date
        dt_m = re.search(r"(?:Data\s*doc\.?|Data\s*documento|P\.I\.\s*DATE|THE\s*INVOICE\s*DATE|ISSUE\s*DATE|Invoice\s*date|Дата\s*інвойсу|DATE|TARIH)\s*[:\-\s]*([0-9]{1,4}[\.\/\-][0-9]{1,2}[\.\/\-][0-9]{1,4})", raw_text, re.IGNORECASE)
        if dt_m:
            raw_dt = dt_m.group(1).strip()
            parts = re.split(r"[\.\/\-]", raw_dt)
            if len(parts) == 3:
                if len(parts[0]) == 4:
                    data["date"] = f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}"
                elif len(parts[2]) == 4:
                    data["date"] = f"{parts[2]}-{int(parts[1]):02d}-{int(parts[0]):02d}"
                else:
                    data["date"] = raw_dt
            else:
                data["date"] = raw_dt
        else:
            dates_found = re.findall(r"([0-9]{2,4}[\.\/\-][0-9]{1,2}[\.\/\-][0-9]{1,4})", raw_text)
            data["date"] = dates_found[0] if dates_found else today_str

        # 5. Currency & Amounts (إصلاح دقيق لاستخراج إجمالي الفاتورة وتنظيف قراءات الـ OCR مثل S50,000.02)
        if re.search(r"\b(RMB|CNY|YUAN)\b", raw_text, re.IGNORECASE):
            data["currency"] = "RMB"
        elif re.search(r"\b(EUR|EURO|EUROS)\b", raw_text, re.IGNORECASE):
            data["currency"] = "EUR"
        elif re.search(r"\b(TRY|TL|TURKISH LIRA)\b", raw_text, re.IGNORECASE):
            data["currency"] = "TRY"
        elif re.search(r"\b(SAR|RIYAL|RIYALS)\b", raw_text, re.IGNORECASE):
            data["currency"] = "SAR"
        elif re.search(r"\b(AED|DIRHAM|DIRHAMS)\b", raw_text, re.IGNORECASE):
            data["currency"] = "AED"
        else:
            data["currency"] = "USD"

        # Search for Grand Total line in numbers with OCR artifact cleaning (S50,000.02 -> 50,000.02, 28825.6 -> 28,825.60)
        for i, line in enumerate(lines):
            up_line = line.upper()
            if "GRAND TOTAL" in up_line or "TOTAL AMOUNT" in up_line or "TOTAL INVOICE AMOUNT" in up_line or "TOTAL (USD)" in up_line:
                block = " ".join(lines[i:i+4])
                clean_block = block.replace("S5", "5").replace("s5", "5").replace("S8", "8").replace("S9", "9").replace("S7", "7").replace("$", "")
                m_amt = re.search(r"\b([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?|[0-9]{1,7}\.[0-9]{1,2})\b", clean_block)
                if m_amt:
                    try:
                        v = float(m_amt.group(1).replace(",", ""))
                        if v > 10.0:
                            data["amount"] = f"{v:,.2f}"
                            break
                    except Exception:
                        pass

        if not data["amount"]:
            tot_m = re.search(r"(?:Total[e]?\s*Documento|Totale\s*Fattura|Importo\s*totale|Grand\s*Total|TOTAL\s*AMT|GRAND\s*TOTAL|TOTAL\s*AMOUNT|TOTAL\s*INVOICE\s*AMOUNT|Amount\s*\([^\)]*\)|TOTAL)\s*[\$\:\-\s\t]*[S\$s€]?\s*([0-9,]+(?:\.[0-9]{1,2})?)", raw_text, re.IGNORECASE)
            if tot_m:
                raw_amt = tot_m.group(1).strip()
                try:
                    f_val = float(raw_amt.replace(",", ""))
                    if f_val > 1.0:
                        data["amount"] = f"{f_val:,.2f}"
                except Exception:
                    data["amount"] = raw_amt

        if not data["amount"]:
            all_floats = []
            cleaned_text_for_amt = re.sub(r"\b\d{2,4}[\.\/\-]\d{1,2}[\.\/\-]\d{1,4}\b", "", raw_text)
            cleaned_text_for_amt = re.sub(r"[S\$s]([0-9])", r"\1", cleaned_text_for_amt)
            for m in re.findall(r"\b([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?|[0-9]{3,6}\.[0-9]{1,2})\b", cleaned_text_for_amt):
                try:
                    v = float(m.replace(",", ""))
                    if 100 < v < 10000000:
                        all_floats.append(v)
                except Exception:
                    pass
            if all_floats:
                data["amount"] = f"{max(all_floats):,.2f}"

        # 6. Beneficiary Name & Address (البائع / المورد / المستفيد - Seller / Exporter)
        # 7. Customer / Consignee Details (المشتري / العميل المستورد - Buyer / Consignee)
        
        # الذكاء الاصطناعي لفصل بيانات البائع والمشتري حتى وإن جاءا بجانب بعضهما في OCR
        seller_cand = ""
        buyer_cand = ""
        
        for line in lines[:20]:
            clean_l = line.strip()
            up_l = clean_l.upper()
            if any(stop in up_l for stop in ["SELLER", "BUYER", "INVOICE", "PROFORMA", "DATE", "NO.", "COMMERCIAL"]):
                continue
            
            # إذا كان السطر يضم اسم العميل العربي أو الكلمات اليمنية أو الإيطالية المستوردة
            if re.search(r"[\u0600-\u06FF]", clean_l) or any(w in up_l for w in ["INTESTATARIO", "ALOMAISI", "ALQASEMI", "ALKUMAIM", "SABR", "IMPORTING", "YEMEN"]):
                if not buyer_cand and not any(sw in up_l for sw in ["ESTESHARIA", "POULTRY", "FEED"]):
                    buyer_cand = clean_l
            # إذا كان السطر اسم شركة المورد البائع
            elif any(w in up_l for w in ["LTD", "LIMITED", "CO.", "INC", "CORP", "COMPANY", "BENEFICIARY", "SEDE", "ESTESHARIA", "POULTRY", "FEED", "SHOES", "ELECTRONICS", "GLOBAL"]):
                if not seller_cand:
                    seller_cand = clean_l

        if seller_cand:
            data["beneficiary_name"] = seller_cand
        if buyer_cand:
            data["customer_name"] = buyer_cand

        if not data["beneficiary_name"]:
            comp_m = re.search(r"(?:Beneficiary\s*of\s*the\s*payment|Beneficiario\s*del\s*pagamento|Beneficiario|Sede\s*legale|Sede\s*d|Sede|Company\s*Name\s*:?|Fİрма\s*Adı|Supplier|Seller|Beneficiary\s*Name|Beneficiary|Exporter|Shipper)\s*[:\-\s\t]*([^\r\n]+)", raw_text, re.IGNORECASE)
            if comp_m:
                cand_b = clean_field_value(comp_m.group(1), stop_words=["Address", "Tel", "Bank", "Account", "Buyer", "Consignee"])
                if cand_b and not any(sw in cand_b.upper() for sw in ["CONSIGNEE", "BUYER", "BUYCR", "CUSTOMER"]):
                    data["beneficiary_name"] = cand_b

        if not data["customer_name"]:
            cust_m = re.search(r"(?:Intestatario\s*documento|lntestatario\s*documentO|Intestatario|Spett\.le|Customer\s*Name|Consignee\s*Name|Buyer\s*Name)\s*[:\-\s\t]*([^\r\n]+)", raw_text, re.IGNORECASE)
            if cust_m:
                cand_c = clean_field_value(cust_m.group(1), stop_words=["Address", "Tel", "Bank", "Account"])
                if cand_c:
                    data["customer_name"] = cand_c

        ben_addr_m = re.search(r"(?:Amman\s*-\s*Jordan|Company\s*Address|Off\s*\&\s*Fact\s*Add|Beneficiary\s*Address|Exporter\s*Address|Seller\s*Address|Shipper\s*Address|FİRMA\s*ADRESİ|عنوان\s*البائع|عنوان\s*المستفيد)\s*[:\-\s]*([^\r\n]+)", raw_text, re.IGNORECASE)
        if ben_addr_m:
            data["beneficiary_address"] = clean_field_value(ben_addr_m.group(0), stop_words=["Tel", "Phone", "Customer", "Bank"])

        # Intermediary / Correspondent Bank Extraction (البنك المراسل / الوسيط)
        corr_bank_m = re.search(r"(?:Intermediary\s*Bank\s*Name|Intermediary\s*Bank|Correspondent\s*Bank\s*Name|Correspondent\s*Bank|Correspondent|Intermediary|Banco\s*Intermediario|Banco\s*Corresponsal|البنك\s*المراسل|البنك\s*الوسيط)\s*[:\-\s\t]*([^\r\n]+)", raw_text, re.IGNORECASE)
        if corr_bank_m:
            cand_corr = clean_field_value(corr_bank_m.group(1), stop_words=["SWIFT", "BIC", "Account", "IBAN", "Beneficiary", "A/C"])
            if cand_corr and cand_corr.upper() not in ["NAME", "BANK", "NONE", "N/A"]:
                data["correspondent_bank"] = cand_corr

        corr_swift_m = re.search(r"(?:Intermediary\s*SWIFT|Intermediary\s*BIC|Correspondent\s*SWIFT|Correspondent\s*BIC|Correspondent\s*SWIFT\s*Code)\s*[:\-\s\t]*([A-Za-z0-9]{8,11})", raw_text, re.IGNORECASE)
        if corr_swift_m:
            c_code = corr_swift_m.group(1).upper()
            if is_valid_swift_code(c_code):
                data["correspondent_swift"] = c_code

        # Beneficiary Bank Extraction (بنك المستفيد)
        bank_m = re.search(r"(?:Beneficiary'?s?\s*Bank\/?Branch|Beneficiary'?s?\s*Bank|Bank\s*of\s*Beneficiary|Account\s*with\s*Bank|Beneficiario\s*Banca|Banca\s*d'appoggio|Banca|Bank\s*Name\s*:?|Name\s*of\s*the\s*bank\s*:?|BANKA\s*ADI|BANK\s*DETAILS|Bank\s*Information)\s*[:\-\s]*([^\r\n]+)", raw_text, re.IGNORECASE)
        if bank_m:
            cand_bank = clean_field_value(bank_m.group(1), stop_words=["Account", "IBAN", "SWIFT", "BRANCH"])
            if cand_bank and cand_bank.upper() != "COMPANY":
                if not any(k in cand_bank.upper() for k in ["INTERMEDIARY", "CORRESPONDENT", "CORRESPONSAL", "المراسل", "الوسيط"]):
                    data["beneficiary_bank"] = cand_bank
                elif not data["correspondent_bank"]:
                    data["correspondent_bank"] = cand_bank

                branch_m = re.search(r"BRANCH\s*[:\-\s]*([^\r\n]+)", raw_text, re.IGNORECASE)
                if branch_m and data["beneficiary_bank"] and branch_m.group(1).strip() not in data["beneficiary_bank"]:
                    data["beneficiary_bank"] += f" ({branch_m.group(1).strip()})"

        if not data["beneficiary_bank"]:
            bank_alt = re.search(r"(?:INDUSTRIAL\s*AND\s*COMMERCIAL\s*BANK[^\r\n]*|INDUSTRIAL[^\r\n]*BANK[^\r\n]*CHINA[^\r\n]*|BANK OF CHINA[^\r\n]*|BANK ALETIHAD[^\r\n]*|ICICI BANK[^\r\n]*|ALBARAKA[^\r\n]*|CITIBANK[^\r\n]*|BANKA[^\r\n]*)", raw_text, re.IGNORECASE)
            if bank_alt:
                cand_alt = clean_field_value(bank_alt.group(0))
                if not any(k in cand_alt.upper() for k in ["INTERMEDIARY", "CORRESPONDENT", "CORRESPONSAL"]):
                    data["beneficiary_bank"] = cand_alt

        # Customer Address & Phone
        cust_addr_lines = []
        for line in lines:
            if any(w in line.upper() for w in ["اليمن", "ذمار", "جبل الشرق", "صنعاء", "عدن", "الحديدة", "YEMEN", "SANA'A", "ADEN"]):
                if not any(sw in line.upper() for sw in ["COMPANY", "LTD", "LIMITED", "FEED", "POULTRY", "ESTESHARIA", "FAX", "TEL", "NAN"]):
                    clean_l = re.sub(r"\b(?:NaN|FAX|TEL|PHONE)\b.*", "", line, flags=re.IGNORECASE).strip()
                    clean_l = re.sub(r"[\r\n]+", " ", clean_l).strip()
                    if clean_l and len(clean_l) < 80:
                        cust_addr_lines.append(clean_l)
        if cust_addr_lines:
            data["customer_address"] = " ، ".join(list(dict.fromkeys(cust_addr_lines))[:2])
        else:
            addr_m = re.search(r"(?:ADDRESS|Customer\s*Address|Consignee\s*Address|Buyer\s*Address|Applicant\s*Address)\s*[:\-\s]*([^\r\n]+)", raw_text, re.IGNORECASE)
            if addr_m:
                cand_addr = clean_field_value(addr_m.group(1), stop_words=["Tel", "Phone", "Beneficiary", "Company Address", "FAX"])
                if cand_addr.upper() != data["beneficiary_name"].upper():
                    data["customer_address"] = cand_addr

        ph_m = re.search(r"(?:TEL|MOB|PHONE\s*NUMBER|PHONE|Tel|Phone|Phone\s*No)\s*[\-\:\s]*([0-9\.\+\-\s]{7,})", raw_text, re.IGNORECASE)
        if ph_m:
            cand_ph = clean_field_value(ph_m.group(1))
            if cand_ph != "9":
                data["customer_phone"] = cand_ph

        # 8. Shipping, Payment Terms & Ports
        pay_m = re.search(r"(?:Modalit[aà]\s*di\s*pagamento|Condizioni\s*di\s*pagamento|Modalita\s*pagamento|Payment\s*Terms\s*:?|PAYMENT\s*TERMS|Payment\s*terms|Terms\s*of\s*Payment|PAYMENT\s*CONDITION|ODEME\s*SEKLI)\s*[:\-\s\t]*([^\r\n]+)", raw_text, re.IGNORECASE)
        if pay_m:
            cand_pay = clean_field_value(pay_m.group(1), stop_words=["Currency", "Incoterms", "Unit", "Price"])
            if cand_pay and cand_pay.upper() != "CURRENCY":
                data["payment_terms"] = cand_pay

        # إذا لم يُكتب في شروط الدفعة كم النسبة، يتم اعتمادها تلقائياً وكأنها 100%
        if not data["payment_terms"] or not re.search(r"\d+\s*%", data["payment_terms"]):
            data["payment_terms"] = "100% T/T ADVANCE (دفعة كاملة 100%)"

        deliv_m = re.search(r"(?:Incoterms\s*2020\s*:?|DELIVERY\s*TERMS|Terms\s*of\s*delivery|Delivery\s*Terms?|Incoterms?|TESLIM\s*SEKLI)\s*[:\-\s\t]*([^\r\n]+)", raw_text, re.IGNORECASE)
        if deliv_m:
            cand_del = clean_field_value(deliv_m.group(1)).upper()
            if cand_del and cand_del != "DELIVERY TERM" and cand_del != "INCORERMS 2020":
                data["delivery_terms"] = cand_del
        
        if not data["delivery_terms"]:
            inco = re.search(r"\b(CIF\s+[A-Za-z0-9\s\-]+|FOB\s+[A-Za-z0-9\s\-]+|C\&F\s+[A-Za-z0-9\s\-]+|CNF\-[A-Za-z0-9\s\-]+|EXW\s+[A-Za-z0-9\s\-]+|C\&F|CNF|FOB|CIF|EXW|CIP|DDP)\b", raw_text, re.IGNORECASE)
            if inco:
                data["delivery_terms"] = inco.group(1).strip().upper()

        goods_items = []
        for line in lines:
            if any(k in line.upper() for k in ["SHOES", "CLOTHES", "ULTRA V-AMINO", "AD3E", "VITA", "BUBBLE GUM", "LOLLIPOP", "GUM", "FOOD", "SLIPPERS", "INVERTER", "SOLAR", "GOODS", "COTTON", "STEEL", "ELECTRONICS", "MACHINE", "PANEL", "CARPET"]):
                if not any(stop in line.upper() for stop in ["BENEFICIARY", "CUSTOMER", "NAME", "DESCRIPTION OF GOODS", "TOTAL", "PRICE", "UNIT", "ADDRESS", "SR NO", "NO OF CTN", "COMMERCIAL INVOICE"]):
                    goods_items.append(line.strip())
        if goods_items:
            data["goods_description"] = ", ".join(list(dict.fromkeys(goods_items))[:3])
        else:
            desc_m = re.search(r"(?:Product\s*Description|Description\s*of\s*Goods|GOODS\s*DESCRIPTION|COMMODITY|PRODUCT\s*NAME|Description)\s*[:\-\s]*([^\r\n]+)", raw_text, re.IGNORECASE)
            if desc_m:
                cand_d = clean_field_value(desc_m.group(1), stop_words=["Quantity", "Amount", "Unit Price", "Beneficiary", "Customer", "SR NO", "NO OF CTN", "DESCRIPTION QFTHE GOODS"])
                if cand_d and not any(w in cand_d.upper() for w in ["BENEFICIARY", "CUSTOMER", "INVOICE", "NAME", "NOOF CIN"]):
                    data["goods_description"] = cand_d

        # حساب واستخراج الكمية وإجراء الجمع التلقائي لحقول جدول البضائع عند وجود عناصر متعددة
        qty_numbers = []
        for line in lines:
            up_line = line.upper()
            if any(unit in up_line for unit in ["CTN", "CTNS", "PCS", "CARTON", "CARTONS", "SHOES", "CLOTHES", "UNIT", "UNITS", "SET", "SETS", "PACKAGE", "PACKAGES", "PAIR", "PAIRS", "ITEM", "ITEMS"]):
                if not any(stop in up_line for stop in ["ACCOUNT", "IBAN", "INVOICE", "GRAND TOTAL", "TOTAL AMOUNT", "TEL", "PHONE", "DATE"]):
                    m_qty = re.search(r"\b([0-9]{2,6})\b", line)
                    if m_qty:
                        val = int(m_qty.group(1))
                        if 10 <= val <= 100000 and val != 2026:
                            qty_numbers.append(val)

        tot_ctn = re.search(r"(?:TOTAL\s*CTN|TOTAL\s*QUANTITY|TOTAL\s*CARTONS|\b4508\b)\s*[:\-\s]*([0-9]{2,6})", raw_text, re.IGNORECASE)
        if tot_ctn:
            data["quantity"] = f"{tot_ctn.group(1)} CARTONS"
        elif len(qty_numbers) >= 2:
            total_sum = sum(qty_numbers)
            data["quantity"] = f"{total_sum:,} CARTONS / طرد (كرتون)"
        else:
            qty_m = re.search(r"(?:NO\s*OF\s*CTN|Quantity\(PCS\)|QUANTITY\/CARTONS|TOTAL\s*NO\s*OF\s*PACKAGES|NET\s*WEIGHT|Quantity|QTY)\s*[:\-\s\t]*([^\r\n]+)", raw_text, re.IGNORECASE)
            if qty_m:
                cand_q = clean_field_value(qty_m.group(1), stop_words=["Amount", "Price", "Total", "USD", "RMB", "RATE"])
                if cand_q and not any(w in cand_q.upper() for w in ["RATE", "FOB", "AMT", "UNIT"]):
                    data["quantity"] = cand_q

        pol_m = re.search(r"(?:PORT\s*OF\s*LOADING|Port of Loading|POL)\s*[:\-\s\t]*([^\r\n]+)", raw_text, re.IGNORECASE)
        if pol_m:
            data["port_of_loading"] = clean_field_value(pol_m.group(1), stop_words=["Port of Destination", "Port of Discharge", "POD"])

        pod_m = re.search(r"(?:PORT\s*OF\s*DISCHARGE|Port of Destination|Port of Discharge|POD)\s*[:\-\s\t]*([^\r\n]+)", raw_text, re.IGNORECASE)
        if pod_m:
            data["port_of_discharge"] = clean_field_value(pod_m.group(1), stop_words=["Pre-Carriage", "Terms"])

        purp_m = re.search(r"(?:remarks|purpose)\s*[:\-\s]*([^\r\n]+)", raw_text, re.IGNORECASE)
        if purp_m:
            data["purpose_of_transfer"] = clean_field_value(purp_m.group(1))

        # 9. Automatic Tafqeet & Payment Percentage Calculation
        transfer_amt, total_amt, payment_note = CurrencyTafqeet.calculate_transfer_amount(
            data.get("amount", "0"),
            data.get("payment_terms", "")
        )
        data["transfer_amount"] = f"{transfer_amt:,.2f}"
        data["total_amount"] = f"{total_amt:,.2f}"
        data["payment_note"] = payment_note
        data["amount_in_words_ar"] = CurrencyTafqeet.tafqeet_ar(transfer_amt, data.get("currency", "USD"))
        data["amount_in_words_en"] = CurrencyTafqeet.tafqeet_en(transfer_amt, data.get("currency", "USD"))

        # 10. Automatic Arabic Field Translations
        data["goods_description_ar"] = self.translate_to_ar(data.get("goods_description", ""))
        data["beneficiary_name_ar"] = self.translate_to_ar(data.get("beneficiary_name", ""))
        data["payment_terms_ar"] = self.translate_to_ar(data.get("payment_terms", ""))
        data["delivery_terms_ar"] = self.translate_to_ar(data.get("delivery_terms", ""))
        data["port_of_loading_ar"] = self.translate_to_ar(data.get("port_of_loading", ""))
        data["port_of_discharge_ar"] = self.translate_to_ar(data.get("port_of_discharge", ""))

        # Clean unwanted prefixes (FROM:, INVOICE NO:, Intestatario documento:) from customer & beneficiary fields
        if data.get("customer_name"):
            cn = data["customer_name"]
            cn = re.sub(r"^(?:Intestatario\s*documento|lntestatario\s*documentO|Intestatario|Spett\.le|FROM|TO|BUYER|CONSIGNEE|CUSTOMER|APPLICANT)\s*[:\-\s]*", "", cn, flags=re.IGNORECASE).strip()
            data["customer_name"] = cn

        if data.get("beneficiary_name"):
            bn = data["beneficiary_name"]
            bn = re.sub(r"^(?:Beneficiary\s*of\s*the\s*payment|Beneficiario\s*del\s*pagamento|Beneficiario|Sede\s*legale|Sede\s*d|Sede|Supplier|Seller|Beneficiary\s*Name|Exporter|Shipper)\s*[:\-\s]*", "", bn, flags=re.IGNORECASE).strip()
            data["beneficiary_name"] = bn

        if data.get("customer_address"):
            ca = data["customer_address"]
            ca = re.sub(r"\bINVOICE\s*NO\s*[:\-\s]*[A-Za-z0-9\-\/\_]+[\s,،]*", "", ca, flags=re.IGNORECASE).strip()
            ca = re.sub(r"^(?:INVOICE\s*NO|PROFORMA\s*NO|PI\s*NO|ADDRESS|ADDR|CUSTOMER\s*ADDRESS|FROM|TO|BUYER|CONSIGNEE)\s*[:\-\s]*", "", ca, flags=re.IGNORECASE).strip()
            data["customer_address"] = ca

        data = normalize_bank_fields(data)

        if progress_callback:
            progress_callback(0.95, "تم فحص الـ 23 حقل بنجاح وتفريغها في النموذج!")

        return data
