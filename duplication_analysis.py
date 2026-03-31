#!/usr/bin/env python3
"""
EBP Duplication Analysis Module

This module contains all the business logic functions for the EBP duplication alert system.
It handles enhanced matrix analysis, report generation, email content creation, and main execution.

Author: EBP Duplication Alert System
Version: 2025-09-30
"""

# =============================================================================
# IMPORTS
# =============================================================================

# Standard library imports
import os
import json
from urllib.parse import quote

# Third-party imports
import requests
import pandas as pd

# Local imports from notification_utils
from notification_utils import (
    log_message, 
    authenticate_gmail,
    send_email_with_gmail_api,
    load_projects_data,
    get_bioproject_id,
    get_project_info,
    format_sequencing_status_table,
    OUTPUT_DIR,
    TODAY,
    LOG_FILE
)

# =============================================================================
# CONFIGURATION
# =============================================================================

# API Configuration
BASE_URL = "https://goat.genomehubs.org/api/v2/search?query="
PROJECT_CONTACTS_URL = "https://docs.google.com/spreadsheets/d/1QLYeyoMcUyMJqGpBuS8CRP-oU6HfhwT3zD5KfrawMT4/edit?usp=sharing"
INPUT_FILE = "GoaT_Projects_Test.tsv"

# GoaT API Fields Parameter - Defines all sequencing status fields to query
COMMON_FIELDS_PARAM = quote(
    "assembly_level,sequencing_status_1000gch,sequencing_status_africabp,sequencing_status_ag100pest,"
    "sequencing_status_aegis,sequencing_status_agi,sequencing_status_agc,sequencing_status_arg,"
    "sequencing_status_asg,sequencing_status_atlasea,sequencing_status_avi,sequencing_status_b10k,"
    "sequencing_status_bat1k,sequencing_status_beenome100,sequencing_status_canbp,sequencing_status_canseq150,"
    "sequencing_status_cbp,sequencing_status_ccgp,sequencing_status_cfgp,sequencing_status_cgp,"
    "sequencing_status_dtol,sequencing_status_ebpn,sequencing_status_ebphk,sequencing_status_endemixit,"
    "sequencing_status_erga-bge,sequencing_status_erga-ch,sequencing_status_erga-com,sequencing_status_erga-pil,"
    "sequencing_status_eurofish,sequencing_status_ffi,sequencing_status_fish,sequencing_status_gaga,"
    "sequencing_status_gap,sequencing_status_gbr,sequencing_status_giga,sequencing_status_hk-ebp,"
    "sequencing_status_i5k,sequencing_status_ilebp,sequencing_status_ipm,sequencing_status_1kfg,"
    "sequencing_status_lmgp,sequencing_status_loewe-tbg,sequencing_status_metainvert,sequencing_status_og,"
    "sequencing_status_ogg,sequencing_status_omg,sequencing_status_other,sequencing_status_pgp,"
    "sequencing_status_phyloalps,sequencing_status_pp,sequencing_status_prgp,sequencing_status_psyche,"
    "sequencing_status_squalomix,sequencing_status_tsi,sequencing_status_vgp,sequencing_status_wa,"
    "sequencing_status_ygg,sequencing_status_zoonomia,sequencing_status_ebp,sequencing_status_25gp,"
    "sequencing_status_anopheles,sequencing_status_bioplatforms,sequencing_status_dgb,sequencing_status_dnazoo,"
    "sequencing_status_erga"
)

# Status categories for analysis
STATUS_CATEGORIES = [
    'not_started', 'sample_collected', 'sample_acquired', 'data_generation', 
    'in_assembly', 'in_progress', 'open', 'insdc_open', 'published'
]

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def append_status_note(html_table: str) -> str:
    """
    Append a reference note to HTML tables for sequencing status descriptions.
    
    Args:
        html_table (str): HTML table content
        
    Returns:
        str: HTML table with appended status description note
    """
    try:
        if not html_table:
            return html_table
        return html_table + (
            "<div style=\"text-align: left; font-style: italic; font-size: 11px; margin-top: 4px;\">"
            "*see below for sequencing status description"
            "</div>"
        )
    except Exception:
        return html_table


# =============================================================================
# CORE ANALYSIS FUNCTIONS
# =============================================================================

def analyze_project_contributions_matrix_enhanced(species_data, target_project, original_counts):
    """
    Enhanced matrix analysis that includes not_started species with other project contributions.
    
    This version properly counts which projects contributed to EBP-standard assemblies
    for species that the target project hasn't started sequencing yet.
    
    Args:
        species_data (list): List of species records from GoaT API
        target_project (str): Name of the target project being analyzed
        original_counts (dict): Original status counts for verification
        
    Returns:
        dict: Enhanced matrix data structure containing:
            - status_order: List of sequencing status categories
            - project_columns: List of all contributing projects (sorted by contribution)
            - matrix: Dictionary mapping status -> project -> count
            - original_counts: Original status counts for reference
    """
    try:
        # Initialize data structures
        status_categories = STATUS_CATEGORIES
        
        project_contributions = {}
        for status in status_categories:
            project_contributions[status] = {}
        
        log_message(f"📊 Processing {len(species_data)} species records for enhanced matrix analysis")
        
        for species_idx, species in enumerate(species_data):
            # Extract data correctly from result.fields
            if 'result' in species and 'fields' in species['result']:
                record = species['result']['fields']
            elif 'result' in species:
                record = species['result']
            else:
                continue
                
            # Get target project status for this species
            target_status_field = f"sequencing_status_{target_project.lower()}"
            target_status = record.get(target_status_field)
            
            # Extract actual status value
            if isinstance(target_status, dict):
                target_status = target_status.get('value') or target_status.get('val')
            elif isinstance(target_status, list) and len(target_status) > 0:
                target_status = target_status[0]
            
            # ENHANCED LOGIC: Handle not_started species properly
            if not target_status or str(target_status).lower() in ['null', 'none', '']:
                # This is a not_started species - we still want to analyze other project contributions!
                target_category = 'not_started'
            else:
                target_category = str(target_status).lower().replace(' ', '_')
                if target_category not in status_categories:
                    continue
                
            # Find all sequencing status fields for other projects
            status_fields = [k for k in record.keys() if k.startswith('sequencing_status_')]
            species_contributing_projects = set()  # Prevent double counting within this species
            
            # Helper to robustly extract a usable status value
            def extract_status_value(raw: object) -> str | None:
                if raw is None:
                    return None
                # Direct string
                if isinstance(raw, str):
                    return raw
                # List: find first non-empty string element
                if isinstance(raw, list):
                    for item in raw:
                        if isinstance(item, str) and item.strip() and item.lower() not in ['null', 'none']:
                            return item
                        if isinstance(item, (int, float)):
                            return str(item)
                        if isinstance(item, dict):
                            candidate = extract_status_value(item.get('value') or item.get('val'))
                            if candidate:
                                return candidate
                    return None
                # Dict: prefer common keys; otherwise any truthy string value
                if isinstance(raw, dict):
                    # Known value keys
                    if 'value' in raw or 'val' in raw:
                        candidate = raw.get('value') or raw.get('val')
                        return candidate if isinstance(candidate, str) else (str(candidate) if candidate is not None else None)
                    # If dict only contains counters, treat as no explicit status
                    if set(raw.keys()).issubset({'sp_count', 'count', 'doc_count'}):
                        return None
                    # Fallback: pick first non-empty string among values
                    for v in raw.values():
                        if isinstance(v, str) and v.strip() and v.lower() not in ['null', 'none']:
                            return v
                        if isinstance(v, (int, float)):
                            return str(v)
                    return None
                # Numbers/bools
                if isinstance(raw, (int, float, bool)):
                    return str(raw)
                return None

            # Process each project status field
            for field in status_fields:
                if not field.startswith('sequencing_status_'):
                    continue
                
                project = field.replace('sequencing_status_', '')
                
                # Skip target project and ebp (as requested by user)
                if project == target_project.lower() or project == 'ebp':
                    continue
                
                value = record.get(field)
                actual_value = extract_status_value(value)
                
                # Only count if there's a valid status and we haven't counted this project for this species yet
                if (actual_value and 
                    str(actual_value).lower() not in ['null', 'none', ''] and 
                    project not in species_contributing_projects):
                    
                    species_contributing_projects.add(project)
                    
                    # Add to project contributions for this target category
                    if project not in project_contributions[target_category]:
                        project_contributions[target_category][project] = 0
                    project_contributions[target_category][project] += 1
        
        # Find ALL contributing projects (no limit!)
        all_contributing_projects = set()
        for status_dict in project_contributions.values():
            all_contributing_projects.update(status_dict.keys())
        
        log_message(f"🎯 Found {len(all_contributing_projects)} contributing projects: {sorted(all_contributing_projects)}")
        
        # Sort projects by total contribution (descending)  
        project_totals = {}
        for project in all_contributing_projects:
            total = sum(project_contributions[status].get(project, 0) for status in status_categories)
            project_totals[project] = total
        
        # Include ALL projects, no 8-project limit
        sorted_projects = sorted(project_totals.items(), key=lambda x: x[1], reverse=True)
        all_projects_list = [proj for proj, count in sorted_projects if count > 0]
        
        log_message(f"✅ ALL {len(all_projects_list)} projects will be included in enhanced matrix: {all_projects_list}")
        
        # Create enhanced matrix structure with ALL projects
        matrix_data = {
            'status_order': status_categories,
            'project_columns': all_projects_list,  # ALL projects included!
            'matrix': project_contributions,
            'original_counts': original_counts
        }
        
        # Log detailed analysis for not_started species
        not_started_contributions = project_contributions.get('not_started', {})
        total_not_started_overlaps = sum(not_started_contributions.values())
        log_message(f"🔍 NOT_STARTED ANALYSIS: {len(not_started_contributions)} projects contributed to {total_not_started_overlaps} species")
        
        for project, count in sorted(not_started_contributions.items(), key=lambda x: x[1], reverse=True):
            log_message(f"   - {project}: {count} species with EBP-standard assemblies")
        
        return matrix_data
        
    except Exception as e:
        log_message(f"Error in enhanced matrix analysis: {e}")
        import traceback
        traceback.print_exc()
        return {
            'status_order': [],
            'project_columns': [],
            'matrix': {},
            'original_counts': {}
        }


# =============================================================================
# REPORT GENERATION FUNCTIONS
# =============================================================================

def get_project_matrix_for_report_1_enhanced(project_name):
    """
    Enhanced matrix data generation for Report 1 that includes not_started species analysis.
    
    This version properly analyzes which projects contributed to EBP-standard assemblies
    for species that the target project hasn't started sequencing yet.
    
    Args:
        project_name (str): Name of the target project
        
    Returns:
        dict: Enhanced matrix data structure for HTML table generation, or None if error
    """
    try:
        project_encoded, bioproject = get_project_info(project_name)
        
        # Get original counts for reference
        original_table_data = get_table_data_from_report_1(project_name)
        original_counts = {}
        for row in original_table_data[1:]:  # Skip header
            status = row[0].replace(" ", "_")
            original_counts[status] = int(row[1])
        
        # Get detailed species data for project analysis
        query_param = quote(
            f"long_list={project_encoded} AND "
            f"ebp_standard_date AND "
            f"bioproject!={bioproject} AND "
            f"tax_rank(species)"
        )
        
        species_data = get_detailed_species_data(query_param, project_name, COMMON_FIELDS_PARAM)
        
        # Analyze project contributions in enhanced matrix format
        matrix_data = analyze_project_contributions_matrix_enhanced(species_data, project_encoded, original_counts)
        
        log_message(f"Enhanced matrix data for report 1: {len(matrix_data['project_columns'])} projects found")
        return matrix_data
        
    except Exception as e:
        log_message(f"Error creating enhanced matrix data for report 1 ({project_name}): {e}")
        return None


def get_project_matrix_for_report_2_enhanced(project_name):
    """
    Enhanced matrix data generation for Report 2 that includes not_started species analysis.
    
    Args:
        project_name (str): Name of the target project
        
    Returns:
        dict: Enhanced matrix data structure for HTML table generation, or None if error
    """
    try:
        project_encoded, bioproject = get_project_info(project_name)
        
        # Get original counts for reference
        original_table_data = get_table_data_from_report_2(project_name)
        original_counts = {}
        for row in original_table_data[1:]:  # Skip header
            status = row[0].replace(" ", "_")
            original_counts[status] = int(row[1])
        
        # Get detailed species data for project analysis
        query_param = quote(
            f"sequencing_status_{project_encoded}>=sample_collected AND "
            f"length(sample_collected)>1 AND "
            f"bioproject=null,!{bioproject} AND "
            f"ebp_standard_date=null AND "
            f"tax_rank(species)"
        )
        
        species_data = get_detailed_species_data(query_param, project_name, COMMON_FIELDS_PARAM)
        
        # Analyze project contributions in enhanced matrix format
        matrix_data = analyze_project_contributions_matrix_enhanced(species_data, project_encoded, original_counts)
        
        log_message(f"Enhanced matrix data for report 2: {len(matrix_data['project_columns'])} projects found")
        return matrix_data
        
    except Exception as e:
        log_message(f"Error creating enhanced matrix data for report 2 ({project_name}): {e}")
        return None


def get_project_matrix_for_report_3_enhanced(project_name):
    """
    Enhanced matrix data generation for Report 3 that includes not_started species analysis.
    
    Args:
        project_name (str): Name of the target project
        
    Returns:
        dict: Enhanced matrix data structure for HTML table generation, or None if error
    """
    try:
        project_encoded, bioproject = get_project_info(project_name)
        
        # Get original counts for reference
        original_table_data = get_table_data_from_report_3(project_name)
        original_counts = {}
        for row in original_table_data[1:]:  # Skip header
            status = row[0].replace(" ", "_")
            original_counts[status] = int(row[1])
        
        # Get detailed species data for project analysis
        query_param = quote(
            f"long_list={project_encoded} AND "
            f"sequencing_status_{project_encoded}=null AND "
            f"length(sample_collected)>=1 AND "
            f"bioproject=!{bioproject},null AND "
            f"ebp_standard_date=null AND "
            f"tax_rank(species)"
        )
        
        species_data = get_detailed_species_data(query_param, project_name, COMMON_FIELDS_PARAM)
        
        # Analyze project contributions in enhanced matrix format
        matrix_data = analyze_project_contributions_matrix_enhanced(species_data, project_encoded, original_counts)
        
        log_message(f"Enhanced matrix data for report 3: {len(matrix_data['project_columns'])} projects found")
        return matrix_data
        
    except Exception as e:
        log_message(f"Error creating enhanced matrix data for report 3 ({project_name}): {e}")
        return None


# =============================================================================
# EMAIL GENERATION FUNCTIONS
# =============================================================================

def create_project_email_content_enhanced(project_row):
    """
    Create enhanced email content for a specific project's duplication report
    using the enhanced matrix analysis that includes not_started species.
    """
    project_name = str(project_row['goat_project'])
    contact_name = str(project_row['contact_name'])

    # Feedback form URL - replace with your actual Google Form URL
    feedback_form_url = "https://forms.gle/u2DmxaWfmnJwHZYi9"
    
    try:
        # Get URLs and counts for all three reports
        report_1 = create_table_url_1(project_name)
        report_2 = create_table_url_2(project_name) 
        report_3 = create_table_url_3(project_name)

        # Use enhanced matrix analysis for all reports
        print(f"\n--- Processing {project_name} Enhanced Report Tables ---")
        
        matrix_1 = get_project_matrix_for_report_1_enhanced(project_name)
        if matrix_1 and matrix_1.get('project_columns'):
            print(f"SUCCESS: Enhanced Report 1 matrix has {len(matrix_1['project_columns'])} contributing projects")
            status_table_html_1 = format_project_matrix_table(matrix_1, project_name)
        else:
            print("Enhanced Report 1: No contributing projects found, using original format")
            status_table_1 = get_table_data_from_report_1(project_name)
            status_table_html_1 = append_status_note(format_sequencing_status_table(status_table_1))
        
        # Use enhanced analysis for Report 2
        matrix_2 = get_project_matrix_for_report_2_enhanced(project_name)
        if matrix_2 and matrix_2.get('project_columns'):
            print(f"SUCCESS: Enhanced Report 2 matrix has {len(matrix_2['project_columns'])} contributing projects")
            status_table_html_2 = format_project_matrix_table(matrix_2, project_name)
        else:
            print("Enhanced Report 2: No contributing projects found, using original format")
            status_table_2 = get_table_data_from_report_2(project_name)
            status_table_html_2 = append_status_note(format_sequencing_status_table(status_table_2))
        
        # Use enhanced analysis for Report 3
        matrix_3 = get_project_matrix_for_report_3_enhanced(project_name)
        if matrix_3 and matrix_3.get('project_columns'):
            print(f"SUCCESS: Enhanced Report 3 matrix has {len(matrix_3['project_columns'])} contributing projects")
            status_table_html_3 = format_project_matrix_table(matrix_3, project_name, filter_statuses=['not_started'])
        else:
            print("Enhanced Report 3: No contributing projects found, using original format")
            status_table_3 = get_table_data_from_report_3(project_name)
            status_table_html_3 = append_status_note(format_sequencing_status_table(status_table_3))

        # Create enhanced email content with all three reports
        email_body = f"""
        <html>
        <body>
        <p>Dear {contact_name},</p>

        <p>This is an automated notification regarding your project: <strong>{project_name}</strong>. <br> 
        The following three reports identify species in your project that overlap with other projects in GoaT.
        This notification is sent at the end of each quarter.</p>
        
        <h3 style="margin-bottom: 0px; margin-top: 5px;">How to read the tables below:</h3>
        <p style="margin-top: 4px;">
        • <strong>sequencing_status_{project_name.upper()}</strong>: the status of species in your project (rows)<br>
        • <strong>duplication_count</strong>: total number of species meeting report criteria<br>
        • <strong>overlap_sum</strong>: sum of overlaps across all other projects in that row<br>
        • <strong>project columns</strong>: number of overlapping species each project contributes<br>
        </p>
        
        <h4 style="margin-bottom: 0px; margin-top: 5px;">Notes:</h4>
        <p style="margin-top: 4px;">
        • Numbers in each cell reflect YOUR project's sequencing status only. To see other projects' status for these species, click the GoaT report links.<br>
        • The overlaps shown are between your project and other projects provided in GoaT. If duplication_count value is greater than overlap_sum value, it means that your project overlaps with projects outside GoaT.<br>
        • Overlap_sum value may exceed duplication_count value when species overlap with multiple projects.
        </p>
        
        <h4>1. Duplication of species that have an EBP-standard assembly available</h4>
        <p>This report identifies species from your target list that have at least one assembly meeting the EBP-standard metrics available in INSDC.</p>

        <p><em>See table reading guide above</em></p>

        {status_table_html_1} <br>
    
            <a href="{report_1}" style="
                color: #0000FF;
                text-decoration: underline;
                font-weight: bold;
                margin-left: 10px;
                vertical-align: middle;
                font-size: 16px;">
                GoaT Report #1
            </a> <br>
            <br>In GoaT, you can sort by assembly level or sequencing status to identify highest-priority overlaps.<br>
            <br><strong>Recommendation:</strong> Consider not sequencing the species if sequencing has not_started. If sequencing has begun, consider working with other project representative(s) on a collaborative basis.
        
        <h4>2. Active duplication of species that your project has started working on</h4>
        <p>This report identifies species that your project has started sample collection or sequencing, and these species have been or are being sequenced by other projects represented in GoaT. However, any existing assemblies do not meet the EBP-standard metrics.</p>
        
        <p><em>See table reading guide above</em></p>

        {status_table_html_2} <br>

            <a href="{report_2}" style=" 
                color: #0000FF;
                text-decoration: underline;
                font-weight: bold;
                margin-left: 10px;
                vertical-align: middle;
                font-size: 16px;">
                GoaT Report #2
            </a> <br>        
            <br>In GoaT, you can sort by assembly level or sequencing status to identify highest-priority overlaps.<br>
            <br><strong>Recommendation:</strong> Consider coordination with identified project representative(s) to avoid duplication or improve existing assemblies.
        
        <h4>3. Potential duplication of species that your project has not started working on</h4>
        <p>This report identifies species from your target list that your project has not started sample collection or sequencing, and these species have been or are being sequenced by other projects represented in GoaT. However, any existing assemblies do not meet the EBP-standard metrics.</p>

        <p><em>See table reading guide above</em></p>

        {status_table_html_3} <br>

            <a href="{report_3}" style="
                color: #0000FF;
                text-decoration: underline;
                font-weight: bold;
                margin-left: 10px;
                vertical-align: middle;
                font-size: 16px;">
                GoaT Report #3
            </a> <br>
            <br>In GoaT, you can sort by assembly level or sequencing status to identify highest-priority overlaps.<br>
            <br><strong>Recommendation:</strong> Consider collaboration with identified projects. 
        
        <p><strong>Sequencing Status Description:</strong><br>
        • not_started: on project target list, but sample has not been collected<br>
        • sample_collected: tissue is available for whole genome sequencing<br>
        • sample_acquired: samples received by the designated sequencing centers<br>
        • data_generation: raw sequencing data is being generated<br>
        • in_assembly: genome assembly is in progress or undergoing quality control<br>
        • in_progress: includes data_generation, in_assembly, and submitted to INSDC<br>
        • open: data publicly available in a project-specific data store<br>
        • insdc_open: assembly is publicly available on INSDC<br>
        • published: has a publication associated with genome assembly</p>
        
        <div style="background-color: #fff3cd; padding: 12px; border-left: 4px solid #ffc107; margin: 15px 0;">
            <p style="margin: 0; font-size: 14px;">
                <strong>📋 Need to contact other projects?</strong> Use our 
                <a href="https://docs.google.com/spreadsheets/d/1Pi7ZkPegDeYuKfx6VD10-Wu5qMMDKR_N1qr9dFlWIGI/edit?gid=81959390#gid=81959390" 
                   style="color: #856404; text-decoration: underline; font-weight: bold;">EBP Project Contact List</a> 
                to find representatives and contact information for all EBP-affiliated projects. if there are any changes, please update your project's contact information.
            </p>
        </div>
        
        <div style="background-color: #f8f9fa; padding: 15px; border-left: 4px solid #007bff; margin: 20px 0;">
            <p style="margin: 0; font-size: 14px;">
                <strong>💬 Your feedback matters!</strong> Help us improve this notification system. 
                Share your thoughts through our 
                <a href="{feedback_form_url}" style="color: #007bff; text-decoration: underline; font-weight: bold;">feedback form</a>.
            </p>
        </div>
        
        <p>Yours sincerely,<br>
        <strong>Fang Chen</strong> on behalf of GoaT team</p>
        
        </body>
        </html>
        """
        
        return email_body
        
    except Exception as e:
        log_message(f"Error creating enhanced email content for {project_name}: {str(e)}")
        raise


# =============================================================================
# DATA EXTRACTION FUNCTIONS
# =============================================================================

def get_detailed_species_data(query_param, project_name, fields_param):
    """
    Get detailed species data from GoaT API for matrix analysis.
    
    Args:
        query_param (str): URL-encoded query parameter
        project_name (str): Name of the target project
        fields_param (str): URL-encoded fields parameter
        
    Returns:
        list: List of species records from GoaT API
    """
    try:
        api_url = (
            "https://goat.genomehubs.org/api/v2/search?"
            f"query={query_param}&"
            f"result=taxon&"
            f"includeEstimates=true&"
            f"taxonomy=ncbi&"
            f"fields={fields_param}&"
            f"size=50000&"
            f"offset=0"
        )
        
        log_message(f"🔍 Fetching detailed species data for {project_name}")
        log_message(f"URL: {api_url}")
        
        response = requests.get(api_url, timeout=60)
        response.raise_for_status()
        
        data = response.json()
        species_data = data.get('results', [])
        
        log_message(f"✅ Retrieved {len(species_data)} species records for detailed analysis")
        return species_data
        
    except Exception as e:
        log_message(f"Error fetching detailed species data for {project_name}: {e}")
        return []


def wrap_header_text(text):
    """
    Wrap header text to two lines by inserting line breaks before underscores or in long words.
    
    Args:
        text (str): Header text to wrap
        
    Returns:
        str: Text with line breaks for wrapping
    """
    if '_' in text:
        # Replace underscores with line breaks
        return text.replace('_', '\n')
    elif len(text) > 8:
        # For long words, try to break at natural points
        if 'status' in text.lower():
            return text.replace('status', '\nstatus')
        elif 'count' in text.lower():
            return text.replace('count', '\ncount')
        elif 'sum' in text.lower():
            return text.replace('sum', '\nsum')
    return text


def format_project_matrix_table(project_matrix, project_name, filter_statuses=None):
    """
    Format project matrix data as an HTML table with enhanced styling.
    Matches the original notebook formatting exactly.
    
    Args:
        project_matrix (dict): Matrix data structure from enhanced analysis
        project_name (str): Name of the target project
        filter_statuses (list): Optional list of statuses to include. If None, includes all statuses.
        
    Returns:
        str: HTML table string
    """
    try:
        if not project_matrix or not project_matrix.get('project_columns'):
            return "<p>No project overlap data available</p>"
        
        status_order = project_matrix['status_order']
        project_columns = project_matrix['project_columns']
        matrix = project_matrix['matrix']
        original_counts = project_matrix.get('original_counts', {})
        
        # Calculate column widths dynamically without exceeding 100%
        num_projects = len(project_columns)
        if num_projects >= 18:
            status_col_width = 9  # 12 * 3/4 = 9
            count_col_width = 5
            overlap_col_width = 5
        else:
            status_col_width = 10.5  # 14 * 3/4 = 10.5
            count_col_width = 6
            overlap_col_width = 6
        remaining_width = max(0.0, 100.0 - status_col_width - count_col_width - overlap_col_width)
        project_col_width = (remaining_width / max(1, len(project_columns))) if project_columns else 0.0

        # Build HTML table - matching original notebook exactly
        html = f"""
        <table style="border-collapse: collapse; width: 100%; margin: 5px 0; font-family: Arial, sans-serif; font-size: 12px; table-layout: fixed;">
        <thead>
            <tr style="background-color: #f2f2f2;">
                <th style="border: 1px solid #ddd; padding: 4px 2px; text-align: left; font-weight: bold; width: {status_col_width}%; overflow-wrap: anywhere; word-break: break-word; white-space: normal;">sequencing_status_{project_name.upper()}</th>
                <th style="border: 1px solid #ddd; padding: 4px 2px; text-align: center; font-weight: bold; width: {count_col_width}%;">duplication_count</th>
                <th style="border: 1px solid #ddd; padding: 4px 2px; text-align: center; font-weight: bold; width: {overlap_col_width}%;">overlap_sum</th>"""
        
        # Add project column headers
        for project in project_columns:
            html += f"""
                <th style=\"border: 1px solid #ddd; padding: 4px 2px; text-align: center; font-weight: bold; width: {project_col_width:.2f}%; overflow-wrap: anywhere; word-break: break-word; white-space: normal; font-size: 11px;\">{project.upper()}</th>"""

        html += """
            </tr>
        </thead>
        <tbody>"""

        # Add data rows (include ALL statuses, including not_started)
        for status in status_order:
            if status not in matrix:
                continue
            
            # Filter statuses if specified
            if filter_statuses is not None and status not in filter_statuses:
                continue
                
            status_data = matrix.get(status, {})
            original_count = original_counts.get(status, 0)

            # Compute raw overlap sum as the sum of project contributions in this row
            overlap_sum = sum(v for v in status_data.values() if isinstance(v, int))

            display_status = status

            html += f"""
            <tr>
                <td style=\"border: 1px solid #ddd; padding: 4px 2px; text-align: left;\">{display_status}</td>
                <td style=\"border: 1px solid #ddd; padding: 4px 2px; text-align: center; font-weight: bold;\">{original_count}</td>
                <td style=\"border: 1px solid #ddd; padding: 4px 2px; text-align: center; font-weight: bold;\">{overlap_sum}</td>"""

            for project in project_columns:
                count = status_data.get(project, 0)
                cell_text = (str(count) if count > 0 else '-')
                html += f"""
                <td style=\"border: 1px solid #ddd; padding: 4px 2px; text-align: center;\">{cell_text}</td>"""

            html += "</tr>"

        html += """
        </tbody>
        </table>"""

        # Add note under the table
        html += (
            "<div style=\"text-align: left; font-style: italic; font-size: 11px; margin-top: 4px;\">"
            "*see below for sequencing status description"
            "</div>"
        )

        return html
        
    except Exception as e:
        log_message(f"Error formatting project matrix table: {e}")
        return "<p>Error generating project matrix table</p>"


# =============================================================================
# URL GENERATION FUNCTIONS
# =============================================================================

def create_table_url_1(project_name):
    """
    Create the GoaT report URL for viewing species with an EBP standard assembly available in INSDC
    """
    try:
        project_encoded, bioproject = get_project_info(project_name)

        # URL encode the query parameters
        query_param = quote(
            f"long_list={project_encoded} AND "
            f"ebp_standard_date AND "
            f"bioproject!={bioproject} AND "
            f"tax_rank(species)"
        )
        fields_param = COMMON_FIELDS_PARAM     

        y_param = quote(f"long_list={project_encoded}")

        # Construct the report URL with updated parameters
        table_url = (
            "https://goat.genomehubs.org/search?"
            f"query={query_param}&"
            f"result=taxon&"
            f"includeEstimates=true&"
            f"taxonomy=ncbi&"
            f"size=10&"
            f"fields={fields_param}&"
            f"report=arc&"
            f"cat=sequencing_status_{project_encoded}&"
            f"collapseMonotypic=true&"
            f"treeStyle=rect&"
            f"treeThreshold=5000&"
            f"pointSize=15&"
            f"offset=0&"
            f"y={y_param}&"
            f"rank=species&"
            f"names=&"
            f"ranks=&"
            f"sortBy=sequencing_status_{project_encoded}&"
            f"sortOrder=desc&"
            f"xOpts=;;1;;"
            f"#long_list={project_encoded} AND ebp_standard_date AND bioproject!={bioproject} AND tax_rank(species)"
        )
        
        return table_url
        
    except Exception as e:
        raise ValueError(f"Error creating sequenced report URL for {project_name}: {str(e)}")


def create_table_url_2(project_name):
    """
    Create the GoaT report URL for viewing species in progress by other projects
    """
    try:
        project_encoded, bioproject = get_project_info(project_name)
            
        # URL encode the query parameters
        query_param = quote(
            f"sequencing_status_{project_encoded}>=sample_collected AND "
            f"length(sample_collected)>1 AND "
            f"bioproject=null,!{bioproject} AND "
            f"ebp_standard_date=null AND "
            f"tax_rank(species)"
        )        
        fields_param = COMMON_FIELDS_PARAM

        y_param = quote(f"sequencing_status_{project_encoded}>=sample_collected")

        # Construct the report URL with updated parameters
        table_url = (
            "https://goat.genomehubs.org/search?"
            f"query={query_param}&"
            f"result=taxon&"
            f"includeEstimates=true&"
            f"taxonomy=ncbi&"
            f"size=10&"
            f"fields={fields_param}&"
            f"report=arc&"
            f"cat=sequencing_status_{project_encoded}&"
            f"collapseMonotypic=true&"
            f"treeStyle=rect&"
            f"treeThreshold=5000&"
            f"pointSize=15&"
            f"offset=0&"
            f"y={y_param}&"
            f"rank=species&"
            f"names=&"
            f"ranks=&"
            f"sortBy=sequencing_status_{project_encoded}&"
            f"sortOrder=desc&"
            f"xOpts=;;1;;"
            f"#sequencing_status_{project_encoded}>=sample_collected AND length(sample_collected)>1 AND bioproject=null,!{bioproject} AND ebp_standard_date=null AND tax_rank(species)"
        )
        
        return table_url
        
    except Exception as e:
        raise ValueError(f"Error creating report URL for {project_name}: {str(e)}")


def create_table_url_3(project_name):
    """
    Create the GoaT report URL for viewing species in progress by other EBP affiliates but not_started by the project
    """
    try:
        project_encoded, bioproject = get_project_info(project_name)
            
        # URL encode the query parameters
        query_param = quote(
            f"long_list={project_encoded} AND "
            f"sequencing_status_{project_encoded}=null AND "
            f"length(sample_collected)>=1 AND "
            f"bioproject=!{bioproject},null AND "
            f"ebp_standard_date=null AND "
            f"tax_rank(species)"
        )
        
        fields_param = COMMON_FIELDS_PARAM
        
        y_param = quote(f"long_list={project_encoded}")

        # Construct the report URL with updated parameters
        table_url = (
            "https://goat.genomehubs.org/search?"
            f"query={query_param}&"
            f"result=taxon&"
            f"includeEstimates=true&"
            f"taxonomy=ncbi&"
            f"size=10&"
            f"fields={fields_param}&"
            f"report=arc&"
            f"cat=sequencing_status_{project_encoded}&"
            f"collapseMonotypic=true&"
            f"treeStyle=rect&"
            f"treeThreshold=5000&"
            f"pointSize=15&"
            f"y={y_param}&"
            f"rank=species"
        )
        
        return table_url
        
    except Exception as e:
        raise ValueError(f"Error creating EBP report URL for {project_name}: {str(e)}")


# =============================================================================
# SPECIES COUNT FUNCTIONS
# =============================================================================

def get_species_count_1(project_name):
    """
    Get count of species with an EBP standard assembly available in INSDC
    Returns tuple of (sequenced_count, total_count)
    """
    try:
        project_encoded = project_name.lower()
        bioproject = get_bioproject_id(project_name)
        if not bioproject:
            raise ValueError(f"No bioproject ID found for {project_name}")

        # Query for numerator (species with EBP standard assemblies)
        numerator_params = quote(
            f"long_list={project_encoded} AND "
            f"ebp_standard_date AND "
            f"bioproject!={bioproject} AND "
            f"tax_rank(species)"
        )

        # Query for denominator (total species in target list)
        denominator_params = quote(
            f"long_list={project_encoded} AND "
            f"tax_rank(species)"
        )

        fields_param = quote(f"long_list,ebp_standard_date,bioproject")

        # Make request for numerator
        numerator_query = (
            "https://goat.genomehubs.org/api/v2/search?"
            f"result=taxon&"
            f"query={numerator_params}&"
            f"taxonomy=ncbi&"
            f"includeEstimates=true&"
            f"fields={fields_param}&"
            f"report=arc&"
            f"summaryValues=count&"
            f"offset=0"
        )
        
        # Make request for denominator
        denominator_query = (
            "https://goat.genomehubs.org/api/v2/search?"
            f"result=taxon&"
            f"query={denominator_params}&"
            f"taxonomy=ncbi&"
            f"includeEstimates=true&"
            f"fields={fields_param}&"
            f"report=arc&"
            f"summaryValues=count&"
            f"offset=0"
        )

        # Get both counts
        numerator_response = requests.get(numerator_query, timeout=10)
        denominator_response = requests.get(denominator_query, timeout=10)
        
        numerator_response.raise_for_status()
        denominator_response.raise_for_status()

        numerator_data = numerator_response.json()
        denominator_data = denominator_response.json()
        
        # Get counts from responses
        numerator = numerator_data['status']['hits'] if 'status' in numerator_data and 'hits' in numerator_data['status'] else 0
        denominator = denominator_data['status']['hits'] if 'status' in denominator_data and 'hits' in denominator_data['status'] else 0
            
        return (numerator, denominator)

    except Exception as e:
        raise ValueError(f"Error getting sequenced species count for {project_name}: {e}")


# =============================================================================
# TABLE DATA FUNCTIONS
# =============================================================================

def get_table_data_from_report_1(project_name):
    """
    Extract pre-aggregated table data from the GoaT report URL
    Returns a list of tuples (status, count) that can be formatted for email display
    """
    try:
        project_encoded, bioproject = get_project_info(project_name)
        
        # Get the total species count from get_species_count_1
        numerator, _ = get_species_count_1(project_name)
        
        # Construct the report URL with report=table
        query_param = quote(
            f"long_list={project_encoded} AND "
            f"ebp_standard_date AND "
            f"bioproject!={bioproject} AND "
            f"tax_rank(species)"
        )
        
        fields_param = COMMON_FIELDS_PARAM
        y_param = quote(f"long_list={project_encoded}")
        
        # Use the API endpoint
        table_url = (
            "https://goat.genomehubs.org/api/v2/search?"
            f"query={query_param}&"
            f"result=taxon&"
            f"includeEstimates=true&"
            f"taxonomy=ncbi&"
            f"fields={fields_param}&"
            f"report=table&"
            f"cat=sequencing_status_{project_encoded}&"
            f"y={y_param}&"
            f"rank=species"
        )
        
        # Log the query for debugging
        log_message(f"Table report URL for {project_name}: {table_url}")
        
        # Make request to get the table data
        response = requests.get(table_url, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        # Process the table data
        table_rows = []
        
        # Add header with proper column names
        table_rows.append((f"sequencing_status_{project_encoded.upper()}", "count"))
        
        # Define the desired order of statuses
        status_order = [
            "sample_collected",
            "sample_acquired",
            "data_generation",
            "in_assembly",
            "in_progress",
            "open",
            "insdc_open",
            "published"
        ]
        
        # Process the table data from the response
        if 'aggs' in data and 'fields' in data['aggs']:
            fields = data['aggs']['fields']
            if 'by_key' in fields and 'buckets' in fields['by_key']:
                status_key = f"sequencing_status_{project_encoded.lower()}"
                if status_key in fields['by_key']['buckets']:
                    bucket = fields['by_key']['buckets'][status_key]
                    if 'value_list' in bucket and 'buckets' in bucket['value_list']:
                        # Create a dictionary of status counts
                        status_counts = {}
                        total_count = 0
                        
                        # First get all status counts and calculate total
                        for status_bucket in bucket['value_list']['buckets']:
                            status = status_bucket['key']
                            count = status_bucket['doc_count']
                            if status: 
                                status_counts[status] = count
                                total_count += count

                        # Calculate not_started count and add it to status_counts
                        not_started_count = numerator - total_count

                        # Add not_started count at the end
                        table_rows.append(("not_started", str(not_started_count)))

                        # Add rows in the specified order
                        for status in status_order:
                            count = status_counts.get(status, 0)
                            table_rows.append((status, str(count)))
       
                        # Log the final table rows
                        log_message(f"Extracted table rows: {table_rows}")
        
                        return table_rows
        
    except Exception as e:
        log_message(f"Error extracting table data from report for {project_name}: {e}")
        raise


def get_table_data_from_report_2(project_name):
    """
    Extract pre-aggregated table data from the GoaT report URL for report 2
    Returns a list of tuples (status, count) that can be formatted for email display
    """
    try:
        project_encoded, bioproject = get_project_info(project_name)
        
        # Construct the report URL with report=table
        query_param = quote(
            f"sequencing_status_{project_encoded}>=sample_collected AND "
            f"length(sample_collected)>1 AND "
            f"bioproject=null,!{bioproject} AND "
            f"ebp_standard_date=null AND "
            f"tax_rank(species)"
        )
        
        fields_param = COMMON_FIELDS_PARAM
        y_param = quote(f"sequencing_status_{project_encoded}>=sample_collected")
        
        # Use the API endpoint
        table_url = (
            "https://goat.genomehubs.org/api/v2/search?"
            f"query={query_param}&"
            f"result=taxon&"
            f"includeEstimates=true&"
            f"taxonomy=ncbi&"
            f"fields={fields_param}&"
            f"report=table&"
            f"cat=sequencing_status_{project_encoded}&"
            f"y={y_param}&"
            f"rank=species"
        )
        
        # Log the query for debugging
        log_message(f"Table report URL for {project_name} (report 2): {table_url}")
        
        # Make request to get the table data
        response = requests.get(table_url, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        # Process the table data
        table_rows = []
        
        # Add header with proper column names
        table_rows.append((f"sequencing_status_{project_encoded.upper()}", "count"))
        
        # Define the desired order of statuses
        status_order = [
            "sample_collected",
            "sample_acquired",
            "data_generation",
            "in_assembly",
            "in_progress",
            "open",
            "insdc_open",
            "published"
        ]
        
        # Process the table data from the response
        if 'aggs' in data and 'fields' in data['aggs']:
            fields = data['aggs']['fields']
            if 'by_key' in fields and 'buckets' in fields['by_key']:
                status_key = f"sequencing_status_{project_encoded.lower()}"
                if status_key in fields['by_key']['buckets']:
                    bucket = fields['by_key']['buckets'][status_key]
                    if 'value_list' in bucket and 'buckets' in bucket['value_list']:
                        # Create a dictionary of status counts
                        status_counts = {}
                        total_count = 0
                        
                        # Get all status counts
                        for status_bucket in bucket['value_list']['buckets']:
                            status = status_bucket['key']
                            count = status_bucket['doc_count']
                            if status:  # Only add rows with a status
                                status_counts[status] = count
                        
                        # Keep data_generation, in_assembly, and in_progress as separate statuses
                        
                        # Add not_started row with calculated count
                        not_started_count = 0
                        table_rows.append(("not_started", str(not_started_count)))
        
                        # Add rows in the specified order
                        for status in status_order:
                            count = status_counts.get(status, 0)
                            table_rows.append((status, str(count)))
                        
        # Log the final table rows
        log_message(f"Extracted table rows for report 2: {table_rows}")
        
        return table_rows
        
    except Exception as e:
        log_message(f"Error extracting table data from report 2 for {project_name}: {e}")
        raise


def get_table_data_from_report_3(project_name):
    """
    Extract pre-aggregated table data from the GoaT report URL for report 3
    Returns a list of tuples (status, count) that can be formatted for email display
    """
    try:
        project_encoded, bioproject = get_project_info(project_name)
        
        # Construct the report URL with report=table
        query_param = quote(
            f"long_list={project_encoded} AND "
            f"sequencing_status_{project_encoded}=null AND "
            f"length(sample_collected)>=1 AND "
            f"bioproject=!{bioproject},null AND "
            f"ebp_standard_date=null AND "
            f"tax_rank(species)"
        )
        
        fields_param = COMMON_FIELDS_PARAM
        y_param = quote(f"long_list={project_encoded}")
        
        # Use the API endpoint
        table_url = (
            "https://goat.genomehubs.org/api/v2/search?"
            f"query={query_param}&"
            f"result=taxon&"
            f"includeEstimates=true&"
            f"taxonomy=ncbi&"
            f"fields={fields_param}&"
            f"report=table&"
            f"cat=sequencing_status_{project_encoded}&"
            f"y={y_param}&"
            f"rank=species"
        )
        
        # Log the query for debugging
        log_message(f"Table report URL for {project_name} (report 3): {table_url}")
        
        # Make request to get the table data
        response = requests.get(table_url, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        # Process the table data
        table_rows = []
        
        # Add header with proper column names
        table_rows.append((f"sequencing_status_{project_encoded.upper()}", "count"))
        
        # Get the total count from the response
        # For Report 3, only include not_started row since other statuses are not applicable
        if 'status' in data and 'hits' in data['status']:
            total_count = data['status']['hits']
            table_rows.append(('not_started', str(total_count)))
        
        # Log the final table rows
        log_message(f"Extracted table rows for report 3: {table_rows}")
        
        return table_rows
        
    except Exception as e:
        log_message(f"Error extracting table data from report 3 for {project_name}: {e}")
        raise


# =============================================================================
# MAIN EXECUTION FUNCTIONS
# =============================================================================

def save_email_to_file(project_name, email_content, output_dir):
    """Save email content to HTML file in saved_emails subfolder"""
    try:
        # Create saved_emails subfolder
        saved_emails_dir = os.path.join(output_dir, "saved_emails")
        os.makedirs(saved_emails_dir, exist_ok=True)
        
        # Use the project_name directly as filename (already formatted with underscores)
        filename = f"{project_name}.html"
        filepath = os.path.join(saved_emails_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(email_content)
        
        log_message(f"📁 Email saved to: {filepath}")
        return filepath
        
    except Exception as e:
        log_message(f"Error saving email for {project_name}: {e}")
        return None


def test_gmail_authentication():
    """Test Gmail authentication before running the main system"""
    try:
        log_message("🔐 Testing Gmail authentication...")
        service = authenticate_gmail()
        if service:
            log_message("✅ Gmail authentication successful")
            return True
        else:
            log_message("❌ Gmail authentication failed")
            return False
    except Exception as e:
        log_message(f"❌ Gmail authentication error: {e}")
        return False


def main():
    """Main execution function for the duplication alert system"""
    try:
        log_message("🚀 Starting EBP Duplication Alert System")
        log_message(f"📅 Processing date: {TODAY}")
        
        # Test Gmail authentication first
        gmail_ok = test_gmail_authentication()
        if not gmail_ok:
            log_message("⚠️ Gmail authentication failed - emails will not be sent")
        
        # Load project data
        projects_df = load_projects_data(INPUT_FILE)
        log_message(f"📊 Loaded {len(projects_df)} projects from {INPUT_FILE}")
        
        # Debug: Show the loaded data
        log_message(f"🔍 Project data columns: {list(projects_df.columns)}")
        log_message(f"🔍 First few rows:")
        for idx, row in projects_df.head().iterrows():
            log_message(f"   Row {idx}: {dict(row)}")
        
        # Process each project
        for index, project_row in projects_df.iterrows():
            try:
                project_name = str(project_row['goat_project'])
                contact_email_raw = str(project_row['contact_email'])
                contact_name_raw = str(project_row['contact_name'])
                
                # Skip if project name is invalid
                if (project_name.lower() in ['nan', 'none', ''] or 
                    contact_email_raw.lower() in ['nan', 'none', ''] or
                    project_name == 'nan' or contact_email_raw == 'nan'):
                    log_message(f"⚠️ Skipping invalid project data at row {index}: project='{project_name}', email='{contact_email_raw}'")
                    continue
                
                # Parse multiple recipients (comma-separated for both emails and names, no spaces)
                contact_emails = [email.strip() for email in contact_email_raw.split(',') if email.strip()]
                # Extract only the first word of each name
                contact_names = [name.strip().strip('"').split()[0] if name.strip().strip('"').split() else name.strip().strip('"') 
                                for name in contact_name_raw.split(',') if name.strip()]
                
                # Ensure we have matching emails and names
                if len(contact_names) != len(contact_emails):
                    # If names don't match emails, use generic names
                    contact_names = [f"Contact {i+1}" for i in range(len(contact_emails))]
                
                log_message(f"\n{'='*60}")
                log_message(f"📧 Processing project: {project_name}")
                log_message(f"📧 Recipients: {len(contact_emails)} contacts")
                for i, (email, name) in enumerate(zip(contact_emails, contact_names)):
                    log_message(f"   {i+1}. {name} <{email}>")
                
                # Send individual emails to each recipient
                for i, (contact_email, contact_name) in enumerate(zip(contact_emails, contact_names)):
                    try:
                        # Create a modified project row for this specific recipient
                        recipient_row = project_row.copy()
                        recipient_row['contact_email'] = contact_email
                        recipient_row['contact_name'] = contact_name
                        
                        # Create enhanced email content for this recipient
                        email_content = create_project_email_content_enhanced(recipient_row)
                        
                        # Save email to file (with recipient identifier if multiple)
                        email_subject = f"EBP Duplication Alert_{project_name}_{TODAY}"
                        if len(contact_emails) > 1:
                            email_file = save_email_to_file(f"EBP_Duplication_Alert_{project_name}_{TODAY}_recipient_{i+1}", email_content, OUTPUT_DIR)
                        else:
                            email_file = save_email_to_file(f"EBP_Duplication_Alert_{project_name}_{TODAY}", email_content, OUTPUT_DIR)
                        
                        # Send email (only if Gmail authentication was successful)
                        if gmail_ok:
                            try:
                                # Optional CC emails 
                                cc_emails = []  # No CC emails for now
                                #cc_emails = ['Harris.Lewin@asu.edu', 'fang.chen.2@asu.edu']
                                
                                send_email_with_gmail_api(
                                    subject=email_subject,
                                    body_html=email_content,
                                    recipient_emails=[contact_email],
                                    cc_emails=cc_emails
                                )
                                log_message(f"📧 Email sent successfully to {contact_name} <{contact_email}>")
                            except Exception as email_error:
                                log_message(f"❌ Failed to send email to {contact_name} <{contact_email}>: {email_error}")
                        else:
                            log_message(f"📧 Email not sent (Gmail authentication failed) - saved to file only")
                            
                    except Exception as recipient_error:
                        log_message(f"❌ Error processing recipient {contact_name} <{contact_email}>: {recipient_error}")
                        continue
                
                log_message(f"✅ Successfully processed {project_name} ({len(contact_emails)} recipients)")
                
            except Exception as e:
                log_message(f"❌ Error processing {project_name}: {e}")
                continue
        
        log_message(f"\n🎉 Duplication alert system completed successfully!")
        log_message(f"📁 All emails saved to: {OUTPUT_DIR}")
        
    except Exception as e:
        log_message(f"❌ Fatal error in main execution: {e}")
        import traceback
        traceback.print_exc()


# =============================================================================
# TESTING FUNCTIONS
# =============================================================================

def test_enhanced_analysis():
    """Test the enhanced analysis functions"""
    try:
        log_message("🧪 Testing enhanced analysis functions")
        
        # Test with a sample project
        test_project = "ERGA-CH"
        
        # Test Report 1
        matrix_1 = get_project_matrix_for_report_1_enhanced(test_project)
        if matrix_1:
            log_message(f"✅ Report 1 test passed: {len(matrix_1.get('project_columns', []))} projects found")
        else:
            log_message("❌ Report 1 test failed")
        
        # Test Report 2
        matrix_2 = get_project_matrix_for_report_2_enhanced(test_project)
        if matrix_2:
            log_message(f"✅ Report 2 test passed: {len(matrix_2.get('project_columns', []))} projects found")
        else:
            log_message("❌ Report 2 test failed")
        
        # Test Report 3
        matrix_3 = get_project_matrix_for_report_3_enhanced(test_project)
        if matrix_3:
            log_message(f"✅ Report 3 test passed: {len(matrix_3.get('project_columns', []))} projects found")
        else:
            log_message("❌ Report 3 test failed")
        
        log_message("🎉 Enhanced analysis testing completed")
        
    except Exception as e:
        log_message(f"❌ Error in enhanced analysis testing: {e}")


def test_table_styling():
    """Test the updated table styling to ensure headers don't wrap"""
    
    # Create a sample matrix with many projects to test column width
    test_matrix = {
        'status_order': ['not_started', 'sample_collected', 'in_progress', 'published'],
        'project_columns': ['PSYCHE', 'PHYLOALPS', 'B10K', 'ATLASEA', 'VGP', 'ERGA-PIL', 'CANBP', 'ASG', 'AG100PEST', 'ERGA-BGE', 'CBP', 'EBPN', 'I5K', 'BEENOME100', 'PGP', 'CCGP', 'BAT1K', 'METAINVERT', 'GAGA', '1KFG', 'LOEWE-TBG', 'ZOONOMIA'],
        'matrix': {
            'not_started': {'PSYCHE': 0, 'PHYLOALPS': 0, 'B10K': 0},
            'sample_collected': {'PSYCHE': 5, 'PHYLOALPS': 3, 'B10K': 2},
            'in_progress': {'PSYCHE': 2, 'PHYLOALPS': 1, 'B10K': 4},
            'published': {'PSYCHE': 1, 'PHYLOALPS': 0, 'B10K': 1}
        },
        'original_counts': {
            'not_started': 847,
            'sample_collected': 10,
            'in_progress': 7,
            'published': 2
        }
    }
    
    # Generate HTML table
    html_table = format_project_matrix_table(test_matrix, "TEST")
    
    # Save to file for inspection
    test_file = "test_table_styling.html"
    with open(test_file, 'w', encoding='utf-8') as f:
        f.write(f"<html><body><h2>Table Styling Test - {len(test_matrix['project_columns'])} Projects</h2>{html_table}</body></html>")
    
    log_message(f"🧪 Table styling test completed - saved to {test_file}")
    log_message(f"📊 Tested with {len(test_matrix['project_columns'])} project columns")


# =============================================================================
# EXECUTION
# =============================================================================

if __name__ == "__main__":
    main()
