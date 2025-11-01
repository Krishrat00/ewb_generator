import os
from google import genai
from google.genai import types
from config import Config
from google.api_core import exceptions as api_exceptions
import cv2
import numpy as np
class CaptchaSolver:
    @staticmethod
    def clean_captcha_image(image_path):
        """
        CAPTCHA इमेज से पतली रेखाओं और शोर को हटाता है।
        
        Args:
            image_path (str): इनपुट इमेज फ़ाइल का पाथ।
        
        Returns:
            numpy.ndarray: साफ़ की गई (cleaned) इमेज।
        """
        
        # 1. इमेज को ग्रेस्केल में लोड करें
        img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            print(f"Error: Could not load image from {image_path}")
            return None
        
        # 2. बाइनराइज़ेशन (Binarization): अक्षरों को काला और बैकग्राउंड को सफ़ेद करें
        # 'OTSU' विधि का उपयोग करके थ्रेशोल्ड निर्धारित करें
        _, binary_img = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        
        # 3. नॉइज़ रिमूवल के लिए मोर्फ़ोलॉजिकल 'Opening' (Erosion followed by Dilation)
        # यह छोटी वस्तुएं (जैसे पतली रेखाएं या डॉट्स) हटा देता है लेकिन अक्षरों को ज़्यादा नुकसान नहीं पहुँचाता
        
        # एक छोटा कर्नेल (Kernel) परिभाषित करें (आमतौर पर 2x2 या 3x3)
        # 2x2 छोटे नॉइज़ के लिए अच्छा है, अगर रेखाएं थोड़ी मोटी हैं तो 3x3 का उपयोग करें
        kernel = np.ones((2, 2), np.uint8) 
        
        # Opening ऑपरेशन लागू करें
        cleaned_img = cv2.morphologyEx(binary_img, cv2.MORPH_OPEN, kernel, iterations=1)
        
        # 4. बैकग्राउंड को वापस सफ़ेद करें (यदि आवश्यक हो, तो यहाँ हम सीधे 'cleaned_img' का उपयोग करेंगे)
        # हम सिर्फ़ काले अक्षर को सफ़ेद बैकग्राउंड पर उल्टा करके वापस सेव करेंगे
        final_cleaned_img = cv2.bitwise_not(cleaned_img)
        
        return final_cleaned_img

    
    # अब आप अपने Gemini कोड में इस 'processed_captcha.png' फ़ाइल का उपयोग करें
    def solve_captcha_with_gemini(self):
        os.environ['GEMINI_API_KEY'] = Config.API_KEY
        try:
            client = genai.Client()
        except Exception as e:
            print(f"❌ Error initializing client: {e}. Make sure GEMINI_API_KEY is set.")
            exit()

        # 2. मॉडल की प्राथमिकता सूची (Model Priority List)
        # PRO को पहले, FLASH को दूसरे नंबर पर
        MODEL_FALLBACK_LIST = ["gemini-2.5-flash"]
        image_file_path = "static/captchas/captcha_live.png" 
        output_file = "processed_captcha.png" # नई, साफ की गई फ़ाइल का नाम

        processed_image = CaptchaSolver.clean_captcha_image(image_file_path)

        if processed_image is not None:
            # साफ़ की गई इमेज को सेव करें
            cv2.imwrite(output_file, processed_image)
            print(f"Image successfully cleaned and saved as {output_file}")
        prompt = "The CAPTCHA image contains a 6-character alphanumeric string. Identify this exact string. Output ONLY the 6-character result, nothing else, no explanation, no quotes."

        uploaded_file = None
        solved_captcha = None
        used_model = None

        try:
            # 3. फ़ाइल अपलोड करें (लोकल फ़ाइल)
            print(f"Uploading current CAPTCHA file: {image_file_path}...")
            uploaded_file = client.files.upload(file=image_file_path)
            print(f"File uploaded successfully: {uploaded_file.name}")
            
            # 4. हर मॉडल को प्राथमिकता क्रम में आज़माएं
            for model_name in MODEL_FALLBACK_LIST:
                print("-" * 40)
                print(f"🎯 Attempting to use model: **{model_name}**")
                
                try:
                    # Gemini API कॉल
                    response = client.models.generate_content(
                        model=model_name,
                        contents=[uploaded_file, prompt]
                    )
                    
                    # यदि सफल, तो लूप तोड़ दें
                    solved_captcha = response.text.strip()
                    used_model = model_name
                    break # ब्रेक करें क्योंकि हमें समाधान मिल गया है
                    
                except api_exceptions.ResourceExhausted as e:
                    # यह एरर तब आती है जब कोटा (Quota) खत्म हो जाता है (HTTP 429)
                    print(f"⚠️ Quota Exhausted for {model_name}: {e}")
                    print("➡️ Switching to the next fallback model...")
                    # यह अगला मॉडल (Flash) ट्राई करने के लिए लूप को जारी रखेगा
                
                except Exception as e:
                    # किसी अन्य API एरर को हैंडल करें (जैसे Bad Request)
                    print(f"❌ An error occurred with {model_name}: {e}")
                    print("➡️ Switching to the next fallback model...")

            # 5. अंतिम परिणाम प्रिंट करें
            if solved_captcha:
                print( f"✅ SUCCESS: Solved CAPTCHA using {used_model}: **{solved_captcha}**")
                return solved_captcha
            else:
                print("❌ FAILURE: All models' quotas are exhausted or an unrecoverable error occurred.")
                return None

        except FileNotFoundError as e:
            return str(e)
        except Exception as e:
            return str(e)

        finally:
            # 6. क्लीनअप: सर्वर से फ़ाइल हटाएँ
            if uploaded_file:
                client.files.delete(name=uploaded_file.name)
                print(f"\n✨ Cleanup complete: Deleted temporary file {uploaded_file.name}.")