from flask import Flask, render_template

app = Flask(__name__)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/hello")
def hello():
    return "Hello World"
    @app.route("/health")
def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    app.run()
@app.errorhandler(404)
def page_not_found(error):
    return "Page not found", 404
