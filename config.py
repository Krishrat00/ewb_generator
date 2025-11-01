import os

class Config:
    # Flask settings
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    
    # Selenium settings
    CHROME_HEADLESS = True
    PAGE_LOAD_TIMEOUT = 30
    IMPLICIT_WAIT = 10
    
    # CAPTCHA settings
    CAPTCHA_MAX_RETRIES = 3
    CAPTCHA_SOLVE_TIMEOUT = 30
    
    # Session settings
    SESSION_TIMEOUT_MINUTES = 30
    
    # Logging
    LOG_LEVEL = 'INFO'
    LOG_FILE = 'logs/automation.log'

    username = os.environ.get('GST_USERNAME', '24AHJPR6707K1ZY')
    password = os.environ.get('GST_PASSWORD', '')