import re
import math
from datetime import datetime
try:
    from num2words import num2words
except ImportError:
    num2words = None

try:
    from hijridate import Gregorian
except ImportError:
    Gregorian = None


class CurrencyTafqeet:
    """
    مكتبة التفقيط المالي بالعملات العربية والأجنبية والتحويل إلى التاريخ الهجري
    """

    CURRENCY_CONFIG = {
        "USD": {
            "name_ar": "دولار أمريكي",
            "plural_ar": "دولارات أمريكية",
            "fraction_ar": "سنت",
            "fraction_plural_ar": "سنتاً",
            "name_en": "US Dollars",
            "fraction_en": "Cents"
        },
        "EUR": {
            "name_ar": "يورو",
            "plural_ar": "يورو",
            "fraction_ar": "سنت",
            "fraction_plural_ar": "سنتاً",
            "name_en": "Euros",
            "fraction_en": "Cents"
        },
        "TRY": {
            "name_ar": "ليرة تركية",
            "plural_ar": "ليرات تركية",
            "fraction_ar": "قرش",
            "fraction_plural_ar": "قروش",
            "name_en": "Turkish Lira",
            "fraction_en": "Kurus"
        },
        "TL": {
            "name_ar": "ليرة تركية",
            "plural_ar": "ليرات تركية",
            "fraction_ar": "قرش",
            "fraction_plural_ar": "قروش",
            "name_en": "Turkish Lira",
            "fraction_en": "Kurus"
        },
        "SAR": {
            "name_ar": "ريال سعودي",
            "plural_ar": "ريالات سعودية",
            "fraction_ar": "هللة",
            "fraction_plural_ar": "هللة",
            "name_en": "Saudi Riyals",
            "fraction_en": "Halalas"
        },
        "AED": {
            "name_ar": "درهم إماراتي",
            "plural_ar": "دراهم إماراتية",
            "fraction_ar": "فلس",
            "fraction_plural_ar": "فلساً",
            "name_en": "UAE Dirhams",
            "fraction_en": "Fils"
        },
        "YER": {
            "name_ar": "ريال يمني",
            "plural_ar": "ريالات يمنية",
            "fraction_ar": "فلس",
            "fraction_plural_ar": "فلساً",
            "name_en": "Yemeni Riyals",
            "fraction_en": "Fils"
        },
        "GBP": {
            "name_ar": "جنيه إسترليني",
            "plural_ar": "جنيهات إسترلينية",
            "fraction_ar": "بنس",
            "fraction_plural_ar": "بنساً",
            "name_en": "Pounds Sterling",
            "fraction_en": "Pence"
        },
        "CNY": {
            "name_ar": "يوان صيني",
            "plural_ar": "يوانات صينية",
            "fraction_ar": "فن",
            "fraction_plural_ar": "فناً",
            "name_en": "Chinese Yuan",
            "fraction_en": "Fen"
        },
        "RMB": {
            "name_ar": "يوان صيني",
            "plural_ar": "يوانات صينية",
            "fraction_ar": "فن",
            "fraction_plural_ar": "فناً",
            "name_en": "Chinese Yuan",
            "fraction_en": "Fen"
        },
        "JOD": {
            "name_ar": "دينار أردني",
            "plural_ar": "دنانير أردنية",
            "fraction_ar": "قرش",
            "fraction_plural_ar": "قرشاً",
            "name_en": "Jordanian Dinars",
            "fraction_en": "Piastres"
        },
        "KWD": {
            "name_ar": "دينار كويتي",
            "plural_ar": "دنانير كويتية",
            "fraction_ar": "فلس",
            "fraction_plural_ar": "فلساً",
            "name_en": "Kuwaiti Dinars",
            "fraction_en": "Fils"
        },
        "QAR": {
            "name_ar": "ريال قطري",
            "plural_ar": "ريالات قطرية",
            "fraction_ar": "درهم",
            "fraction_plural_ar": "درهماً",
            "name_en": "Qatari Riyals",
            "fraction_en": "Dirhams"
        },
        "BHD": {
            "name_ar": "دينار بحريني",
            "plural_ar": "دنانير بحرينية",
            "fraction_ar": "فلس",
            "fraction_plural_ar": "فلساً",
            "name_en": "Bahraini Dinars",
            "fraction_en": "Fils"
        },
        "OMR": {
            "name_ar": "ريال عماني",
            "plural_ar": "ريالات عمانية",
            "fraction_ar": "بيسة",
            "fraction_plural_ar": "بيسةً",
            "name_en": "Omani Rials",
            "fraction_en": "Baisas"
        },
        "EGP": {
            "name_ar": "جنيه مصري",
            "plural_ar": "جنيهات مصرية",
            "fraction_ar": "قرش",
            "fraction_plural_ar": "قرشاً",
            "name_en": "Egyptian Pounds",
            "fraction_en": "Piastres"
        }
    }

    @staticmethod
    def get_today_date() -> str:
        """إرجاع تاريخ اليوم بالتنسيق المعتمد YYYY-MM-DD"""
        return datetime.now().strftime("%Y-%m-%d")

    @staticmethod
    def get_hijri_date(greg_date_str: str = "") -> str:
        """
        تحويل التاريخ الميلادي إلى التاريخ الهجري الدقيق (مثال: 20 ربيع الأول 1448 هـ)
        """
        try:
            if greg_date_str:
                parts = [int(p) for p in re.findall(r"\d+", greg_date_str)]
                if len(parts) >= 3:
                    if parts[0] > 1000:
                        y, m, d = parts[0], parts[1], parts[2]
                    else:
                        d, m, y = parts[0], parts[1], parts[2]
                else:
                    dt = datetime.now()
                    y, m, d = dt.year, dt.month, dt.day
            else:
                dt = datetime.now()
                y, m, d = dt.year, dt.month, dt.day

            if Gregorian:
                h = Gregorian(y, m, d).to_hijri()
                m_name = h.month_name('ar')
                return f"{h.day} {m_name} {h.year} هـ"

            # خوارزمية احتياطية للحساب تقويم أم القرى
            a = math.floor(y / 100)
            b = 2 - a + math.floor(a / 4)
            jd = math.floor(365.25 * (y + 4716)) + math.floor(30.6001 * (m + 1)) + d + b - 1524.5
            l = jd - 1948440 + 10632
            n = math.floor((l - 1) / 10631)
            l = l - 10631 * n + 354
            j = (math.floor((10985 - l) / 5316)) * (math.floor((50 * l) / 17719)) + (math.floor(l / 5670)) * (math.floor((43 * l) / 15238))
            l = l - (math.floor((30 - j) / 15)) * (math.floor((17719 * j) / 50)) - (math.floor(j / 16)) * (math.floor((15238 * j) / 43)) + 29
            m_h = math.floor((24 * l) / 709)
            d_h = int(l - math.floor((709 * m_h) / 24))
            y_h = int(30 * n + j - 30)

            months_ar = ['محرم', 'صفر', 'ربيع الأول', 'ربيع الثاني', 'جمادى الأولى', 'جمادى الآخرة', 'رجب', 'شعبان', 'رمضان', 'شوال', 'ذو القعدة', 'ذو الحجة']
            m_name = months_ar[m_h - 1] if 1 <= m_h <= 12 else ''
            return f"{d_h} {m_name} {y_h} هـ"
        except Exception:
            return "20 ربيع الأول 1448 هـ"

    @staticmethod
    def calculate_transfer_amount(total_amount_val: float | str, payment_terms_text: str) -> tuple[float, float, str]:
        """
        احتساب مبلغ الحوالة آلياً بحسب بند Payment Terms
        """
        try:
            if isinstance(total_amount_val, str):
                cleaned = re.sub(r"[^\d\.]", "", total_amount_val)
                total_amt = float(cleaned) if cleaned else 0.0
            else:
                total_amt = float(total_amount_val)
        except Exception:
            total_amt = 0.0

        ratio = 1.0
        note = "100% دفعة كاملة بحسب شروط الفاتورة"

        match = re.search(r"(\d+(?:\.\d+)?)\s*%", payment_terms_text)
        if match:
            percent = float(match.group(1))
            ratio = percent / 100.0
            note = f"مبلغ الحوالة محسوب بنسبة {percent}% بحسب الفاتورة"
        elif "ADVANCE" in payment_terms_text.upper() or "DEPOSIT" in payment_terms_text.upper():
            deposit_match = re.search(r"(\d+)\s*PERCENT", payment_terms_text, re.IGNORECASE)
            if deposit_match:
                percent = float(deposit_match.group(1))
                ratio = percent / 100.0
                note = f"مبلغ الحوالة محسوب بنسبة مقدمة {percent}%"

        transfer_amt = total_amt * ratio
        return round(transfer_amt, 2), round(total_amt, 2), note

    @staticmethod
    def _num_to_words_en(n: int) -> str:
        if n == 0:
            return "Zero"
        units = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
                 "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
        tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]
        scales = ["", "Thousand", "Million", "Billion"]

        def _sub_1000(num):
            p = []
            h = num // 100
            rem = num % 100
            if h > 0:
                p.append(f"{units[h]} Hundred")
            if rem > 0:
                if rem < 20:
                    p.append(units[rem])
                else:
                    t = rem // 10
                    u = rem % 10
                    p.append(f"{tens[t]}-{units[u]}" if u else tens[t])
            return " ".join(p)

        res = []
        idx = 0
        val = n
        while val > 0:
            chunk = val % 1000
            if chunk > 0:
                sub = _sub_1000(chunk)
                sc = scales[idx]
                res.append(f"{sub} {sc}".strip())
            val //= 1000
            idx += 1
        return " ".join(reversed(res))

    @staticmethod
    def _num_to_words_ar(n: int) -> str:
        if n == 0:
            return "صفر"
        ones = ["", "واحد", "اثنان", "ثلاثة", "أربعة", "خمسة", "ستة", "سبعة", "ثمانية", "تسعة", "عشرة",
                "أحد عشر", "اثنا عشر", "ثلاثة عشر", "أربعة عشر", "خمسة عشر", "ستة عشر", "سبعة عشر", "ثمانية عشر", "تسعة عشر"]
        tens = ["", "", "عشرون", "ثلاثون", "أربعون", "خمسون", "ستون", "سبعون", "ثمانون", "تسعون"]
        hundreds = ["", "مائة", "مائتان", "ثلاثمائة", "أربعمائة", "خمسمائة", "ستمائة", "سبعمائة", "ثمانمائة", "تسعمائة"]

        def _sub_1000(num):
            p = []
            h = num // 100
            rem = num % 100
            if h > 0:
                p.append(hundreds[h])
            if rem > 0:
                if rem < 20:
                    p.append(ones[rem])
                else:
                    u = rem % 10
                    t = rem // 10
                    if u > 0:
                        p.append(f"{ones[u]} و{tens[t]}")
                    else:
                        p.append(tens[t])
            return " و".join(p)

        if n < 1000:
            return _sub_1000(n)

        p = []
        m = (n // 1_000_000) % 1000
        if m == 1:
            p.append("مليون")
        elif m == 2:
            p.append("مليونان")
        elif 3 <= m <= 10:
            p.append(f"{_sub_1000(m)} ملايين")
        elif m > 10:
            p.append(f"{_sub_1000(m)} مليوناً")

        th = (n // 1000) % 1000
        if th == 1:
            p.append("ألف")
        elif th == 2:
            p.append("ألفان")
        elif 3 <= th <= 10:
            p.append(f"{_sub_1000(th)} آلاف")
        elif th > 10:
            p.append(f"{_sub_1000(th)} ألفاً")

        rem = n % 1000
        if rem > 0:
            p.append(_sub_1000(rem))

        return " و".join(p)

    @classmethod
    def tafqeet_ar(cls, amount: float | str, currency_code: str = "USD") -> str:
        """توليد التفقيط العربي بالعملة والكسور مع الضوابط اللغوية الدقيقة"""
        try:
            amt = float(amount)
        except (ValueError, TypeError):
            return ""

        code = currency_code.upper().strip() if currency_code else "USD"
        cfg = cls.CURRENCY_CONFIG.get(code, cls.CURRENCY_CONFIG["USD"])
        integer_part = int(amt)
        decimal_part = int(round((amt - integer_part) * 100))

        if num2words:
            try:
                words_int = num2words(integer_part, lang="ar")
            except Exception:
                words_int = cls._num_to_words_ar(integer_part)
        else:
            words_int = cls._num_to_words_ar(integer_part)

        curr_name = cfg["name_ar"]
        result = f"فقط {words_int} {curr_name}"

        if decimal_part > 0:
            if num2words:
                try:
                    words_dec = num2words(decimal_part, lang="ar")
                except Exception:
                    words_dec = cls._num_to_words_ar(decimal_part)
            else:
                words_dec = cls._num_to_words_ar(decimal_part)

            single_base = cfg["fraction_ar"]
            if decimal_part == 1:
                frac_str = f"و {single_base} واحد"
            elif decimal_part == 2:
                if single_base.endswith("ة"):
                    frac_str = f"و {single_base[:-1]}تان"
                else:
                    frac_str = f"و {single_base}ان"
            elif 3 <= decimal_part <= 10:
                frac_plural = cfg.get("fraction_plural_ar", single_base)
                frac_str = f"و {words_dec} {frac_plural}"
            else:
                single_acc = single_base
                if not single_acc.endswith("اً") and not single_acc.endswith("ة"):
                    single_acc += "اً"
                elif single_acc.endswith("ة") and not single_acc.endswith("ةً"):
                    single_acc += "ً"
                frac_str = f"و {words_dec} {single_acc}"

            result += f" {frac_str}"

        result += " لا غير"
        return result

    @classmethod
    def tafqeet_en(cls, amount: float | str, currency_code: str = "USD") -> str:
        """توليد التفقيط الإنجليزي بالعملة والكسور"""
        try:
            amt = float(amount)
        except (ValueError, TypeError):
            return ""

        code = currency_code.upper().strip() if currency_code else "USD"
        cfg = cls.CURRENCY_CONFIG.get(code, cls.CURRENCY_CONFIG["USD"])
        integer_part = int(amt)
        decimal_part = int(round((amt - integer_part) * 100))

        if num2words:
            try:
                words_int = num2words(integer_part, lang="en").title()
            except Exception:
                words_int = cls._num_to_words_en(integer_part)
        else:
            words_int = cls._num_to_words_en(integer_part)

        curr_name = cfg["name_en"]
        result = f"Only {words_int} {curr_name}"

        if decimal_part > 0:
            if num2words:
                try:
                    words_dec = num2words(decimal_part, lang="en").title()
                except Exception:
                    words_dec = cls._num_to_words_en(decimal_part)
            else:
                words_dec = cls._num_to_words_en(decimal_part)

            frac_name = cfg["fraction_en"]
            result += f" And {words_dec} {frac_name}"

        result += " Only"
        return result
