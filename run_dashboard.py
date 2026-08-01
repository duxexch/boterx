#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Boterx Dashboard — Entry Point"""

import os
import sys

# Add parent dir to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load .env
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

from dashboard.app import app

if __name__ == '__main__':
    port = int(os.getenv('DASHBOARD_PORT', '8080'))
    host = os.getenv('DASHBOARD_HOST', '0.0.0.0')
    print(f"🚀 Boterx Dashboard: http://{host}:{port}")
    app.run(host=host, port=port, debug=True, threaded=True)
