from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai
import stripe
import firebase_admin
from firebase_admin import credentials, firestore
import os

app = Flask(__name__)
CORS(app)

# --- 1. ANAHTARLAR ---
genai.configure(api_key="AIzaSyDxm_GxbTIRqEcwYBWsa1vMwubLdBVxjnc")
model = genai.GenerativeModel('gemini-2.0-flash') 

stripe.api_key = "sk_test_51RalPZLBmahSK3WTUJrzDoqUuFI5AOm2xUxQVj2ZaWmD1UF7eHGE0h5bMkBxu1lr4HBHygRksjoipgJ07w5r7GRO00ur6xP5SX"
endpoint_secret = "whsec_9c7ed488f8f3f6db579cc0819014205a30f8128f5fcf0b0ed04c227e24553a35"

# Fiyat ID'lerine karşılık gelen kredi miktarları
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

# --- 3. TEKLİF ÜRETME (STRATEJİ MODU EKLENDİ) ---
@app.route('/api/generate', methods=['POST'])
def generate_proposal():
    data = request.json
    job_desc = data.get('job_description', '')
    skills = data.get('skills', '')
    strategy_mode = data.get('strategy_mode', False)

    try:
        if strategy_mode:
            # STRATEJİ MODU AÇIKSA: Rakipleri analiz eden yırtıcı prompt
            prompt = f"""You are an elite freelance strategist and master copywriter.
Job Description: {job_desc}
My Skills: {skills}

Do two specific things:
1. BATTLE ANALYSIS: Analyze what 90% of average freelancers will do wrong in their proposals for this job. Identify the client's "hidden pain point" or real need. Give a 2-3 sentence ruthless strategy to stand out.
2. THE PITCH: Write the perfect cover letter based on this strategy. Highly persuasive, professional, concise, and absolutely NO placeholders like [Name].

Format your exact response like this:
[STRATEGY]
(write your battle analysis here)
[PROPOSAL]
(write the actual cover letter here)"""
            
            response = model.generate_content(prompt)
            text = response.text
            
            # Gelen cevabı frontend'in anlayacağı şekilde ikiye bölüyoruz
            strategy_analysis = ""
            proposal = text
            
            if "[STRATEGY]" in text and "[PROPOSAL]" in text:
                parts = text.split("[PROPOSAL]")
                strategy_analysis = parts[0].replace("[STRATEGY]", "").strip()
                proposal = parts[1].strip()
            
            return jsonify({
                'success': True, 
                'proposal': proposal,
                'strategy_analysis': strategy_analysis
            })
            
        else:
            # STRATEJİ MODU KAPALIYSA: Normal hızlı teklif (Eski kodun aynısı)
            prompt = f"Expert cover letter for: {job_desc}. Focus on these skills: {skills}. Human-like, persuasive, and professional. No placeholders like [Name]."
            response = model.generate_content(prompt)
            return jsonify({'success': True, 'proposal': response.text})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# --- 4. STRIPE ÖDEME SAYFASI ---
@app.route('/api/create-checkout-session', methods=['POST'])
def create_checkout_session():
    data = request.json
    try:
        price_id = data.get('price_id')
        if not price_id:
            return jsonify({'error': 'Missing price_id'}), 400

        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': price_id,
                'quantity': 1,
            }],
            mode='payment',
            success_url=data['return_url'] + '?success=true',
            cancel_url=data['return_url'] + '?canceled=true',
        )
        return jsonify({'url': checkout_session.url})
    except Exception as e:
        print(f"❌ Stripe Hatası: {e}")
        return jsonify({'error': str(e)}), 400

# --- 5. WEBHOOK: DİNAMİK KREDİ YÜKLEME ---
@app.route('/stripe_webhook', methods=['POST'])
def stripe_webhook():
    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature')

    try:
        event = stripe.webhook.construct_event(payload, sig_header, endpoint_secret)
    except Exception as e:
        return jsonify(success=False), 400

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        customer_email = session['customer_details']['email']
        
        line_items = stripe.checkout.Session.list_line_items(session['id'], limit=1)
        price_id = line_items.data[0].price.id
        
        added_credits = PRICE_LOOKUP.get(price_id, 10)
        
        try:
            users_ref = db.collection('users').where('email', '==', customer_email).limit(1).get()
            
            for doc in users_ref:
                user_id = doc.id
                current_credits = doc.to_dict().get('credits', 0)
                
                db.collection('users').document(user_id).update({
                    'credits': current_credits + added_credits
                })
                print(f"💰 BAŞARI: {customer_email} hesabına {added_credits} kredi yüklendi!")
                
        except Exception as e:
            print(f"❌ Firebase Kredi Yükleme Hatası: {e}")

    return jsonify(success=True)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
    
