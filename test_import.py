import sys
import os
# Add current directory to path
sys.path.append(os.getcwd())

try:
    from app.planner import IntentPlanner
    from datetime import timedelta
    print(f"Import successful. Timedelta: {timedelta}")
    
    # Try to access timedelta inside IntentPlanner method (simulated)
    ip = IntentPlanner(None, None)
    print("Instance created")
except Exception as e:
    print(f"Import failed: {e}")
    import traceback
    traceback.print_exc()
