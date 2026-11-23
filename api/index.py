"""
Vercel Serverless Function Handler for KTM-WDC FastAPI Application
"""
import sys
import os

# Ensure project root is in Python module search path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.main import app
