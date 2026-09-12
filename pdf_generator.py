import os
import re
import textwrap
from typing import Dict, Any
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

import arabic_reshaper
from bidi.algorithm import get_display

from template_manager import TemplateManager
from tafqeet import CurrencyTafqeet
from parser import normalize_bank_fields


class SWIFTPDFGenerator:
    """
    محرك إنشاء القالب الرسمي المعتمد لبنك القاسمي للتمويل الأصغر الإسلامي (صفحتين A4 ممتلئتين تماماً)
    (Qasemi Islamic Microfinance Bank - Official 2-Page A4 Full-Page Layout)
    مطابق تماماً للقالب الأصلي 100% بالترتيب والتفقيط الصحيح من اليمين إلى اليسار
    """

    def __init__(self):
        self.styles = getSampleStyleSheet()
        self.tmpl_mgr = TemplateManager()
        self.setup_fonts()

    def setup_fonts(self):
        self.font_regular = "Helvetica"
        self.font_bold = "Helvetica-Bold"

        segoe_reg = "C:\\Windows\\Fonts\\segoeui.ttf"
        segoe_bold = "C:\\Windows\\Fonts\\segoeuib.ttf"
        arial_reg = "C:\\Windows\\Fonts\\arial.ttf"
        arial_bold = "C:\\Windows\\Fonts\\arialbd.ttf"

        if os.path.exists(segoe_reg):
            try:
                pdfmetrics.registerFont(TTFont("ArabicFont", segoe_reg))
                self.font_regular = "ArabicFont"
            except Exception as e:
                print(f"Error registering Segoe UI regular font: {e}")
        elif os.path.exists(arial_reg):
            try:
                pdfmetrics.registerFont(TTFont("ArabicFont", arial_reg))
                self.font_regular = "ArabicFont"
            except Exception as e:
                print(f"Error registering regular font: {e}")

        if os.path.exists(segoe_bold):
            try:
                pdfmetrics.registerFont(TTFont("ArabicFont-Bold", segoe_bold))
                self.font_bold = "ArabicFont-Bold"
            except Exception as e:
                print(f"Error registering Segoe UI bold font: {e}")
        elif os.path.exists(arial_bold):
            try:
                pdfmetrics.registerFont(TTFont("ArabicFont-Bold", arial_bold))
                self.font_bold = "ArabicFont-Bold"
            except Exception as e:
                print(f"Error registering bold font: {e}")

    def ar(self, text: str) -> str:
        """
        إعادة تشكيل وتوجيه النص العربي لمنع انعكاس الكلمات أو الأحرف في ReportLab
        """
        if not text:
            return ""
        try:
            txt_str = str(text).strip()
            if not re.search(r"[\u0600-\u06FF]", txt_str):
                return txt_str
            
            lines = txt_str.split("\n")
            reshaped_lines = []
            for line in lines:
                if re.search(r"[\u0600-\u06FF]", line):
                    reshaped_lines.append(get_display(arabic_reshaper.reshape(line)))
                else:
                    reshaped_lines.append(line)
            return "\n".join(reshaped_lines)
        except Exception:
            return str(text)

    def ar_multiline(self, text: str, font_name: str = None, font_size: float = 7.0, max_pts: float = 545) -> str:
        """
        تقسيم النص العربي الطويل بحسب العرض الفعلي بالنقاط ليملأ السطر الأول كاملاً إلى نهاية الحقل (545pt out of 563pt)
        """
        if not text:
            return ""
        try:
            f_name = font_name or self.font_regular
            words = str(text).strip().split()
            lines = []
            current_line = []
            
            for word in words:
                test_line = " ".join(current_line + [word])
                reshaped = get_display(arabic_reshaper.reshape(test_line))
                w_pts = pdfmetrics.stringWidth(reshaped, f_name, font_size)
                if w_pts <= max_pts:
                    current_line.append(word)
                else:
                    if current_line:
                        lines.append(" ".join(current_line))
                    current_line = [word]
            if current_line:
                lines.append(" ".join(current_line))
                
            reshaped_lines = [get_display(arabic_reshaper.reshape(l)) for l in lines]
            return "<br/>".join(reshaped_lines)
        except Exception:
            return self.ar(text)

    def generate_pdf(self, data: Dict[str, Any], output_path: str) -> str:
        """
        توليد ملف الـ PDF الرسمي المكون من صفحتين A4 ممتلئتين تماماً ومطابقتين للنموذج الأصلي
        """
        data = normalize_bank_fields(data)
        config = self.tmpl_mgr.load_template()

        out_dir = os.path.dirname(output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            rightMargin=16,
            leftMargin=16,
            topMargin=10,
            bottomMargin=10
        )

        elements = []

        logo_path = os.path.join(os.path.dirname(__file__), "assets", "qasemi_bank_logo.png")
        if not os.path.exists(logo_path):
            logo_path = os.path.join(os.path.dirname(__file__), "qasemi_logo.jpg")

        cell_reg = ParagraphStyle('CellReg', fontName=self.font_regular, fontSize=8.5, leading=11, alignment=1)
        cell_bold = ParagraphStyle('CellBold', fontName=self.font_bold, fontSize=8.5, leading=11, textColor=colors.HexColor("#1A202C"))
        cell_ar = ParagraphStyle('CellAr', fontName=self.font_bold, fontSize=8.5, leading=11, alignment=2, textColor=colors.HexColor("#1A202C"))
        cell_en = ParagraphStyle('CellEn', fontName=self.font_bold, fontSize=8.5, leading=11, alignment=0, textColor=colors.HexColor("#1A202C"))

        # ====================================================
        #  PAGE 1: OFFICIAL QASEMI BANK FOREIGN TRANSFER ORDER
        # ====================================================

        # 1. Header Banner (طلب إصدار حوالة خارجية | FOREIGN TRANSFER ORDER)
        logo_img = None
        if os.path.exists(logo_path):
            try:
                logo_img = RLImage(logo_path, width=200, height=48)
            except Exception:
                logo_img = Paragraph(f"<b>{self.ar('بنك القاسمي للتمويل الأصغر الإسلامي')}</b><br/><b>QASEMI ISLAMIC MICROFINANCE BANK</b>", cell_ar)
        else:
            logo_img = Paragraph(f"<b>{self.ar('بنك القاسمي للتمويل الأصغر الإسلامي')}</b><br/><b>QASEMI ISLAMIC MICROFINANCE BANK</b>", cell_ar)

        header_title_p = Paragraph(
            f"<font color='white' size=13><b>{self.ar('طلب إصدار حوالة خارجية')}</b></font><br/>"
            f"<font color='white' size=10><b>FOREIGN TRANSFER ORDER</b></font>",
            ParagraphStyle('HBox', fontName=self.font_bold, alignment=1, leading=16)
        )

        header_table = Table([[logo_img, header_title_p]], colWidths=[275, 288])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('BACKGROUND', (1, 0), (1, 0), colors.HexColor("#DC2626")),
            ('PADDING', (1, 0), (1, 0), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(header_table)
        elements.append(Spacer(1, 4))

        # 2. Top Info Bar (التاريخ : | الموافق : | الفرع : | مرجع الحوالة من اليمين لليسار)
        greg_dt = data.get("application_date") or data.get("date") or CurrencyTafqeet.get_today_date()
        hijri_dt = CurrencyTafqeet.get_hijri_date(greg_dt)
        ref_no = data.get("invoice_no") or ""
        branch_name = data.get("branch_name") or "المركز الرئيسي فرع عدن"

        lbl_style = ParagraphStyle(
            'TopInfoLbl',
            fontName=self.font_bold,
            fontSize=8.5,
            leading=11,
            alignment=1,
            textColor=colors.white
        )
        val_style = ParagraphStyle(
            'TopInfoVal',
            fontName=self.font_bold,
            fontSize=8.5,
            leading=11,
            alignment=1,
            textColor=colors.HexColor("#1A202C")
        )
        branch_val_style = ParagraphStyle(
            'BranchValStyle',
            fontName=self.font_bold,
            fontSize=7.8,
            leading=10,
            alignment=1,
            textColor=colors.HexColor("#1A202C")
        )

        top_info_data = [
            [
                Paragraph(f"<b>{ref_no}</b>", val_style),
                Paragraph(f"<b>{self.ar('مرجع الحوالة')}</b>", lbl_style),
                Paragraph(f"<b>{self.ar(branch_name)}</b>", branch_val_style),
                Paragraph(f"<b>{self.ar('الفرع:')}</b>", lbl_style),
                Paragraph(f"<b>{self.ar(hijri_dt)}</b>", val_style),
                Paragraph(f"<b>{self.ar('الموافق:')}</b>", lbl_style),
                Paragraph(f"<b>{greg_dt}</b>", val_style),
                Paragraph(f"<b>{self.ar('التاريخ:')}</b>", lbl_style),
            ]
        ]
        top_info_tbl = Table(top_info_data, colWidths=[68, 58, 126, 36, 114, 42, 75, 44])
        top_info_tbl.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
            ('BACKGROUND', (1, 0), (1, 0), colors.HexColor("#475569")),
            ('BACKGROUND', (3, 0), (3, 0), colors.HexColor("#475569")),
            ('BACKGROUND', (5, 0), (5, 0), colors.HexColor("#475569")),
            ('BACKGROUND', (7, 0), (7, 0), colors.HexColor("#475569")),
            ('BACKGROUND', (0, 0), (0, 0), colors.HexColor("#F8FAFC")),
            ('BACKGROUND', (2, 0), (2, 0), colors.HexColor("#F8FAFC")),
            ('BACKGROUND', (4, 0), (4, 0), colors.HexColor("#F8FAFC")),
            ('BACKGROUND', (6, 0), (6, 0), colors.HexColor("#F8FAFC")),
            ('PADDING', (0, 0), (-1, -1), 3.0),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(top_info_tbl)
        elements.append(Spacer(1, 4))

        # 3. Instruction Header Bar (عربي على اليمين | إنجليزي على اليسار)
        instr_ar = self.ar("الرجاء إصدار حوالة خارجية بياناتها كما يلي")
        instr_en = "PLEASE ISSUE A FOREIGN TRANSFER AS FOLLOWS"
        instr_p = Paragraph(
            f"<b><font color='white'>{instr_en} &nbsp;&nbsp;&nbsp;|&nbsp;&nbsp;&nbsp; {instr_ar}</font></b>",
            ParagraphStyle('InstrP', fontName=self.font_bold, fontSize=8.5, alignment=1)
        )
        instr_tbl = Table([[instr_p]], colWidths=[563])
        instr_tbl.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#475569")),
            ('PADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(instr_tbl)
        elements.append(Spacer(1, 4))

        # 4. Transfer Amount & Tafqeet Box (من اليمين إلى اليسار: عملة الحوالة | مبلغ الحوالة رقماً | المبلغ بالحروف فقط)
        t_amt = data.get("transfer_amount") or data.get("amount") or ""
        curr = data.get("currency") or "USD"
        tafq_ar = data.get("amount_in_words_ar") or ""
        tafq_en = data.get("amount_in_words_en") or ""

        amt_box_data = [
            [
                Paragraph(f"<b>{self.ar('المبلغ بالحروف فقط')}<br/>Amount in words only</b>", ParagraphStyle('ACell3', fontName=self.font_bold, fontSize=8, alignment=1)),
                Paragraph(f"<b>{self.ar('مبلغ الحوالة رقماً')}<br/>Transfer amount</b>", ParagraphStyle('ACell2', fontName=self.font_bold, fontSize=8, alignment=1)),
                Paragraph(f"<b>{self.ar('عملة الحوالة')}<br/>Transfer currency</b>", ParagraphStyle('ACell1', fontName=self.font_bold, fontSize=8, alignment=1)),
            ],
            [
                Paragraph(f"<b>{self.ar(tafq_ar)}</b><br/><i>{tafq_en}</i>", ParagraphStyle('ACellV3', fontName=self.font_bold, fontSize=8.5, alignment=1, textColor=colors.HexColor("#1E3A8A"))),
                Paragraph(f"<b>{t_amt}</b>", ParagraphStyle('ACellV2', fontName=self.font_bold, fontSize=12, alignment=1, textColor=colors.HexColor("#DC2626"))),
                Paragraph(f"<b>{curr}</b>", ParagraphStyle('ACellV1', fontName=self.font_bold, fontSize=11, alignment=1, textColor=colors.HexColor("#1D4ED8"))),
            ]
        ]
        amt_box_tbl = Table(amt_box_data, colWidths=[313, 145, 105])
        amt_box_tbl.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 4.5),
        ]))
        elements.append(amt_box_tbl)
        elements.append(Spacer(1, 4))

        # 5. Beneficiary Details Table (بيانات المستفيد: على اليمين | DETAILS OF BENEFICIARY على اليسار)
        ben_ar = self.ar("بيانات المستفيد:")
        ben_head_left = Paragraph("<b><font color='white'>DETAILS OF BENEFICIARY</font></b>", ParagraphStyle('BenHeadEn', fontName=self.font_bold, fontSize=8.5, alignment=0))
        ben_head_right = Paragraph(f"<b><font color='white'>{ben_ar}</font></b>", ParagraphStyle('BenHeadAr', fontName=self.font_bold, fontSize=8.5, alignment=2))
        ben_head_tbl = Table([[ben_head_left, ben_head_right]], colWidths=[281, 282])
        ben_head_tbl.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#1E293B")),
            ('PADDING', (0, 0), (-1, -1), 4),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(ben_head_tbl)

        ben_name_val = data.get("beneficiary_name_ar") or data.get("beneficiary_name") or ""
        ben_addr_val = data.get("beneficiary_address") or ""
        ben_bank_val = data.get("beneficiary_bank") or ""

        ben_table_data = [
            [
                Paragraph("BENEFICIARY'S NAME", cell_en),
                Paragraph(self.ar(ben_name_val), cell_reg),
                Paragraph(f"<b>{self.ar('اسم المستفيد')}</b>", cell_ar),
            ],
            [
                Paragraph("ADDRESS", cell_en),
                Paragraph(self.ar(ben_addr_val), cell_reg),
                Paragraph(f"<b>{self.ar('العنوان')}</b>", cell_ar),
            ],
            [
                Paragraph("PHONE NUMBER", cell_en),
                Paragraph(data.get("beneficiary_phone") or "", cell_reg),
                Paragraph(f"<b>{self.ar('رقم الهاتف')}</b>", cell_ar),
            ],
            [
                Paragraph("CITY & COUNTRY", cell_en),
                Paragraph(self.ar(data.get("beneficiary_city_country") or ""), cell_reg),
                Paragraph(f"<b>{self.ar('المدينة والبلد')}</b>", cell_ar),
            ],
            [
                Paragraph("BENEFICIARY'S ACCOUNT NO.", cell_en),
                Paragraph(f"<b>{data.get('beneficiary_acc_no') or ''}</b>", ParagraphStyle('BAcc', fontName=self.font_bold, fontSize=9, alignment=1, textColor=colors.HexColor("#1E3A8A"))),
                Paragraph(f"<b>{self.ar('رقم حساب المستفيد')}</b>", cell_ar),
            ],
            [
                Paragraph("IBAN", cell_en),
                Paragraph(data.get("iban") or "", cell_reg),
                Paragraph(f"<b>{self.ar('رقم الحساب البنكي الدولي')}</b>", cell_ar),
            ],
            [
                Paragraph("BENEFICIARY'S BANK / BRANCH", cell_en),
                Paragraph(self.ar(ben_bank_val), cell_reg),
                Paragraph(f"<b>{self.ar('بنك المستفيد/ الفرع')}</b>", cell_ar),
            ],
            [
                Paragraph("SWIFT/BIC", cell_en),
                Paragraph(f"<b>{data.get('swift_code') or ''}</b>", ParagraphStyle('BSwift', fontName=self.font_bold, fontSize=9, alignment=1, textColor=colors.HexColor("#1D4ED8"))),
                Paragraph(f"<b>{self.ar('كود السويفت')}</b>", cell_ar),
            ],
        ]
        ben_tbl = Table(ben_table_data, colWidths=[175, 263, 125])
        ben_tbl.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor("#F8FAFC")),
            ('BACKGROUND', (2, 0), (2, -1), colors.HexColor("#F8FAFC")),
            ('PADDING', (0, 0), (-1, -1), 4),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(ben_tbl)
        elements.append(Spacer(1, 4))

        # 6. Debit Account, Charges & Purpose
        cust_acc = data.get("customer_account") or ""
        
        chg_type = (data.get("charge_type") or "OUR").upper()
        our_chk = "[ X ]" if chg_type == "OUR" else "[   ]"
        ben_chk = "[ X ]" if chg_type == "BEN" else "[   ]"
        sha_chk = "[ X ]" if chg_type == "SHA" else "[   ]"

        chg_str = f"OUR {our_chk} &nbsp;&nbsp;&nbsp; BEN {ben_chk} &nbsp;&nbsp;&nbsp; SHA {sha_chk}"

        purpose_val = data.get("purpose_of_transfer") or ""

        debit_table_data = [
            [
                Paragraph("BY DEBITING MY ACCOUNT NUMBER", cell_en),
                Paragraph(f"<b>{cust_acc}</b>", ParagraphStyle('DAcc', fontName=self.font_bold, fontSize=9.5, alignment=1, textColor=colors.HexColor("#1E3A8A"))),
                Paragraph(f"<b>{self.ar('وذلك خصماً من حسابي طرفكم رقم')}</b>", cell_ar),
            ],
            [
                Paragraph("DETAILS OF CHARGES", cell_en),
                Paragraph(f"<b>{chg_str}</b>", ParagraphStyle('Chg', fontName=self.font_bold, fontSize=8.5, alignment=1, textColor=colors.HexColor("#1D4ED8"))),
                Paragraph(f"<b>{self.ar('تفاصيل التحويل (العمولات)')}</b>", cell_ar),
            ],
            [
                Paragraph("PURPOSE OF TRANSFER", cell_en),
                Paragraph(self.ar(purpose_val), ParagraphStyle('Purp', fontName=self.font_regular, fontSize=8, alignment=1)),
                Paragraph(f"<b>{self.ar('الغرض من التحويل')}</b>", cell_ar),
            ]
        ]
        debit_tbl = Table(debit_table_data, colWidths=[175, 263, 125])
        debit_tbl.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor("#F8FAFC")),
            ('BACKGROUND', (2, 0), (2, -1), colors.HexColor("#F8FAFC")),
            ('PADDING', (0, 0), (-1, -1), 4),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(debit_tbl)
        elements.append(Spacer(1, 4))

        # 7. Terms Agreement & Applicant Signature Box (طابق القالب الأصلي 100%)
        app_name = data.get("customer_name") or config.get("customer_name") or ""
        app_addr = data.get("customer_address") or config.get("customer_address") or ""
        app_phone = data.get("customer_phone") or config.get("customer_phone") or ""

        # Clean unwanted prefixes (FROM:, INVOICE NO:) and clean multiline characters
        app_name = re.sub(r"^(?:FROM|TO|BUYER|CONSIGNEE|CUSTOMER|APPLICANT)\s*[:\-\s]*", "", app_name, flags=re.IGNORECASE).strip()
        app_addr = re.sub(r"^(?:INVOICE\s*NO|PROFORMA\s*NO|PI\s*NO|ADDRESS|ADDR|CUSTOMER\s*ADDRESS)\s*[:\-\s]*", "", app_addr, flags=re.IGNORECASE).strip()
        app_addr = re.sub(r"\bINVOICE\s*NO\s*[:\-\s]*[A-Za-z0-9\-\/\_]+[\s,،]*", "", app_addr, flags=re.IGNORECASE).strip()
        app_addr = re.sub(r"^(?:FROM|TO|BUYER|CONSIGNEE)\s*[:\-\s]*", "", app_addr, flags=re.IGNORECASE).strip()
        app_addr = app_addr.replace("\n", " ").replace("\r", " ").strip()
        app_addr = re.sub(r"\s+", " ", app_addr)

        agree_ar = self.ar("أوافق على الشروط والأحكام الواردة خلف هذه الاستمارة وعلى مسؤوليتي صحة كافة البيانات")
        agree_en = "I/WE AGREE TO THE TERMS AND CONDITIONS CONTAINED BEHIND THIS FORM AND TO MY RESPONSIBILITY FOR THE VALIDITY OF ALL DATA"
        agree_p_ar = Paragraph(f"<b>{agree_ar}</b>", ParagraphStyle('AgreePAr', fontName=self.font_bold, fontSize=7.5, alignment=1, textColor=colors.black))
        agree_p_en = Paragraph(f"<b>{agree_en}</b>", ParagraphStyle('AgreePEn', fontName=self.font_bold, fontSize=7, alignment=1, textColor=colors.black))

        lbl_app_name = Paragraph(f"NAME OF THE APPLICANT &nbsp;&nbsp; <b>{self.ar('اسم العميل المحول')}</b>", cell_ar)
        lbl_app_addr = Paragraph(f"ADDRESS &nbsp;&nbsp; <b>{self.ar('العنوان')}</b>", cell_ar)
        lbl_app_phone = Paragraph(f"PHONE NUMBER &nbsp;&nbsp; <b>{self.ar('الهاتف')}</b>", cell_ar)

        val_app_name = Paragraph(f"<b>{self.ar(app_name)}</b>", cell_ar)
        val_app_addr = Paragraph(f"<b>{self.ar(app_addr)}</b>", cell_ar)
        val_app_phone = Paragraph(f"<b>{app_phone}</b>", ParagraphStyle('ValPh', fontName=self.font_bold, fontSize=8.5, alignment=2))

        sig_lbl_p = Paragraph(f"SIGNATURE &nbsp;&nbsp; <b>{self.ar('التوقيع')}</b><br/><br/><br/>_____________________", ParagraphStyle('SigBoxP', fontName=self.font_bold, fontSize=8, alignment=1))

        sig_box_data = [
            [sig_lbl_p, val_app_name, lbl_app_name],
            ["", val_app_addr, lbl_app_addr],
            ["", val_app_phone, lbl_app_phone],
        ]
        sig_tbl = Table(sig_box_data, colWidths=[150, 243, 170])
        sig_tbl.setStyle(TableStyle([
            ('SPAN', (0, 0), (0, 2)),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
            ('BACKGROUND', (2, 0), (2, -1), colors.HexColor("#F8FAFC")),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 3),
        ]))

        elements.append(agree_p_ar)
        elements.append(Spacer(1, 2))
        elements.append(agree_p_en)
        elements.append(Spacer(1, 3))
        elements.append(sig_tbl)
        elements.append(Spacer(1, 4))

        # 8. For Bank Use Only Box (لاستعمال البنك فقط - إعادة التصميم حسب القالب الأصلي)
        ar_head_p = Paragraph(
            f"<b><font color='#EA580C' size=8.5>{self.ar('لاستعمال البنك فقط:')}</font></b>",
            ParagraphStyle('ArBankHeadP', fontName=self.font_bold, alignment=2, leading=11)
        )
        en_head_p = Paragraph(
            "<b><font color='#EA580C' size=8>FOR BANK USE ONLY</font></b>",
            ParagraphStyle('EnBankHeadP', fontName=self.font_bold, alignment=2, leading=10)
        )

        bank_hdr_tbl = Table(
            [
                ["", ar_head_p],
                ["", en_head_p],
            ],
            colWidths=[423, 140]
        )
        bank_hdr_tbl.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LINEBELOW', (0, 0), (1, 0), 1.5, colors.HexColor("#EA580C")),
            ('PADDING', (0, 0), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 0), (1, 0), 2),
            ('TOPPADDING', (0, 1), (1, 1), 2),
        ]))

        corr_bank = data.get("correspondent_bank") or ""
        corr_swift = data.get("correspondent_swift") or ""

        corr_str = corr_bank
        if corr_swift:
            corr_str += f" (SWIFT: {corr_swift})"

        bank_use_data = [
            [
                Paragraph("<b>CORRESPONDENT</b>", cell_en),
                Paragraph(f"<b>{corr_str}</b>", ParagraphStyle('CorrP', fontName=self.font_bold, fontSize=8, alignment=1, textColor=colors.HexColor("#1E3A8A"))),
                Paragraph(f"<b>{self.ar('البنك المراسل')}</b>", cell_ar),
            ],
            [
                Paragraph("<b>VALUE DATE</b>", cell_en),
                Paragraph(f"<b>{data.get('value_date') or ''}</b>", cell_reg),
                Paragraph(f"<b>{self.ar('تاريخ الاستحقاق')}</b>", cell_ar),
            ],
            [
                Paragraph("<b>CURRENCY</b>", cell_en),
                Paragraph(f"<b>{curr}</b>", cell_reg),
                Paragraph(f"<b>{self.ar('العملة')}</b>", cell_ar),
            ],
            [
                Paragraph("<b>AMOUNT</b>", cell_en),
                Paragraph(f"<b>{t_amt}</b>", cell_reg),
                Paragraph(f"<b>{self.ar('المبلغ')}</b>", cell_ar),
            ],
            [
                Paragraph("<b>EX RATE</b>", cell_en),
                Paragraph("", cell_reg),
                Paragraph(f"<b>{self.ar('سعر الصرف')}</b>", cell_ar),
            ],
            [
                Paragraph("<b>EQVT.</b>", cell_en),
                Paragraph("", cell_reg),
                Paragraph(f"<b>{self.ar('المعادل')}</b>", cell_ar),
            ],
            [
                Paragraph("<b>COMMISSION</b>", cell_en),
                Paragraph("", cell_reg),
                Paragraph(f"<b>{self.ar('العمولة')}</b>", cell_ar),
            ],
            [
                Paragraph("<b>SWIFT CHGS.</b>", cell_en),
                Paragraph("", cell_reg),
                Paragraph(f"<b>{self.ar('أجور سويفت')}</b>", cell_ar),
            ],
            [
                Paragraph("<b>TOTAL</b>", cell_en),
                Paragraph(f"<b>{t_amt} {curr}</b>", ParagraphStyle('TotP', fontName=self.font_bold, fontSize=8.5, alignment=1, textColor=colors.HexColor("#DC2626"))),
                Paragraph(f"<b>{self.ar('الإجمالي')}</b>", cell_ar),
            ]
        ]
        bank_use_tbl = Table(bank_use_data, colWidths=[175, 263, 125])
        bank_use_tbl.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#FCA5A5")),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#FEF2F2")),
            ('PADDING', (0, 0), (-1, -1), 2.5),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))

        bank_sig_data = [
            [
                Paragraph(f"<b>AUTHORIZED BY<br/>{self.ar('مدير عمليات / مدير الفرع:')}</b><br/><br/>_____________________", ParagraphStyle('BOff3', fontName=self.font_bold, fontSize=7.5, alignment=1)),
                Paragraph(f"<b>CHECKED BY<br/>{self.ar('مراجع عمليات الفرع:')}</b><br/><br/>_____________________", ParagraphStyle('BOff2', fontName=self.font_bold, fontSize=7.5, alignment=1)),
                Paragraph(f"<b>TRANSFERS OFFICER<br/>{self.ar('أخصائي الحوالات:')}</b><br/><br/>_____________________", ParagraphStyle('BOff1', fontName=self.font_bold, fontSize=7.5, alignment=1)),
            ]
        ]
        bank_sig_tbl = Table(bank_sig_data, colWidths=[188, 188, 187])
        bank_sig_tbl.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
            ('BACKGROUND', (0, 0), (-1, -1), colors.white),
            ('PADDING', (0, 0), (-1, -1), 4),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ]))

        elements.append(bank_hdr_tbl)
        elements.append(Spacer(1, 2))
        elements.append(bank_use_tbl)
        elements.append(Spacer(1, 10))
        elements.append(bank_sig_tbl)

        # ====================================================
        #  PAGE 2: OFFICIAL 12 TERMS & CONDITIONS (البنود الـ 12)
        # ====================================================
        elements.append(PageBreak())

        p2_header_p = Paragraph(
            f"<font color='white' size=12><b>{self.ar('الأحكام والشروط المنظمة للتحويلات')}</b></font><br/>"
            f"<font color='white' size=9><b>CONDITIONS GOVERNING MONEY TRANSFERS</b></font>",
            ParagraphStyle('P2Title', fontName=self.font_bold, alignment=1, leading=14)
        )
        p2_header_tbl = Table([[logo_img, p2_header_p]], colWidths=[275, 288])
        p2_header_tbl.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('BACKGROUND', (1, 0), (1, 0), colors.HexColor("#DC2626")),
            ('PADDING', (1, 0), (1, 0), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(p2_header_tbl)
        elements.append(Spacer(1, 6))

        terms_banner_left = Paragraph("<b><font color='white'>Terms:</font></b>", ParagraphStyle('TBLeft', fontName=self.font_bold, fontSize=8.5, alignment=0))
        terms_banner_right = Paragraph(f"<b><font color='white'>{self.ar('مصطلحات')}</font></b>", ParagraphStyle('TBRight', fontName=self.font_bold, fontSize=8.5, alignment=2))
        terms_banner_tbl = Table([[terms_banner_left, terms_banner_right]], colWidths=[281, 282])
        terms_banner_tbl.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#52525B")),
            ('PADDING', (0, 0), (-1, -1), 3.5),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(terms_banner_tbl)

        p2_terms_en_content = Paragraph(
            "<b>QIMB: Qasemi Islamic Microfinance Bank</b><br/>"
            "<b>Client: Any bank customer either corporate or private</b>",
            ParagraphStyle('P2TermEn', fontName=self.font_bold, fontSize=8, leading=11.5, alignment=0, textColor=colors.black)
        )
        p2_terms_ar_content = Paragraph(
            f"<b>{self.ar('البنك: بنك القاسمي للتمويل الأصغر الإسلامي.')}</b><br/>"
            f"<b>{self.ar('العميل: عميل البنك سواءً كان منشأة أو فرد.')}</b>",
            ParagraphStyle('P2TermAr', fontName=self.font_bold, fontSize=8, leading=11.5, alignment=2, textColor=colors.black)
        )
        p2_terms_hdr_tbl = Table([[p2_terms_en_content, p2_terms_ar_content]], colWidths=[281, 282])
        p2_terms_hdr_tbl.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
            ('PADDING', (0, 0), (-1, -1), 4),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        elements.append(p2_terms_hdr_tbl)
        elements.append(Spacer(1, 4))

        ar_terms_raw = [
            "ما لم يتم الاتفاق على خلاف هذه الشروط خطأً وبصورة صريحة ومحددة عند طلب التحويل، فإن تغيير المبالغ المطلوب تحويلها من عملة أخرى يكون بسعر بيع العملة في وقت توريد مبلغ التحويل إلى البنك أو وضعه تحت تصرف البنك بأي شكل من الأشكال.",
            "لتنفيذ التحويل يجب أن يكون لدى العميل رصيد دائن في الحساب الجاري قبل الاستخدام لتغطية قيمة تلك الحوالة وأجور ونفقات التحويل.",
            "يتقاضى البنك عمولات وأجور التحويل بحسب التكلفة التقديرية لمصروفات التحويل وفقاً للتعرفة المصرفية المعلنة في البنك عند التحويل.",
            "يعلم العميل بأن البنك يقوم بإصدار التحويل بالعملة التي يطلب العميل تحويلها، أما ترتيبات دفع قيمة الحوالة إلى المستفيد والعملة التي تدفع بها قيمة الحوالة فتخضع لشروط دفع الحوالات الواردة لدى بنك المستفيد دون أي مسؤولية على البنك.",
            "يحق لبنكك وفقاً لتقديره أن يستعين بأي مراسل أو وكيل لإجراء التحويل نيابةً عن العميل ولن يكون مسؤولاً عما يصدر عن مراسليه أو وكلائه من أخطاء أو تقصير أو تأخير أو سهو.",
            "لن يكون البنك مسؤولاً عما قد ينشأ من خسارة أو ضرر نتيجة لما يحدث في برامج وأنظمة العمل والاتصال وخدمات السويفت من توقف أو أخطاء أو سهو أو تمزيق أو أي ظروف أخرى خارجة عن إرادة البنك أو إرادة أي من الوكلاء أو المراسلين.",
            "يقرّ العميل بالتوقيع على هذه الاستمارة بأنه وافق على تنفيذ التحويل وهو يعلم بأن طلب إلغاء التحويل لن يكون متاحاً إلا في حالة تمكن بنك المستفيد من استلام إخطار البنك ومراسله إن وجد بالإلغاء قبل حلول تاريخ استحقاق التحويل وفي أثناء أوقات العمل اليومي لبنك المستفيد ولن يتحمل البنك أي مسؤولية في حال رفض المستفيد إلغاء التحويل وإعادة المبلغ.",
            "إذا كان تنفيذ طلب التحويل قد تطلب تغيير المبلغ المقدم من العميل إلى عملة أخرى فيعاد المبلغ في حالة إلغاء التحويل بنفس العملة التي تم بها دفع المبلغ الأصلي إلى البنك ويتم تغيير العملة في هذه الحالة بسعر شراء العملة المتداول في البنك وقت إعادة المبلغ مخصوماً منه عمولات أو مصاريف البنك والبنك المراسل وذلك إذا كان المتسبب في الخطأ العميل.",
            "يعلم العميل بأنه وفي حالة حلول تاريخ استحقاق التحويل فإن التحويل يكون غير قابل للإلغاء أو التعديل وأنه إذا كان له أي مطالبات تتعلق بالحوالة على العميل أن يخاطب مباشرة مع المستفيد لإصدار حوالة جديدة لأمر العميل.",
            "من المعلوم للعميل أن يطلب أي تعديل في بيانات التحويل ويجب أن يكون قبل حلول تاريخ استحقاق التحويل وأن طلب التعديل يكون في حالة طلب تصحيح رقم حساب المستفيد أو اسم المستفيد فقط، أما إذا تضمن أي طلب آخر للتعديل فيخضع لشروط إلغاء التحويل.",
            "لا يعتبر طلب التحويل هذا صحيحاً إلا إذا كان موقعاً من المفوضين بالتوقيع عن البنك.",
            "تعد النسخة العربية هي المرجع الرئيسي في هذه الطلب."
        ]

        en_terms_raw = [
            "Unless a clear and specific agreement is made and entered apart from these conditions at the time of requesting the transfer of any amount, the conversion of the amount(s) to be transferred into another currency shall be done on the basis of the exchange rate at the time of depositing the amount(s) to be transferred to QIMB to at the time of making the amount at QIMB's full disposition or under its control.",
            "For the execution of a money transfer, the clients should have a credit balance in their current account to cover the value of that transfer and required tariffs and any other relevant charges.",
            "QIMB shall be entitled to commissions and tariffs for making any money transfer in accordance with the estimated cost for transfer expenses and in compliance with QIMB's stated banking tariff at the time of transferring.",
            "The client shall have full knowledge that QIMB may do the transferring in accordance with the currency requested by the client. Any arrangements concerning the paying of the transferred value to the designated beneficiary shall be subject to the conditions governing the payment of transfers forwarded to QIMB. The same conditions shall govern the type of currency in which the transfer is to be paid out. QIMB shall bear no responsibility in this regard.",
            "QIMB shall have the right in its own discretion to seek the assistance of any correspondent agent bank to implement the transferring on behalf of (its client). It shall bear no responsibility for any act, mistake, failure, delay or neglectfulness committed by its correspondent or agent banks).",
            "If in case QIMB's programs, work and communication systems or SWIFT services stop working, encounter any errors, or cause any delay, neglectfulness or impairment or as a result of any other working conditions beyond the control of QIMB or any of its correspondent or agent bank, QIMB shall bear no responsibility for any losses or damages resulting thereof.",
            "The client shall acknowledge that they have agreed to the execution of the transferring and at the same time is fully aware that canceling such a transfer must be through submitting an application to that effect to QIMB prior the due date of the transferred amount and within the working daily hours of beneficiary bank. This is so because the cancelation of the transfer shall not be possible unless the beneficiary bank receives a notice of cancelation from QIMB or its correspondent bank, if available, the due date of transferred amount and within the working daily hours of beneficiary's bank.",
            "If in case the execution of the money transfer application demands that the amount to be transferred shall be converted to another currency, such an amount must be returned in the same currency in which the principal amount was deposited to QIMB in the conversion shall be based on the current exchange rate in QIMB at the time of the return of the amount, cancellation fees or commission and actual bank expenses shall be deducted from the returned amount in case the client is the cause.",
            "The client shall be fully aware that if the date for the payment transfer is due, no cancellation or amendment shall be made to the transfer. If the client has any claims in this regard, s/he shall contact the beneficiary to issue a new transfer in his/her own favor.",
            "The client shall be fully aware that any amendment or change to the date of the money transfer shall be affected before the date of its maturity. The request for making any amendment shall be confined to correcting either the beneficiary's account number or name only. If the request incorporates any other amendment, this matter shall be subject to the conditions governing the cancelation of money transfer.",
            "This application shall be valid only if signed by the ones authorized by QIMB to do so and attested by QIMB official stamp.",
            "For the interpretation of the related articles, the Arab version stands as the main reference."
        ]

        p_ar_txt = ParagraphStyle('ArTermTxt', fontName=self.font_regular, fontSize=7.0, leading=9.2, alignment=2, textColor=colors.HexColor("#0F172A"))
        p_ar_num = ParagraphStyle('ArTermNum', fontName=self.font_bold, fontSize=8.0, alignment=1, textColor=colors.HexColor("#0F172A"))

        ar_rows = []
        for idx, text in enumerate(ar_terms_raw, 1):
            formatted_text = self.ar_multiline(text, font_name=self.font_regular, font_size=7.0, max_pts=515)
            p_t = Paragraph(formatted_text, p_ar_txt)
            p_n = Paragraph(f"<b>{idx}</b>", p_ar_num)
            ar_rows.append([p_t, p_n])

        ar_tbl = Table(ar_rows, colWidths=[533, 30])
        ar_tbl.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.75, colors.HexColor("#475569")),
            ('BACKGROUND', (1, 0), (1, -1), colors.HexColor("#F8FAFC")),
            ('PADDING', (0, 0), (-1, -1), 2.5),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(ar_tbl)
        elements.append(Spacer(1, 6))

        p_en_txt = ParagraphStyle('EnTermTxt', fontName=self.font_regular, fontSize=6.8, leading=9.0, alignment=0, textColor=colors.HexColor("#0F172A"))
        p_en_num = ParagraphStyle('EnTermNum', fontName=self.font_bold, fontSize=7.5, alignment=1, textColor=colors.HexColor("#0F172A"))

        en_rows = []
        for idx, text in enumerate(en_terms_raw, 1):
            p_n = Paragraph(f"<b>{idx:02d}</b>", p_en_num)
            p_t = Paragraph(text, p_en_txt)
            en_rows.append([p_n, p_t])

        en_tbl = Table(en_rows, colWidths=[30, 533])
        en_tbl.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.75, colors.HexColor("#475569")),
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor("#F8FAFC")),
            ('PADDING', (0, 0), (-1, -1), 2.0),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(en_tbl)
        elements.append(Spacer(1, 4))

        # Single 5-column Table for Page 2 Bottom Section (Total Width 563pt)
        # Perfectly aligned with en_tbl and ar_tbl margins!
        sig_lbl_p = Paragraph(
            f"<b><font color='white' size=8.5>{self.ar('التوقيع')}</font></b><br/>"
            f"<b><font color='white' size=7.5>signature</font></b>",
            ParagraphStyle('SigLblP', fontName=self.font_bold, alignment=1, leading=10)
        )
        sig_val_p = Paragraph("", ParagraphStyle('SigValP', fontName=self.font_bold, alignment=1))

        cname_lbl_p = Paragraph(
            f"<b><font color='white' size=8.5>{self.ar('اسم العميل')}</font></b><br/>"
            f"<b><font color='white' size=7.5>Customer Name</font></b>",
            ParagraphStyle('CNameLblP', fontName=self.font_bold, alignment=1, leading=10)
        )
        cname_val_p = Paragraph(
            f"<b><font color='#0F172A' size=9.0>{self.ar(app_name)}</font></b>",
            ParagraphStyle('CNameValP', fontName=self.font_bold, alignment=1, leading=11)
        )

        p2_bottom_tbl = Table(
            [[sig_val_p, sig_lbl_p, "", cname_val_p, cname_lbl_p]],
            colWidths=[205, 70, 13, 185, 90],
            rowHeights=[26]
        )
        p2_bottom_tbl.setStyle(TableStyle([
            # Box 1: Signature (Cols 0 and 1)
            ('BOX', (0, 0), (1, 0), 0.75, colors.HexColor("#475569")),
            ('LINEBEFORE', (1, 0), (1, 0), 0.75, colors.HexColor("#475569")),
            ('BACKGROUND', (0, 0), (0, 0), colors.white),
            ('BACKGROUND', (1, 0), (1, 0), colors.HexColor("#5C6B73")),

            # Box 2: Customer Name (Cols 3 and 4)
            ('BOX', (3, 0), (4, 0), 0.75, colors.HexColor("#475569")),
            ('LINEBEFORE', (4, 0), (4, 0), 0.75, colors.HexColor("#475569")),
            ('BACKGROUND', (3, 0), (3, 0), colors.white),
            ('BACKGROUND', (4, 0), (4, 0), colors.HexColor("#5C6B73")),

            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 3),
        ]))

        # Bottom Orange Line across full page width (563pt)
        orange_line = Table([[""]], colWidths=[563])
        orange_line.setStyle(TableStyle([
            ('LINEBELOW', (0, 0), (0, 0), 2.5, colors.HexColor("#EA580C")),
            ('PADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
        ]))

        elements.append(Spacer(1, 6))
        elements.append(p2_bottom_tbl)
        elements.append(Spacer(1, 6))
        elements.append(orange_line)

        doc.build(elements)
        return output_path
