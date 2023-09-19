import atexit
import json
import os
import random
import string
import subprocess
from functools import wraps
from pathlib import Path
from subprocess import Popen
from typing import Callable, Optional
from flask_cors import CORS

import psutil
from dotenv import load_dotenv
from flask import (Flask, abort, jsonify, redirect, render_template, request,
                   session)
from waitress import serve

load_dotenv(verbose=True)


app = Flask(__name__)
CORS(app)
app.secret_key = os.environ.get("SECRET_KEY")
app.config["TEMPLATES_AUTO_RELOAD"] = os.environ.get("TEMPLATES_AUTO_RELOAD") == "yes"

messages_file_path = Path(os.environ.get("MESSAGES_PATH", "./mapi.json")).resolve()
if not messages_file_path.exists():
    messages_file_path.write_text("[]")
messages = json.loads(messages_file_path.read_text())

CF_PROCESS: Optional[Popen] = None


def auth_admin(f: Callable):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("is_admin", False):
            abort(418)
        return f(*args, **kwargs)
    return wrapper


def fully_kill_process(process: Optional[Popen]):
    if process is None: return
    for child_process in psutil.Process(process.pid).children(True):
        try:
            child_process.kill()
        except psutil.NoSuchProcess:
            pass
    process.kill()


def save_messages():
    global messages
    messages_file_path.write_text(json.dumps(messages))


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        if not session.get("is_admin", False):
            return render_template("login.html")
        return redirect("/messages")
    if request.form.get("username", "") == os.environ.get("MAPI_USERNAME") and request.form.get("password", "") == os.environ.get("MAPI_PASSWORD"):
        print("Admin logged in!")
        session["is_admin"] = True
    return redirect("/")


@app.route("/submit", methods=["POST"])
def submit():
    global messages
    if not request.is_json or request.json is None:
        print("Invalid request received, ignored...")
        abort(418)
    message = request.json.get("message", "")
    origin = request.json.get("origin", "")
    print(f"Received message: {repr(message)} from {repr(origin)}")
    if message and origin:
        message_id = "".join(random.sample(string.ascii_letters, 10))
        messages.append({"id": message_id, "message": message, "origin": origin})
        save_messages()
    else:
        print("Invalid message received, ignored...")
    return jsonify({"success": True})


@app.route("/messages", methods=["GET"])
@auth_admin
def get_messages():
    global messages
    return jsonify(messages)


@app.route("/clear", methods=["GET"])
@auth_admin
def clear_messages():
    global messages
    messages.clear()
    save_messages()
    return redirect("/messages")


@app.route("/delete/<string:message_id>", methods=["GET"])
@auth_admin
def delete_message(message_id: str):
    global messages
    messages = [message for message in messages if message["id"] != message_id]
    save_messages()
    return redirect("/messages")


@app.route("/logout", methods=["GET"])
def logout():
    session["is_admin"] = False
    return redirect("/")


def start_server():
    global CF_PROCESS
    if os.environ.get("RUN_CLOUDFLARED") == "yes":
        cf_domain = os.environ.get("CLOUDFLARED_DOMAIN")
        if not Path("./cf_creds.json").exists():
            print("Retrieving cloudflare credentials...")
            subprocess.run(f"cloudflared tunnel token --cred-file cf_creds.json {cf_domain}", shell=True)
        CF_PROCESS = Popen(f"cloudflared tunnel run --cred-file cf_creds.json --url 0.0.0.0:8001 {cf_domain}", shell=True, start_new_session=True)
    atexit.register(lambda: fully_kill_process(CF_PROCESS))

    print("Starting server...")
    serve(app, listen="0.0.0.0:8001")

if __name__ == "__main__":
    start_server()