from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai
import stripe
import firebase_admin
from firebase_admin import credentials, firestore
import os

app = Flask(__name__)

# --- CORS AYARI (Failed to Fetch Hatasını Çözer) ---
# Vercel'den gelen tüm isteklere kapıyı açıyoruz
CORS(app, resources={r"/*": {"origins": "*"}})

# --- 1. ANAHTARLAR ---
# API Key'ini kontrol et, tırnak içinde eksik karakter kalmasın
genai.configure(api_key="AIzaSyDUZvolrIgqNjvYOm6Z1dhSGZb4xD8pU9s")

# En stabil model 1.5-flash sürümüdür
model = genai.GenerativeModel('models/gemini-1.5-flash')

stripe.api_key = "sk_test_51RalPZLBmahSK3WTUJrzDoqUuFI5AOm2xUxQVj2ZaWmD1UF7eHGE0h5bMkBxu1lr4HBHygRksjoipgJ07w5r7GRO00ur6xP5SX"
endpoint_secret = "whsec_9c7ed488f8f3f6db579cc0819014205a30f8128f5fcf0b0ed04c227e24553a35"

PRICE_LOOKUP = {
    'price_1TBISfLBmahSK3WT0xPewOeT': 10,   # Starter
    'price_1TBIMXLBmahSK3WTiXPxFKe4': 35,   # Professional
    'price_1TBIPRLBmahSK3WTQLpt1D1T': 100   # Elite
}

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

# --- SUNUCU KONTROLÜ (Adım 1 Testi İçin) ---
@app.route('/')
def home():
    return "CoverAI Backend is LIVE! 🚀"

# --- 3. TEKLİF ÜRETME ---
@app.route('/api/generate', methods=['POST'])
def generate_proposal():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Veri alınamadı'}), 400

        job_desc = data.get('job_description', '')
        skills = data.get('skills', '')
        strategy_mode = data.get('strategy_mode', False)

        if strategy_mode:
            prompt = f"""You are an elite freelance strategist. 
            Analyze the job: {job_desc} 
            My skills: {skills}
            1. BATTLE ANALYSIS: What are the competitor weaknesses?
            2. THE PITCH: Write a professional proposal.
            Format: [STRATEGY] ... [PROPOSAL] ..."""
        else:
            prompt = f"Expert cover letter for: {job_desc}. Focus on: {skills}."

        response = model.generate_content(prompt)
        
        if not response.text:
            return jsonify({'success': False, 'error': 'AI cevap oluşturamadı'})

        text = response.text
        strategy_analysis = "Strategy generated."
        proposal = text

        if "[STRATEGY]" in text and "[PROPOSAL]" in text:
            parts = text.split("[PROPOSAL]")
            strategy_analysis = parts[0].replace("[STRATEGY]", "").strip()
            proposal = parts[1].strip()

        return jsonify({
            'success': True, 
            'proposal': proposal,
            'strategy_analysis': strategy_analysis if strategy_mode else ""
        })

    except Exception as e:
        print(f"🔥 Üretim Hatası: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

# --- 4. STRIPE & WEBHOOK (Değişmedi) ---
@app.route('/api/create-checkout-session', methods=['POST'])
def create_checkout_session():
    data = request.json
    try:
        price_id = data.get('price_id')
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{'price': price_id, 'quantity': 1}],
            mode='payment',
            success_url=data['return_url'] + '?success=true',
            cancel_url=data['return_url'] + '?canceled=true',
        )
        return jsonify({'url': checkout_session.url})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/stripe_webhook', methods=['POST'])
def stripe_webhook():
    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature')
    try:
        event = stripe.webhook.construct_event(payload, sig_header, endpoint_secret)
        if event['type'] == 'checkout.session.completed':
            session = event['data']['object']
            customer_email = session['customer_details']['email']
            line_items = stripe.checkout.Session.list_line_items(session['id'], limit=1)
            price_id = line_items.data[0].price.id
            added_credits = PRICE_LOOKUP.get(price_id, 10)
            
            users_ref = db.collection('users').where('email', '==', customer_email).limit(1).get()
            for doc in users_ref:
                db.collection('users').document(doc.id).update({'credits': doc.to_dict().get('credits', 0) + added_credits})
        return jsonify(success=True)
    except:
        return jsonify(success=False), 400

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
