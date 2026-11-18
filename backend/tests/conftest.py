import os

# Set testing database before any application or model modules are loaded
os.environ["DATABASE_URL"] = "sqlite:///./test.db"
