from flask import Flask, render_template, request, jsonify, send_from_directory
import requests
import os
import csv
import json
from datetime import datetime

app = Flask(__name__, static_folder='static')

# Configuration
OPENWEATHER_KEY = "ec8ecd486662eb30efb5e29afc7851c5"
FAST2SMS_API_KEY = "zgl87ILMxnj9diyV3AuGWEcRCZwD06JsYK4Nt2eQ5ObSTmakqvPSbaNKywjDUhVIR9X2m3Z4kWJuiOEc"
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')


# Language translations
TRANSLATIONS = {
    'en': {
        'dashboard': 'Dashboard',
        'lake_database': 'Lake Database',
        'ml_predictions': 'ML & Predictions',
        'risk_assessment': 'Risk Assessment',
        'safety': 'Safety Precautions',
      
    },
    'hi': {
        'dashboard': 'डैशबोर्ड',
        'lake_database': 'झील डेटाबेस',
        'ml_predictions': 'एमएल और भविष्यवाणियाँ',
        'risk_assessment': 'जोखिम मूल्यांकन',
        'safety': 'सुरक्षा सावधानियाँ',
    },
    'mr': {
        'dashboard': 'डॅशबोर्ड',
        'lake_database': 'तलाव डेटाबेस',
        'ml_predictions': 'एमएल आणि अंदाज',
        'risk_assessment': 'धोका मूल्यांकन',
        'safety': 'सुरक्षा खबरदारी',
    },
    'gu': {
        'dashboard': 'ડેશબોર્ડ',
        'lake_database': 'સરોવર ડેટાબેઝ',
        'ml_predictions': 'એમએલ અને આગાહીઓ',
        'risk_assessment': 'જોખમ મૂલ્યાંકન',
        'safety': 'સલામતી સાવચેતીઓ',
    }
}

@app.route('/')
def dashboard():
    return render_template('index.html')

@app.route('/api/translations/<lang>')
def get_translations(lang):
    return jsonify(TRANSLATIONS.get(lang, TRANSLATIONS['en']))



@app.route('/api/lakes')
def get_lakes():
    try:
        lakes = []
        with open('lakes.csv', mode='r') as csv_file:
            csv_reader = csv.DictReader(csv_file)
            for row in csv_reader:
                lakes.append({
                    'name': row['Lake Name'],
                    'state': row['State/UT'],
                    'latitude': float(row['Latitude']),
                    'longitude': float(row['Longitude'])
                })
        
        glof_events = []
        with open('glof_events.csv', mode='r') as csv_file:
            csv_reader = csv.DictReader(csv_file)
            for row in csv_reader:
                if row['region'] in ['Uttarakhand', 'Sikkim', 'Ladakh', 'Himachal Pradesh']:
                    glof_events.append({
                        'lake_name': row['lake_name'],
                        'latitude': float(row['latitude']),
                        'longitude': float(row['longitude']),
                        'elevation': int(row['elevation_m']),
                        'region': row['region'],
                        'outburst_count': int(row['outburst_count']),
                        'glof_period': row['glof_period'],
                        'lake_type': row['lake_type'],
                        'weather_conditions': row['weather_conditions'],
                        'glof_occurred': bool(int(row['glof_occurred']))
                    })
        
        return jsonify({
            'lakes': lakes,
            'glof_events': glof_events
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/weather', methods=['GET'])
def get_weather():
    lat = request.args.get("lat")
    lon = request.args.get("lon")
    if not lat or not lon:
        return jsonify({"error": "Missing coordinates"}), 400

    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&units=metric&appid={OPENWEATHER_KEY}"
        response = requests.get(url)
        return jsonify(response.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/alert', methods=['POST'])
def send_alert():
    data = request.get_json()
    lake_name = data.get("lake_name", "Unknown Lake")
    risk_score = data.get("risk_score", 0)
    
    # Initialize the alert system
    from glof_alert_system import GLOFAlertSystem, GLOFRiskLevel
    
    risk_level = GLOFRiskLevel.CRITICAL if risk_score > 70 else GLOFRiskLevel.HIGH if risk_score > 40 else GLOFRiskLevel.MODERATE
    
    glof_system = GLOFAlertSystem(
        fast2sms_api_key=FAST2SMS_API_KEY,
        email_config={
            'smtp_host': 'smtp.gmail.com',
            'smtp_port': 587,
            'username': 'your_email@gmail.com',
            'password': 'your_app_password'
        }
    )
    
    success = glof_system.send_glof_alert(
        glacial_lake=lake_name,
        risk_level=risk_level,
        additional_info=f"Automated alert: Risk score {risk_score}%"
    )
    
    return jsonify({"status": "success" if success else "failed"})

if __name__ == '__main__':
    app.run(port=5001, debug=True)