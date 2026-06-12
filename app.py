from flask import Flask, render_template, request
import requests

app = Flask(__name__)

API_KEY = "16cbb45a0c4032115c3e4244ccbdd00f"

def get_suitability(condition, wind_speed):
    condition = condition.lower()

    if "clear" in condition and wind_speed <= 5:
        return "Excellent"
    elif "cloud" in condition and wind_speed <= 8:
        return "Good"
    elif "rain" in condition or wind_speed > 12:
        return "Not Ideal"
    else:
        return "Moderate"

@app.route("/", methods=["GET", "POST"])
def home():
    weather = None
    error = None

    if request.method == "POST":
        city = request.form.get("city", "").strip()

        if not city:
            error = "⚠️ Please enter a city name before checking photography conditions."
            return render_template("index.html", weather=weather, error=error)

        url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={API_KEY}&units=metric"

        try:
            response = requests.get(url)
            data = response.json()

            if response.status_code == 200:
                condition = data["weather"][0]["main"]
                wind_speed = data["wind"]["speed"]

                weather = {
                    "city": data["name"],
                    "temperature": round(data["main"]["temp"]),
                    "condition": condition,
                    "humidity": data["main"]["humidity"],
                    "wind_speed": wind_speed,
                    "suitability": get_suitability(condition, wind_speed)
                }
            else:
                error = "❌ We could not find that city. Please check the spelling and try again."

        except Exception:
            error = "⚠️ Weather service is temporarily unavailable. Please try again later."

    return render_template("index.html", weather=weather, error=error)

@app.route("/hello")
def hello():
    return "Hello World"

if __name__ == "__main__":
    app.run(debug=True)
