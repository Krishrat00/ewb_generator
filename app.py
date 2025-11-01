from flask import Flask, jsonify, request, render_template_string, send_file
from flask_cors import CORS
import uuid, os, logging, threading
from datetime import datetime
from gst_automator import GSTAutomator
from config import Config

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("GSTService")

# in-memory sessions: sid -> {"automator": GSTAutomator(), "created_at":..., "last_activity":...}
sessions = {}
lock = threading.Lock()
global invoice_data
def create_session_obj():
    sid = str(uuid.uuid4())
    print("🚀 Creating GSTAutomator instance...")
    automator = GSTAutomator()   # change to True if you want headless
    sessions[sid] = {
        "automator": automator,
        "created_at": datetime.now(),
        "last_activity": datetime.now()
    }
    # load login page and capture captcha immediately
    automator.load_login_page(sid)
    return sid

# ---------------- Disable Captcha Caching ----------------
@app.after_request
def add_no_cache_headers(response):
    if "static/captchas" in request.path or "static/previews" in request.path:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# -------------- Routes & Frontend --------------
@app.route("/", methods=["GET"])
def home_page():
    # minimal UI: captcha input only; everything else hardcoded in backend (auto flow)
    html = """
    <!doctype html>
    <html>
    <head><title>GST Auto EWB</title></head>
    <body style="font-family:Segoe UI;padding:30px;">
      <h3>GST Auto E-Way Bill</h3>
      <div id="captcha-area">Loading...</div>
      <input id="captcha_text" placeholder="Enter captcha" />
      <button onclick="login()">Login & Create EWB</button>
      <button onclick="refreshCaptcha()">Refresh Captcha</button>
      <pre id="status"></pre>
      <img id="preview" style="max-width:600px;display:block;margin-top:10px;" />
<button id="confirmSubmitBtn" class="btn btn-success">Create & Submit</button>

<script>
document.getElementById("confirmSubmitBtn").addEventListener("click", async () => {
  const btn = document.getElementById("confirmSubmitBtn");
  btn.disabled = true;
  btn.innerText = "Generating...";

  try {
    const res = await fetch("/api/submit-bill", {  // your actual API endpoint
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
      }),
    });

    const data = await res.json();
    if (data.success) {
      alert("EWB Generated Successfully!");
      if (data.download_url) {
        // Trigger automatic download on mobile
        const link = document.createElement("a");
        link.href = data.download_url;
        link.download = ""; // let the browser decide the name
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
      }
    } else {
      alert("Error: " + (data.error || "Unknown error"));
    }
  } catch (err) {
    alert("Network or server error");
    console.error(err);
  } finally {
    btn.disabled = false;
    btn.innerText = "Create & Submit";
  }
});
</script>

      <script>
        let sessionId = null;
        async function start() {
            const res = await fetch('/api/start-session');
            const data = await res.json();
            if (data.success) {
                sessionId = data.session_id;
                document.getElementById('captcha-area').innerHTML = `<img src="${data.captcha_url}?t=${Date.now()}" />`;
            } else {
                document.getElementById('captcha-area').innerText = 'Failed to start session';
            }
        }
        async function refreshCaptcha() {
            if (!sessionId) return;
            const res = await fetch('/api/refresh-captcha', {
                method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({session_id:sessionId})
            });
            const data = await res.json();
            if (data.success) {
                document.getElementById('captcha-area').innerHTML = `<img src="${data.captcha_url}?t=${Date.now()}" />`;
            } else {
                document.getElementById('captcha-area').innerText = 'Failed';
            }
        }
        async function login() {
            document.getElementById('status').innerText = "Logging in...";
            const payload = { session_id: sessionId, captcha_text: document.getElementById('captcha_text').value };
            const res = await fetch('/api/login', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload) });
            const data = await res.json();
            document.getElementById('status').innerText = JSON.stringify(data, null, 2);
            if (!data.success && data.new_captcha) {
                // replace captcha
                document.getElementById('captcha-area').innerHTML = `<img src="${data.new_captcha}?t=${Date.now()}" />`;
            }
            if (data.success && data.preview_image) {
                document.getElementById('preview').src = data.preview_image + '?t=' + Date.now();
                document.getElementById('submitBtn').style.display = 'inline-block';
            }
        }
        async function confirmSubmit() {
            document.getElementById('status').innerText = "Submitting...";
            const res = await fetch('/api/submit-bill', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({session_id:sessionId}) });
            const data = await res.json();
            document.getElementById('status').innerText = JSON.stringify(data, null, 2);
            if (data.success) {
                document.getElementById('submitBtn').style.display = 'none';
            }
        }
        start();
      </script>
    </body>
    </html>
    """
    return render_template_string(html)

@app.route("/api/start-session", methods=["GET"])
def start_session():
    try:
        with lock:
            sid = create_session_obj()
        automator = sessions[sid]["automator"]
        captcha = automator.get_captcha(sid)
        captcha["session_id"] = sid
        return jsonify(captcha)
    except Exception as e:
        logger.exception("start_session failed")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/refresh-captcha", methods=["POST"])
def refresh_captcha():
    try:
        sid = request.json.get("session_id")
        automator = sessions.get(sid)
        if not automator:
            return jsonify({"success": False, "error": "Invalid session"}), 404
        return jsonify(automator.get_captcha(sid))
    except Exception as e:
        logger.exception("refresh captcha failed")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/login", methods=["POST"])
def api_login_and_create():
    """
    Accepts {"session_id":..., "captcha_text": "..."}
    Uses Config.username/password and the provided captcha to login.
    On successful login, automatically runs create_eway_bill with hardcoded invoice_data,
    returns preview image info back to frontend.
    """
    try:
        payload = request.json
        sid = payload.get("session_id")
        captcha_text = payload.get("captcha_text", "")
        if sid not in sessions:
            return jsonify({"success": False, "error": "Invalid session"}), 404
        automator = sessions[sid]["automator"]

        # build credentials from Config
        credentials = {"username": Config.username, "password": Config.password, "captcha": captcha_text}

        # hardcoded invoice data (change as needed)
        invoice_data = {
            "doc_no": "1001",
            "gstin": "URP",                # or a GSTIN string
            "name": "Demo Company",
            "state": "UTTAR PRADESH",
            "city": "Lucknow",
            "pincode": "226001",
            "amount": "15000",
            "igst_rate": "5.000",
            "transporter_id": "09AAEFC1392H1ZH",
        }

        # call master flow (login + navigate + fill + preview)
        result = automator.create_eway_bill(credentials, invoice_data, sid, auto_submit=False)

        # if login failed (create_eway_bill will return login error), refresh captcha and return new url
        if not result.get("success"):
            # after login failure, load_login_page already called inside login() to refresh captcha
            new_c = automator.get_captcha(sid)
            result["new_captcha"] = new_c.get("captcha_url")
        else:
            # on success preview returned with preview_image path
            pass

        return jsonify(result)
    except Exception as e:
        logger.exception("create flow failed")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/submit-bill", methods=["POST"])
def submit_bill():
    try:
        sid = request.json.get("session_id")
        if sid not in sessions:
            return jsonify({"success": False, "error": "Invalid session"}), 404
        automator = sessions[sid]["automator"]
        res = automator.confirm_and_submit()
        pdf_name = f"EWB.pdf"
        pdf_path = os.path.join("downloads", pdf_name)

        # Save the PDF file (already done)
        # return the downloadable link
        return jsonify({
            "success": True,
            "message": "EWB generated successfully.",
            "download_url": f"/Downloads/{pdf_name}"
        })
    except Exception as e:
        logger.exception("submit failed")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/cleanup")
def cleanup():
    with lock:
        for sid, obj in list(sessions.items()):
            try:
                obj["automator"].close()
            except:
                pass
            sessions.pop(sid, None)
    return jsonify({"success": True, "message": "All sessions closed"})

@app.route("/download/<filename>")
def download_pdf(filename):
    file_path = os.path.join("downloads", filename)
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    else:
        return jsonify({"error": "File not found"}), 404

if __name__ == "__main__":
    os.makedirs("static/captchas", exist_ok=True)
    os.makedirs("static/previews", exist_ok=True)
    port = int(os.environ.get("PORT", 5099))
    app.run(host="0.0.0.0", port=port, debug=False)
