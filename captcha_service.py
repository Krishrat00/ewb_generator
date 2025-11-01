from flask import Flask, render_template_string, request, jsonify, send_file
from selenium import webdriver
from selenium.webdriver.common.by import By
import threading, time, os

app = Flask(__name__)

USERNAME = "your_gst_username"
PASSWORD = "your_gst_password"

captcha_text = None
captcha_event = threading.Event()
latest_captcha_path = "static/captcha.png"
login_status = {"success": False, "message": ""}

os.makedirs("static", exist_ok=True)

# ------------------ Selenium Driver Setup ------------------
options = webdriver.ChromeOptions()
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--window-size=1920,1080")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument("--start-maximized")
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option('useAutomationExtension', False)
options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) "
                     "Chrome/122.0.0.0 Safari/537.36")

print("🚀 Creating driver now...")
driver = webdriver.Chrome(options=options)
driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
print("✅ Driver created successfully")
# ------------------------------------------------------------

HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
  <title>GST Login Captcha</title>
  <style>
    body { font-family: Arial, sans-serif; text-align: center; margin-top: 100px; }
    img { border: 1px solid #ccc; margin-top: 20px; display: none; }
    input, button { margin-top: 20px; padding: 10px; font-size: 16px; }
    #status { margin-top: 30px; font-weight: bold; }
  </style>
</head>
<body>
  <h2>GST Login Captcha</h2>

  <button id="start-login">Start Login</button><br>

  <img id="captcha-img" src="" alt="captcha" width="250" height="80"/>
  <form id="captcha-form" style="display:none;">
    <input type="text" name="captcha" id="captcha" placeholder="Enter Captcha" required />
    <br/>
    <button type="submit">Submit</button>
  </form>

  <div id="status"></div>

  <script>
    const startBtn = document.getElementById('start-login');
    const form = document.getElementById('captcha-form');
    const img = document.getElementById('captcha-img');
    const statusDiv = document.getElementById('status');

    startBtn.addEventListener('click', async () => {
      statusDiv.innerText = "Starting login, please wait...";
      const res = await fetch('/start_login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
      });
      const data = await res.json();
      statusDiv.innerText = data.message;
      setTimeout(loadCaptcha, 5000);
    });

    async function loadCaptcha() {
      try {
        const res = await fetch('/get_captcha');
        if (res.ok) {
          const blob = await res.blob();
          img.src = URL.createObjectURL(blob);
          img.style.display = 'block';
          form.style.display = 'block';
          statusDiv.innerText = "Captcha loaded. Please enter it below.";
        } else {
          statusDiv.innerText = "Waiting for captcha...";
          setTimeout(loadCaptcha, 3000);
        }
      } catch {
        setTimeout(loadCaptcha, 3000);
      }
    }

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const captcha = document.getElementById('captcha').value;
      const res = await fetch('/submit_captcha', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ captcha })
      });
      const data = await res.json();
      statusDiv.innerText = data.message;
      document.getElementById('captcha').value = "";
    });

    setInterval(async () => {
      const res = await fetch('/login_status');
      const data = await res.json();
      statusDiv.innerText = data.message;
      if (data.success) {
        statusDiv.style.color = "green";
      } else if (data.message.toLowerCase().includes("fail")) {
        statusDiv.style.color = "red";
      }
    }, 3000);
  </script>
</body>
</html>"""


def login_with_retry(username, password):
    global captcha_text, login_status

    print("🌍 Navigating to eWayBill login page...")
    driver.get("https://ewaybillgst.gov.in/login.aspx")
    time.sleep(5)

    print("📄 Current URL:", driver.current_url)
    print("📄 Page Title:", driver.title)
    with open("debug_page.html", "w", encoding="utf-8") as f:
        f.write(driver.page_source)
    print("✅ Saved debug_page.html")

    MAX_RETRIES = 5
    for attempt in range(1, MAX_RETRIES + 1):
        print(f"[Attempt {attempt}] Trying to capture CAPTCHA...")

        try:
            captcha_img = driver.find_element(By.ID, "imgcaptcha")
            captcha_img.screenshot(latest_captcha_path)
            print(f"📸 Captcha saved: {latest_captcha_path}")
        except Exception as e:
            print("❌ Could not find captcha element:", e)
            login_status["message"] = "Could not find CAPTCHA element."
            return

        captcha_event.clear()
        captcha_event.wait(timeout=120)

        if not captcha_event.is_set():
            login_status["message"] = "⏰ Timeout waiting for captcha input."
            continue

        print(f"User entered captcha: {captcha_text}")

        try:
            username_field = driver.find_element(
                By.XPATH, "//*[contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'username')]"
            )
            password_field = driver.find_element(
                By.XPATH, "//*[contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'password')]"
            )
            captcha_field = driver.find_element(
                By.XPATH, "//*[contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'captcha')]"
            )

            username_field.clear()
            password_field.clear()
            captcha_field.clear()

            username_field.send_keys(username)
            password_field.send_keys(password)
            captcha_field.send_keys(captcha_text)

            login_btn = driver.find_element(By.ID, "btnLogin")
            login_btn.click()
        except Exception as e:
            login_status["message"] = f"⚠️ Field error: {e}"
            continue

        time.sleep(3)

        if "dashboard" in driver.current_url.lower():
            login_status.update({"success": True, "message": "✅ Login successful!"})
            return True
        else:
            login_status.update({"success": False, "message": "❌ Captcha invalid or expired. Retrying..."})
            continue

    login_status["message"] = "🚫 All retries failed. Please restart."
    return False


@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route("/get_captcha")
def get_captcha():
    if not os.path.exists(latest_captcha_path) or os.path.getsize(latest_captcha_path) < 1000:
        return jsonify({"error": "Captcha not ready"}), 404
    return send_file(latest_captcha_path, mimetype="image/png", cache_timeout=0)


@app.route("/submit_captcha", methods=["POST"])
def submit_captcha():
    global captcha_text
    data = request.get_json()
    captcha_text = data.get("captcha", "")
    captcha_event.set()
    return jsonify({"message": "Captcha submitted! Trying login..."})


@app.route("/login_status")
def login_status_route():
    return jsonify(login_status)


@app.route("/start_login", methods=["POST"])
def start_login():
    print("🔥 /start_login called")
    data = request.get_json() or {}
    username = data.get("username", USERNAME)
    password = data.get("password", PASSWORD)

    login_status.update({"success": False, "message": "⏳ Starting login..."})
    if os.path.exists(latest_captcha_path):
        os.remove(latest_captcha_path)

    threading.Thread(target=login_with_retry, args=(username, password), daemon=True).start()
    return jsonify({"message": "Login started, waiting for captcha..."})

if __name__ == "__main__":
    app.run(debug=True)
