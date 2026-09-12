import json
import os
import re
import socket
import getpass
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple


from parser import normalize_bank_fields


class InvoiceRegistry:
    """
    سجل الحماية والتدقيق المالي لمنع تكرار الفواتير والحوالات الصادرة وإدارتها على مستوى الموظفين والفروع
    (Multi-User Central Invoice Duplicate Prevention & Audit Registry)
    """

    def __init__(self, db_path: str = "invoice_history_db.json"):
        # إمكانية الربط بمجلد شبكي مشترك عبر خادم البنك المركز الرئيسي
        self.db_path = os.getenv("QASEMI_SHARED_DB_PATH", db_path)
        self.ensure_db_exists()

    def ensure_db_exists(self):
        if not os.path.exists(self.db_path):
            try:
                out_dir = os.path.dirname(self.db_path)
                if out_dir:
                    os.makedirs(out_dir, exist_ok=True)
                with open(self.db_path, "w", encoding="utf-8") as f:
                    json.dump([], f, ensure_ascii=False, indent=4)
            except Exception as e:
                print(f"Error creating shared registry db: {e}")

    def load_history(self) -> List[Dict[str, Any]]:
        try:
            if os.path.exists(self.db_path):
                with open(self.db_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    recs = []
                    if isinstance(data, list):
                        recs = data
                    elif isinstance(data, dict):
                        recs = list(data.values())
                    for r in recs:
                        if isinstance(r, dict):
                            normalize_bank_fields(r)
                    return recs
        except Exception as e:
            print(f"Error loading invoice registry: {e}")
        return []

    def get_all_records(self) -> List[Dict[str, Any]]:
        return self.load_history()

    def list_all_invoices(self) -> List[Dict[str, Any]]:
        return self.load_history()

    def normalize_str(self, val: str) -> str:
        if not val:
            return ""
        return re.sub(r"[^A-Za-z0-9]", "", str(val)).upper()

    def is_duplicate(self, invoice_no: str, beneficiary_name: str = "") -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        التحقق اللحظي التشاركي مما إذا كان رقم الفاتورة سبق إدخالها من موظف آخر أو نفس الموظف
        """
        norm_inv = self.normalize_str(invoice_no)
        if not norm_inv or norm_inv in ["NEW", "0", "NONE"]:
            return False, None

        history = self.load_history()

        for rec in history:
            rec_inv = self.normalize_str(rec.get("invoice_no", ""))
            if norm_inv == rec_inv:
                return True, rec

        return False, None

    def register_invoice(self, data: Dict[str, Any]) -> bool:
        """
        تسجيل وحفظ الفاتورة في السجل المشترك مع توثيق اسم الموظف والجهاز والفرع والتاريخ
        """
        inv_no = data.get("invoice_no", "").strip()
        if not inv_no:
            return False

        history = self.load_history()

        # توثيق هويات الموظفين والأجهزة للتتبع والأمان المالي
        user_name = getpass.getuser()
        pc_name = socket.gethostname()

        record = {
            "invoice_no": inv_no,
            "pi_no": data.get("pi_no", ""),
            "date": data.get("date", ""),
            "application_date": data.get("application_date", ""),
            "branch_name": data.get("branch_name", "المركز الرئيسي"),
            "payment_terms": data.get("payment_terms", ""),
            "delivery_terms": data.get("delivery_terms", ""),
            "goods_description": data.get("goods_description", ""),
            "quantity": data.get("quantity", ""),
            "amount": data.get("amount", ""),
            "transfer_amount": data.get("transfer_amount", ""),
            "total_amount": data.get("total_amount", ""),
            "amount_in_words_ar": data.get("amount_in_words_ar", ""),
            "amount_in_words_en": data.get("amount_in_words_en", ""),
            "currency": data.get("currency", "USD"),
            "transport_mode": data.get("transport_mode", ""),
            "port_of_loading": data.get("port_of_loading", ""),
            "port_of_discharge": data.get("port_of_discharge", ""),
            "customer_name": data.get("customer_name", ""),
            "customer_address": data.get("customer_address", ""),
            "customer_phone": data.get("customer_phone", ""),
            "customer_account": data.get("customer_account", ""),
            "beneficiary_name": data.get("beneficiary_name", ""),
            "beneficiary_address": data.get("beneficiary_address", ""),
            "beneficiary_phone": data.get("beneficiary_phone", ""),
            "beneficiary_acc_no": data.get("beneficiary_acc_no", ""),
            "iban": data.get("iban", ""),
            "beneficiary_bank": data.get("beneficiary_bank", ""),
            "swift_code": data.get("swift_code", ""),
            "correspondent_bank": data.get("correspondent_bank", ""),
            "correspondent_swift": data.get("correspondent_swift", ""),
            "charge_type": data.get("charge_type", "OUR"),
            "purpose_of_transfer": data.get("purpose_of_transfer", ""),
            "user_name": user_name,
            "pc_name": pc_name,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "PROCESSED_AND_SAVED"
        }

        normalize_bank_fields(record)

        is_dup, existing = self.is_duplicate(inv_no, data.get("beneficiary_name", ""))
        if is_dup and existing:
            existing.update(record)
        else:
            history.append(record)

        try:
            with open(self.db_path, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=4)
            return True
        except Exception as e:
            print(f"Error saving to invoice registry: {e}")
            return False

    def save_invoice(self, invoice_no: str, data: Dict[str, Any]) -> bool:
        data["invoice_no"] = invoice_no
        return self.register_invoice(data)

    def update_or_save_invoice(self, orig_inv_no: str, new_inv_no: str, data: Dict[str, Any]) -> bool:
        """
        تحديث واعتمد السجل الأصلي للفاتورة بالسجل المشترك عند تعديل بياناتها
        """
        history = self.load_history()
        norm_orig = self.normalize_str(orig_inv_no)
        norm_new = self.normalize_str(new_inv_no)

        target_record = None
        if norm_orig:
            for rec in history:
                if self.normalize_str(rec.get("invoice_no", "")) == norm_orig:
                    target_record = rec
                    break

        if not target_record and norm_new:
            for rec in history:
                if self.normalize_str(rec.get("invoice_no", "")) == norm_new:
                    target_record = rec
                    break

        user_name = getpass.getuser()
        pc_name = socket.gethostname()

        updated_fields = {
            "invoice_no": new_inv_no,
            "pi_no": data.get("pi_no", ""),
            "date": data.get("date", ""),
            "application_date": data.get("application_date", ""),
            "branch_name": data.get("branch_name", "المركز الرئيسي فرع عدن"),
            "payment_terms": data.get("payment_terms", ""),
            "delivery_terms": data.get("delivery_terms", ""),
            "goods_description": data.get("goods_description", ""),
            "quantity": data.get("quantity", ""),
            "amount": data.get("amount", ""),
            "transfer_amount": data.get("transfer_amount", ""),
            "total_amount": data.get("total_amount", ""),
            "amount_in_words_ar": data.get("amount_in_words_ar", ""),
            "amount_in_words_en": data.get("amount_in_words_en", ""),
            "currency": data.get("currency", "USD"),
            "transport_mode": data.get("transport_mode", ""),
            "port_of_loading": data.get("port_of_loading", ""),
            "port_of_discharge": data.get("port_of_discharge", ""),
            "customer_name": data.get("customer_name", ""),
            "customer_address": data.get("customer_address", ""),
            "customer_phone": data.get("customer_phone", ""),
            "customer_account": data.get("customer_account", ""),
            "beneficiary_name": data.get("beneficiary_name", ""),
            "beneficiary_address": data.get("beneficiary_address", ""),
            "beneficiary_phone": data.get("beneficiary_phone", ""),
            "beneficiary_acc_no": data.get("beneficiary_acc_no", ""),
            "iban": data.get("iban", ""),
            "beneficiary_bank": data.get("beneficiary_bank", ""),
            "swift_code": data.get("swift_code", ""),
            "correspondent_bank": data.get("correspondent_bank", ""),
            "correspondent_swift": data.get("correspondent_swift", ""),
            "charge_type": data.get("charge_type", "OUR"),
            "purpose_of_transfer": data.get("purpose_of_transfer", ""),
            "user_name": user_name,
            "pc_name": pc_name,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "MODIFIED_AND_SAVED"
        }

        normalize_bank_fields(updated_fields)

        if target_record:
            target_record.update(updated_fields)
        else:
            history.append(updated_fields)

        try:
            with open(self.db_path, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=4)
            return True
        except Exception as e:
            print(f"Error updating invoice in registry: {e}")
            return False

    def delete_invoice(self, invoice_no: str) -> bool:
        norm_target = self.normalize_str(invoice_no)
        if not norm_target:
            return False

        history = self.load_history()
        new_history = [
            rec for rec in history
            if self.normalize_str(rec.get("invoice_no", "")) != norm_target
        ]

        if len(new_history) < len(history):
            try:
                with open(self.db_path, "w", encoding="utf-8") as f:
                    json.dump(new_history, f, ensure_ascii=False, indent=4)
                return True
            except Exception as e:
                print(f"Error deleting from invoice registry: {e}")
        return False

    def clear_all_history(self) -> bool:
        try:
            with open(self.db_path, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=4)
            return True
        except Exception as e:
            print(f"Error clearing invoice registry: {e}")
            return False
