#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Database migration script for Nyaa.
Compatible with Python 3.13 and Flask-Migrate 4.0.
"""
import sys
from typing import List

from flask_migrate import Migrate
from flask.cli import FlaskGroup

from nyaa import create_app
from nyaa.extensions import db

app = create_app('config')
migrate = Migrate(app, db)

def create_cli_app():
    return app

cli = FlaskGroup(create_app=create_cli_app)

if __name__ == "__main__":
    # Patch sys.argv to default to 'db'
    if len(sys.argv) > 1 and sys.argv[1] not in ['--help', '-h']:
        if sys.argv[1] not in ['db', 'routes', 'shell', 'run']:
            args: List[str] = sys.argv.copy()
            args.insert(1, 'db')
            sys.argv = args

    cli()
