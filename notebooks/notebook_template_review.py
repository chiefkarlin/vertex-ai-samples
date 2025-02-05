
import argparse
import json
import os
import sys
import urllib.request
import csv

parser = argparse.ArgumentParser()
parser.add_argument('--notebook-dir', dest='notebook_dir',
                    default=None, type=str, help='Notebook directory')
parser.add_argument('--notebook', dest='notebook',
                    default=None, type=str, help='Notebook to review')
parser.add_argument('--notebook-file', dest='notebook_file',
                    default=None, type=str, help='File with list of notebooks to review')
parser.add_argument('--errors', dest='errors', action='store_true', 
                    default=False, help='Report errors')
parser.add_argument('--errors-csv', dest='errors_csv', action='store_true', 
                    default=False, help='Report errors as CSV')
parser.add_argument('--errors-codes', dest='errors_codes',
                    default=None, type=str, help='Report only specified errors')
parser.add_argument('--title', dest='title', action='store_true',
                    default=False, help='Output description')
parser.add_argument('--desc', dest='desc', action='store_true', 
                    default=False, help='Output description')
parser.add_argument('--uses', dest='uses', action='store_true', 
                    default=False, help='Output uses (resources)')
parser.add_argument('--steps', dest='steps', action='store_true', 
                    default=False, help='Ouput steps')
parser.add_argument('--web', dest='web', action='store_true', 
                    default=False, help='Output format in HTML')
parser.add_argument('--repo', dest='repo', action='store_true', 
                    default=False, help='Output format in Markdown')
args = parser.parse_args()

if args.errors_codes:
    args.errors_codes = args.errors_codes.split(',')
    args.errors = True

if args.errors_csv:
    args.errors = True

# Copyright cell
ERROR_COPYRIGHT = 0

# Links cell
ERROR_TITLE_HEADING = 1
ERROR_HEADING_CASE = 2
ERROR_HEADING_CAP = 3
ERROR_LINK_GIT_MISSING = 4
ERROR_LINK_COLAB_MISSING = 5
ERROR_LINK_WORKBENCH_MISSING = 6
ERROR_LINK_GIT_BAD = 7
ERROR_LINK_COLAB_BAD = 8
ERROR_LINK_WORKBENCH_BAD = 9

# globals
num_errors = 0
last_tag = ''

def parse_dir(directory):
    entries = os.scandir(directory)
    for entry in entries:
        if entry.is_dir():
            if entry.name[0] == '.':
                continue
            if entry.name == 'src' or entry.name == 'images' or entry.name == 'sample_data':
                continue
            print("\n##", entry.name, "\n")
            parse_dir(entry.path)
        elif entry.name.endswith('.ipynb'):
            parse_notebook(entry.path)

def parse_notebook(path):
    with open(path, 'r') as f:
        try:
            content = json.load(f)
        except:
            print("Corrupted notebook:", path)
            return
        
        cells = content['cells']
        
        # cell 1 is copyright
        nth = 0
        cell, nth = get_cell(path, cells, nth)
        if not 'Copyright' in cell['source'][0]:
            report_error(path, ERROR_COPYRIGHT, "missing copyright cell")
            
        # check for notices
        cell, nth = get_cell(path, cells, nth)
        if cell['source'][0].startswith('This notebook'):
            cell, nth = get_cell(path, cells, nth)
            
        # cell 2 is title and links
        if not cell['source'][0].startswith('# '):
            report_error(path, ERROR_TITLE_HEADING, "title cell must start with H1 heading")
            title = ''
        else:
            title = cell['source'][0][2:].strip()
            check_sentence_case(path, title)
            
            # H1 title only
            if len(cell['source']) == 1:
                cell, nth = get_cell(path, cells, nth)
           
        # check links.
        source = ''
        git_link = None
        colab_link = None
        workbench_link = None
        for line in cell['source']:
            source += line
            if '<a href="https://github.com' in line:
                git_link = line.strip()[9:-2].replace('" target="_blank', '')
                try:
                    code = urllib.request.urlopen(git_link).getcode()
                except Exception as e:
                    # if new notebook
                    derived_link = os.path.join('https://github.com/GoogleCloudPlatform/vertex-ai-samples/blob/main/notebooks/', path)
                    if git_link != derived_link:
                        report_error(path, ERROR_LINK_GIT_BAD, f"bad GitHub link: {git_link}")
                    
            if '<a href="https://colab.research.google.com/' in line:
                colab_link = 'https://github.com/' + line.strip()[50:-2].replace('" target="_blank', '')
                try:
                    code = urllib.request.urlopen(colab_link).getcode()
                except Exception as e:
                    # if new notebook
                    derived_link = os.path.join('https://colab.research.google.com/github/GoogleCloudPlatform/vertex-ai-samples/blob/main/notebooks', path)
                    if colab_link != derived_link:
                        report_error(path, ERROR_LINK_COLAB_BAD, f"bad Colab link: {colab_link}")
                    

            if '<a href="https://console.cloud.google.com/vertex-ai/workbench/' in line:
                workbench_link = line.strip()[91:-2].replace('" target="_blank', '')
                try:
                    code = urllib.request.urlopen(workbench_link).getcode()
                except Exception as e:
                    derived_link = os.path.join('https://console.cloud.google.com/vertex-ai/workbench/deploy-notebook?download_url=https://raw.githubusercontent.com/GoogleCloudPlatform/vertex-ai-samples/main/notebooks/', path)
                    if colab_link != workbench_link:
                        report_error(path, ERROR_LINK_WORKBENCH_BAD, f"bad Workbench link: {workbench_link}")

        if 'View on GitHub' not in source or not git_link:
            report_error(path, ERROR_LINK_GIT_MISSING, 'Missing link for GitHub')
        if 'Run in Colab' not in source or not colab_link:
            report_error(path, ERROR_LINK_COLAB_MISSING, 'Missing link for Colab')    
        if 'Open in Vertex AI Workbench' not in source or not workbench_link:
            report_error(path, ERROR_LINK_WORKBENCH_MISSING, 'Missing link for Workbench')
            
        # Overview
        cell, nth = get_cell(path, cells, nth)
        if not cell['source'][0].startswith("## Overview"):
            report_error(path, 11, "Overview section not found")
            
        # Objective
        cell, nth = get_cell(path, cells, nth)
        if not cell['source'][0].startswith("### Objective"):
            report_error(path, 12, "Objective section not found")
            costs = []
        else:
            desc, uses, steps, costs = parse_objective(path, cell)
            add_index(path, tag, title, desc, uses, steps, git_link, colab_link, workbench_link)
            
        # (optional) Recommendation
        cell, nth = get_cell(path, cells, nth)
        if cell['source'][0].startswith("### Recommendations"):
            cell, nth = get_cell(path, cells, nth)
            
        # Dataset
        if not cell['source'][0].startswith("### Dataset") and not cell['source'][0].startswith("### Model") and not cell['source'][0].startswith("### Embedding"):
            report_error(path, 13, "Dataset/Model section not found")
            
        # Costs
        cell, nth = get_cell(path, cells, nth)
        if not cell['source'][0].startswith("### Costs"):
            report_error(path, 14, "Costs section not found")
        else:
            text = ''
            for line in cell['source']:
                text += line
            if 'BQ' in costs and 'BigQuery' not in text:
                report_error(path, 20, 'Costs section missing reference to BiqQuery')
            if 'Vertex' in costs and 'Vertex' not in text:
                report_error(path, 20, 'Costs section missing reference to Vertex')
            if 'Dataflow' in costs and 'Dataflow' not in text:    
                report_error(path, 20, 'Costs section missing reference to Dataflow')
                
        # (optional) Setup local environment
        cell, nth = get_cell(path, cells, nth)
        if cell['source'][0].startswith('### Set up your local development environment'):
            cell, nth = get_cell(path, cells, nth)
            if cell['source'][0].startswith('**Otherwise**, make sure your environment meets'):
                cell, nth = get_cell(path, cells, nth)
                
        # (optional) Helper functions
        if 'helper' in cell['source'][0]:
            cell, nth = get_cell(path, cells, nth)
            cell, nth = get_cell(path, cells, nth)
                
        # Installation
        if not cell['source'][0].startswith("## Install"):
            if cell['source'][0].startswith("### Install"):
                report_error(path, 27, "Installation section needs to be H2 heading")
            else:
                report_error(path, 21, "Installation section not found")
        else:
            cell, nth = get_cell(path, cells, nth)
            if cell['cell_type'] != 'code':
                report_error(path, 22, "Installation code section not found")
            else:
                if cell['source'][0].startswith('! mkdir'):
                    cell, nth = get_cell(path, cells, nth)
                if 'requirements.txt' in cell['source'][0]:
                    cell, nth = get_cell(path, cells, nth)
                    
                text = ''
                for line in cell['source']:
                    text += line
                    if 'pip ' in line:
                        if 'pip3' not in line:
                            report_error(path, 23, "Installation code section: use pip3")
                        if line.endswith('\\\n'):
                            continue
                        if '-q' not in line:
                            report_error(path, 23, "Installation code section: use -q with pip3")
                        if 'USER_FLAG' not in line and 'sh(' not in line:
                            report_error(path, 23, "Installation code section: use {USER_FLAG} with pip3")
                if 'if IS_WORKBENCH_NOTEBOOK:' not in text:
                    report_error(path, 24, "Installation code section out of date (see template)")
            
        # Restart kernel
        while True:
            cont = False
            cell, nth = get_cell(path, cells, nth)
            for line in cell['source']:
                if 'pip' in line:
                    report_error(path, 25, f"All pip installations must be in a single code cell: {line}")
                    cont = True
                    break
            if not cont:
                break
           
        if not cell['source'][0].startswith("### Restart the kernel"):
            report_error(path, 26, "Restart the kernel section not found")
        else:
            cell, nth = get_cell(path, cells, nth) # code cell
            if cell['cell_type'] != 'code':
                report_error(path, 28, "Restart the kernel code section not found")
                
        # (optional) Check package versions
        cell, nth = get_cell(path, cells, nth)
        if cell['source'][0].startswith('#### Check package versions'):
            cell, nth = get_cell(path, cells, nth) # code cell
            cell, nth = get_cell(path, cells, nth) # next text cell
            
        # Before you begin
        if not cell['source'][0].startswith("## Before you begin"):
            report_error(path, 29, "Before you begin section not found")
        else:
            # maybe one or two cells
            if len(cell['source']) < 2:
                cell, nth = get_cell(path, cells, nth)
                if not cell['source'][0].startswith("### Set up your Google Cloud project"):
                    report_error(path, 30, "Before you begin section incomplete")
              
        # (optional) enable APIs
        cell, nth = get_cell(path, cells, nth)
        if cell['source'][0].startswith("### Enable APIs"):
            cell, nth = get_cell(path, cells, nth) # code cell
            cell, nth = get_cell(path, cells, nth) # next text cell
            
        # Set project ID
        if not cell['source'][0].startswith('#### Set your project ID'):
            report_error(path, 31, "Set project ID section not found")
        else: 
            cell, nth = get_cell(path, cells, nth)
            if cell['cell_type'] != 'code':
                report_error(path, 32, "Set project ID code section not found")
            elif not cell['source'][0].startswith('PROJECT_ID = "[your-project-id]"'):
                report_error(path, 33, f"Set project ID not match template: {line}")
            
            cell, nth = get_cell(path, cells, nth)
            if cell['cell_type'] != 'code' or 'or PROJECT_ID == "[your-project-id]":' not in cell['source'][0]:
                report_error(path, 33, f"Set project ID not match template: {line}")  
            
            cell, nth = get_cell(path, cells, nth)
            if cell['cell_type'] != 'code' or '! gcloud config set project' not in cell['source'][0]:
                report_error(path, 33, f"Set project ID not match template: {line}")   
            
        '''
        # Region
        cell, nth = get_cell(path, cells, nth)
        if cell['source'][0].startswith("### Region"): 
            report_error(path, 34, "Region section not found")
        '''


def get_cell(path, cells, nth):
    while empty_cell(path, cells, nth):
        nth += 1
        
    cell = cells[nth]
    if cell['cell_type'] == 'markdown':
        check_text_cell(path, cell)
    return cell, nth + 1


def empty_cell(path, cells, nth):
    if len(cells[nth]['source']) == 0:
        report_error(path, 10, f'empty cell: cell #{nth}')
        return True
    else:
        return False

def check_text_cell(path, cell):
    
    branding = {
        'Vertex SDK': 'Vertex AI SDK',
        'Vertex Training': 'Vertex AI Training',
        'Vertex Prediction': 'Vertex AI Prediction',
        'Vertex Batch Prediction': 'Vertex AI Batch Prediction',
        'Vertex XAI': 'Vertex Explainable AI',
        'Vertex Explainability': 'Vertex Explainable AI',
        'Vertex AI Explainability': 'Vertex Explainable AI',
        'Vertex Pipelines': 'Vertex AI Pipelines',
        'Vertex Experiments': 'Vertex AI Experiments',
        'Vertex TensorBoard': 'Vertex AI TensorBoard',
        'Vertex Hyperparameter Tuning': 'Vertex AI Hyperparameter Tuning',
        'Vertex Metadata': 'Vertex ML Metadata',
        'Vertex AI Metadata': 'Vertex ML Metadata',
        'Vertex AI ML Metadata': 'Vertex ML Metadata',
        'Vertex Vizier': 'Vertex AI Vizier',
        'Vertex Feature Store': 'Vertex AI Feature Store',
        'Vertex Forecasting': 'Vertex AI Forecasting',
        'Vertex Matching Engine': 'Vertex AI Matching Engine',
        'Vertex TabNet': 'Vertex AI TabNet',
        'Tabnet': 'TabNet',
        'Vertex Two Towers': 'Vertex AI Two-Towers',
        'Vertex Two-Towers': 'Vertex AI Two-Towers',
        'Vertex Dataset': 'Vertex AI Dataset',
        'Vertex Model': 'Vertex AI Model',
        'Vertex Endpoint': 'Vertex AI Endpoint',
        'Vertex Private Endpoint': 'Vertex AI Private Endpoint',
        'Automl': 'AutoML',
        'AutoML Tables': 'AutoML Tabular',
        'AutoML Vision': 'AutoML Image',
        'AutoML Language': 'AutoML Text',
        'Tensorflow': 'TensorFlow',
        'Tensorboard': 'TensorBoard',
        'Google Cloud Notebooks': 'Vertex AI Workbench Notebooks',
        'BQ': 'BigQuery',
        'Bigquery': 'BigQuery',
        'BQML': 'BigQuery ML',
        'GCS': 'Cloud Storage',
        'Google Cloud Storage': 'Cloud Storage',
        'Pytorch': 'PyTorch',
        'Sklearn': 'scikit-learn',
        'sklearn': 'scikit-learn'
    }
    
    for line in cell['source']:
        if 'TODO' in line:
            report_error(path, 14, f'TODO in cell: {line}')
        if 'we ' in line.lower() or "let's" in line.lower() in line.lower():
            report_error(path, 15, f'Do not use first person (e.g., we), replace with 2nd person (you): {line}')
        if 'will' in line.lower() or 'would' in line.lower():
            report_error(path, 16, f'Do not use future tense (e.g., will), replace with present tense: {line}')
            
        for mistake, brand in branding.items():
            if mistake in line:
                report_error(path, 27, f"Branding {brand}: {line}")


def check_sentence_case(path, heading):
    words = heading.split(' ')
    if not words[0][0].isupper():
        report_error(path, ERROR_HEADING_CAP, f"heading must start with capitalized word: {words[0]}")
        
    for word in words[1:]:
        word = word.replace(':', '').replace('(', '').replace(')', '')
        if word in ['E2E', 'Vertex', 'AutoML', 'ML', 'AI', 'GCP', 'API', 'R', 'CMEK', 'TF', 'TFX', 'TFDV', 'SDK',
                    'VM', 'CPR', 'NVIDIA', 'ID', 'DASK', 'ARIMA_PLUS', 'KFP', 'I/O', 'GPU', 'Google', 'TensorFlow', 
                    'PyTorch'
                   ]:
            continue
        if word.isupper():
            report_error(path, ERROR_HEADING_CASE, f"heading is not sentence case: {word}")


def report_error(notebook, code, msg):
    global num_errors
    
    if args.errors:
        if args.errors_codes:
            if str(code) not in args.errors_codes:
                return
            
        if args.errors_csv:
            print(notebook, ',', code)
        else:
            print(f"{notebook}: ERROR ({code}): {msg}", file=sys.stderr)
            num_errors += 1

def parse_objective(path, cell):
    desc = ''
    in_desc = True
    uses = ''
    in_uses = False
    steps = ''
    in_steps = False
    costs = []
    
    for line in cell['source'][1:]:
        if line.startswith('This tutorial uses'):
            in_desc = False
            in_steps = False
            in_uses = True
            uses += line
            continue
        elif line.startswith('The steps performed'):
            in_desc = False
            in_uses = False
            in_steps = True
            steps += line
            continue
            
        if in_desc:
            if len(desc) > 0 and line.strip() == '':
                in_desc = False
                continue
            desc += line
        elif in_uses:
            sline = line.strip()
            if len(sline) == 0:
                uses += '\n'
            else:
                ch = sline[0]
                if ch in ['-', '*', '1', '2', '3', '4', '5', '6', '7', '8', '9']:
                    uses += line
        elif in_steps:
            sline = line.strip()
            if len(sline) == 0:
                steps += '\n'
            else:
                ch = sline[0]
                if ch in ['-', '*', '1', '2', '3', '4', '5', '6', '7', '8', '9']:
                    steps += line
            
    if desc == '':
        report_error(path, 17, "Objective section missing desc")
    else:
        desc = desc.lstrip()
        sentences = desc.split('.')
        if len(sentences) > 1:
            desc = sentences[0] + '.\n'
        if desc.startswith('In this tutorial, you learn') or desc.startswith('In this notebook, you learn'):
            desc = desc[22].upper() + desc[23:]
        
    if uses == '':
        report_error(path, 18, "Objective section missing uses services list")
    else:
        if 'BigQuery' in uses:
            costs.append('BQ')
        if 'Vertex' in uses:
            costs.append('Vertex')
        if 'Dataflow' in uses:
            costs.append('Dataflow')
            
    if steps == '':
        report_error(path, 19, "Objective section missing steps list")
            
    return desc, uses, steps, costs

def add_index(path, tag, title, desc, uses, steps, git_link, colab_link, workbench_link):
    global last_tag
    
    if not args.web and not args.repo:
        return
    
    title = title.split(':')[-1].strip()
    title = title[0].upper() + title[1:]
    if args.web:
        title = title.replace('`', '')
        
        print('    <tr>')
        print('        <td>')
        tags = tag.split(',')
        for tag in tags:
            print(f'            {tag.strip()}<br/>\n')
        print('        </td>')
        print('        <td>')
        print(f'            {title}<br/>\n')
        if args.desc:
            desc = desc.replace('`', '')
            print(f'            {desc}<br/>\n')
        if linkback:
            text = ''
            for tag in tags:
                text += tag.strip() + ' '
                
            print(f'            Learn more about <a src="https://cloud.google.com/{linkback}">{text}</a><br/>\n')
        print('        </td>')
        print('        <td>')
        if colab_link:
            print(f'            <a src="{colab_link}">Colab</a><br/>\n')
        if git_link:
            print(f'            <a src="{git_link}">GitHub</a><br/>\n')
        if workbench_link:
            print(f'            <a src="{workbench_link}">Vertex AI Workbench</a><br/>\n')
        print('        </td>')
        print('    </tr>\n')
    elif args.repo:
        tags = tag.split(',')
        if tags != last_tag and tag != '':
            last_tag = tags
            flat_list = ''
            for item in tags:
                flat_list += item.replace("'", '') + ' '
            print(f"\n### {flat_list}\n")
        print(f"\n[{title}]({git_link})\n")
    
        if args.desc:
            print(desc)

        if args.uses:
            print(uses)

        if args.steps:
            print(steps)

if args.web:
    print('<table>')
    print('    <th>Vertex AI Feature</th>')
    print('    <th>Description</th>')
    print('    <th>Open in</th>')

if args.notebook_dir:
    if not os.path.isdir(args.notebook_dir):
        print("Error: not a directory:", args.notebook_dir)
        exit(1)
    tag = ''
    parse_dir(args.notebook_dir)
elif args.notebook:
    if not os.path.isfile(args.notebook):
        print("Error: not a notebook:", args.notebook)
        exit(1)
    tag = ''
    parse_notebook(args.notebook)
elif args.notebook_file:
    if not os.path.isfile(args.notebook_file):
        print("Error: file does not exist", args.notebook_file)
    else:
        with open(args.notebook_file, 'r') as csvfile:
            reader = csv.reader(csvfile)
            heading = True
            for row in reader:
                if heading:
                    heading = False
                else:
                    tag = row[0]
                    notebook = row[1]
                    try:
                        linkback = row[2]
                    except:
                        linkback = None
                    parse_notebook(notebook)
else:
    print("Error: must specify a directory or notebook")
    exit(1)

if args.web:
    print('</table>\n')
    
exit(num_errors)
