# EBP Duplication Alert System

Automated notification system for detecting and reporting species duplication across Earth BioGenome Project (EBP) projects in the GoaT (Genome of All Types) database.

## Overview

The system analyzes project data from GoaT, identifies species overlaps across EBP-affiliated projects, and sends automated email notifications to project representatives with detailed duplication reports. Each report includes three types of analyses:

1. **Report #1**: Species with EBP-standard assemblies available
2. **Report #2**: Active duplications with non-standard assemblies
3. **Report #3**: Potential duplications (not started by target project)

## Architecture

- **`notification_streamlined.ipynb`**: Execution and testing interface (Jupyter notebook)
- **`duplication_analysis.py`**: Business logic for matrix analysis, report generation, and email creation
- **`notification_utils.py`**: Utility functions for Gmail API authentication, data loading, and HTML formatting
- **`projectsMap.py`**: Project name to NCBI Bioproject ID mapping dictionary
- **`validate_tsv.py`**: TSV input file validator

## Prerequisites

- Python 3.x
- Required packages:
  - `google-auth-oauthlib`
  - `google-api-python-client`
  - `pandas`
  - `requests`
- Gmail API credentials (`credentials.json` and `token.json`)
- Input TSV file with project information (columns: `goat_project`, `sequencing_status`, `contact_email`, `contact_name`)

## Usage

Execute all cells in `notification_streamlined.ipynb` to run the complete duplication alert system. The notebook imports and orchestrates all components including `duplication_analysis.py` and `notification_utils.py`.

## Configuration

- **Input File**: Modify `INPUT_FILE` in `duplication_analysis.py` (default: `GoaT_Projects_Test.tsv`)
- **CC Emails**: Uncomment and modify `cc_emails` list in `duplication_analysis.py` main() function
- **Output Directory**: All outputs saved to `./output_files/` (emails, logs)

## Output

- **Email Reports**: HTML emails sent to project contacts via Gmail API
- **Saved Emails**: HTML copies archived in `./output_files/saved_emails/`
- **Processing Logs**: Detailed logs in `./output_files/Overlaps_GoaT_Projects_[DATE].txt`

## Important Notes

- Projects without bioproject IDs will be skipped (no email sent)
- Multiple recipients per project are supported (comma-separated in TSV)
- TSV validation available via `python validate_tsv.py [filename]`

## System Flow

1. Load and validate project data from TSV
2. For each project, query GoaT API for duplication data
3. Generate three reports with enhanced matrix analysis
4. Create HTML email content with formatted tables
5. Send notifications via Gmail API
6. Log all processing steps and results

