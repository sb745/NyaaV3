#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WSGI entry point for the Nyaa application.
Compatible with Python 3.13.
"""
import gevent.monkey
gevent.monkey.patch_all()

from nyaa import create_app
from flask import Flask

app: Flask = create_app('config')

if app.config['DEBUG']:
    from werkzeug.debug import DebuggedApplication
    app.wsgi_app = DebuggedApplication(app.wsgi_app, True)

if __name__ == '__main__':
    import gevent.pywsgi
    gevent_server = gevent.pywsgi.WSGIServer(("localhost", 5000), app.wsgi_app)
    gevent_server.serve_forever()
