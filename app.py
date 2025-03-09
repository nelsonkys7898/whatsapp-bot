# app.py（完整修正版）
from flask import Flask, request, jsonify
from datetime import datetime
import dialogflow
import gspread
from google.oauth2 import service_account
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# ====== Google Sheets配置 ======
def get_google_sheet():
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = service_account.Credentials.from_service_account_file(
        "credentials/sheets.json", 
        scopes=scope
    )
    client = gspread.authorize(creds)
    return client.open("Homestay_Bookings").sheet1

# ====== Dialogflow处理 ======
def process_dialogflow(session_id, message):
    creds = service_account.Credentials.from_service_account_file(
        "credentials/dialogflow.json"
    )
    session_client = dialogflow.SessionsClient(credentials=creds)
    session = session_client.session_path(
        os.getenv("DIALOGFLOW_PROJECT_ID"),
        session_id
    )
    
    text_input = dialogflow.TextInput(
        text=message,
        language_code="en"
    )
    query_input = dialogflow.QueryInput(text=text_input)
    
    return session_client.detect_intent(
        request={"session": session, "query_input": query_input}
    )

# ====== 主路由 ======
@app.route('/webhook', methods=['POST'])
def webhook():
    # 获取基础数据
    user_message = request.form.get('Body', '').strip()
    user_phone = request.form.get('From', '')
    media_url = request.form.get('MediaUrl0', '')
    
    # 处理Dialogflow
    df_response = process_dialogflow(user_phone, user_message)
    if not df_response:
        return jsonify({"messages": [{"body": "⚠️ Service unavailable"}])
    
    intent = df_response.query_result.intent.display_name
    params = df_response.query_result.parameters
    
    # 处理预订
    if intent == "BookHomestay":
        try:
            guests = int(params.get('guests', 0))
            if guests > 6:
                return jsonify({"messages": [{"body": "❌ Max 6 guests"}])
        except:
            return jsonify({"messages": [{"body": "❌ Invalid guest number"}])
        
        sheet = get_google_sheet()
        if sheet:
            try:
                sheet.append_row([
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    user_phone,
                    params.get('checkin_date', ''),
                    params.get('checkout_date', ''),
                    guests,
                    "",
                    "Pending Payment"
                ])
                return jsonify({"messages": [{
                    "body": "✅ Booked! Transfer to: MAYBANK 1234567890"
                }]})
            except Exception as e:
                print(f"Sheets error: {str(e)}")
                return jsonify({"messages": [{"body": "⚠️ Save failed"}])
    
    # 处理付款
    elif intent == "ConfirmPayment" and media_url:
        sheet = get_google_sheet()
        if sheet:
            try:
                records = sheet.get_all_records()
                for idx, row in enumerate(reversed(records)):
                    if row['Phone'] == user_phone:
                        row_num = len(records) - idx
                        sheet.update_cell(row_num, 7, media_url)
                        sheet.update_cell(row_num, 8, "Pending Verification")
                        break
                return jsonify({"messages": [{
                    "body": "📨 Payment received!"
                }]})
            except Exception as e:
                print(f"Update error: {str(e)}")
    
    return jsonify({
        "messages": [{
            "body": df_response.query_result.fulfillment_text
        }]
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)