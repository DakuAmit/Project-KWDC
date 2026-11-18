import os
from fastapi.templating import Jinja2Templates

# Calculate robust absolute path to backend/app/templates
_core_dir = os.path.dirname(os.path.abspath(__file__))
_app_dir = os.path.dirname(_core_dir)
TEMPLATES_DIR = os.path.join(_app_dir, "templates")

if not os.path.exists(TEMPLATES_DIR):
    for candidate in ["backend/app/templates", "app/templates", "../templates"]:
        if os.path.exists(candidate):
            TEMPLATES_DIR = os.path.abspath(candidate)
            break

templates = Jinja2Templates(directory=TEMPLATES_DIR)
