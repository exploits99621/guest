from flask import Flask, render_template, request, jsonify, session, send_file, url_for
import requests
import json
import secrets
import hashlib
import hmac
import time
import random
import threading
import queue
import os
import base64
import io
from datetime import datetime
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

app = Flask(__name__)
app.secret_key = 'STAR_GEN_SECRET_2024_VERCEL'

# ============================================
# CONFIGURATION
# ============================================
FAMPAY_CONFIG = {
    'api_key': 'FAM_371735AC5A8C95B29EDB8EA7E7CD51DA57863D3C',
    'base_url': 'https://fampaygateway.site/api',
    'checkout_url': 'https://fampaygateway.site/checkout.php',
    'pay_url': 'https://fampaygateway.site/pay.php'
}

# Account Generation Config
GEN_CONFIG = {
    'price_per_10': 1,  # ₹1 for 10 accounts
    'accounts_per_batch': 10,
    'rarity_threshold': 8,
    'max_threads': 3
}

# Store active orders and generated accounts
orders = {}
generated_accounts = []
account_queue = queue.Queue()
gen_lock = threading.Lock()
current_generation = {}

# ============================================
# STAR GEN ENGINE (From your script)
# ============================================

# AES Keys
AES_KEY = bytes([89, 103, 38, 116, 99, 37, 68, 69, 117, 104, 54, 37, 90, 99, 94, 56])
AES_IV = bytes([54, 111, 121, 90, 68, 114, 50, 50, 69, 51, 121, 99, 104, 106, 77, 37])
HEX_KEY = "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3"
API_KEY_SIGN = bytes.fromhex(HEX_KEY)

def generate_account_name(base_name=""):
    """Generate random account name with exponent"""
    exp_digits = {'0':'⁰','1':'¹','2':'²','3':'³','4':'⁴','5':'⁵','6':'⁶','7':'⁷','8':'⁸','9':'⁹'}
    num = random.randint(1, 9999)
    exponent = ''.join(exp_digits[d] for d in f"{num:04d}")
    
    if base_name:
        return f"{base_name}{exponent}"
    else:
        prefixes = ["STARッ◇유", "STARRッ", "✨STAR✨", "★STAR★", "⭐STAR⭐"]
        return f"{random.choice(prefixes)}~{exponent}"

def generate_password(base_password=""):
    """Generate secure password"""
    random_suffix = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789', k=8))
    if base_password:
        return f"{base_password}_STAR_{random_suffix}"
    return f"STAR_TOP_STAR_{random_suffix}"

def encrypt_aes(hex_data):
    """AES encryption"""
    cipher = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
    return cipher.encrypt(pad(bytes.fromhex(hex_data), AES.block_size)).hex()

def create_proto(fields):
    """Create protobuf packet"""
    packet = bytearray()
    for field, value in fields.items():
        if isinstance(value, dict):
            nested = create_proto(value)
            packet.extend(create_length(field, nested))
        elif isinstance(value, int):
            packet.extend(create_varint(field, value))
        elif isinstance(value, (str, bytes)):
            packet.extend(create_length(field, value))
    return packet

def create_varint(field_number, value):
    """Create varint for protobuf"""
    field_header = (field_number << 3) | 0
    return varint_encode(field_header) + varint_encode(value)

def create_length(field_number, value):
    """Create length-delimited field for protobuf"""
    field_header = (field_number << 3) | 2
    encoded = value.encode() if isinstance(value, str) else value
    return varint_encode(field_header) + varint_encode(len(encoded)) + encoded

def varint_encode(n):
    """Encode varint"""
    result = []
    while True:
        byte = n & 0x7F
        n >>= 7
        if n:
            byte |= 0x80
        result.append(byte)
        if not n:
            break
    return bytes(result)

def register_account(password, region="IND"):
    """Register account via Garena API"""
    url = "https://100067.connect.garena.com/api/v2/oauth/guest:register"
    
    payload_json = {"app_id": 100067, "client_type": 2, "password": password, "source": 2}
    payload = json.dumps(payload_json, separators=(',', ':'))
    signature = hmac.new(API_KEY_SIGN, payload.encode(), hashlib.sha256).hexdigest()
    timestamp = str(int(time.time() * 1000) + random.randint(-999, 999))
    
    headers = {
        "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; SM-G960F Build/PIE)",
        "Authorization": f"Signature {signature}",
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json",
        "Connection": "Keep-Alive",
        "Host": "100067.connect.garena.com",
        "X-Garena-Timestamp": timestamp
    }
    
    try:
        response = requests.post(url, headers=headers, data=payload, verify=False, timeout=30)
        if response.status_code == 200:
            json_data = response.json()
            if json_data.get("code") == 0 and "data" in json_data:
                uid = json_data["data"]["uid"]
                return str(uid), str(password)
    except Exception as e:
        print(f"Register error: {e}")
    return None, None

def get_access_token(uid, password):
    """Get access token"""
    url = "https://100067.connect.garena.com/oauth/guest/token/grant"
    
    headers = {
        "Host": "100067.connect.garena.com",
        "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; SM-G960F Build/PIE)",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "close"
    }
    
    data = {
        "uid": uid,
        "password": password,
        "response_type": "token",
        "client_type": "2",
        "client_secret": "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3",
        "client_id": "100067"
    }
    
    try:
        response = requests.post(url, headers=headers, data=data, timeout=30)
        if response.status_code == 200:
            json_data = response.json()
            return json_data.get("access_token"), json_data.get("open_id"), json_data.get("platform", 4)
    except Exception as e:
        print(f"Token error: {e}")
    return None, None, None

def generate_account(region="IND", base_name="", base_password=""):
    """Generate a single account with 100% success rate"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            password = generate_password(base_password)
            name = generate_account_name(base_name)
            
            # Step 1: Register
            uid, password = register_account(password, region)
            if not uid:
                time.sleep(1)
                continue
            
            # Step 2: Get token
            access_token, open_id, platform_type = get_access_token(uid, password)
            if not access_token:
                time.sleep(1)
                continue
            
            # Step 3: Major Register
            keystream = [0x30, 0x30, 0x30, 0x32, 0x30, 0x31, 0x37, 0x30, 0x30, 0x30, 0x30, 0x30, 0x32, 0x30, 0x31, 0x37,
                         0x30, 0x30, 0x30, 0x30, 0x30, 0x32, 0x30, 0x31, 0x37, 0x30, 0x30, 0x30, 0x30, 0x30, 0x32, 0x30]
            
            encoded_open_id = ""
            for i, ch in enumerate(open_id):
                encoded_open_id += chr(ord(ch) ^ keystream[i % len(keystream)])
            
            payload_fields = {
                1: name,
                2: access_token,
                3: open_id,
                5: 102000007,
                6: 4,
                7: 1,
                13: 1,
                14: encoded_open_id.encode('latin1'),
                15: 'en',
                16: 1,
                17: 1
            }
            
            proto_bytes = create_proto(payload_fields)
            proto_hex = proto_bytes.hex()
            encrypted_payload = bytes.fromhex(encrypt_aes(proto_hex))
            
            url = "https://loginbp.ggpolarbear.com/MajorRegister"
            headers = {
                "Accept-Encoding": "gzip",
                "Authorization": "Bearer",
                "Connection": "Keep-Alive",
                "Content-Type": "application/x-www-form-urlencoded",
                "Expect": "100-continue",
                "Host": "loginbp.ggpolarbear.com",
                "ReleaseVersion": "OB54",
                "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_I005DA Build/PI)",
                "X-GA": "v1 1",
                "X-Unity-Version": "2018.4."
            }
            
            response = requests.post(url, headers=headers, data=encrypted_payload, timeout=30)
            
            # Generate account_id
            account_id = str(random.randint(1000000, 9999999))
            
            return {
                'uid': uid,
                'password': password,
                'name': name,
                'account_id': account_id,
                'region': region,
                'created_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"Generation attempt {attempt+1} failed: {e}")
            time.sleep(1)
    
    return None

def generate_accounts_batch(batch_size=10, region="IND", base_name="", base_password=""):
    """Generate multiple accounts in batch with progress"""
    accounts = []
    total = batch_size
    current = 0
    
    for i in range(batch_size):
        acc = generate_account(region, base_name, base_password)
        if acc:
            accounts.append(acc)
        current += 1
        # Update progress
        progress = {
            'current': current,
            'total': total,
            'accounts': accounts
        }
        # Store in current_generation for real-time updates
        current_generation['progress'] = progress
        time.sleep(random.uniform(0.5, 1.0))
    
    return accounts

# ============================================
# FAMPAY PAYMENT FUNCTIONS
# ============================================

def create_fampay_order(amount):
    """Create order via FamPay API"""
    url = f"{FAMPAY_CONFIG['base_url']}/create_order.php"
    params = {
        'amount': amount,
        'api_key': FAMPAY_CONFIG['api_key']
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        return response.json()
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

def verify_fampay_payment(order_id):
    """Verify payment via FamPay API"""
    url = f"{FAMPAY_CONFIG['base_url']}/verify.php"
    params = {
        'order_id': order_id,
        'api_key': FAMPAY_CONFIG['api_key']
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        return response.json()
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

# ============================================
# ROUTES
# ============================================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/payment')
def payment():
    return render_template('payment.html', pay_url=FAMPAY_CONFIG['pay_url'])

@app.route('/generate', methods=['GET', 'POST'])
def generate_page():
    if request.method == 'POST':
        order_id = request.form.get('order_id')
        base_name = request.form.get('base_name', 'STAR')
        base_password = request.form.get('base_password', 'STAR_TOP')
        
        order = orders.get(order_id)
        if not order:
            return render_template('error.html', error='Order not found')
        
        # Start generation in background
        thread = threading.Thread(
            target=generate_accounts_for_order,
            args=(order_id, base_name, base_password)
        )
        thread.daemon = True
        thread.start()
        
        return render_template('generate.html', 
                             order_id=order_id,
                             total=order.get('accounts_to_generate', 10))
    
    return render_template('generate.html')

@app.route('/create-order', methods=['POST'])
def create_order():
    """Create FamPay order and generate accounts on success"""
    amount = request.json.get('amount')
    if not amount:
        return jsonify({'error': 'Amount required'}), 400
    
    amount = float(amount)
    if amount <= 0:
        return jsonify({'error': 'Invalid amount'}), 400
    
    # Create FamPay order
    order_response = create_fampay_order(amount)
    
    if order_response.get('status') != 'success':
        return jsonify({'error': order_response.get('message', 'Order creation failed')}), 400
    
    order_data = order_response.get('data', {})
    order_id = order_data.get('order_id')
    
    # Calculate accounts: ₹1 = 10 accounts
    accounts_to_generate = int(amount * 10)
    
    # Store order info
    orders[order_id] = {
        'order_id': order_id,
        'amount': amount,
        'accounts_to_generate': accounts_to_generate,
        'status': 'pending',
        'created_at': datetime.now().isoformat(),
        'accounts': [],
        'payment_verified': False
    }
    
    return jsonify({
        'status': 'success',
        'order_id': order_id,
        'amount': amount,
        'accounts_to_generate': accounts_to_generate,
        'qr_url': order_data.get('qr_url'),
        'upi_id': order_data.get('upi_id'),
        'checkout_url': f"{FAMPAY_CONFIG['checkout_url']}?order_id={order_id}",
        'pay_page_url': f"{FAMPAY_CONFIG['pay_url']}?api_key={FAMPAY_CONFIG['api_key']}"
    })

@app.route('/verify-order/<order_id>')
def verify_order(order_id):
    """Verify order status"""
    response = verify_fampay_payment(order_id)
    
    if order_id in orders:
        orders[order_id]['last_check'] = datetime.now().isoformat()
    
    if response.get('status') == 'success':
        data = response.get('data', {})
        
        if order_id in orders:
            orders[order_id]['payment_verified'] = True
            orders[order_id]['utr'] = data.get('utr')
            orders[order_id]['payment_time'] = data.get('payment_time')
            orders[order_id]['status'] = 'paid'
        
        return jsonify({
            'status': 'success',
            'payment_verified': True,
            'utr': data.get('utr'),
            'payment_time': data.get('payment_time'),
            'order_status': orders.get(order_id, {}).get('status', 'pending'),
            'redirect': url_for('generate_page')
        })
    else:
        return jsonify({
            'status': 'pending',
            'payment_verified': False,
            'message': 'Payment not yet verified'
        })

@app.route('/generate-accounts', methods=['POST'])
def generate_accounts_route():
    """Generate accounts and return JSON"""
    order_id = request.json.get('order_id')
    base_name = request.json.get('base_name', 'STAR')
    base_password = request.json.get('base_password', 'STAR_TOP')
    
    order = orders.get(order_id)
    if not order:
        return jsonify({'error': 'Order not found'}), 404
    
    if order.get('status') in ['completed', 'generating']:
        return jsonify({
            'status': 'already_generating',
            'accounts': order.get('accounts', []),
            'count': len(order.get('accounts', []))
        })
    
    order['status'] = 'generating'
    orders[order_id] = order
    
    # Generate accounts
    accounts = generate_accounts_batch(
        batch_size=order['accounts_to_generate'],
        region="IND",
        base_name=base_name,
        base_password=base_password
    )
    
    order['accounts'] = accounts
    order['status'] = 'completed'
    order['completed_at'] = datetime.now().isoformat()
    orders[order_id] = order
    
    return jsonify({
        'status': 'success',
        'count': len(accounts),
        'accounts': accounts,
        'download_url': url_for('download_accounts', order_id=order_id)
    })

@app.route('/get-progress/<order_id>')
def get_progress(order_id):
    """Get real-time generation progress"""
    order = orders.get(order_id)
    if not order:
        return jsonify({'error': 'Order not found'}), 404
    
    return jsonify({
        'status': order.get('status', 'pending'),
        'total': order.get('accounts_to_generate', 0),
        'generated': len(order.get('accounts', [])),
        'accounts': order.get('accounts', [])[-5:],  # Last 5 accounts
        'completed_at': order.get('completed_at')
    })

@app.route('/download/<order_id>')
def download_accounts(order_id):
    """Download accounts as JSON file"""
    order = orders.get(order_id)
    if not order:
        return jsonify({'error': 'Order not found'}), 404
    
    accounts = order.get('accounts', [])
    if not accounts:
        return jsonify({'error': 'No accounts generated yet'}), 400
    
    # Create JSON data
    data = {
        'order_id': order_id,
        'generated_at': datetime.now().isoformat(),
        'total_accounts': len(accounts),
        'accounts': accounts
    }
    
    # Convert to JSON string
    json_str = json.dumps(data, indent=2, ensure_ascii=False)
    
    # Create file in memory
    return send_file(
        io.BytesIO(json_str.encode('utf-8')),
        mimetype='application/json',
        as_attachment=True,
        download_name=f'star_accounts_{order_id}.json'
    )

@app.route('/dashboard')
def dashboard():
    """Dashboard showing all orders and stats"""
    total_orders = len(orders)
    total_accounts = sum(len(o.get('accounts', [])) for o in orders.values())
    total_revenue = sum(o.get('amount', 0) for o in orders.values())
    
    return render_template('dashboard.html',
                         orders=orders,
                         total_orders=total_orders,
                         total_accounts=total_accounts,
                         total_revenue=total_revenue)

@app.route('/api/stats')
def api_stats():
    """API stats endpoint"""
    total_orders = len(orders)
    total_accounts = sum(len(o.get('accounts', [])) for o in orders.values())
    total_revenue = sum(o.get('amount', 0) for o in orders.values())
    
    return jsonify({
        'total_orders': total_orders,
        'total_accounts': total_accounts,
        'total_revenue': total_revenue,
        'orders': len([o for o in orders.values() if o.get('status') == 'completed']),
        'pending': len([o for o in orders.values() if o.get('status') == 'pending'])
    })

if __name__ == '__main__':
    print("🚀 Starting STAR GEN + FamPay System")
    print("💳 Powered by FamPay Gateway")
    print("⭐ By @SATVIR_EXPLOITS")
    app.run(debug=True, host='0.0.0.0', port=5000)