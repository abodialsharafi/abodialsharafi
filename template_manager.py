import json
import os
from typing import Dict, Any

class TemplateManager:
    """
    محرك إدارة وحفظ القوالب الرسمية المكونة من صفحتين (صفحة البيانات + صفحة الشروط والبنود)
    """

    def __init__(self, config_path: str = "swift_template_config.json"):
        self.config_path = config_path
        self.default_terms = (
            "1. يقر الآمر بالحوالة بصحة كافة البيانات المذكورة أعلاه وخلوها من أي أخطاء، ويتحمل المسؤولية الكاملة عن أي تأخير أو رفض صادر من البنك المستفيد أو البنك الوسيط نتيجة خطأ في البيانات.\n"
            "2. يخضع تنفيذ هذا الطلب للقوانين واللوائح المصرفية النافذة ولتعليمات مكافحة غسيل الأموال وتمويل الإرهاب وقواعد لجنة سويفت العالمية (SWIFT).\n"
            "3. جميع العمولات والرسوم البنكية المفروضة من البنوك الوسيطة أو البنك المستفيد تقتطع من مبلغ الحوالة ما لم يُتفق على خلاف ذلك صراحة في شروط الدفع.\n"
            "4. البنك غير مسؤول عن أي تأخير أو خطأ في إرسال البرقيات ينجم عن أسباب خارجة عن إرادته أو انقطاع في شبكات الاتصالات العالمية.\n"
            "5. لا يجوز تعديل أو إلغاء الحوالة بعد صدور رسالة السويفت إلا بعد موافقة البنك المستفيد وقبوله بإعادة المبلغ المرقن.\n"
            "6. يلتزم العميل بتقديم الفاتورة التجارية الأصيلة وبوليصة الشحن الواردة للجهات الجمركية والمصرفية عند طلبها.\n"
            "7. يقر العميل بأن البضاعة الموضحة بالفاتورة لا تخالف لوائح الاستيراد أو العقوبات الدولية الحظر المصرفي.\n"
            "8. يعتبر التوقيع والختم الرسمي أدناه إقراراً بالالتزام الكامل بالمواصفات والشروط والبنود الواردة في هذه الوثيقة المكونة من صفحتين."
        )
        self.default_template = {
            "bank_title": "طلب إصدار حوالة خارجية سويفت",
            "bank_name": "البنك التجاري المعتمد",
            "customer_name": "شركة العميل المستورد المحدودة",
            "customer_address": "الجمهورية اليمنية - صنعاء",
            "customer_phone": "+967-770000000",
            "customer_account": "1234567890",
            "page2_title": "الشروط والبنود العامة لطلب إصدار الحوالة الخارجية",
            "page2_terms": self.default_terms,
            "custom_template_path": ""
        }
        self.ensure_config_exists()

    def ensure_config_exists(self):
        if not os.path.exists(self.config_path):
            self.save_template(self.default_template)

    def load_template(self) -> Dict[str, Any]:
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    # دمج القيم الافتراضية إذا كانت بعض الحقول غائبة
                    for k, v in self.default_template.items():
                        if k not in config:
                            config[k] = v
                    return config
        except Exception as e:
            print(f"Error loading template config: {e}")
        return self.default_template

    def save_template(self, data: Dict[str, Any]) -> bool:
        try:
            current = self.load_template()
            current.update(data)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(current, f, ensure_ascii=False, indent=4)
            return True
        except Exception as e:
            print(f"Error saving template config: {e}")
            return False
