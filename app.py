import os
from dotenv import load_dotenv

load_dotenv("/home/bandana07/professional-photography-planner-main/.env")

import re
import requests
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, request, redirect, url_for
from database import db, User
from werkzeug.security import generate_password_hash, check_password_hash
app = Flask(__name__)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///users.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

with app.app_context():
    db.create_all()

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
        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}&daily=uv_index_max&timezone=auto"
        )
        response = requests.get(url, timeout=10)
        data = response.json()
        uv = data["daily"]["uv_index_max"][0]
        return round(uv, 1)
    except Exception:
        return None


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

    # Bad weather
    if condition in ["rain", "thunderstorm", "snow", "drizzle"]:
        return "Not Ideal"

    # Very windy
    if wind > 8:
        return "Not Ideal"

    # Night photography
    if time_period == "Nighttime Conditions":
        if condition == "clear":
            return "Good"
        else:
            return "Fair"

    # Excellent photography conditions
    if (
        condition == "clear"
        and 15 <= temp <= 25
        and humidity <= 70
        and wind <= 4
        and (uv is None or uv <= 6)
    ):
        return "Excellent"

    # Good photography conditions
    if (
        condition in ["clear", "clouds"]
        and 10 <= temp <= 30
        and wind <= 8
    ):
        return "Good"

    return "Fair"
    @app.route("/register", methods=["GET", "POST"])
def register():
    message = None

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        hashed_password = generate_password_hash(password)

        user = User(username=username, password=hashed_password)
        db.session.add(user)
        db.session.commit()

        message = "User registered successfully."

    return message or "Register page"


@app.route("/login", methods=["GET", "POST"])
def login():
    message = None

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            message = "Login successful."
        else:
            message = "Invalid username or password."

    return message or "Login page"


@app.route("/", methods=["GET", "POST"])
def index():
    weather = None
    error = None

    if request.method == "POST":
        city = clean_city(request.form.get("city", ""))

        if not city:
            error = "Please enter a valid Australian city."
            return render_template("index.html", weather=weather, error=error)

        try:
            current_url = (
                f"https://api.openweathermap.org/data/2.5/weather?"
                f"q={city},AU&appid={OPENWEATHER_API_KEY}&units=metric"
            )

            response = requests.get(current_url, timeout=10)
            data = response.json()

            if response.status_code != 200:
                error = "City not found. Please try another Australian city."
                return render_template("index.html", weather=weather, error=error)

            temp = round(data["main"]["temp"])
            feels_like = round(data["main"]["feels_like"])
            humidity = data["main"]["humidity"]
            wind = round(data["wind"]["speed"], 2)
            condition = data["weather"][0]["main"]
            description = data["weather"][0]["description"].title()
            icon_code = data["weather"][0]["icon"]

            sunrise = data["sys"]["sunrise"]
            sunset = data["sys"]["sunset"]
            timezone_offset = data["timezone"]

            lat = data["coord"]["lat"]
            lon = data["coord"]["lon"]

            uv = get_uv_index(lat, lon)
            rain_risk = "Low"

            if condition.lower() in ["rain", "drizzle", "thunderstorm"]:
               rain_risk = "High"

            sunrise_dt = datetime.fromtimestamp(sunrise, timezone.utc) + timedelta(seconds=timezone_offset)
            sunset_dt = datetime.fromtimestamp(sunset, timezone.utc) + timedelta(seconds=timezone_offset)
            current_dt = datetime.now(timezone.utc) + timedelta(seconds=timezone_offset)

            if sunrise_dt <= current_dt <= sunset_dt:
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
                "uv": uv,
                "rain_risk": rain_risk,
                "uv_advice": uv_message,
                "time_period": time_period,
                "time_icon": time_icon,
                "theme_class": theme_class,
            }

        except Exception:
            error = "Something went wrong. Please check your API key or internet connection."

    return render_template("index.html", weather=weather, error=error)
if __name__ == "__main__":
    app.run(debug=True)
