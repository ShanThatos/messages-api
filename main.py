import atexit
import json
import os
from pathlib import Path
from subprocess import Popen
from typing import Optional

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, session
import psutil
from waitress import serve

load_dotenv(verbose=True)


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY")
app.config["TEMPLATES_AUTO_RELOAD"] = os.environ.get("TEMPLATES_AUTO_RELOAD") == "yes"

messages_file_path = Path(os.environ.get("MESSAGES_PATH", "./mapi.json")).resolve()
if not messages_file_path.exists():
    messages_file_path.write_text("[]")
messages = json.loads(messages_file_path.read_text())

CF_PROCESS: Optional[Popen] = None


def fully_kill_process(process: Optional[Popen]):
    if process is None: return
    for child_process in psutil.Process(process.pid).children(True):
        child_process.kill()
    process.kill()


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        if not session.get("is_admin", False):
            return render_template("login.html")
        else:
            return render_template("index.html")
    if request.form.get("username", "") == os.environ.get("USERNAME") and request.form.get("password", "") == os.environ.get("PASSWORD"):
        session["is_admin"] = True
    return redirect("/")


@app.route("/submit", methods=["POST"])
def submit():
    print("wow")
    return jsonify({"success": True})


@app.route("/logout", methods=["GET"])
def logout():
    session["is_admin"] = False
    return redirect("/")


def start_server():
    global CF_PROCESS
    if os.environ.get("RUN_CLOUDFLARED") == "yes":
        CF_PROCESS = Popen(f"cloudflared tunnel run --url 0.0.0.0:8001 {os.environ.get("CLOUDFLARED_DOMAIN")}", shell=True, start_new_session=True)
    atexit.register(lambda: fully_kill_process(CF_PROCESS))

    serve(app, listen="0.0.0.0:8001")

if __name__ == "__main__":
    start_server()