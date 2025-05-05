import os
import json
import re
import time
import numpy as np
import pandas as pd
import google.generativeai as genai
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from PIL import Image
from io import BytesIO
from dotenv import load_dotenv
from PIL import ImageFilter


#loud the file
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=api_key)

ROWS_TO_PROCESS = 1
CSV_PATH = "military_bases.csv"
OUTPUT_DIR = "screenshots"
os.makedirs(OUTPUT_DIR, exist_ok=True)

df = pd.read_csv(CSV_PATH).head(ROWS_TO_PROCESS)

#gemini question prompt
def build_prompt(country):
    return (f""" You are a top-level analyst in satellite image interpretation working for the US Department of Defense.
                We received intel that this location may be a military base or facility operated by the armed forces of {country}.

                Please analyze the satellite image and respond ONLY with a valid JSON object that contains the following keys:

                1. "findings": List of confirmed structures, vehicles, and systems (with confidence_score between 0-1).
                2. "suspicious_elements": Things that look suspicious but uncertain (also with confidence_score).
                3. "analysis": Your detailed interpretation of the image.
                4. "movement_analysis": Describe any signs of recent activity or movement (e.g., tire tracks, equipment relocation).
                5. "physical_changes": Describe any structural or environmental changes (e.g., new buildings, roads, fencing).
                6. "things_to_continue_analyzing": Suggestions for follow-up.
                7. "recommended_next_step": Suggestion for a human analyst.
                8. "action": One of ["zoom-in", "zoom-out", "move-left", "move-right", "move-up", "move-down", "finish"].
                    If the image is too close and you can't understand what you're seeing, consider using "zoom-out".
                    If the image is too empty, unclear, or lacks structures, consider using directional movement
                    ("move-left", "move-right", "move-up", "move-down") to explore nearby areas.
                    You can assume that moving slightly in any direction will give a new, different nearby image.
                    Only choose "zoom-in" if you see something suspicious you want to investigate more closely.
                    If the image is blurry or empty, do NOT zoom in again. Instead, move in a direction to find a nearby clearer region.
                ⚠️ Respond ONLY with a valid JSON object. No explanations outside of it.
                """
            )
def clean_json_response(text):
    # הסרה של תגיות ```json ``` מההתחלה והסוף
    text = re.sub(r"^```(json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()

#analyze image
def analyze_image(image_path, country):
    model = genai.GenerativeModel("models/gemini-2.0-flash-thinking-exp-01-21")
    img = Image.open(image_path)
    prompt = build_prompt(country)
    response = model.generate_content([prompt, img])
    cleaned = clean_json_response(response.text)
    
    try:
        parsed = json.loads(cleaned)
        return parsed  # או parsed['analysis'] למשל
    except json.JSONDecodeError as e:
        print("JSON parsing failed:", e)
        print("--- Raw response ---\n", response.text)
        return {"error": "Parsing failed"}

def adjust_coordinates(lat, lon, altitude, action):
    if action == "zoom-in":
        altitude = max(500, altitude / 1.5)  
    elif action == "zoom-out":
        altitude = min(10000, altitude * 0.85)  
    elif action == "move-left":
        lon -= 0.05
    elif action == "move-right":
        lon += 0.05
    elif action == "move-up":
        lat += 0.05
    elif action == "move-down":
        lat -= 0.05
    return lat, lon, altitude

def is_image_sharp(image):
    gray = image.convert("L")
    edges = gray.filter(ImageFilter.FIND_EDGES)
    std = np.std(np.array(edges))
    print(f"🔍 Image sharpness std dev = {std}")
    return std > 10  # Adjust the threshold as needed

# Check if the image contains the Google Earth logo
def is_google_earth_splash(image):
    # חיתוך רצועה מרכזית באופק
    middle_strip = np.array(image.crop((image.width // 4, image.height // 3, 3 * image.width // 4, image.height // 2)))
    std_dev = np.std(middle_strip)
    brightness = np.mean(middle_strip)
    # רקע כהה עם ניגוד גבוה → כנראה שזה מסך פתיחה
    return brightness < 70 and std_dev > 30

#chrome photos
chrome_options = Options()
chrome_options.add_argument("--start-maximized")
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)

results = []

for i, row in df.iterrows():
    lat = row['latitude']
    lon = row['longitude']
    country = row['country']
    altitude = 4000 # starting zoom level
    history = []
    last_action = None
    same_action_count = 0

    for step in range(8):
        url = f"https://earth.google.com/web/@{lat},{lon},{altitude}a"
        driver.get(url)
    
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, 'canvas'))
            )
            time.sleep(10)
        except:
            pass

        png_data = driver.get_screenshot_as_png()
        img = Image.open(BytesIO(png_data))
        img = img.resize((1024, int((1024 / img.width) * img.height)))
        # Check if the image contains the Google Earth logo
        if is_google_earth_splash(img):
            print(f"🛑 Google Earth splash detected at step {step}. Stopping.")
            break
        #save the image
        image_path = os.path.join(OUTPUT_DIR, f"processed_{i}_{step}.jpeg")
        img.save(image_path, "JPEG", quality=85)
        
        # בדיקת חדות
        image_is_blurry = not is_image_sharp(img)
        if image_is_blurry:
            print(f"🛑 Blurry image detected at step {step}. Stopping analysis.")
            results.append({
                "index": i,
                "country": country,
                "step": step,
                "latitude": lat,
                "longitude": lon,
                "analysis": "Stopped due to blurry image"
            })
            break
        if step == 0:
            prompt = build_prompt(country)
        else:
            blur_note = "⚠️ Previous image may be blurry or unclear.\n" if image_is_blurry else ""
            history_prompt = (
                f"{blur_note}Here is the analysis of previous analysts about this area and their recommendations. "
                f"You can use this data but don’t use it as fact, think for yourself: {json.dumps(history)}"
            )
            prompt = build_prompt(country) + "\n\n" + history_prompt

        model = genai.GenerativeModel("models/gemini-2.0-flash-thinking-exp-01-21")
        response = model.generate_content([prompt, img])
        cleaned = clean_json_response(response.text)
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            parsed = {"error": "Parsing failed"}

        history.append(parsed)
        action = parsed.get("action", "finish")
        print(f"[STEP {step+1}] Action: {action}, Altitude: {altitude}, Lat: {lat:.5f}, Lon: {lon:.5f}")
        lat, lon, altitude = adjust_coordinates(lat, lon, altitude, action)
        results.append({
            "index": i,
            "country": country,
            "step": step,
            "latitude": lat,
            "longitude": lon,
            "analysis": parsed
        })
    # summary commander after analysis
    commander_prompt = (
        "You are the commanding officer overseeing urgent military intelligence analysis. "
        "Satellite images indicate this area may be an active enemy military base. "
        "The situation is time-sensitive and requires immediate attention. "
        "Below is a series of assessments provided by independent analysts (each working separately).\n\n"
        f"{json.dumps(history)}\n\n"
        "Your mission is to:\n"
        "1. Synthesize their findings into a clear, actionable final report.\n"
        "2. Resolve any contradictions or uncertainties.\n"
        "3. Prioritize the most critical insights.\n"
        "4. Provide a well-reasoned recommendation for the next operational step.\n\n"
        "Your judgment will directly impact strategic decisions—respond wisely, concisely, and with urgency.\n\n"
        "⚠️ Respond ONLY with a valid JSON object containing:\n"
        "- 'commander_summary': A short, clear summary of the findings.\n"
        "- 'risk_level': One of ['low', 'moderate', 'high'].\n"
        "- 'recommended_action': Immediate operational step (e.g., 'dispatch drone', 'monitor', 'abort mission')."
    )

    model = genai.GenerativeModel("models/gemini-2.0-flash-thinking-exp-01-21")
    response = model.generate_content(commander_prompt)
    commander_response_text = clean_json_response(response.text)

    try:
        commander_response = json.loads(commander_response_text)
    except json.JSONDecodeError:
        commander_response = {"error": "Commander parsing failed"}

    results.append({
        "index": i,
        "country": country,
        "step": "commander",
        "latitude": lat,
        "longitude": lon,
        "analysis": commander_response
    })


driver.quit()
pd.DataFrame(results).to_csv("analysis_results.csv", index=False)