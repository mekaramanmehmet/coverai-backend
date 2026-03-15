from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai
import stripe
import firebase_admin
from firebase_admin import credentials, firestore
import os # Bulut sunucu portu için eklendi

app = Flask(__name__)
CORS(app)

# --- 1. ANAHTARLARIN (Aynen Korundu) ---
genai.configure(api_key="AIzaSyDxm_GxbTIRqEcwYBWsa1vMwubLdBVxjnc")
model = genai.GenerativeModel('gemini-2.0-flash') 

stripe.api_key = "sk_test_51RalPZLBmahSK3WTUJrzDoqUuFI5AOm2xUxQVj2ZaWmD1UF7eHGE0h5bMkBxu1lr4HBHygRksjoipgJ07w5r7GRO00ur6xP5SX"
endpoint_secret = "whsec_9c7ed488f8f3f6db579cc0819014205a30f8128f5fcf0b0ed04c227e24553a35"

# --- 2. FIREBASE BAŞLATMA ---
try:
    if not firebase_admin._apps:
        cred = credentials.Certificate("serviceAccountKey.json")
        firebase_admin.initialize_app(cred)
        print("✅ Firebase başarıyla başlatıldı.")
    db = firestore.client()
except Exception as e:
    print(f"❌ Firebase başlatma hatası: {e}")
    db = None

# --- 3. TEKLİF ÜRETME ---
@app.route('/api/generate', methods=['POST'])
def generate_proposal():
    data = request.json
    prompt = f"You are an expert copywriter. Write a cover letter for this job: {data.get('job_description', '')}. Skills: {data.get('skills', '')}. Keep it concise, no placeholders."
    try:
        response = model.generate_content(prompt)
        return jsonify({'success': True, 'proposal': response.text})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# --- 4. STRIPE ÖDEME SAYFASI OLUŞTURMA ---
@app.route('/api/create-checkout-session', methods=['POST'])
def create_checkout_session():
    data = request.json
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': data['price_id'],
                'quantity': 1,
            }],
            mode='payment',
            success_url=data['return_url'] + '?success=true',
            cancel_url=data['return_url'] + '?canceled=true',
        )
        return jsonify({'url': checkout_session.url})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# --- 5. WEBHOOK: ÖDEME ONAYI VE KREDİ YÜKLEME ---
@app.route('/stripe_webhook', methods=['POST'])
def stripe_webhook():
    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature')

    try:
        event = stripe.webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except Exception as e:
        print(f"⚠️ Webhook Hatası: {e}")
        return jsonify(success=False), 400

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        customer_email = session['customer_details']['email']
        
        try:
            users_ref = db.collection('users').where('email', '==', customer_email).limit(1).get()
            
            for doc in users_ref:
                user_id = doc.id
                current_credits = doc.to_dict().get('credits', 0)
                
                db.collection('users').document(user_id).update({
                    'credits': current_credits + 10
                })
                print(f"💰 BAŞARI: {customer_email} hesabına 10 kredi yüklendi!")
                
        except Exception as e:
            print(f"❌ Firebase Kredi Yükleme Hatası: {e}")

    return jsonify(success=True)

# --- BULUT SUNUCU İÇİN GÜNCELLENEN KISIM ---
if __name__ == '__main__':
    # Render veya diğer sunucuların verdiği portu al, yoksa 5000 kullan
    port = int(os.environ.get("PORT", 5000))
    print(f"🚀 CoverAI Pro Aktif! Port: {port}")
    app.run(host='0.0.0.0', port=port)
    