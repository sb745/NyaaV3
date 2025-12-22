#!/usr/bin/env python3
"""
Main entry point for running the Nyaa application.
Compatible with Python 3.13.
"""
from nyaa import create_app

app = create_app('config')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5500, debug=True)
