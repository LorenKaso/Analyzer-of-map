import pandas as pd
import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from PIL import Image
from io import BytesIO

ROWS_TO_PROCESS = 5
CSV_PATH = "military_bases.csv"
OUTPUT_DIR = "screenshots"
os.makedirs(OUTPUT_DIR, exist_ok=True)

df = pd.read_csv(CSV_PATH).head(ROWS_TO_PROCESS)

chrome_options = Options()
chrome_options.add_argument("--start-maximized")
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)

for i, row in df.iterrows():
    lat = row['latitude']
    lon = row['longitude']
    url = f"https://earth.google.com/web/@{lat},{lon},1000a"
    driver.get(url)

    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.TAG_NAME, 'canvas'))
        )
        time.sleep(15)  # המתנה נוספת לוודאות שהמפה רונדרת לגמרי
    except:
        pass  # מתעלמים משגיאת זמן וממשיכים

    png_data = driver.get_screenshot_as_png()
    img = Image.open(BytesIO(png_data))
    new_width = 1024
    new_height = int((new_width / img.width) * img.height)
    img = img.resize((new_width, new_height))
    final_path = os.path.join(OUTPUT_DIR, f"processed_{i}.jpeg")
    img.save(final_path, "JPEG", quality=85)

driver.quit()
