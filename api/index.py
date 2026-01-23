"""
Vercel Serverless Function Entry Point.
This file wraps the FastAPI app for Vercel deployment.
"""
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import the FastAPI app
from src.main import app

# Vercel expects a handler - FastAPI app works directly
handler = app
