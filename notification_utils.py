"""
Notification Utilities Module for EBP Duplication Alert System

This module provides core utility functions for the duplication alert notification system,
including Gmail API authentication, email sending, data loading, and HTML table formatting.

Key Features:
    - Gmail API authentication and email sending
    - Project data loading from TSV files
    - GoaT API integration for bioproject and species data
    - HTML table generation for email reports
    - Logging and file management

Functions:
    - authenticate_gmail(): Authenticate with Gmail API using OAuth2
    - send_email_with_gmail_api(): Send HTML emails via Gmail API
    - load_projects_data(): Load and parse project data from TSV files
    - get_bioproject_id(): Fetch bioproject ID from GoaT API
    - get_project_info(): Retrieve project contact information
    - format_sequencing_status_table(): Generate HTML tables for email reports
    - log_message(): Write timestamped log messages

Configuration:
    - SCOPES: Gmail API permissions
    - CREDENTIALS_FILE: OAuth2 credentials file path
    - TOKEN_FILE: OAuth2 token storage file path
    - OUTPUT_DIR: Directory for saving output files and logs
    - TODAY: Current date in ISO format

Dependencies:
    - google-auth-oauthlib: Gmail OAuth2 authentication
    - google-api-python-client: Gmail API client
    - pandas: Data manipulation and TSV parsing
    - requests: HTTP requests to GoaT API
    - projectsMap: Project name mapping dictionary

Author: EBP Duplication Alert System
Date: October 2025
"""

import os
import requests
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import date
from urllib.parse import quote
import json
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import base64
from base64 import b64encode
from projectsMap import projectsMap

# Constants
SCOPES = ['https://www.googleapis.com/auth/gmail.send']
CREDENTIALS_FILE = 'credentials.json'
TOKEN_FILE = 'token.json'
TODAY = date.today().isoformat()
OUTPUT_DIR = "./output_files"
os.makedirs(OUTPUT_DIR, exist_ok=True)
LOG_FILE = os.path.join(OUTPUT_DIR, f"Overlaps_GoaT_Projects_{TODAY}.txt")

def log_message(message):
    """Log message with timestamp"""
    print(message)  # Add print for immediate feedback
    with open(LOG_FILE, "a") as log:
        log.write(f"{TODAY}: {message}\n")

def authenticate_gmail():
    """Authenticate with Gmail API"""
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
        creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
    return creds

def send_email_with_gmail_api(subject, body_html, recipient_emails, cc_emails=None):
    """Send email using Gmail API"""
    creds = authenticate_gmail()
    try:
        service = build('gmail', 'v1', credentials=creds)
        
        # Debug print to check recipient emails
        print(f"Sending email to: {recipient_emails}")
        if cc_emails:
            print(f"CC: {cc_emails}")
        
        # Validate recipient emails
        if not recipient_emails or not any(recipient_emails):
            raise ValueError("No valid recipient email addresses provided")
            
        # Filter out any empty strings and strip whitespace
        valid_emails = [email.strip() for email in recipient_emails if email and email.strip()]
        valid_cc_emails = []
        if cc_emails:
            valid_cc_emails = [email.strip() for email in cc_emails if email and email.strip()]
        
        if not valid_emails:
            raise ValueError("No valid recipient email addresses after filtering")
            
        # Create the email message
        msg = MIMEMultipart()
        msg['From'] = "lori.chenfang@gmail.com"  # Replace with your email
        msg['To'] = ", ".join(valid_emails)  # Join valid emails with comma
        if valid_cc_emails:
            msg['Cc'] = ", ".join(valid_cc_emails)
        msg['Subject'] = subject
        msg.attach(MIMEText(body_html, 'html'))

        # Encode the message
        raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        # Add 'SENT' label to save in Sent folder
        message = {
            'raw': raw_message,
            'labelIds': ['SENT']
        }

        # Send the email
        sent_message = service.users().messages().send(userId='me', body=message).execute()
        print(f"Email sent successfully! Message ID: {sent_message['id']}")
        return True

    except Exception as e:
        print(f"An error occurred while sending the email: {e}")
        log_message(f"Email sending error: {str(e)}")
        return False

def load_projects_data(input_file):
    """Load and validate projects data"""
    try:
        project_info = pd.read_csv(input_file, sep="\t", na_values=["", "NA"], keep_default_na=False)
        if project_info.empty:
            log_message("Error: Input file is empty")
            return None
            
        # Convert numeric columns to string where needed
        string_columns = ['goat_project', 'contact_name', 'contact_email']
        for col in string_columns:
            if col in project_info.columns:
                project_info[col] = project_info[col].astype(str)
                
        return project_info
    except Exception as e:
        log_message(f"Error loading projects data: {str(e)}")
        return None

def get_bioproject_id(project_name):
    """
    Get bioproject ID from projectsMap
    Args:
        project_name (str): Name of the project
    Returns:
        str: Bioproject ID if found, empty string if not found
    """
    try:
        # Convert project name to lowercase to match projectsMap keys
        project_key = project_name.lower()
        return projectsMap.get(project_key, "")
        
    except Exception as e:
        raise ValueError(f"Error getting bioproject for {project_name}: {e}")

def get_project_info(project_name):
    """
    Helper function to get common project information
    Returns tuple of (project_encoded, bioproject)
    """
    try:
        project_encoded = project_name.lower()
        bioproject = get_bioproject_id(project_name)
        if not bioproject:
            raise ValueError(f"No bioproject ID found for {project_name}")
        return project_encoded, bioproject
    except Exception as e:
        raise ValueError(f"Error getting project info for {project_name}: {str(e)}") 

def format_sequencing_status_table(table_rows):
    """
    Format the sequencing status table data into an HTML table
    Returns HTML string with styled table
    """
    try:
        # Validate input
        if not table_rows:
            log_message("Warning: No table rows provided")
            return ""
            
        if len(table_rows) < 2:
            log_message("Warning: Not enough rows to create table")
            return ""

        # Start building HTML
        html = """
        <table style="
            border-collapse: collapse;
            width: 35%;
            margin: 5px 0;
            font-family: Arial, sans-serif;
            font-size: 14px
        ">
        <colgroup>
            <col style="width: 70%;">
            <col style="width: 30%;">
        </colgroup>
        <thead>
            <tr style="background-color: #f2f2f2;">
                <th style="
                    border: 1px solid #ddd;
                    padding: 3px 3px;
                    text-align: left;
                    font-weight: bold;
                    width: 70%;
                ">{}</th>
                <th style="
                    border: 1px solid #ddd;
                    padding: 3px 3px;
                    text-align: left;
                    font-weight: bold;
                    width: 30%;
                ">{}</th>
            </tr>
        </thead>
        <tbody>
        """.format(table_rows[0][0], table_rows[0][1])

        # Add data rows
        for row in table_rows[1:]:
            if len(row) != 2:
                log_message(f"Warning: Invalid row format: {row}")
                continue
                
            html += """
            <tr>
                <td style="
                    border: 1px solid #ddd;
                    padding: 3px;
                    width: 70%;
                ">{}</td>
                <td style="
                    border: 1px solid #ddd;
                    padding: 3px;
                    width: 30%;
                ">{}</td>
            </tr>
            """.format(row[0], row[1])

        html += """
        </tbody>
        </table>
        """

        return html

    except Exception as e:
        log_message(f"Error formatting table: {e}")
        return ""




