import os
from dotenv import load_dotenv

load_dotenv("/home/bandana07/professional-photography-planner-main/.env")

import re
import requests
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, request, redirect, url_for, session

app = Flask(__name__)
app.secret_key = "photography_planner_secret_key"

DATABASE = "database.db"

def init_db():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fullname TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS favourites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT NOT NULL,
            location TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS search_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT NOT NULL,
            city TEXT NOT NULL,
            searched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()

init_db()

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")


def clean_city(city):
    city = city.strip()
    city = re.sub(r"[^a-zA-Z\s,]", "", city)
    return city


def format_time(timestamp, timezone_offset):
    local_time = datetime.fromtimestamp(timestamp, timezone.utc) + timedelta(seconds=timezone_offset)
    return local_time.strftime("%I:%M %p")


def get_uv_index(lat, lon):
    try:
        # Requesting uv_index_max and moon_phase from Open-Meteo
        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}"
            f"&daily=uv_index_max,moon_phase"
            f"&current=sun_azimuth,sun_elevation"
            f"&timezone=auto"
        )
        response = requests.get(url, timeout=10)
        data = response.json()

        uv = data.get("daily", {}).get("uv_index_max", [None])[0]
        azimuth = data.get("current", {}).get("sun_azimuth", None)
        elevation = data.get("current", {}).get("sun_elevation", None)

        # Get the moon phase number (0.0 to 1.0)
        moon_val = data.get("daily", {}).get("moon_phase", [None])[0]
        moon_phase_str = "N/A"

        if moon_val is not None:
            if moon_val == 0.0 or moon_val == 1.0:
                moon_phase_str = "New Moon 🌑"
            elif 0.0 < moon_val < 0.25:
                moon_phase_str = "Waxing Crescent 🌒"
            elif moon_val == 0.25:
                moon_phase_str = "First Quarter 🌓"
            elif 0.25 < moon_val < 0.5:
                moon_phase_str = "Waxing Gibbous 🌔"
            elif moon_val == 0.5:
                moon_phase_str = "Full Moon 🌕"
            elif 0.5 < moon_val < 0.75:
                moon_phase_str = "Waning Gibbous 🌖"
            elif moon_val == 0.75:
                moon_phase_str = "Third Quarter 🌗"
            else:
                moon_phase_str = "Waning Crescent 🌘"

        return {
            "uv": round(uv, 1) if uv is not None else None,
            "sun_azimuth": round(azimuth) if azimuth is not None else "N/A",
            "sun_elevation": round(elevation) if elevation is not None else "N/A",
            "moon_phase": moon_phase_str
        }
    except Exception:
        return {"uv": None, "sun_azimuth": "N/A", "sun_elevation": "N/A", "moon_phase": "N/A"}


def uv_advice(uv, time_period):
    if time_period == "Nighttime Conditions":
        return "Nighttime conditions. UV exposure is minimal."

    if uv is None:
        return "UV data not available."

    if uv <= 2:
        return "Low UV. Excellent for outdoor photography."
    elif uv <= 5:
        return "Moderate UV. Good for photography, use sun protection."
    elif uv <= 7:
        return "High UV. Avoid long outdoor shoots."
    else:
        return "Very high UV. Schedule shoots during Golden Hour."


def photography_rating(temp, humidity, wind, condition, uv, time_period):
    condition = condition.lower()

    # Bad weather conditions
    if condition in ["rain", "thunderstorm", "snow", "drizzle"]:
        return "Not Ideal"

    # Very windy conditions (adjusted for kph)
    if wind > 30:
        return "Not Ideal"

    # Night photography rules
    if time_period == "Nighttime Conditions":
        if condition == "clear":
            return "Good"
        else:
            return "Fair"

    # Excellent daytime conditions (adjusted wind threshold to 15 kph)
    if (
        condition == "clear"
        and 15 <= temp <= 25
        and humidity <= 70
        and wind <= 15
        and (uv is None or uv <= 6)
    ):
        return "Excellent"

    # Good daytime conditions (adjusted wind threshold to 25 kph)
    if (
        condition in ["clear", "clouds"]
        and 10 <= temp <= 30
        and wind <= 25
    ):
        return "Good"

    return "Fair"

def get_summary_title(rating):
    if rating == "Excellent":
        return "Excellent photography conditions today."
    elif rating == "Good":
        return "Good photography conditions today."
    elif rating == "Fair":
        return "Photography conditions are fair today."
    else:
        return "Outdoor photography is not recommended today."


def get_summary_text(rating, condition, rain_risk, wind):
    condition = condition.lower()

    # 1. Figure out the base summary
    if rating == "Excellent":
        base_summary = "Low rain chance, comfortable weather and light winds make today ideal for outdoor photography."
    elif rating == "Good":
        if "cloud" in condition:
            base_summary = "Cloudy skies can create soft and even lighting, which is great for portraits."
        else:
            base_summary = "Weather conditions are generally good for outdoor photography."
    elif rating == "Fair":
        base_summary = "Weather conditions are acceptable, but rain risk or wind may affect your session."
    else:
        base_summary = "Rain, strong wind or poor weather conditions may make outdoor photography difficult."

    # 2. Figure out the wind warning (assuming 'wind' is passed in km/h)
    if wind > 30:
        wind_note = f" 💨 WARNING: Very windy ({wind} km/h). Drone flights not recommended. Secure your tripods!"
    elif wind > 15:
        wind_note = f" 💨 Breezy ({wind} km/h). Watch for motion blur in trees and hold light stands steady."
    else:
        wind_note = f" 🍃 Wind is calm at {wind} km/h."

    # 3. Glue them together and return it!
    return base_summary + wind_note


def get_summary_tip(rating):
    if rating == "Excellent":
        return "Use golden hour for warm and soft natural lighting."
    elif rating == "Good":
        return "Cloud cover is useful for soft portrait lighting."
    elif rating == "Fair":
        return "Check the hourly forecast before heading out."
    else:
        return "Consider indoor photography or protect your camera equipment."


@app.route("/", methods=["GET"])
def index():
    # If the user is not logged in, send them to the login page
    if "user" not in session:
        return redirect(url_for("login"))

    # Detect time of day for the home page theme background
    current_hour = datetime.now().hour
    theme_class = "day-theme" if (6 <= current_hour < 18) else "night-theme"

    return render_template("index.html", theme=theme_class)

@app.route('/weather', methods=['GET', 'POST'])
def weather_page():

    # Redirect users to login if they are not logged in
    if "user" not in session:
        return redirect(url_for("login"))

    weather = None
    forecast_48h = []
    error = None
    uv_rec = "UV recommendation is not available."

    url_city = request.args.get('city')

    if url_city:
        # The favourites link sends "City, State, Country". This splits it at the comma so we only search for "City"
        only_the_city = url_city.split(",")[0].strip()
        city = clean_city(only_the_city)
    else:
        city = None

    if request.method == "POST" or city:
        if request.method == "POST":
            city = clean_city(request.form.get("city", ""))

        if not city:
            error = "Please enter a valid city."
            return render_template("index.html", weather=None, error=error, theme="dark")

        try:
            # 1. Geocoding: Get coordinates for the city name
            geo_url = f"http://api.openweathermap.org/geo/1.0/direct?q={city}&limit=1&appid={OPENWEATHER_API_KEY}"
            geo_response = requests.get(geo_url, timeout=10)
            geo_data = geo_response.json()

            if not geo_data:
                error = "City not found. Please try another city."
                return render_template("index.html", weather=None, error=error, theme="day-theme")

            # Extract lat/lon
            lat = geo_data[0]['lat']
            lon = geo_data[0]['lon']

            # 2. Weather: Use coordinates instead of city name
            current_url = (
                f"https://api.openweathermap.org/data/2.5/weather?"
                f"lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}&units=metric"
            )

            response = requests.get(current_url, timeout=10)
            data = response.json()

            if response.status_code != 200:
                error = "City not found. Please try another city."
                return render_template("index.html", weather=weather, error=error)


            temp = round(data["main"]["temp"])
            feels_like = round(data["main"]["feels_like"])
            humidity = data["main"]["humidity"]
            pressure = data["main"].get("pressure")
            wind = round(data["wind"]["speed"], 2)
            condition = data["weather"][0]["main"]
            description = data["weather"][0]["description"].title()
            icon_code = data["weather"][0]["icon"]


            sunrise = data["sys"]["sunrise"]
            sunset = data["sys"]["sunset"]
            timezone_offset = data["timezone"]

            weather_timestamp = data.get("dt")

            if weather_timestamp is not None:
                local_updated_time = datetime.fromtimestamp(
                    weather_timestamp + timezone_offset,
                    tz=timezone.utc
                )
                last_updated = local_updated_time.strftime("%I:%M %p")
            else:
                last_updated = "N/A"

            # Grab lat and lon from your working OpenWeatherMap request above this
            lat = data.get('coord', {}).get('lat')
            lon = data.get('coord', {}).get('lon')

            if lat and lon:
            # forecast_days=2 forces the API to cross the midnight wall
            # forecast_hours=25 gives us the current hour + the next 24 hours
                om_url = (
                    f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                    f"&hourly=temperature_2m,precipitation_probability,wind_speed_10m,relative_humidity_2m,weather_code,is_day"
                    f"&daily=uv_index_max" # Add this!
                    f"&wind_speed_unit=ms&timezone=auto&forecast_days=2&forecast_hours=25"
                )
            om_response = requests.get(om_url, timeout=10)

            if om_response.status_code == 200:
                om_data = om_response.json()
                hourly = om_data.get('hourly', {})

                daily = om_data.get('daily', {})
                uv_values = daily.get("uv_index_max") or []

                if uv_values and uv_values[0] is not None:
                    uv_max = round(float(uv_values[0]), 1)
                else:
                    uv_max = None

                uv = uv_max

                if uv_max is None:
                    uv_rec = "UV recommendation is not available."

                elif uv_max < 3:
                    uv_rec = f"Max UV Index: {uv_max}. Low risk. Safe for all-day outdoor shooting."

                elif uv_max < 6:
                    uv_rec = f"Max UV Index: {uv_max}. Moderate risk. Wear sunscreen if shooting outside."

                elif uv_max < 8:
                    uv_rec = f"Max UV Index: {uv_max}. High risk. Seek shade when reviewing photos."

                else:
                    uv_rec = f"Max UV Index: {uv_max}. Very high risk. Avoid shooting in direct sun."

                # range(1, ...) skips index 0 (the current hour) and starts at the next hour!
                for i in range(1, len(hourly.get('time', []))):
                    raw_time = hourly['time'][i]
                    dt_obj = datetime.strptime(raw_time, "%Y-%m-%dT%H:%M")
                    display_time = dt_obj.strftime("%-I %p")

                    f_temp = round(hourly['temperature_2m'][i])
                    f_rain = hourly['precipitation_probability'][i]
                    f_wind = round(hourly['wind_speed_10m'][i], 2)
                    f_humidity = hourly['relative_humidity_2m'][i]

                    if f_rain < 20 and f_wind < 6:
                        f_rating = "Excellent"
                    elif f_rain < 40 and f_wind < 8:
                        f_rating = "Good"
                    elif f_rain < 60:
                        f_rating = "Moderate"
                    else:
                        f_rating = "Not Ideal"

                    is_day = hourly.get('is_day', [])[i]
                    suffix = "d" if is_day == 1 else "n"
                    code = hourly['weather_code'][i]

                    if code == 0: f_icon = f"01{suffix}"
                    elif code == 1: f_icon = f"02{suffix}"
                    elif code == 2: f_icon = f"03{suffix}"
                    elif code == 3: f_icon = f"04{suffix}"
                    elif code in [45, 48]: f_icon = f"50{suffix}"
                    elif code in [51, 53, 55, 61, 63, 65, 80, 81, 82]: f_icon = f"10{suffix}"
                    elif code in [71, 73, 75, 85, 86]: f_icon = f"13{suffix}"
                    elif code in [95, 96, 99]: f_icon = f"11{suffix}"
                    else: f_icon = f"04{suffix}"

                    final_icon_url = f"https://openweathermap.org/img/wn/{f_icon}@2x.png"

                    if f_rain >= 30:
                        final_icon_url = f"https://openweathermap.org/img/wn/09{suffix}@2x.png"

                    if f_wind >= 6:
                        final_icon_url = "data:image/svg+xml;charset=UTF-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2264%22%20height%3D%2264%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22%237dd3fc%22%20stroke-width%3D%222%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%3E%3Cpath%20d%3D%22M9.59%204.59A2%202%200%201%201%2011%208H2m10.59%2011.41A2%202%200%201%200%2014%2016H2m15.73-8.27A2.5%202.5%200%201%201%2019.5%2012H2%22%2F%3E%3C%2Fsvg%3E"

                    forecast_48h.append({
                        "time": display_time,
                        "temp": f_temp,
                        "condition": "Forecast",
                        "icon": final_icon_url,
                        "humidity": f_humidity,
                        "wind": f_wind,
                        "rain": f_rain,
                        "rating": f_rating
                    })

            uv = get_uv_index(lat, lon)

            # Fetch solar position and UV data together
            solar_data = get_uv_index(lat, lon)
            uv = solar_data["uv"]
            sun_azimuth = solar_data["sun_azimuth"]
            sun_elevation = solar_data["sun_elevation"]
            moon_phase = solar_data["moon_phase"]

            rain_risk = 20

            if condition.lower() in ["rain", "drizzle"]:
                rain_risk = 60
            elif condition.lower() == "thunderstorm":
                rain_risk = 90

            sunrise_dt = datetime.fromtimestamp(sunrise, timezone.utc) + timedelta(seconds=timezone_offset)
            sunset_dt = datetime.fromtimestamp(sunset, timezone.utc) + timedelta(seconds=timezone_offset)
            current_dt = datetime.now(timezone.utc) + timedelta(seconds=timezone_offset)

            # ADDED THIS LINE: Defines is_day so the code below doesn't crash
            is_day = sunrise_dt <= current_dt <= sunset_dt

            if is_day:
                time_period = "Daytime Conditions"
                time_icon = "🌞"
                theme_class = "day-theme"
            else:
                time_period = "Nighttime Conditions"
                time_icon = "🌙"
                theme_class = "night-theme"

            morning_golden = f"{sunrise_dt.strftime('%I:%M %p')} - {(sunrise_dt + timedelta(hours=1)).strftime('%I:%M %p')}"
            evening_golden = f"{(sunset_dt - timedelta(hours=1)).strftime('%I:%M %p')} - {sunset_dt.strftime('%I:%M %p')}"
            morning_blue = f"{(sunrise_dt - timedelta(minutes=30)).strftime('%I:%M %p')} - {sunrise_dt.strftime('%I:%M %p')}"
            evening_blue = f"{sunset_dt.strftime('%I:%M %p')} - {(sunset_dt + timedelta(minutes=30)).strftime('%I:%M %p')}"

            rating = photography_rating(temp, humidity, wind, condition, uv, time_period)
            uv_message = uv_advice(uv, time_period)
            summary_title = get_summary_title(rating)
            summary_text = get_summary_text(rating, condition, rain_risk, wind)
            summary_tip = get_summary_tip(rating)

            # =====================================================
            # Photography Insight
            # =====================================================

            if rating == "Excellent":

                insight_overall = "🟢 Excellent"

                insight_why = [
                   "Clear skies provide bright, natural lighting.",
                   "Excellent visibility produces sharp, detailed images.",
                   "Light wind keeps the camera stable."
                ]

                insight_best = [
                   "Capture landscapes during the golden hour.",
                   "Use a tripod for maximum sharpness.",
                   "Take advantage of the clear sky for wide-angle photography."
                ]

                insight_tips = [
                   "Avoid harsh midday sunlight.",
                   "Use a lens hood to reduce glare.",
                   "Carry water and sunscreen during long outdoor shoots."
                ]


            elif rating == "Good":

                insight_overall = "🟡 Good"

                insight_why = [
                   "Soft cloud cover creates balanced natural lighting.",
                   "Low rain risk makes outdoor photography comfortable.",
                   "Light wind helps reduce camera movement."
                ]

                insight_best = [
                   "Portrait photography works well in these conditions.",
                   "Shoot during the golden hour for warmer colours.",
                   "Position your subject to make the most of the soft light."
                ]

                insight_tips = [
                   "Carry a microfiber cloth for your lens.",
                   "UV is moderate around midday.",
                   "Cloud cover may reduce colourful sunsets."
                ]


            elif rating == "Fair":

                insight_overall = "🟠 Fair"

                insight_why = [
                   "Photography is still possible.",
                   "Cloud cover reduces available natural light.",
                   "Weather conditions may change throughout the day."
                ]

                insight_best = [
                   "Increase ISO when required.",
                   "Use a wider aperture.",
                   "Look for sheltered shooting locations."
                ]

                insight_tips = [
                   "Carry a waterproof camera cover.",
                   "Monitor the weather before travelling.",
                   "Keep spare batteries warm and dry."
                ]


            else:

                insight_overall = "🔴 Poor"

                insight_why = [
                   "Heavy rain reduces visibility.",
                   "Strong wind may cause camera shake.",
                   "Outdoor photography is difficult."
                ]

                insight_best = [
                   "Move to an indoor location.",
                   "Use weather-sealed equipment.",
                   "Wait for a break in the weather before shooting."
                ]

                insight_tips = [
                   "Protect your camera from moisture.",
                   "Avoid slippery shooting locations.",
                   "Use a rain cover for your lens."
                ]

            alerts = []

            # Weather condition alerts
            if condition.lower() == "clear":
                alerts.append("☀️ Clear skies. Excellent lighting for outdoor photography.")
            elif condition.lower() == "clouds":
                alerts.append("☁️ Cloud cover provides soft, even lighting. Great for portrait photography.")
            elif condition.lower() == "mist":
                alerts.append("🌫️ Mist creates a dramatic atmosphere but may reduce visibility.")
            elif condition.lower() == "fog":
                alerts.append("🌫️ Dense fog may reduce visibility. Use caution while shooting.")
            elif condition.lower() == "snow":
                alerts.append("❄️ Snow creates beautiful scenery. Protect your camera from moisture.")
            elif condition.lower() == "thunderstorm":
                alerts.append("⛈️ Thunderstorms are dangerous. Outdoor photography is not recommended.")
            elif condition.lower() == "squall":
                alerts.append("💨 Very windy conditions. Use a sturdy tripod and secure your equipment.")

            # Risk alerts
            if rain_risk >= 80:
                alerts.append("⛈️ Very high rain risk. Outdoor photography is not recommended.")
            elif rain_risk >= 60:
                alerts.append("☔ Moderate rain risk. Carry waterproof protection for your camera.")

            if uv and uv >= 8: # CHANGED: Added safety check for 'uv' so it doesn't break if UV is None
                alerts.append("☀️ Very high UV. Use sunscreen and protect camera equipment.")

            if wind >= 35:
                alerts.append("💨 Strong wind may affect tripod stability.")

            if temp >= 35:
                alerts.append("🔥 Very hot conditions. Stay hydrated during outdoor shoots.")

            # Default message
            if not alerts:
                alerts.append("✅ No major weather alerts. Conditions are suitable for photography.")

            visibility_km = round(data.get("visibility", 10000) / 1000)
            clouds_percent = data.get("clouds", {}).get("all", 0)
            wind_direction_deg = data.get("wind", {}).get("deg", 0)

            # Convert wind angle to clean cardinal directions (N, NE, E, etc.)
            cardinals = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
            wind_cardinal = cardinals[round(wind_direction_deg / 45) % 8]

            # Simple logic for long-exposure water reflections
            reflection_suitability = "Perfect (Glassy)" if wind <= 4 else "Choppy / Rippled"

            # Your existing alerts, ratings, and time logic stays right here...

            weather = {
                "city": data["name"],
                "country": data["sys"]["country"],
                "temp": temp,
                "feels_like": feels_like,
                "humidity": humidity,
                "wind": wind,
                "condition": condition,
                "description": description,
                "icon_url": f"https://openweathermap.org/img/wn/{icon_code}@2x.png",
                "sunrise": format_time(sunrise, timezone_offset),
                "sunset": format_time(sunset, timezone_offset),
                "morning_golden": morning_golden,
                "evening_golden": evening_golden,
                "morning_blue": morning_blue,
                "evening_blue": evening_blue,
                "rating": rating,
                "summary_title": summary_title,
                "summary_text": summary_text,
                "summary_tip": summary_tip,
                "uv": uv_max,
                "sun_azimuth": sun_azimuth,
                "sun_elevation": sun_elevation,
                "moon_phase": moon_phase,
                "rain_risk": rain_risk,
                "alerts": alerts,
                "time_period": time_period,
                "time_icon": time_icon,
                "theme_class": theme_class,
                "theme": theme_class,
                "wind_direction": wind_cardinal,
                "visibility": visibility_km,
                "clouds_percent": clouds_percent,
                "reflection_suitability": reflection_suitability,
                "uv_rec": uv_rec,  # <--- ADD THIS EXACT LINE HERE!
                "pressure": pressure,
                "last_updated": last_updated,
                "insight_overall": insight_overall,
                "insight_why": insight_why,
                "insight_best": insight_best,
                "insight_tips": insight_tips,
            }


            condition_text = weather["description"].lower()

            if "rain" in condition_text or "drizzle" in condition_text or "thunder" in condition_text:
                weather["theme"] = "rain-theme"
            elif "snow" in condition_text:
                weather["theme"] = "snow-theme"
            elif "cloud" in condition_text or "overcast" in condition_text:
                weather["theme"] = "cloud-theme"
            elif "clear" in condition_text:
                if is_day:
                    weather["theme"] = "day-theme"
                else:
                    weather["theme"] = "night-theme"
            else:
                if is_day:
                    weather["theme"] = "day-theme"
                else:
                    weather["theme"] = "night-theme"

            if "user" in session:
                conn = sqlite3.connect(DATABASE)
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO search_history (user_email, city) VALUES (?, ?)",
                    (session["user"], city)
                )
                conn.commit()
                conn.close()

        except Exception as e:
            error = str(e)

        # --- 7-DAY FORECAST LOGIC ---
        forecast_7d = []
        if 'lat' in locals() and 'lon' in locals() and lat and lon:
            daily_url = (
                f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                f"&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
                f"&timezone=auto&forecast_days=7"
            )
            daily_response = requests.get(daily_url, timeout=10)

            if daily_response.status_code == 200:
                daily_data = daily_response.json().get('daily', {})

                for i in range(len(daily_data.get('time', []))):
                    raw_date = daily_data['time'][i]
                    date_obj = datetime.strptime(raw_date, "%Y-%m-%d")
                    day_name = date_obj.strftime("%A")

                    if i == 0:
                        day_name = "Today"

                    d_max = round(daily_data['temperature_2m_max'][i])
                    d_min = round(daily_data['temperature_2m_min'][i])
                    d_rain = daily_data['precipitation_probability_max'][i]
                    d_code = daily_data['weather_code'][i]

                    if d_code == 0: d_icon = "01d"
                    elif d_code == 1: d_icon = "02d"
                    elif d_code == 2: d_icon = "03d"
                    elif d_code == 3: d_icon = "04d"
                    elif d_code in [45, 48]: d_icon = "50d"
                    elif d_code in [51, 53, 55, 61, 63, 65, 80, 81, 82]: d_icon = "10d"
                    elif d_code in [71, 73, 75, 85, 86]: d_icon = "13d"
                    elif d_code in [95, 96, 99]: d_icon = "11d"
                    else: d_icon = "04d"

                    d_icon_url = f"https://openweathermap.org/img/wn/{d_icon}@2x.png"

                    # Keep the strict 30% photography rain rule for the daily forecast!
                    if d_rain >= 30:
                        d_icon_url = "https://openweathermap.org/img/wn/09d@2x.png"

                    forecast_7d.append({
                        "day": day_name,
                        "max": d_max,
                        "min": d_min,
                        "rain": d_rain,
                        "icon": d_icon_url
                    })

        # FIXED: Now passes 'theme=weather["theme"]' so your weather page loads the right theme background color/image!
        return render_template(
            "weather.html",
            weather=weather,
            forecast_48h=forecast_48h,
            forecast_7d=forecast_7d,
            error=error,
            theme=weather["theme"] if weather else "home-theme"
        )

@app.route("/login", methods=["GET", "POST"])
def login():
    if "user" in session:
        return redirect(url_for("index"))
    error = None

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        if not email:
            error = "Email is required."
        elif "@" not in email:
            error = "Please enter a valid email address."
        elif not password:
            error = "Password is required."
        else:
            conn = sqlite3.connect(DATABASE)
            cursor = conn.cursor()

            cursor.execute(
                "SELECT password FROM users WHERE email = ?",
                (email,)
            )

            user = cursor.fetchone()
            conn.close()

            if user and check_password_hash(user[0], password):
                session["user"] = email
                return redirect(url_for("index"))
            else:
                error = "Invalid email or password."

    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if "user" in session:
        return redirect(url_for("index"))
    error = None
    success = None

    if request.method == "POST":
        fullname = request.form.get("fullname", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()

        if not fullname:
            error = "Full name is required."
        elif not email:
            error = "Email is required."
        elif "@" not in email:
            error = "Please enter a valid email address."
        elif len(password) < 8:
            error = "Password must be at least 8 characters."
        elif password != confirm_password:
            error = "Passwords do not match."
        else:
            hashed_password = generate_password_hash(password)

            try:
                conn = sqlite3.connect(DATABASE)
                cursor = conn.cursor()

                cursor.execute(
                    "INSERT INTO users (fullname, email, password) VALUES (?, ?, ?)",
                    (fullname, email, hashed_password)
                )

                conn.commit()
                conn.close()

                return redirect(url_for("login"))

            except sqlite3.IntegrityError:
                error = "This email is already registered. Please use another email."

    return render_template("register.html", error=error, success=success)


from datetime import datetime, timezone, timedelta

@app.route("/favourites", methods=["GET", "POST"])
def favourites():
    if "user" not in session:
        return redirect(url_for("login"))

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Handle adding a new location via the Geocoding API
    if request.method == "POST":
        location_input = request.form.get("location", "").strip()
        if location_input:
            api_key = os.environ.get("OPENWEATHER_API_KEY")
            if api_key:
                geo_url = f"http://api.openweathermap.org/geo/1.0/direct?q={location_input}&limit=1&appid={api_key}"
                try:
                    response = requests.get(geo_url).json()
                    if len(response) > 0:
                        geo_data = response[0]
                        city = geo_data.get("name")
                        state = geo_data.get("state", "")
                        country = geo_data.get("country", "")

                        if state:
                            official_location = f"{city}, {state}, {country}"
                        else:
                            official_location = f"{city}, {country}"

                        cursor.execute(
                            "INSERT INTO favourites (user_email, location) VALUES (?, ?)",
                            (session["user"], official_location)
                        )
                        conn.commit()
                except Exception as e:
                    print(f"API Error: {e}")

    # Fetch saved favourites
    cursor.execute(
        "SELECT id, location FROM favourites WHERE user_email = ?",
        (session["user"],)
    )
    raw_favourites = cursor.fetchall()
    conn.close()

    # Process each favourite to attach live, dynamic Golden Hour data
    processed_favourites = []
    api_key = os.environ.get("OPENWEATHER_API_KEY")

    for fav in raw_favourites:
        fav_id = fav[0]
        full_location_string = fav[1]

        # Default placeholder times in case the API call fails
        morning_golden = "6:00 AM – 7:00 AM"
        evening_golden = "5:30 PM – 6:30 PM"

        if api_key:
            # Fetch current weather data to get sunrise, sunset, and local timezone offset
            weather_url = f"http://api.openweathermap.org/data/2.5/weather?q={full_location_string}&appid={api_key}"
            try:
                w_resp = requests.get(weather_url).json()
                if w_resp.get("cod") == 200:
                    sunrise_raw = w_resp["sys"]["sunrise"]
                    sunset_raw = w_resp["sys"]["sunset"]
                    timezone_offset = w_resp.get("timezone", 0) # Offset in seconds from UTC

                    # Convert UTC timestamps to the target location's local time using the offset
                    local_tz = timezone(timedelta(seconds=timezone_offset))
                    sunrise_dt = datetime.fromtimestamp(sunrise_raw, tz=local_tz)
                    sunset_dt = datetime.fromtimestamp(sunset_raw, tz=local_tz)

                    # Calculate Golden Hour windows (1 hour following sunrise, 1 hour preceding sunset)
                    m_start = sunrise_dt.strftime("%I:%M %p")
                    m_end = (sunrise_dt + timedelta(hours=1)).strftime("%I:%M %p")
                    morning_golden = f"{m_start} – {m_end}"

                    e_start = (sunset_dt - timedelta(hours=1)).strftime("%I:%M %p")
                    e_end = sunset_dt.strftime("%I:%M %p")
                    evening_golden = f"{e_start} – {e_end}"
            except Exception as e:
                print(f"Error fetching solar data for {full_location_string}: {e}")

        # Append structured data packet back to the list
        processed_favourites.append({
            "id": fav_id,
            "location_string": full_location_string,
            "morning_golden": morning_golden,
            "evening_golden": evening_golden
        })

    return render_template("favourites.html", favourites=processed_favourites)

@app.route("/history")
def history():
    if "user" not in session:
        return redirect(url_for("login"))

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT city, searched_at FROM search_history WHERE user_email = ? ORDER BY searched_at DESC LIMIT 10",
        (session["user"],)
    )

    history = cursor.fetchall()
    conn.close()

    return render_template("history.html", history=history)

@app.route("/remove_favourite/<int:fav_id>")
def remove_favourite(fav_id):
    if "user" not in session:
        return redirect(url_for("login"))

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM favourites WHERE id = ? AND user_email = ?",
        (fav_id, session["user"])
    )

    conn.commit()
    conn.close()

    return redirect(url_for("favourites"))

@app.route('/weather-by-coords')
def weather_by_coords():
    lat = request.args.get('lat')
    lon = request.args.get('lon')

    if not lat or not lon:
        return redirect(url_for('home'))

    try:
        geo_url = f"https://api.bigdatacloud.net/data/reverse-geocode-client?latitude={lat}&longitude={lon}&localityLanguage=en"
        response = requests.get(geo_url, timeout=5)

        if response.status_code == 200:
            data = response.json()

            # Check cityDistrict (like Liverpool), city, locality (like Macquarie Fields), or fallback
            city_name = data.get('cityDistrict') or data.get('city') or data.get('locality') or "Sydney"

            # Clean up trailing words like "City of Liverpool" if the API returns it that way
            if "City of " in city_name:
                city_name = city_name.replace("City of ", "")
        else:
            city_name = "Sydney"

        return redirect(url_for('weather_page', city=city_name))

    except Exception:
        return redirect(url_for('weather_page', city="Sydney"))
