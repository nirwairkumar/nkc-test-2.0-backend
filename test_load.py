import sys
import os

# Ensure we are in the backend directory or add it to path if needed
# But imports in main.py are relative to backend root now
try:
    from main import app
    print("SUCCESS: App loaded successfully.")
    print("Routes:")
    for route in app.routes:
        print(f" - {route.path} [{route.methods}]")
except Exception as e:
    print(f"FAILURE: Could not load app. Error: {e}")
    import traceback
    traceback.print_exc()
