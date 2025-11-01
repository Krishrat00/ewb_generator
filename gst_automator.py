import os, time, base64, logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.action_chains import ActionChains
import json
# import undetected_chromedriver as uc
from pyvirtualdisplay import Display



logger = logging.getLogger("GSTAutomator")

class GSTAutomator:
    def __init__(self, headless=True):
        self.driver = None
        self.setup_driver(headless=headless)

    def setup_driver(self, headless=True):
        print("⚙️ Setting up Selenium WebDriver...")
        download_dir = os.path.abspath("Downloads")
        os.makedirs(download_dir, exist_ok=True)

        chrome_opts = webdriver.ChromeOptions()
        if headless:
            # from pyvirtualdisplay import Display
            self.display = Display(visible=0, size=(1280, 1024))
            self.display.start()
            print("🖥️ Virtual display started")

        if headless:
            chrome_opts.add_argument("--headless=new")

        chrome_opts.add_argument("--no-sandbox")
        chrome_opts.add_argument("--disable-dev-shm-usage")
        chrome_opts.add_argument("--disable-blink-features=AutomationControlled")

        # Silent PDF printing setup
        settings = {
            "recentDestinations": [{"id": "Save as PDF", "origin": "local"}],
            "selectedDestinationId": "Save as PDF",
            "version": 2,
            "isHeaderFooterEnabled": False,
            "isLandscapeEnabled": False,
            "isDuplexEnabled": False
        }

        prefs = {
            "printing.print_preview_sticky_settings.appState": json.dumps(settings),
            "savefile.default_directory": download_dir,
            "printing.default_destination_selection_rules": {
                "kind": "local",
                "namePattern": "Save as PDF"
            }
        }

        chrome_opts.add_experimental_option("prefs", prefs)
        chrome_opts.add_argument("--kiosk-printing")

        self.driver = webdriver.Chrome(options=chrome_opts)
        # self.driver.set_window_size(1280, 1024)
        logger.info(f"✅ Selenium driver initialized (downloads → {download_dir})")


    # ---------- LOGIN PAGE + CAPTCHA ----------
    def load_login_page(self, session_id):
        try:
            self.driver.get("https://ewaybillgst.gov.in/Login.aspx")
            WebDriverWait(self.driver, 12).until(EC.presence_of_element_located((By.ID, "imgcaptcha")))
            return self.get_captcha(session_id)
        except Exception as e:
            logger.exception("Failed to load login page")
            return {"success": False, "error": str(e)}

    def get_captcha(self, session_id):
        try:
            captcha_el = self.driver.find_element(By.ID, "imgcaptcha")
            os.makedirs("static/captchas", exist_ok=True)
            path = f"static/captchas/{session_id}.png"
            captcha_el.screenshot(path)
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            return {"success": True, "captcha_url": f"/{path}", "captcha_b64": b64}
        except Exception as e:
            logger.exception("Failed to capture captcha")
            return {"success": False, "error": str(e)}

    # ---------- LOGIN ----------
    def login(self, username, password, captcha_text):
        try:
            driver = self.driver
            wait = WebDriverWait(driver, 10)
            wait.until(EC.presence_of_element_located((By.ID, "imgcaptcha")))

            driver.find_element(By.ID, "txt_username").clear()
            driver.find_element(By.ID, "txt_password").clear()
            driver.find_element(By.ID, "txtCaptcha").clear()
            driver.find_element(By.ID, "txt_username").send_keys(username)
            driver.find_element(By.ID, "txt_password").send_keys(password)
            driver.find_element(By.ID, "txtCaptcha").send_keys(captcha_text)

            login_btn = wait.until(EC.element_to_be_clickable((By.ID, "btnLogin")))
            driver.execute_script("arguments[0].click();", login_btn)

            # Handle alert for invalid login
            try:
                WebDriverWait(driver, 4).until(EC.alert_is_present())
                alert = driver.switch_to.alert
                msg = alert.text
                alert.accept()
                logger.info("GSTService: alert during login -> %s", msg)
                self.driver.get("https://ewaybillgst.gov.in/Login.aspx")
                WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.ID, "imgcaptcha")))
                return {"success": False, "error": msg}
            except TimeoutException:
                pass

            time.sleep(2)
            if "MainMenu.aspx" in driver.current_url:
                logger.info("GSTService: login successful")
                return {"success": True}
            else:
                try:
                    err = driver.find_element(By.ID, "lblError").text.strip()
                except:
                    err = "Invalid credentials or captcha."
                self.driver.get("https://ewaybillgst.gov.in/Login.aspx")
                WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.ID, "imgcaptcha")))
                return {"success": False, "error": err}
        except Exception as e:
            logger.exception("Login failed with exception")
            return {"success": False, "error": str(e)}

    # ---------- BILL PAGE ----------
    def navigate_to_bill_generation(self):
        try:
            driver = self.driver
            driver.get("https://ewaybillgst.gov.in/BillGeneration/BillGeneration.aspx")
            WebDriverWait(driver, 12).until(
                EC.presence_of_element_located((By.ID, "ctl00_ContentPlaceHolder1_rbtOutwardInward_0"))
            )
            logger.info("GSTService: navigated to Bill Generation page")
              # Dummy input to ensure page is loaded
            return True
        except Exception as e:
            logger.exception("Failed to load bill generation page")
            return False

    # ---------- CONSIGNOR DETAILS ----------
    def fill_consignor_details(self, data):
        driver = self.driver
        logger.info("Filling Bill Details")
        time.sleep(5)
        driver.find_element(By.ID, "txtDocNo").send_keys("1001")
        logger.info("Filling Consignor Details")
        wait = WebDriverWait(driver, 10)
        try:
            gstin = (data.get("gstin") or "").strip()
            if gstin and gstin.upper() != "URP":
                gst_field = wait.until(EC.presence_of_element_located((By.ID, "ctl00_ContentPlaceHolder1_txtToGSTIN")))
                gst_field.clear()
                gst_field.send_keys(gstin)
                time.sleep(2)
            else:
                driver.find_element(By.ID, "ctl00_ContentPlaceHolder1_txtToGSTIN").clear()
                driver.find_element(By.ID, "ctl00_ContentPlaceHolder1_txtToGSTIN").send_keys("URP")
                driver.find_element(By.ID, "ctl00_ContentPlaceHolder1_txtToTrdName").send_keys(data.get("name", ""))
                Select(driver.find_element(By.ID, "slToState")).select_by_visible_text(data.get("state", ""))
                driver.find_element(By.ID, "ctl00_ContentPlaceHolder1_txtToPlace").send_keys(data.get("city", ""))
                driver.find_element(By.ID, "ctl00_ContentPlaceHolder1_txtToPincode").send_keys(data.get("pincode", ""))

            return {"success": True}
        except Exception as e:
            logger.exception("Failed to fill consignor details")
            return {"success": False, "error": str(e)}

    # ---------- INVOICE DETAILS + PREVIEW ----------
    def fill_invoice_and_preview(self, invoice_data, session_id):
        driver = self.driver
        wait = WebDriverWait(driver, 1)
        try:
            time.sleep(2)
            # HSN Code (added)
            try:
                hsn_field = driver.find_element(By.ID, "txt_HSN_1")
                hsn_field.clear()
                hsn_field.send_keys(invoice_data.get("hsn_code", "5407"))
            except Exception:
                logger.warning("HSN code field not found, skipping.")
            # Taxable amount
            trc = wait.until(EC.presence_of_element_located((By.ID, "txt_TRC_1")))
            trc.clear()
            trc.send_keys(invoice_data.get("amount", ""))

            # IGST rate
            Select(wait.until(EC.presence_of_element_located((By.ID, "SelectIGST_1")))).select_by_value(
                invoice_data.get("igst_rate", "5.000")
            )

            
            time.sleep(2)
            # Transporter GSTIN (added)
            try:
                trans_gstin = driver.find_element(By.ID, "ctl00_ContentPlaceHolder1_txtTransGSTIN")
                trans_gstin.clear()
                trans_gstin.send_keys(invoice_data.get("transporter_gstin", ""))
            except Exception:
                logger.warning("Transporter GSTIN field not found, skipping.")

            # Transporter ID
            trans_field = wait.until(EC.presence_of_element_located((By.ID, "ctl00_ContentPlaceHolder1_txtTransid")))
            trans_field.clear()
            trans_field.send_keys(invoice_data.get("transporter_id", ""))

            # wait 5 sec before preview for auto calculations
            time.sleep(2)

            # Preview
            preview_btn = wait.until(EC.element_to_be_clickable((By.ID, "btnPreview")))
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", preview_btn)
            time.sleep(0.5)
            driver.execute_script("arguments[0].click();", preview_btn)
            logger.info("Clicked Preview button via JS safely")

            # Handle preview alert
            try:
                WebDriverWait(driver, 6).until(EC.alert_is_present())
                alert = driver.switch_to.alert
                logger.info("Preview alert: %s", alert.text)
                alert.accept()
            except TimeoutException:
                pass

            time.sleep(5)
            os.makedirs("static/previews", exist_ok=True)
            path = f"static/previews/{session_id}.png"
            driver.save_screenshot(path)
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")

            return {"success": True, "preview_image": f"/{path}", "preview_b64": b64}
        except Exception as e:
            logger.exception("Error during invoice fill/preview")
            return {"success": False, "error": str(e)}

    # ---------- FINAL SUBMIT ----------
    def confirm_and_submit(self):
        driver = self.driver
        try:
            ActionChains(driver).move_by_offset(50, 50).click().perform()
            time.sleep(0.5)
            # Click submit button
            submit_btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.ID, "btnsbmt")))
            submit_btn.click()

            # Wait for alert and accept it
            for _ in range(2):  # Adjust if 1 or 2 alerts can appear
                try:
                    WebDriverWait(driver, 3).until(EC.alert_is_present())
                    alert = driver.switch_to.alert
                    print("Alert text:", alert.text)
                    alert.accept()
                    time.sleep(1)
                except Exception:
                    break

            # Wait for Print button
            print_btn = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.XPATH, "//a[@onclick='printOnlyDiv()']"))
            )

            # Scroll into view (to avoid footer blocking)
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", print_btn)
            time.sleep(0.8)
            try:
                print_btn.click()
            except Exception:
                # If footer or overlay blocks it, fallback to JS click
                driver.execute_script("arguments[0].click();", print_btn)

            # Headless “silent” print to PDF
            time.sleep(2)
            driver.execute_script('window.print();')

            # Wait a few seconds for Chrome to generate the file
            time.sleep(5)

            return {"success": True, "message": "EWB printed to PDF successfully."}
        except Exception as e:
            logger.exception("Failed in confirm_and_submit flow")
            return {"success": False, "error": str(e)}


    # ---------- MASTER FLOW ----------
    def create_eway_bill(self, credentials, invoice_data, session_id, auto_submit=False):
        login_result = self.login(credentials["username"], credentials["password"], credentials["captcha"])
        if not login_result.get("success"):
            return login_result

        if not self.navigate_to_bill_generation():
            return {"success": False, "error": "Failed to load Bill Generation page"}

        res = self.fill_consignor_details(invoice_data)
        if not res.get("success"):
            return res

        preview_res = self.fill_invoice_and_preview(invoice_data, session_id)
        if not preview_res.get("success"):
            return preview_res

        if auto_submit:
            return self.confirm_and_submit()

        return preview_res

    def close(self):
        try:
            self.driver.quit()
        except:
            pass
