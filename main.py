import os
import sys
import json
import time
import re
import threading
import base64
import subprocess
import tempfile
from datetime import datetime

import flet as ft

from parser import CommercialInvoiceParser, normalize_bank_fields
from pdf_generator import SWIFTPDFGenerator
from invoice_registry import InvoiceRegistry
from template_manager import TemplateManager
from tafqeet import CurrencyTafqeet


# Colors & Theme Constants
PRIMARY_COLOR = "#004B87"
SECONDARY_COLOR = "#0083B0"
ACCENT_ORANGE = "#E65100"
BG_COLOR = "#F4F6F9"
CARD_BG = "#FFFFFF"
HEADER_TEXT_COLOR = "#1A202C"
LIGHT_ORANGE_BG = "#FFF3E0"


def get_logo_b64_src() -> str:
    base_dir = os.path.dirname(__file__)
    possible_paths = [
        os.path.join(base_dir, "assets", "qasemi_bank_logo.png"),
        os.path.join(base_dir, "qasemi_logo.jpg"),
        os.path.join(base_dir, "assets", "qasemi_logo.png"),
        r"C:\Users\hp\.gemini\antigravity\scratch\swift_invoice_app\assets\qasemi_bank_logo.png",
        r"C:\Users\hp\.gemini\antigravity\scratch\swift_invoice_app\qasemi_logo.jpg",
    ]
    for p in possible_paths:
        if os.path.exists(p):
            try:
                with open(p, "rb") as f:
                    data = base64.b64encode(f.read()).decode("utf-8")
                    mime = "image/png" if p.lower().endswith(".png") else "image/jpeg"
                    return f"data:{mime};base64,{data}"
            except Exception:
                pass
    return ""


def pick_file_native() -> str:
    temp_dir = tempfile.gettempdir()
    temp_file = os.path.join(temp_dir, f"qasemi_sel_{int(time.time()*1000)}.txt")
    if os.path.exists(temp_file):
        try:
            os.remove(temp_file)
        except Exception:
            pass

    # Method 1: Python Tkinter Native Unicode File Dialog (Topmost Focus)
    try:
        temp_file_py = temp_file.replace("\\", "\\\\")
        py_script = f"""import os, sys
from tkinter import Tk, filedialog
root = Tk()
root.withdraw()
root.attributes('-topmost', True)
f = filedialog.askopenfilename(
    title='اختر ملف الفاتورة التجارية (PDF أو صورة)',
    filetypes=[('جميع الملفات المدعومة', '*.pdf;*.png;*.jpg;*.jpeg;*.webp;*.txt'), ('جميع الملفات', '*.*')]
)
root.destroy()
if f:
    with open(r'{temp_file_py}', 'w', encoding='utf-8') as out:
        out.write(f)
"""
        subprocess.run([sys.executable, "-c", py_script], capture_output=True, timeout=120)
        if os.path.exists(temp_file):
            with open(temp_file, "r", encoding="utf-8", errors="ignore") as tf:
                content = tf.read().strip().strip('"\'')
                if content and os.path.exists(content):
                    try:
                        os.remove(temp_file)
                    except Exception:
                        pass
                    return content
    except Exception as e:
        print(f"Tkinter picker notice: {e}")

    # Method 2: PowerShell UTF-8 File Export Fallback
    try:
        temp_file_ps = temp_file.replace("\\", "/")
        ps_cmd = (
            "[System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms') | Out-Null; "
            "$f = New-Object System.Windows.Forms.OpenFileDialog; "
            "$f.Title = 'اختر ملف الفاتورة التجارية (PDF أو صورة)'; "
            "$f.Filter = 'جميع الملفات المدعومة (*.pdf;*.png;*.jpg;*.jpeg;*.webp;*.txt)|*.pdf;*.png;*.jpg;*.jpeg;*.webp;*.txt|جميع الملفات (*.*)|*.*'; "
            f"if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {{ [System.IO.File]::WriteAllText('{temp_file_ps}', $f.FileName, [System.Text.Encoding]::UTF8) }}"
        )
        cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Sta", "-Command", ps_cmd]
        subprocess.run(cmd, capture_output=True, timeout=120)
        if os.path.exists(temp_file):
            with open(temp_file, "r", encoding="utf-8-sig", errors="ignore") as tf:
                content = tf.read().strip().strip('"\'')
                if content and os.path.exists(content):
                    try:
                        os.remove(temp_file)
                    except Exception:
                        pass
                    return content
    except Exception as e:
        print(f"PowerShell picker notice: {e}")

    return ""


def main(page: ft.Page):
    page.title = "بنك القاسمي للتمويل الاصغر الاسلامي - طلب اصدار حوالة خارجية"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.rtl = True
    page.padding = 15
    page.spacing = 12
    page.bgcolor = BG_COLOR
    page.scroll = ft.ScrollMode.AUTO
    page.window_width = 1400
    page.window_height = 900
    page.window_min_width = 1200
    page.window_min_height = 750
    page.window_maximized = True

    base_dir = os.path.dirname(__file__)
    icon_path = os.path.join(base_dir, "assets", "icon.png")
    if os.path.exists(icon_path):
        try:
            page.window_icon = icon_path
        except Exception:
            pass
        try:
            if hasattr(page, "window"):
                page.window.icon = icon_path
        except Exception:
            pass

    # Managers Init
    parser = CommercialInvoiceParser()
    pdf_gen = SWIFTPDFGenerator()
    registry = InvoiceRegistry()
    tmpl_mgr = TemplateManager()

    saved_config = tmpl_mgr.load_template()
    app_state = {"last_parsed_data": {}, "editing_original_inv_no": None}

    # Cross-Platform File Picker setup (Only instantiated on Mobile/Web to prevent Desktop 'Unknown control: FilePicker' banner)
    is_desktop_win = (os.name == "nt" and not os.environ.get("ANDROID_ARGUMENT"))
    file_picker = None
    if not is_desktop_win:
        try:
            file_picker = ft.FilePicker()
            page.overlay.append(file_picker)

            def on_file_picker_result(e):
                if e.files:
                    for f in e.files:
                        if f.bytes:
                            temp_dir = tempfile.gettempdir()
                            tmp_p = os.path.join(temp_dir, f.name or "uploaded_invoice.pdf")
                            with open(tmp_p, "wb") as out_f:
                                out_f.write(f.bytes)
                            process_file_path(tmp_p)
                            return
                        elif f.path and os.path.exists(f.path):
                            process_file_path(f.path)
                            return
                status_text.value = "❌ لم يتم اختيار أي ملف."
                progress_bar.visible = False
                page.update()

            file_picker.on_result = on_file_picker_result
        except Exception as ex:
            print(f"FilePicker init notice: {ex}")
            file_picker = None

    # Progress Indicator Control
    progress_bar = ft.ProgressBar(height=10, value=0.0, color=ACCENT_ORANGE, bgcolor=ft.Colors.ORANGE_100)
    status_text = ft.Text("جاهز لاستقبال وإرفاق فواتير الحوالات الخارجية.", size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_800)

    status_banner = ft.Container(
        content=ft.Column(
            controls=[
                ft.Row(
                    controls=[status_text],
                    alignment=ft.MainAxisAlignment.START,
                    spacing=10,
                ),
                progress_bar,
            ],
            spacing=8,
        ),
        padding=10,
        bgcolor=LIGHT_ORANGE_BG,
        border_radius=8,
        border=ft.Border.all(1.5, ft.Colors.ORANGE_300),
    )

    # Text Fields for Verification & Editing
    txt_app_date = ft.TextField(label="تاريخ طلب الحوالة (Application Date)", value=datetime.now().strftime("%Y-%m-%d"), col={"sm": 12, "md": 6, "lg": 3})
    
    dd_branch = ft.Dropdown(
        label="فرع البنك (Branch)",
        value="المركز الرئيسي فرع عدن",
        col={"sm": 12, "md": 6, "lg": 3},
        options=[
            ft.dropdown.Option("المركز الرئيسي فرع عدن", "المركز الرئيسي فرع عدن"),
            ft.dropdown.Option("الاداره العامه بنك القاسمي للتمويل الاصغر الاسلامي", "الاداره العامه بنك القاسمي للتمويل الاصغر الاسلامي"),
            ft.dropdown.Option("فرع الحديده", "فرع الحديده"),
            ft.dropdown.Option("فرع تعز شارع جمال", "فرع تعز شارع جمال"),
            ft.dropdown.Option("فرع صنعاء شارع الخمسين", "فرع صنعاء شارع الخمسين"),
            ft.dropdown.Option("فرع عدن مول", "فرع عدن مول"),
            ft.dropdown.Option("فرع مارب", "فرع مارب"),
        ]
    )

    txt_invoice_no = ft.TextField(label="1. رقم الفاتورة (Invoice No / Proforma No)", col={"sm": 12, "md": 6, "lg": 3})
    txt_pi_no = ft.TextField(label="رقم البوليصة/البورفورما (PI / BL No)", col={"sm": 12, "md": 6, "lg": 3})
    txt_date = ft.TextField(label="2. تاريخ الفاتورة (Date)", col={"sm": 12, "md": 6, "lg": 3})
    txt_payment_terms = ft.TextField(label="3. شروط الدفع (Payment Terms)", col={"sm": 12, "md": 6, "lg": 3})
    txt_delivery_terms = ft.TextField(label="4. شروط التسليم (Delivery Terms)", col={"sm": 12, "md": 6, "lg": 3})
    txt_goods_desc = ft.TextField(label="5. نوع البضاعة (Goods Description)", multiline=True, min_lines=2, col={"sm": 12, "md": 12, "lg": 12})
    txt_quantity = ft.TextField(label="6. الكمية / الوزن (Quantity)", col={"sm": 12, "md": 6, "lg": 3})
    
    txt_total_amount = ft.TextField(label="7. إجمالي الفاتورة (Total Amount)", col={"sm": 12, "md": 6, "lg": 3})
    txt_transfer_amount = ft.TextField(label="مبلغ الحوالة المحسوب (Transfer Amount)", col={"sm": 12, "md": 6, "lg": 3})
    txt_currency = ft.TextField(label="8. العملة (Currency)", value="USD", col={"sm": 12, "md": 6, "lg": 3})
    
    txt_words_ar = ft.TextField(label="تفقيط المبلغ بالعربية (Amount in Words AR)", col={"sm": 12, "md": 12, "lg": 12})
    txt_words_en = ft.TextField(label="تفقيط المبلغ بالإنجليزية (Amount in Words EN)", col={"sm": 12, "md": 12, "lg": 12})

    # التحديث التلقائي الفوري للتفقيط عند تغيير المبلغ أو العملة يدوياً
    def recalculate_tafqeet_live(e=None):
        if e and e.control == txt_total_amount:
            txt_transfer_amount.value = txt_total_amount.value
        elif e and e.control == txt_transfer_amount and not txt_total_amount.value:
            txt_total_amount.value = txt_transfer_amount.value

        amt_val_str = txt_transfer_amount.value.strip() or txt_total_amount.value.strip()
        curr_str = txt_currency.value.strip() or "USD"
        if amt_val_str:
            clean_num = re.sub(r"[^\d\.]", "", amt_val_str.replace(",", ""))
            if clean_num:
                try:
                    num_float = float(clean_num)
                    txt_words_ar.value = CurrencyTafqeet.tafqeet_ar(num_float, curr_str)
                    txt_words_en.value = CurrencyTafqeet.tafqeet_en(num_float, curr_str)
                except Exception:
                    pass
        try:
            page.update()
        except Exception:
            pass

    txt_total_amount.on_change = recalculate_tafqeet_live
    txt_transfer_amount.on_change = recalculate_tafqeet_live
    txt_currency.on_change = recalculate_tafqeet_live

    txt_transport = ft.TextField(label="9. وسيلة النقل (Transport Mode)", col={"sm": 12, "md": 6, "lg": 3})
    txt_port_loading = ft.TextField(label="10. ميناء المغادرة (Port of Loading / From)", col={"sm": 12, "md": 6, "lg": 6})
    txt_port_discharge = ft.TextField(label="11. ميناء الوصول (Port of Discharge / To)", col={"sm": 12, "md": 6, "lg": 6})

    txt_cust_name = ft.TextField(label="12. اسم العميل المستورد (Customer Name / Consignee)", value="", col={"sm": 12, "md": 6, "lg": 6})
    txt_cust_address = ft.TextField(label="13. عنوان العميل المستورد (Address)", value="", col={"sm": 12, "md": 12, "lg": 12})
    txt_cust_phone = ft.TextField(label="14. هاتف العميل المستورد (Tel / Phone)", value="", col={"sm": 12, "md": 6, "lg": 6})
    txt_cust_acc = ft.TextField(label="رقم حساب العميل بالبنك (Account No)", value="", col={"sm": 12, "md": 6, "lg": 6})

    txt_ben_name = ft.TextField(label="15. اسم المورد المستفيد (Beneficiary Name / Seller)", col={"sm": 12, "md": 6, "lg": 6})
    txt_ben_address = ft.TextField(label="16. عنوان المورد المستفيد (Address / Country)", col={"sm": 12, "md": 12, "lg": 12})
    txt_ben_phone = ft.TextField(label="17. هاتف المورد المستفيد (Tel / Phone)", col={"sm": 12, "md": 6, "lg": 6})

    txt_ben_acc = ft.TextField(label="18. رقم حساب المستفيد (Beneficiary Account No)", col={"sm": 12, "md": 4, "lg": 4})
    txt_iban = ft.TextField(label="19. رقم الحساب الدولي (IBAN)", col={"sm": 12, "md": 4, "lg": 4})
    txt_ben_bank = ft.TextField(label="20. بنك المستفيد / الفرع (Beneficiary Bank/Branch)", col={"sm": 12, "md": 12, "lg": 12})
    txt_swift = ft.TextField(label="21. كود السويفت (SWIFT / BIC)", col={"sm": 12, "md": 4, "lg": 4})
    txt_corr_bank = ft.TextField(label="22. البنك المراسل (Correspondent / Intermediary Bank)", col={"sm": 12, "md": 6, "lg": 6})
    txt_corr_swift = ft.TextField(label="23. سويفت البنك المراسل (Correspondent SWIFT)", col={"sm": 12, "md": 6, "lg": 6})

    dd_charge_type = ft.Dropdown(
        label="نوع تفاصيل الخصم والعمولة (Details of Charges)",
        value="OUR",
        col={"sm": 12, "md": 12, "lg": 12},
        options=[
            ft.dropdown.Option("OUR", "OUR - جميع الرسوم على العميل الآمر بالحوالة (All Charges on Applicant)"),
            ft.dropdown.Option("BEN", "BEN - جميع الرسوم خصماً من المستفيد (All Charges on Beneficiary)"),
            ft.dropdown.Option("SHA", "SHA - رسوم مشتركة بين العميل والمستفيد (Shared Charges)"),
        ]
    )

    txt_purpose = ft.TextField(
        label="الغرض من التحويل (Purpose of Transfer)",
        value="مقابل شراء بضاعة تجارية (Payment for purchasing goods)",
        col={"sm": 12, "md": 12, "lg": 12}
    )

    sec_invoice = ft.Container(
        content=ft.ResponsiveRow(
            controls=[
                txt_app_date, dd_branch, txt_invoice_no, txt_pi_no,
                txt_date, txt_payment_terms, txt_delivery_terms, txt_transport,
                txt_total_amount, txt_transfer_amount, txt_currency, txt_quantity,
                txt_words_ar,
                txt_words_en,
                txt_goods_desc,
                txt_port_loading, txt_port_discharge,
            ],
            run_spacing=12,
            spacing=12,
        ),
        visible=True,
    )

    sec_customer = ft.Container(
        content=ft.ResponsiveRow(
            controls=[
                txt_cust_name, txt_cust_acc,
                txt_cust_address, txt_cust_phone,
            ],
            run_spacing=12,
            spacing=12,
        ),
        visible=False,
    )

    sec_beneficiary = ft.Container(
        content=ft.ResponsiveRow(
            controls=[
                txt_ben_name, txt_ben_phone,
                txt_ben_address,
            ],
            run_spacing=12,
            spacing=12,
        ),
        visible=False,
    )

    sec_bank = ft.Container(
        content=ft.ResponsiveRow(
            controls=[
                txt_ben_acc, txt_iban, txt_swift,
                txt_ben_bank,
                txt_corr_bank, txt_corr_swift,
                dd_charge_type,
                txt_purpose,
            ],
            run_spacing=12,
            spacing=12,
        ),
        visible=False,
    )

    active_tab = "inv"

    def switch_tab(tab_name: str):
        nonlocal active_tab
        active_tab = tab_name
        sec_invoice.visible = (tab_name == "inv")
        sec_customer.visible = (tab_name == "cust")
        sec_beneficiary.visible = (tab_name == "ben")
        sec_bank.visible = (tab_name == "bank")

        btn_tab_inv.style = ft.ButtonStyle(
            bgcolor=ACCENT_ORANGE if tab_name == "inv" else ft.Colors.BLUE_GREY_100,
            color=ft.Colors.WHITE if tab_name == "inv" else ft.Colors.BLACK
        )
        btn_tab_cust.style = ft.ButtonStyle(
            bgcolor=ACCENT_ORANGE if tab_name == "cust" else ft.Colors.BLUE_GREY_100,
            color=ft.Colors.WHITE if tab_name == "cust" else ft.Colors.BLACK
        )
        btn_tab_ben.style = ft.ButtonStyle(
            bgcolor=ACCENT_ORANGE if tab_name == "ben" else ft.Colors.BLUE_GREY_100,
            color=ft.Colors.WHITE if tab_name == "ben" else ft.Colors.BLACK
        )
        btn_tab_bank.style = ft.ButtonStyle(
            bgcolor=ACCENT_ORANGE if tab_name == "bank" else ft.Colors.BLUE_GREY_100,
            color=ft.Colors.WHITE if tab_name == "bank" else ft.Colors.BLACK
        )
        page.update()

    btn_tab_inv = ft.Button(
        "1. بيانات الفاتورة والحوالة",
        icon=ft.Icons.RECEIPT_LONG,
        style=ft.ButtonStyle(bgcolor=ACCENT_ORANGE, color=ft.Colors.WHITE),
        on_click=lambda _: switch_tab("inv")
    )
    btn_tab_cust = ft.Button(
        "2. بيانات العميل المستورد",
        icon=ft.Icons.PERSON,
        style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_GREY_100, color=ft.Colors.BLACK),
        on_click=lambda _: switch_tab("cust")
    )
    btn_tab_ben = ft.Button(
        "3. بيانات المورد المستفيد",
        icon=ft.Icons.STORE,
        style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_GREY_100, color=ft.Colors.BLACK),
        on_click=lambda _: switch_tab("ben")
    )
    btn_tab_bank = ft.Button(
        "4. البيانات البنكية والسويفت",
        icon=ft.Icons.ACCOUNT_BALANCE_WALLET,
        style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_GREY_100, color=ft.Colors.BLACK),
        on_click=lambda _: switch_tab("bank")
    )

    tab_bar_row = ft.Row(
        controls=[btn_tab_inv, btn_tab_cust, btn_tab_ben, btn_tab_bank],
        alignment=ft.MainAxisAlignment.START,
        spacing=8,
        scroll=ft.ScrollMode.AUTO,
    )

    form_card = ft.Card(
        content=ft.Container(
            content=ft.Column(
                controls=[
                    tab_bar_row,
                    ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
                    sec_invoice,
                    sec_customer,
                    sec_beneficiary,
                    sec_bank,
                ],
                spacing=10,
            ),
            padding=15,
        ),
        elevation=2,
    )

    def clear_form():
        app_state["last_parsed_data"] = {}
        app_state["editing_original_inv_no"] = None
        txt_invoice_no.value = ""
        txt_pi_no.value = ""
        txt_date.value = ""
        txt_app_date.value = datetime.now().strftime("%Y-%m-%d")
        dd_branch.value = "المركز الرئيسي فرع عدن"
        dd_charge_type.value = "OUR"
        txt_payment_terms.value = ""
        txt_delivery_terms.value = ""
        txt_goods_desc.value = ""
        txt_quantity.value = ""
        txt_total_amount.value = "0.00"
        txt_transfer_amount.value = "0.00"
        txt_words_ar.value = ""
        txt_words_en.value = ""
        txt_transport.value = ""
        txt_port_loading.value = ""
        txt_port_discharge.value = ""
        txt_cust_name.value = ""
        txt_cust_address.value = ""
        txt_cust_phone.value = ""
        txt_cust_acc.value = ""
        txt_ben_name.value = ""
        txt_ben_address.value = ""
        txt_ben_phone.value = ""
        txt_ben_acc.value = ""
        txt_iban.value = ""
        txt_ben_bank.value = ""
        txt_swift.value = ""
        txt_corr_bank.value = ""
        txt_corr_swift.value = ""
        txt_purpose.value = ""
        progress_bar.visible = False
        status_text.value = "تمت إعادة تعيين وتفريغ جميع حقول النموذج بنجاح."
        page.update()

    def populate_form(r_data: dict):
        r_data = normalize_bank_fields(r_data)

        # 1. Branch Name
        b_name = (r_data.get("branch_name") or "").strip()
        if b_name:
            opt_keys = [opt.key for opt in dd_branch.options]
            if b_name not in opt_keys:
                dd_branch.options.append(ft.dropdown.Option(b_name, b_name))
            dd_branch.value = b_name

        # 2. Application Date
        if r_data.get("application_date"):
            txt_app_date.value = r_data["application_date"]

        # 3. Charge Type
        chg = (r_data.get("charge_type") or "").upper().strip()
        if chg in ["OUR", "BEN", "SHA"]:
            dd_charge_type.value = chg

        txt_invoice_no.value = r_data.get("invoice_no", "")
        txt_pi_no.value = r_data.get("pi_no", "")
        txt_date.value = r_data.get("date", "")
        txt_payment_terms.value = r_data.get("payment_terms", "")
        txt_delivery_terms.value = r_data.get("delivery_terms", "")
        txt_goods_desc.value = r_data.get("goods_description", "")
        txt_quantity.value = r_data.get("quantity", "")
        txt_total_amount.value = r_data.get("total_amount") or r_data.get("amount", "0.00")
        txt_transfer_amount.value = r_data.get("transfer_amount") or r_data.get("amount", "0.00")
        txt_words_ar.value = r_data.get("amount_in_words_ar", "")
        txt_words_en.value = r_data.get("amount_in_words_en", "")
        txt_currency.value = r_data.get("currency", "USD")
        txt_transport.value = r_data.get("transport_mode", "")
        txt_port_loading.value = r_data.get("port_of_loading", "")
        txt_port_discharge.value = r_data.get("port_of_discharge", "")
        
        cfg = tmpl_mgr.load_template()
        txt_cust_name.value = r_data.get("customer_name", "") or cfg.get("customer_name", "") or txt_cust_name.value
        txt_cust_address.value = r_data.get("customer_address", "") or cfg.get("customer_address", "") or txt_cust_address.value
        txt_cust_phone.value = r_data.get("customer_phone", "") or cfg.get("customer_phone", "") or txt_cust_phone.value
        txt_cust_acc.value = r_data.get("customer_account", "") or cfg.get("customer_account", "") or txt_cust_acc.value
        
        txt_ben_name.value = r_data.get("beneficiary_name", "")
        txt_ben_address.value = r_data.get("beneficiary_address", "")
        txt_ben_phone.value = r_data.get("beneficiary_phone", "")
        txt_ben_acc.value = r_data.get("beneficiary_acc_no", "")
        txt_iban.value = r_data.get("iban", "")
        txt_ben_bank.value = r_data.get("beneficiary_bank", "")
        txt_swift.value = r_data.get("swift_code", "")
        txt_corr_bank.value = r_data.get("correspondent_bank", "")
        txt_corr_swift.value = r_data.get("correspondent_swift", "")
        txt_purpose.value = r_data.get("purpose_of_transfer", "")
        recalculate_tafqeet_live()
        page.update()

    def gather_form_data() -> dict:
        cur_transfer_amt = txt_transfer_amount.value.strip() or txt_total_amount.value.strip()
        cur_total_amt = txt_total_amount.value.strip() or txt_transfer_amount.value.strip()
        res_data = {
            "application_date": txt_app_date.value,
            "branch_name": dd_branch.value or "المركز الرئيسي فرع عدن",
            "invoice_no": txt_invoice_no.value,
            "pi_no": txt_pi_no.value,
            "date": txt_date.value,
            "payment_terms": txt_payment_terms.value,
            "delivery_terms": txt_delivery_terms.value,
            "goods_description": txt_goods_desc.value,
            "quantity": txt_quantity.value,
            "amount": cur_transfer_amt,
            "transfer_amount": cur_transfer_amt,
            "total_amount": cur_total_amt,
            "amount_in_words_ar": txt_words_ar.value,
            "amount_in_words_en": txt_words_en.value,
            "currency": txt_currency.value,
            "transport_mode": txt_transport.value,
            "port_of_loading": txt_port_loading.value,
            "port_of_discharge": txt_port_discharge.value,
            "customer_name": txt_cust_name.value,
            "customer_address": txt_cust_address.value,
            "customer_phone": txt_cust_phone.value,
            "customer_account": txt_cust_acc.value,
            "beneficiary_name": txt_ben_name.value,
            "beneficiary_address": txt_ben_address.value,
            "beneficiary_phone": txt_ben_phone.value,
            "beneficiary_acc_no": txt_ben_acc.value,
            "iban": txt_iban.value,
            "beneficiary_bank": txt_ben_bank.value,
            "swift_code": txt_swift.value,
            "correspondent_bank": txt_corr_bank.value,
            "correspondent_swift": txt_corr_swift.value,
            "charge_type": dd_charge_type.value,
            "purpose_of_transfer": txt_purpose.value,
        }
        return normalize_bank_fields(res_data)

    def merge_parsed_data(old_data: dict, new_data: dict) -> dict:
        if not old_data:
            return new_data
        merged = dict(old_data)
        for k, v in new_data.items():
            if k == "raw_text":
                merged["raw_text"] = (old_data.get("raw_text", "") + "\n\n--- PAGE BREAK ---\n\n" + v).strip()
            elif v and (not merged.get(k) or merged.get(k) in ["1.00", "0.00", "USD", "TRY", "Unit", "N/A"]):
                merged[k] = v
        return merged

    def on_inv_no_change(e):
        if txt_invoice_no.border_color and txt_invoice_no.value.strip():
            txt_invoice_no.border_color = None
            page.update()

    txt_invoice_no.on_change = on_inv_no_change

    def merge_parsed_data(old_data: dict, new_data: dict) -> dict:
        if not old_data:
            return new_data
        merged = dict(old_data)
        for k, v in new_data.items():
            if k == "raw_text":
                merged["raw_text"] = (old_data.get("raw_text", "") + "\n\n--- PAGE BREAK ---\n\n" + v).strip()
            elif v:
                merged[k] = v
        return merged

    def process_file_path(file_path: str):
        if not file_path or not os.path.exists(file_path):
            return

        def process_worker():
            progress_bar.visible = True
            progress_bar.value = 0.15
            status_text.value = f"جاري المعالجة والترجمة: [15%] - قراءة الفاتورة {os.path.basename(file_path)}"
            try:
                page.update()
            except Exception:
                pass

            def on_parser_progress(pct_val, msg):
                progress_bar.value = pct_val
                if msg:
                    status_text.value = f"جاري المعالجة والترجمة: [{int(pct_val * 100):02d}%] - {msg}"
                try:
                    page.update()
                except Exception:
                    pass

            try:
                parsed_res = parser.parse_invoice(file_path, progress_callback=on_parser_progress)
                app_state["editing_original_inv_no"] = None
                app_state["last_parsed_data"] = parsed_res

                inv_n = parsed_res.get("invoice_no", "").strip()
                is_dup = False
                if inv_n:
                    is_dup, _ = registry.is_duplicate(inv_n)

                populate_form(parsed_res)

                filled_count = sum(1 for k, v in parsed_res.items() if v and k not in ["raw_text", "application_date", "branch_name", "charge_type"])
                progress_bar.visible = True
                progress_bar.value = 1.0

                if is_dup:
                    status_text.value = f"⚠️ تنبيه: الفاتورة رقم [{inv_n}] موجودة سابقاً في السجل! (تم استخراج وتفريغ {filled_count} من 23 حقل)"
                else:
                    status_text.value = f"✅ اكتملت قراءة وتفريغ وترجمة [100% - {filled_count} من 23 حقل] من الفاتورة بنجاح!"
                page.update()
            except Exception as ex:
                status_text.value = f"❌ خطأ أثناء معالجة الفاتورة: {str(ex)}"
                progress_bar.visible = False
                page.update()

        threading.Thread(target=process_worker, daemon=True).start()

    def trigger_attach_invoice(e=None):
        status_text.value = "جاري فتح نافذة اختيار ملف الفاتورة..."
        progress_bar.visible = True
        progress_bar.value = None
        page.update()

        is_desktop_win = (os.name == "nt" and not os.environ.get("ANDROID_ARGUMENT"))
        if is_desktop_win or file_picker is None:
            def attach_worker():
                f_p = pick_file_native()
                if f_p:
                    clean_p = f_p.strip().strip('"\'')
                    if os.path.exists(clean_p):
                        process_file_path(clean_p)
                        return
                status_text.value = "❌ لم يتم اختيار أي ملف."
                progress_bar.visible = False
                page.update()
            threading.Thread(target=attach_worker, daemon=True).start()
        elif file_picker:
            try:
                file_picker.pick_files(
                    dialog_title="اختر ملف الفاتورة التجارية",
                    file_type=ft.FilePickerFileType.ANY,
                    allow_multiple=False,
                    with_data=True
                )
            except Exception as ex:
                status_text.value = f"❌ خطأ عند فتح مستعرض الملفات: {ex}"
                progress_bar.visible = False
                page.update()

    BTN_HEIGHT = 38
    BTN_PADDING = ft.padding.Padding(10, 4, 10, 4)

    def exit_app_action(e=None):
        try:
            page.window_close()
        except Exception:
            pass
        try:
            sys.exit(0)
        except Exception:
            pass

    btn_attach_invoice = ft.Button(
        "إرفاق فاتورة",
        icon=ft.Icons.UPLOAD_FILE,
        height=BTN_HEIGHT,
        style=ft.ButtonStyle(bgcolor=ACCENT_ORANGE, color=ft.Colors.WHITE, padding=BTN_PADDING),
        on_click=trigger_attach_invoice
    )

    btn_view_translation = ft.Button(
        "معاينة وترجمة",
        icon=ft.Icons.TRANSLATE,
        height=BTN_HEIGHT,
        style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_800, color=ft.Colors.WHITE, padding=BTN_PADDING),
        on_click=lambda _: open_translation_dialog()
    )

    btn_save_registry = ft.Button(
        "حفظ بالسجل",
        icon=ft.Icons.SAVE,
        height=BTN_HEIGHT,
        style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN_700, color=ft.Colors.WHITE, padding=BTN_PADDING),
        on_click=lambda _: save_to_history()
    )

    btn_load_history = ft.Button(
        "سجل الحوالات",
        icon=ft.Icons.EDIT_NOTE,
        height=BTN_HEIGHT,
        style=ft.ButtonStyle(bgcolor=ACCENT_ORANGE, color=ft.Colors.WHITE, padding=BTN_PADDING),
        on_click=lambda _: open_history_dialog()
    )

    btn_export_pdf = ft.Button(
        "تصدير PDF",
        icon=ft.Icons.PICTURE_IN_PICTURE,
        height=BTN_HEIGHT,
        style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN_700, color=ft.Colors.WHITE, padding=BTN_PADDING),
        on_click=lambda _: export_pdf_action()
    )

    btn_customize_terms = ft.Button(
        "تخصيص العميل",
        icon=ft.Icons.SETTINGS,
        height=BTN_HEIGHT,
        style=ft.ButtonStyle(bgcolor=ft.Colors.TEAL_700, color=ft.Colors.WHITE, padding=BTN_PADDING),
        on_click=lambda _: open_terms_customization_dialog()
    )

    btn_reset_form = ft.Button(
        "إعادة تعيين",
        icon=ft.Icons.REFRESH,
        height=BTN_HEIGHT,
        style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_GREY_600, color=ft.Colors.WHITE, padding=BTN_PADDING),
        on_click=lambda _: clear_form()
    )

    btn_exit_app = ft.Button(
        "إغلاق التطبيق",
        icon=ft.Icons.EXIT_TO_APP,
        height=BTN_HEIGHT,
        style=ft.ButtonStyle(bgcolor=ft.Colors.RED_700, color=ft.Colors.WHITE, padding=BTN_PADDING),
        on_click=exit_app_action,
    )

    top_action_bar = ft.Container(
        content=ft.Row(
            controls=[
                btn_attach_invoice,
                btn_view_translation,
                btn_save_registry,
                btn_load_history,
                btn_export_pdf,
                btn_customize_terms,
                btn_reset_form,
            ],
            spacing=6,
            scroll=ft.ScrollMode.AUTO,
            alignment=ft.MainAxisAlignment.START,
        ),
        padding=ft.padding.Padding(6, 4, 6, 4),
        bgcolor=ft.Colors.WHITE,
        border_radius=8,
        border=ft.Border.all(1, ft.Colors.BLUE_GREY_100),
    )

    def open_translation_dialog():
        raw_txt = app_state["last_parsed_data"].get("raw_text", "لم يتم إرفاق أو قراءة أي فاتورة بعد.")
        
        translated_full_text = parser.translate_to_ar(raw_txt) if raw_txt and raw_txt != "لم يتم إرفاق أو قراءة أي فاتورة بعد." else "لا يوجد نص مترجم"

        d_inv_no = ft.TextField(label="1. رقم الفاتورة (Invoice No)", value=txt_invoice_no.value, col={"sm": 12, "md": 6})
        d_date = ft.TextField(label="2. تاريخ الفاتورة (Date)", value=txt_date.value, col={"sm": 12, "md": 6})
        d_ben_name = ft.TextField(label="3. اسم المورد المستفيد (Beneficiary Name)", value=txt_ben_name.value, col={"sm": 12, "md": 6})
        d_ben_bank = ft.TextField(label="4. بنك المستفيد (Beneficiary Bank)", value=txt_ben_bank.value, col={"sm": 12, "md": 6})
        d_swift = ft.TextField(label="5. كود السويفت (SWIFT Code)", value=txt_swift.value, col={"sm": 12, "md": 4})
        d_acc = ft.TextField(label="6. رقم الحساب (Account No)", value=txt_ben_acc.value, col={"sm": 12, "md": 4})
        d_iban = ft.TextField(label="7. IBAN", value=txt_iban.value, col={"sm": 12, "md": 4})
        d_cust_name = ft.TextField(label="8. العميل المستورد (Customer Name)", value=txt_cust_name.value, col={"sm": 12, "md": 6})
        d_total_amt = ft.TextField(label="9. إجمالي المبلغ (Total Amount)", value=txt_total_amount.value, col={"sm": 12, "md": 6})
        d_goods_desc = ft.TextField(label="10. وصف البضاعة (Goods Description)", value=txt_goods_desc.value, col={"sm": 12, "md": 12})
        d_payment_terms = ft.TextField(label="11. شروط الدفع (Payment Terms)", value=txt_payment_terms.value, col={"sm": 12, "md": 6})
        d_delivery_terms = ft.TextField(label="12. شروط التسليم (Delivery Terms)", value=txt_delivery_terms.value, col={"sm": 12, "md": 6})
        d_port_load = ft.TextField(label="13. ميناء المغادرة (Port of Loading)", value=txt_port_loading.value, col={"sm": 12, "md": 6})
        d_port_disc = ft.TextField(label="14. ميناء الوصول (Port of Discharge)", value=txt_port_discharge.value, col={"sm": 12, "md": 6})

        def apply_verified_translation(e):
            txt_invoice_no.value = d_inv_no.value
            txt_date.value = d_date.value
            txt_ben_name.value = d_ben_name.value
            txt_ben_bank.value = d_ben_bank.value
            txt_swift.value = d_swift.value
            txt_ben_acc.value = d_acc.value
            txt_iban.value = d_iban.value
            txt_cust_name.value = d_cust_name.value
            txt_total_amount.value = d_total_amt.value
            txt_transfer_amount.value = d_total_amt.value
            txt_goods_desc.value = d_goods_desc.value
            txt_payment_terms.value = d_payment_terms.value
            txt_delivery_terms.value = d_delivery_terms.value
            txt_port_loading.value = d_port_load.value
            txt_port_discharge.value = d_port_disc.value
            recalculate_tafqeet_live()
            dlg_trans.open = False
            status_text.value = "تمت ترجمة الفاتورة وتطبيق الـ 23 حقل في النموذج بنجاح!"
            page.update()

        dlg_trans = ft.AlertDialog(
            title=ft.Text("🌐 معاينة وترجمة البيانات النصية والحقول الاستخراجية للفاتورة", weight=ft.FontWeight.BOLD, color=PRIMARY_COLOR),
            content=ft.Container(
                content=ft.Column([
                    ft.Text("📋 المراجعة والمطابقة الدلالية للحقول المترجمة (يمكنك التعديل مباشرة قبل التطبيق):", weight=ft.FontWeight.BOLD, size=13, color=ACCENT_ORANGE),
                    ft.ResponsiveRow([
                        d_inv_no, d_date,
                        d_ben_name, d_ben_bank,
                        d_swift, d_acc, d_iban,
                        d_cust_name, d_total_amt,
                        d_goods_desc, d_payment_terms,
                        d_delivery_terms, d_port_load, d_port_disc
                    ], run_spacing=10, spacing=10),
                    ft.Divider(height=10),
                    ft.Text("📄 النص الكامل المترجم آلياً للغة العربية:", weight=ft.FontWeight.BOLD, size=13, color=PRIMARY_COLOR),
                    ft.TextField(value=translated_full_text, multiline=True, min_lines=6, read_only=False),
                    ft.Divider(height=10),
                    ft.Text("🔤 النص الأصلي الخام المستخرج (Original OCR Text):", weight=ft.FontWeight.BOLD, size=12, color=ft.Colors.BLUE_GREY_700),
                    ft.TextField(value=raw_txt, multiline=True, min_lines=4, read_only=True),
                ], spacing=10, scroll=ft.ScrollMode.AUTO, height=480),
            ),
            actions=[
                ft.Button("تطبيق وتحديث النموذج", icon=ft.Icons.CHECK_CIRCLE, on_click=apply_verified_translation, style=ft.ButtonStyle(bgcolor=ACCENT_ORANGE, color=ft.Colors.WHITE)),
                ft.Button("إغلاق الشاشة", icon=ft.Icons.CLOSE, on_click=lambda _: setattr(dlg_trans, "open", False) or page.update(), style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_GREY_200, color=ft.Colors.BLACK)),
            ],
        )
        page.overlay.append(dlg_trans)
        dlg_trans.open = True
        page.update()

    def save_to_history():
        data = gather_form_data()
        inv_n = data.get("invoice_no", "").strip()

        if not inv_n:
            txt_invoice_no.border_color = ft.Colors.RED
            txt_invoice_no.focus()
            status_text.value = "❌ خطأ: رقم الفاتورة إجباري ومطلوب. لا يمكن حفظ أي فاتورة أو حوالة بدون رقم فاتورة!"
            page.update()
            return
        txt_invoice_no.border_color = None

        orig_inv = app_state.get("editing_original_inv_no")
        is_dup, existing = registry.is_duplicate(inv_n)

        # Enforce uniqueness: block save if inv_n already exists for a different record
        if is_dup and (not orig_inv or registry.normalize_str(orig_inv) != registry.normalize_str(inv_n)):
            dlg_dup = ft.AlertDialog(
                title=ft.Text("❌ رقم الفاتورة مكرر ومسجل سابقاً", weight=ft.FontWeight.BOLD, color=ft.Colors.RED_700),
                content=ft.Container(
                    content=ft.Column([
                        ft.Text(f"رقم الفاتورة [{inv_n}] مسجل سابقاً بالنظام!", size=14, weight=ft.FontWeight.BOLD),
                        ft.Text(f"المستفيد المسجل سابقاً: {existing.get('beneficiary_name', 'N/A')}", size=13),
                        ft.Text(f"مبلغ الحوالة: {existing.get('transfer_amount', '0.00')} {existing.get('currency', 'USD')}", size=13),
                        ft.Text(f"تاريخ التسجيل: {existing.get('timestamp', 'N/A')}", size=12, color=ft.Colors.BLUE_GREY_700),
                        ft.Divider(height=10),
                        ft.Text("لا يمكن حفظ فاتورتين بنفس الرقم في النظام لمنع التكرار والأخطاء المالية.", size=13, color=ft.Colors.RED_800),
                    ], spacing=8),
                    width=480,
                ),
                actions=[
                    ft.Button("موافق", style=ft.ButtonStyle(bgcolor=ACCENT_ORANGE, color=ft.Colors.WHITE), on_click=lambda _: setattr(dlg_dup, "open", False) or page.update())
                ],
            )
            page.overlay.append(dlg_dup)
            dlg_dup.open = True
            txt_invoice_no.border_color = ft.Colors.RED
            status_text.value = f"❌ خطأ: رقم الفاتورة [{inv_n}] مسجل سابقاً بالنظام ولا يمكن تكراره!"
            page.update()
            return

        if orig_inv:
            registry.update_or_save_invoice(orig_inv, inv_n, data)
            app_state["editing_original_inv_no"] = inv_n
            status_text.value = f"✅ تم تحديث وحفظ بيانات الفاتورة الأصلية رقم [{inv_n}] في السجل بنجاح!"
        else:
            registry.save_invoice(inv_n, data)
            app_state["editing_original_inv_no"] = inv_n
            status_text.value = f"✅ تم حفظ الحوالة رقم [{inv_n}] بالسجل بنجاح!"

        page.update()

    def export_pdf_action():
        data = gather_form_data()
        inv_n = data.get("invoice_no", "").strip()

        if not inv_n:
            txt_invoice_no.border_color = ft.Colors.RED
            txt_invoice_no.focus()
            status_text.value = "❌ خطأ: رقم الفاتورة إجباري. لا يمكن تصدير طلب الحوالة بدون رقم فاتورة!"
            page.update()
            return
        txt_invoice_no.border_color = None

        # Auto-save data into registry on PDF export
        orig_inv = app_state.get("editing_original_inv_no")
        registry.update_or_save_invoice(orig_inv or inv_n, inv_n, data)
        app_state["editing_original_inv_no"] = inv_n

        def worker():
            status_text.value = "جاري إنشاء وتصدير وثيقة PDF الرسمية (A4)..."
            progress_bar.visible = True
            progress_bar.value = None
            page.update()
            
            clean_inv = re.sub(r'[^A-Za-z0-9]', '_', inv_n)
            filename = f"SWIFT_Transfer_{clean_inv}.pdf"
            
            is_desktop_win = (os.name == "nt" and not os.environ.get("ANDROID_ARGUMENT"))
            
            out_path = os.path.join(tempfile.gettempdir(), filename)
            
            if is_desktop_win:
                desktop_dir = os.path.join(os.path.expanduser("~"), "Desktop")
                if os.path.exists(desktop_dir):
                    out_path = os.path.join(desktop_dir, filename)
            else:
                dl_dirs = ["/storage/emulated/0/Download", "/sdcard/Download"]
                for dl_dir in dl_dirs:
                    if os.path.exists(dl_dir):
                        try:
                            candidate = os.path.join(dl_dir, filename)
                            pdf_gen.generate_pdf(data, candidate)
                            out_path = candidate
                            break
                        except Exception:
                            pass

            try:
                pdf_gen.generate_pdf(data, out_path)

                progress_bar.visible = True
                progress_bar.value = 1.0
                status_text.value = f"✅ تم تصدير وثيقة PDF الرسمية (A4) بنجاح: {filename}"
                
                if is_desktop_win and hasattr(os, "startfile"):
                    try:
                        os.startfile(out_path)
                    except Exception:
                        pass

                dlg_pdf_ok = ft.AlertDialog(
                    title=ft.Text("✅ تم تصدير وثيقة PDF (A4) بنجاح", weight=ft.FontWeight.BOLD, color=PRIMARY_COLOR),
                    content=ft.Container(
                        content=ft.Column([
                            ft.Text("تم إنشاء وثيقة طلب إصدار الحوالة الخارجية (صفحتين A4) بنجاح!", size=13, weight=ft.FontWeight.BOLD),
                            ft.Text(f"📄 اسم الملف: {filename}", size=12, color=ACCENT_ORANGE, weight=ft.FontWeight.BOLD),
                            ft.Text(f"📁 مكان الحفظ: {out_path}", size=11, color=ft.Colors.BLUE_GREY_700),
                        ], spacing=8),
                        padding=10,
                    ),
                    actions=[
                        ft.Button("موافق", style=ft.ButtonStyle(bgcolor=ACCENT_ORANGE, color=ft.Colors.WHITE), on_click=lambda _: setattr(dlg_pdf_ok, "open", False) or page.update())
                    ],
                )
                page.overlay.append(dlg_pdf_ok)
                dlg_pdf_ok.open = True
                page.update()
            except Exception as ex:
                progress_bar.visible = False
                status_text.value = f"❌ خطأ في تصدير PDF: {str(ex)}"
                page.update()

        threading.Thread(target=worker, daemon=True).start()

    def open_history_dialog():
        records = registry.list_all_invoices()
        
        def load_selected_record(record_data):
            app_state["last_parsed_data"] = dict(record_data)
            app_state["editing_original_inv_no"] = record_data.get("invoice_no")
            populate_form(record_data)
            switch_tab("inv")
            dlg_history.open = False
            status_text.value = f"✅ تم استرجاع وتعبئة بيانات الحوالة الأصلية رقم [{record_data.get('invoice_no')}] بنجاح للتعديل وتحديث السجل!"
            page.update()

        def delete_record_item(inv_no):
            def confirm_delete(e):
                registry.delete_invoice(inv_no)
                dlg_confirm.open = False
                dlg_history.open = False
                page.update()
                open_history_dialog()

            dlg_confirm = ft.AlertDialog(
                title=ft.Text("تأكيد الحذف", weight=ft.FontWeight.BOLD, color=ft.Colors.RED_700),
                content=ft.Text(f"هل أنت تأكيد من حذف هذا السجل رقم [{inv_no}] نهائياً؟", size=14),
                actions=[
                    ft.Button("نعم", style=ft.ButtonStyle(bgcolor=ft.Colors.RED_700, color=ft.Colors.WHITE), on_click=confirm_delete),
                    ft.Button("لا", style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_GREY_200, color=ft.Colors.BLACK), on_click=lambda _: setattr(dlg_confirm, "open", False) or page.update()),
                ],
            )
            page.overlay.append(dlg_confirm)
            dlg_confirm.open = True
            page.update()

        rows = []
        for r in records:
            inv_no = r.get("invoice_no", "N/A")
            b_name = r.get("beneficiary_name", "N/A")
            amt = r.get("amount", "0.00")
            dt = r.get("date", "N/A")
            curr = r.get("currency", "USD")

            rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(inv_no, weight=ft.FontWeight.BOLD, size=13)),
                        ft.DataCell(ft.Text(b_name[:40], size=12)),
                        ft.DataCell(ft.Text(f"{amt} {curr}", weight=ft.FontWeight.BOLD, color=PRIMARY_COLOR)),
                        ft.DataCell(ft.Text(dt, size=12)),
                        ft.DataCell(
                            ft.Row([
                                ft.Button(
                                    "تعديل واسترجاع",
                                    icon=ft.Icons.EDIT,
                                    style=ft.ButtonStyle(bgcolor=ACCENT_ORANGE, color=ft.Colors.WHITE),
                                    on_click=lambda _, data=r: load_selected_record(data)
                                ),
                                ft.IconButton(
                                    icon=ft.Icons.DELETE_FOREVER,
                                    tooltip="حذف نهائي",
                                    icon_color=ft.Colors.RED_700,
                                    on_click=lambda _, num=inv_no: delete_record_item(num)
                                )
                            ], alignment=ft.MainAxisAlignment.END, spacing=5)
                        ),
                    ]
                )
            )

        tbl = ft.DataTable(
            column_spacing=25,
            columns=[
                ft.DataColumn(ft.Text("رقم الفاتورة", weight=ft.FontWeight.BOLD, size=13)),
                ft.DataColumn(ft.Text("اسم المستفيد", weight=ft.FontWeight.BOLD, size=13)),
                ft.DataColumn(ft.Text("المبلغ", weight=ft.FontWeight.BOLD, size=13)),
                ft.DataColumn(ft.Text("التاريخ", weight=ft.FontWeight.BOLD, size=13)),
                ft.DataColumn(ft.Text("إجراءات السجل", weight=ft.FontWeight.BOLD, size=13)),
            ],
            rows=rows,
        )

        scrollable_table = ft.Row(
            controls=[tbl],
            scroll=ft.ScrollMode.AUTO,
            alignment=ft.MainAxisAlignment.START,
        )

        dlg_history = ft.AlertDialog(
            title=ft.Text("📋 سجل الفواتير والحوالات المحفوظة (سجل التعديل والاسترجاع)", weight=ft.FontWeight.BOLD, color=PRIMARY_COLOR, size=16),
            content=ft.Container(
                content=ft.Column([
                    scrollable_table
                ], scroll=ft.ScrollMode.AUTO, height=450),
                padding=5,
            ),
            actions=[
                ft.Button(
                    "إغلاق الشاشة",
                    icon=ft.Icons.CLOSE,
                    style=ft.ButtonStyle(bgcolor=ACCENT_ORANGE, color=ft.Colors.WHITE),
                    on_click=lambda _: setattr(dlg_history, "open", False) or page.update()
                )
            ],
        )
        page.overlay.append(dlg_history)
        dlg_history.open = True
        page.update()

    def open_terms_customization_dialog():
        txt_cfg_customer_name = ft.TextField(label="اسم الشركة المستوردة المعتمدة", value=saved_config.get("customer_name", ""), expand=True)
        txt_cfg_customer_addr = ft.TextField(label="العنوان المعتمد", value=saved_config.get("customer_address", ""), expand=True)
        txt_cfg_customer_phone = ft.TextField(label="الهاتف المعتمد", value=saved_config.get("customer_phone", ""), expand=True)
        txt_cfg_customer_acc = ft.TextField(label="رقم الحساب الجاري المعتمد بالبنك", value=saved_config.get("customer_account", ""), expand=True)

        def save_cfg():
            saved_config["customer_name"] = txt_cfg_customer_name.value
            saved_config["customer_address"] = txt_cfg_customer_addr.value
            saved_config["customer_phone"] = txt_cfg_customer_phone.value
            saved_config["customer_account"] = txt_cfg_customer_acc.value

            tmpl_mgr.save_template(saved_config)
            
            txt_cust_name.value = txt_cfg_customer_name.value
            txt_cust_address.value = txt_cfg_customer_addr.value
            txt_cust_phone.value = txt_cfg_customer_phone.value
            txt_cust_acc.value = txt_cfg_customer_acc.value

            dlg_terms.open = False
            status_text.value = "تم حفظ الإعدادات الافتراضية للعميل بنجاح!"
            page.update()

        dlg_terms = ft.AlertDialog(
            title=ft.Text("تخصيص البيانات الإفتراضية للعميل الآمر بالحوالة"),
            content=ft.Container(
                content=ft.Column(
                    controls=[
                        txt_cfg_customer_name,
                        txt_cfg_customer_addr,
                        txt_cfg_customer_phone,
                        txt_cfg_customer_acc,
                    ],
                    spacing=12,
                    height=300,
                ),
                width=550,
            ),
            actions=[
                ft.Button("حفظ الإعدادات", on_click=lambda _: save_cfg(), style=ft.ButtonStyle(bgcolor=ACCENT_ORANGE, color=ft.Colors.WHITE)),
                ft.TextButton("إلغاء", on_click=lambda _: setattr(dlg_terms, "open", False) or page.update()),
            ],
        )
        page.overlay.append(dlg_terms)
        dlg_terms.open = True
        page.update()

    # Header Title & Qasemi Logo
    header_title = ft.Text(
        "بنك القاسمي للتمويل الأصغر الإسلامي - طلب إصدار حوالة خارجية",
        size=14,
        weight=ft.FontWeight.BOLD,
        color=PRIMARY_COLOR,
        text_align=ft.TextAlign.RIGHT,
        max_lines=2,
        overflow=ft.TextOverflow.ELLIPSIS,
    )
    header_subtitle = ft.Text(
        "FOREIGN MONEY TRANSFER ORDER",
        size=10,
        weight=ft.FontWeight.BOLD,
        color=ft.Colors.BLUE_GREY_700,
        text_align=ft.TextAlign.RIGHT,
        max_lines=1,
        overflow=ft.TextOverflow.ELLIPSIS,
    )

    logo_src = get_logo_b64_src()
    logo_img = ft.Image(src=logo_src, width=150, height=45, fit="contain") if logo_src else ft.Container()

    header_container = ft.Container(
        content=ft.Row(
            controls=[
                logo_img,
                ft.Container(
                    content=ft.Column(
                        [header_title, header_subtitle],
                        alignment=ft.MainAxisAlignment.CENTER,
                        horizontal_alignment=ft.CrossAxisAlignment.START,
                        spacing=2,
                    ),
                    expand=True,
                    padding=ft.padding.Padding(8, 0, 8, 0),
                ),
                ft.Container(
                    content=btn_exit_app,
                    alignment=ft.alignment.Alignment(-1.0, -1.0),
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.padding.Padding(6, 4, 6, 4),
    )

    page.scroll = ft.ScrollMode.AUTO
    page.add(
        header_container,
        top_action_bar,
        status_banner,
        form_card,
    )


if __name__ == "__main__":
    assets_path = os.path.join(os.path.dirname(__file__), "assets")
    if hasattr(ft, "run"):
        try:
            ft.run(main, assets_dir=assets_path)
        except Exception:
            ft.app(target=main, assets_dir=assets_path)
    else:
        ft.app(target=main, assets_dir=assets_path)

