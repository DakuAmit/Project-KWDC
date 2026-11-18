import uvicorn
import os
import sys

# Ensure current directory is on PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from seeders.seed_data import seed_database

if __name__ == "__main__":
    print("===============================================================")
    print("🚀 Starting KTM-WDC Commercial Logistics Python Engine (FastAPI)")
    print("===============================================================")
    
    # Initialize and seed database if necessary
    try:
        seed_database()
    except Exception as e:
        print(f"Database initialization: {e}")

    # Launch Uvicorn Server
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        log_level="info"
    )
