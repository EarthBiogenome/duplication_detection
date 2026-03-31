"""
TSV File Validator for EBP Duplication Alert System

This script validates TSV input files to ensure they are properly formatted
for the duplication alert notification system. It checks for common issues
that could cause parsing errors or email sending failures.

Usage:
    python validate_tsv.py                              # Validates default file
    python validate_tsv.py <filename>.tsv               # Validates specific file

Expected TSV Format:
    - Columns: goat_project, sequencing_status, contact_email, contact_name
    - Multiple emails: comma-separated, no spaces (e.g., email1@x.com,email2@y.com)
    - Multiple names: comma-separated, no spaces (e.g., John Doe,Jane Smith)
    - Empty contacts: OK (projects will be skipped during processing)

Validation Checks:
    - File structure and column names
    - Trailing/leading spaces in emails
    - Spaces after commas in email/name lists
    - Mismatched email/name counts
    - Special characters in emails (informational)

Author: EBP Duplication Alert System
Date: October 2025
"""

import pandas as pd
import sys

# Set UTF-8 encoding for Windows console
sys.stdout.reconfigure(encoding='utf-8')

def validate_tsv_file(filename):
    """Validate a TSV file for the duplication alert system"""
    print(f"[INFO] Validating file: {filename}")
    print("=" * 60)
    
    try:
        # Read the TSV file
        df = pd.read_csv(filename, sep='\t')
        
        print(f'[OK] File loaded successfully')
        print(f'[INFO] Total rows: {len(df)}')
        print(f'[INFO] Columns: {list(df.columns)}')
        
        # Check for empty emails and names
        empty_emails = df['contact_email'].isna() | (df['contact_email'] == '')
        empty_names = df['contact_name'].isna() | (df['contact_name'] == '')
        
        print(f'\n[INFO] Projects with empty emails: {empty_emails.sum()} (OK if intentional)')
        print(f'[INFO] Projects with empty names: {empty_names.sum()} (OK if intentional)')
        
        # Find specific issues
        print(f'\n[CHECK] Scanning for potential issues...')
        issues_found = False
        warning_count = 0
        
        for i, row in df.iterrows():
            project = row['goat_project']
            email = row['contact_email']
            name = row['contact_name']
            
            # Only flag issues that would cause parsing problems
            # Check for trailing spaces in emails
            if not pd.isna(email) and str(email).strip() != '' and str(email) != str(email).strip():
                print(f'  [WARN] Row {i+2}: {project} - Email has trailing/leading spaces: "{email}"')
                warning_count += 1
            # Check for spaces in comma-separated emails (should not have spaces after comma)
            elif not pd.isna(email) and ', ' in str(email):
                print(f'  [WARN] Row {i+2}: {project} - Email has space after comma: {email}')
                warning_count += 1
            # Check for spaces in comma-separated names (should not have spaces after comma)
            elif not pd.isna(name) and ', ' in str(name):
                print(f'  [WARN] Row {i+2}: {project} - Name has space after comma: {name}')
                warning_count += 1
            # Check for multiple contact names but only one email
            elif not pd.isna(name) and ',' in str(name) and (pd.isna(email) or ',' not in str(email)):
                print(f'  [WARN] Row {i+2}: {project} - Multiple names but single/no email')
                warning_count += 1
            # Check email with apostrophe (informational only - should work fine)
            elif not pd.isna(email) and "'" in str(email):
                print(f'  [INFO] Row {i+2}: {project} - Email contains apostrophe: {email} (OK)')
        
        if warning_count == 0:
            print('  [OK] No issues found!')
        else:
            print(f'\n[SUMMARY] Found {warning_count} warnings')
        
        # Show sample of rows with contacts
        print(f'\n[INFO] Sample rows with contacts:')
        has_contacts = df[~empty_emails][:5]
        for i, row in has_contacts.iterrows():
            print(f'  Row {i+2}: {row["goat_project"]}')
            print(f'    Email: {row["contact_email"]}')
            print(f'    Name: {row["contact_name"]}')
        
        print("\n" + "=" * 60)
        print("[OK] Validation complete!")
        return True
        
    except Exception as e:
        print(f'[ERROR] Failed to validate file: {e}')
        return False

if __name__ == "__main__":
    # You can specify a file or use the default
    import sys
    filename = sys.argv[1] if len(sys.argv) > 1 else 'GoaT_Linked_Projects_10102025.tsv'
    validate_tsv_file(filename)

