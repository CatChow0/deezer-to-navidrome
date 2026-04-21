#!/usr/bin/env python3
import os

from flask import Flask

from core.config import ensure_dirs
from core import scheduler
from routes.cache import cache_bp
from routes.dedup import dedup_bp
from routes.playlists import playlists_bp
from routes.search import search_bp
from routes.system import system_bp

ensure_dirs()
scheduler.start()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me")

app.register_blueprint(playlists_bp)
app.register_blueprint(cache_bp)
app.register_blueprint(dedup_bp)
app.register_blueprint(search_bp)
app.register_blueprint(system_bp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
