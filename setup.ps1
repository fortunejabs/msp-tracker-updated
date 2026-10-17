# setup.ps1 — Recreate the project from scratch on Windows
py -3.12 -m venv venv
.\venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install --timeout 120 --retries 10 -r requirements.txt
django-admin startproject config .
python manage.py startapp tracker
Write-Host "Project ready"
