"""
Glacial Lake Outburst Flood (GLOF) Alert Notification System
Specialized alert system for GLOF warnings with SMS, email, and offline capabilities.
"""

import json
import logging
import requests
import smtplib
from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum
from dataclasses import dataclass, asdict
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import threading
import time
from queue import Queue

# Configuration Classes
class GLOFRiskLevel(Enum):
    LOW = "Low Risk"
    MODERATE = "Moderate Risk"
    HIGH = "High Risk"
    CRITICAL = "Critical"

class UserType(Enum):
    LOCAL = "LOCAL"
    ADMIN = "ADMIN"  # Changed from DEFENCE_AUTHORITY to ADMIN
    RESCUE = "RESCUE"
    EMERGENCY_TEAM = "EMERGENCY_TEAM"

class AlertStatus(Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    OFFLINE_QUEUED = "OFFLINE_QUEUED"

@dataclass
class GLOFContact:
    name: str
    phone: str
    email: str
    user_type: UserType
    region: str
    lake_area: str
    id: str = None
    active: bool = True
    created_at: str = None

@dataclass
class GLOFAlert:
    id: str
    glacial_lake: str
    risk_level: GLOFRiskLevel
    timestamp: str
    message: str
    contacts: List[str]
    status: AlertStatus
    created_at: str
    sent_at: str = None
    retry_count: int = 0
    additional_data: Dict = None

class GLOFContactManager:
    """Manages predefined GLOF contacts"""
    
    def __init__(self):
        # Predefined contacts - these are the only contacts in the system
        self.contacts = [
            GLOFContact(
                id="Defence_Base",
                name="DEFENCE AUTHORITY",
                phone="+918956911720",
                email="bhavsarkrishna02@gmail.com",
                user_type=UserType.ADMIN,
                region="NORTH_REGION",
                lake_area="ALL"
            ),
            GLOFContact(
                id="emergency_team_1",
                name="Emergency Response Team",
                phone="+919765743155",
                email="rajputmanas593@gmail.com",
                user_type=UserType.EMERGENCY_TEAM,
                region="NORTH_REGION",
                lake_area="ALL"
            ),
            GLOFContact(
                id="rescue_pangong_1",
                name="Local residential store pangong Tso",
                phone="+919699216764",
                email="yash61304@gmail.com",
                user_type=UserType.RESCUE,
                region="NORTH_REGION",
                lake_area="ALL"
            )
        ]
        
        logging.info(f"Initialized GLOF system with {len(self.contacts)} predefined contacts")
        
    def get_contacts_for_lake(self, lake_name: str, user_types: List[UserType] = None) -> List[GLOFContact]:
        """Get contacts for specified lake and user types"""
        filtered_contacts = []
        
        for contact in self.contacts:
            # Check if contact covers this lake (ALL covers everything)
            if contact.lake_area == "ALL" or contact.lake_area == lake_name:
                # Check user type filter
                if not user_types or contact.user_type in user_types:
                    if contact.active:
                        filtered_contacts.append(contact)
        
        return filtered_contacts
    
    def get_all_contacts(self) -> List[GLOFContact]:
        """Get all active contacts"""
        return [contact for contact in self.contacts if contact.active]
    
    def get_contact_by_id(self, contact_id: str) -> Optional[GLOFContact]:
        """Get contact by ID"""
        for contact in self.contacts:
            if contact.id == contact_id:
                return contact
        return None

class Fast2SMSProvider:
    """Fast2SMS integration for GLOF alerts"""
    
    def __init__(self, api_key: str, sender_id: str = "GLOF"):
        self.api_key = api_key
        self.sender_id = sender_id
        self.base_url = "https://www.fast2sms.com/dev/bulkV2"
        
    def send_glof_sms(self, phone_numbers: List[str], message: str) -> Dict:
        try:
            clean_numbers = [num.replace('+91', '').replace('-', '').replace(' ', '') for num in phone_numbers]
            payload = {
                'authorization': self.api_key,
                'sender_id': self.sender_id,
                'message': message,
                'language': 'english',
                'route': 'q',
                'numbers': ','.join(clean_numbers)
            }
            headers = {'authorization': self.api_key}
            response = requests.post(self.base_url, data=payload, headers=headers, timeout=30)
            response.raise_for_status()  # Raise HTTP errors
            result = response.json()
            logging.info(f"SMS sent to {len(clean_numbers)} recipients: {result}")
            return {'success': True, 'response': result}
        except requests.exceptions.RequestException as e:
            logging.error(f"SMS failed: {str(e)}. Response: {e.response.text if e.response else 'No response'}")
            return {'success': False, 'error': str(e)}

class GLOFEmailProvider:
    """Email provider for GLOF alerts"""
    
    def __init__(self, smtp_host: str, smtp_port: int, username: str, password: str):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        
    def send_glof_email(self, recipients: List[str], glacial_lake: str, message: str) -> Dict:
        """Send GLOF alert emails"""
        try:
            subject = f"🚨 CRITICAL GLOF ALERT - {glacial_lake}"
            
            msg = MIMEMultipart()
            msg['From'] = self.username
            msg['Subject'] = subject
            
            # Create HTML version of the message
            html_message = f"""
            <html>
            <body style="font-family: Arial, sans-serif;">
                <div style="background-color: #ff4444; color: white; padding: 20px; border-radius: 10px; margin-bottom: 20px;">
                    <h2>🚨 GLACIAL LAKE OUTBURST FLOOD ALERT</h2>
                </div>
                <div style="background-color: #f9f9f9; padding: 20px; border-radius: 5px;">
                    <pre style="font-family: Arial, sans-serif; font-size: 14px; line-height: 1.6;">
{message}
                    </pre>
                </div>
                <div style="margin-top: 20px; padding: 15px; background-color: #ffffcc; border-radius: 5px;">
                    <strong>⚠️ This is an automated emergency alert. Take immediate action as advised.</strong>
                </div>
            </body>
            </html>
            """
            
            msg.attach(MIMEText(message, 'plain'))
            msg.attach(MIMEText(html_message, 'html'))
            
            server = smtplib.SMTP(self.smtp_host, self.smtp_port)
            server.starttls()
            server.login(self.username, self.password)
            
            failed_recipients = []
            successful_sends = 0
            
            for recipient in recipients:
                try:
                    msg['To'] = recipient
                    server.sendmail(self.username, recipient, msg.as_string())
                    successful_sends += 1
                    del msg['To']  # Remove To header for next iteration
                except Exception as e:
                    failed_recipients.append(recipient)
                    logging.error(f"Failed to send GLOF email to {recipient}: {e}")
            
            server.quit()
            
            logging.info(f"GLOF emails sent successfully to {successful_sends} recipients")
            return {
                'success': len(failed_recipients) == 0,
                'successful_sends': successful_sends,
                'failed_recipients': failed_recipients
            }
        except Exception as e:
            logging.error(f"GLOF email sending error: {e}")
            return {'success': False, 'error': str(e)}

class GLOFOfflineManager:
    """Manages offline GLOF alerts"""
    
    def __init__(self):
        self.offline_queue = Queue()
        self.is_online = True  # Assume online by default
    
    def add_offline_alert(self, alert: GLOFAlert) -> bool:
        """Add alert to offline queue"""
        try:
            self.offline_queue.put(alert)
            logging.info(f"Alert queued offline: {alert.id}")
            return True
        except Exception as e:
            logging.error(f"Failed to queue offline alert: {e}")
            return False
    
    def get_queued_alerts(self) -> List[GLOFAlert]:
        """Get all queued offline alerts"""
        queued_alerts = []
        while not self.offline_queue.empty():
            queued_alerts.append(self.offline_queue.get())
        return queued_alerts

    def check_connectivity(self) -> bool:
        """Check if system is online"""
        try:
            # Simple connectivity check
            requests.get("https://www.google.com", timeout=5)
            self.is_online = True
            return True
        except:
            self.is_online = False
            return False
        

class GLOFMessageFormatter:
    """Formats GLOF alert messages"""
    
    @staticmethod
    def format_glof_message(glacial_lake: str, risk_level: GLOFRiskLevel, 
                           timestamp: str = None, additional_info: str = None) -> str:
        """Format GLOF alert message using the specified template"""
        
        if not timestamp:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M IST')
        
        # Base message template
        message = f"""⚠️ *[{risk_level.value.upper()} GLOF ALERT]*

*Glacial Lake:* {glacial_lake}
*Risk Level:* {risk_level.value}
*Time:* {timestamp}

*Immediate evacuation advised. Emergency team notified.*"""

        # Add additional information if provided
        if additional_info:
            message += f"\n\n*Additional Info:* {additional_info}"
            
        return message
    
    @staticmethod
    def format_all_clear_message(glacial_lake: str, timestamp: str = None) -> str:
        """Format all-clear message"""
        if not timestamp:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M IST')
            
        return f"""✅ *[GLOF ALL CLEAR]*

*Glacial Lake:* {glacial_lake}
*Status:* Risk Level Reduced
*Time:* {timestamp}

*Immediate threat has passed. Continue monitoring.*"""

class GLOFAlertSystem:
    """Main GLOF Alert Notification System"""
    
    def __init__(self, fast2sms_api_key: str, email_config: Dict = None):
        self.contact_manager = GLOFContactManager()
        self.sms_provider = Fast2SMSProvider(fast2sms_api_key, sender_id="GLOF")
        self.email_provider = GLOFEmailProvider(**email_config) if email_config else None
        self.offline_manager = GLOFOfflineManager()
        self.message_formatter = GLOFMessageFormatter()
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - [GLOF] %(message)s',
            handlers=[
                logging.FileHandler('glof_alerts.log'),
                logging.StreamHandler()
            ]
        )
        
        logging.info("GLOF Alert System initialized with predefined contacts")
        self._show_contacts()
        
    def _show_contacts(self):
        """Display loaded contacts"""
        contacts = self.contact_manager.get_all_contacts()
        logging.info(f"Loaded {len(contacts)} contacts:")
        for contact in contacts:
            logging.info(f"  - {contact.name} ({contact.user_type.value}) - {contact.phone}")
        
    def send_glof_alert(self, glacial_lake: str, risk_level: GLOFRiskLevel, 
                       additional_info: str = None, target_user_types: List[UserType] = None) -> bool:
        """Send GLOF alert for specified glacial lake"""
        try:
            # Default to all user types if none specified
            if not target_user_types:
                target_user_types = [UserType.LOCAL, UserType.ADMIN, UserType.RESCUE, UserType.EMERGENCY_TEAM]
            
            # Get contacts for this lake
            contacts = self.contact_manager.get_contacts_for_lake(glacial_lake, target_user_types)
            
            if not contacts:
                logging.warning(f"No contacts found for glacial lake: {glacial_lake}")
                return False
            
            # Format alert message
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M IST')
            message = self.message_formatter.format_glof_message(
                glacial_lake, risk_level, timestamp, additional_info
            )
            
            # Create alert record
            alert = GLOFAlert(
                id=f"glof_{glacial_lake.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                glacial_lake=glacial_lake,
                risk_level=risk_level,
                timestamp=timestamp,
                message=message,
                contacts=[c.id for c in contacts],
                status=AlertStatus.PENDING,
                created_at=datetime.now().isoformat(),
                additional_data={'additional_info': additional_info} if additional_info else None
            )
            
            # Send alerts
            success = self._send_alert(alert, contacts)
            
            if success:
                logging.info(f"GLOF alert sent successfully for {glacial_lake} - Risk: {risk_level.value}")
                logging.info(f"Recipients: {[c.name for c in contacts]}")
            else:
                logging.error(f"Failed to send GLOF alert for {glacial_lake}")
                
            return success
            
        except Exception as e:
            logging.error(f"Error sending GLOF alert: {e}")
            return False
    
    def send_all_clear(self, glacial_lake: str, target_user_types: List[UserType] = None) -> bool:
        """Send all-clear message for glacial lake"""
        try:
            if not target_user_types:
                target_user_types = [UserType.LOCAL, UserType.ADMIN, UserType.RESCUE, UserType.EMERGENCY_TEAM]
            
            contacts = self.contact_manager.get_contacts_for_lake(glacial_lake, target_user_types)
            
            if not contacts:
                logging.warning(f"No contacts found for glacial lake: {glacial_lake}")
                return False
            
            message = self.message_formatter.format_all_clear_message(glacial_lake)
            
            # Send via SMS and email
            success = self._send_message(contacts, message, f"GLOF All Clear - {glacial_lake}")
            
            if success:
                logging.info(f"All-clear sent for {glacial_lake}")
                logging.info(f"Recipients: {[c.name for c in contacts]}")
            
            return success
            
        except Exception as e:
            logging.error(f"Error sending all-clear for {glacial_lake}: {e}")
            return False
    
    def _send_alert(self, alert: GLOFAlert, contacts: List[GLOFContact]) -> bool:
        """Send alert via SMS and email"""
        try:
            phone_numbers = [c.phone for c in contacts if c.phone]
            email_addresses = [c.email for c in contacts if c.email]
            
            sms_success = False
            email_success = False
            
            # Always try SMS first
            if phone_numbers:
                sms_result = self.sms_provider.send_glof_sms(phone_numbers, alert.message)
                sms_success = sms_result.get('success', False)
                
                if not sms_success:
                    logging.error(f"SMS failed: {sms_result.get('error', 'Unknown error')}")
                    # Queue alert if offline
                    if not self.offline_manager.is_online:
                        alert.status = AlertStatus.OFFLINE_QUEUED
                        self.offline_manager.add_offline_alert(alert)
                        return True  # Consider queued as success
            
            # Try emails if online and configured
            if self.email_provider and email_addresses:
                if self.offline_manager.is_online:
                    email_result = self.email_provider.send_glof_email(
                        email_addresses, alert.glacial_lake, alert.message
                    )
                    email_success = email_result.get('success', False)
                    
                    if not email_success:
                        logging.error(f"Email failed: {email_result.get('error', 'Unknown error')}")
            
            # Update alert status
            if sms_success or email_success:
                alert.status = AlertStatus.SENT
                alert.sent_at = datetime.now().isoformat()
                return True
            else:
                alert.status = AlertStatus.FAILED
                return False
                
        except Exception as e:
            logging.error(f"Error in _send_alert: {e}")
            if not self.offline_manager.is_online:
                alert.status = AlertStatus.OFFLINE_QUEUED
                self.offline_manager.add_offline_alert(alert)
                return True
            return False
    
    def _send_message(self, contacts: List[GLOFContact], message: str, subject: str) -> bool:
        """Generic method to send message to contacts"""
        try:
            phone_numbers = [c.phone for c in contacts if c.phone]
            email_addresses = [c.email for c in contacts if c.email]
            
            sms_success = False
            email_success = False
            
            if self.offline_manager.is_online and phone_numbers:
                sms_result = self.sms_provider.send_glof_sms(phone_numbers, message)
                sms_success = sms_result.get('success', False)
            
            if self.email_provider and self.offline_manager.is_online and email_addresses:
                email_result = self.email_provider.send_glof_email(email_addresses, subject, message)
                email_success = email_result.get('success', False)
            
            return sms_success or email_success
            
        except Exception as e:
            logging.error(f"Error sending message: {e}")
            return False
    
    def get_all_contacts(self) -> List[Dict]:
        """Get all contacts information"""
        contacts = self.contact_manager.get_all_contacts()
        return [
            {
                'id': contact.id,
                'name': contact.name,
                'phone': contact.phone,
                'email': contact.email,
                'user_type': contact.user_type.value,
                'region': contact.region,
                'lake_area': contact.lake_area
            }
            for contact in contacts
        ]

# Example usage
def main():
    """Example usage of GLOF Alert System"""
    
    # Email configuration (optional)
    email_config = {
        'smtp_host': 'smtp.gmail.com',
        'smtp_port': 587,
        'username': 'your_email@gmail.com',
        'password': 'your_app_password'
    }
    
    # Initialize GLOF alert system
    glof_system = GLOFAlertSystem(
        fast2sms_api_key="zgl87ILMxnj9diyV3AuGWEcRCZwD06JsYK4Nt2eQ5ObSTmakqvPSbaNKywjDUhVIR9X2m3Z4kWJuiOEc",
        email_config=email_config
    )
    
    print("GLOF Alert System initialized with predefined contacts!")
    print("\nAvailable contacts:")
    contacts = glof_system.get_all_contacts()
    for contact in contacts:
        print(f"- {contact['name']} ({contact['user_type']}) - {contact['phone']}")
    
    # Example: Send a critical alert
    print("\nSending test alert...")
    success = glof_system.send_glof_alert(
        glacial_lake="Pangong Tso",
        risk_level=GLOFRiskLevel.CRITICAL,
        additional_info="Water levels rising rapidly. Immediate evacuation required."
    )
    
    if success:
        print("Alert sent successfully!")
    else:
        print("Failed to send alert.")

if __name__ == "__main__":
    main()

# Integration Example
"""
Usage with predefined contacts:

```python
from glof_alert_system import GLOFAlertSystem, GLOFRiskLevel, UserType

# Initialize with your API credentials
glof_alerts = GLOFAlertSystem(fast2sms_api_key="YOUR_API_KEY")

# Send alert to all contacts
glof_alerts.send_glof_alert("Pangong Tso", GLOFRiskLevel.HIGH)

# Send alert to specific user types only
glof_alerts.send_glof_alert(
    "Pangong Tso", 
    GLOFRiskLevel.CRITICAL,
    target_user_types=[UserType.ADMIN, UserType.EMERGENCY_TEAM]
)

# Send all-clear
glof_alerts.send_all_clear("Pangong Tso")
```

Predefined Contacts:
✅ DEFENCE AUTHORITY (Admin) - +918956911720
✅ Emergency Response Team - +919765743155  
✅ Local residential store pangong Tso (Rescue) - +919699216764
✅ All contacts cover ALL lake areas in NORTH_REGION
✅ No dynamic contact creation - fixed contacts only
"""