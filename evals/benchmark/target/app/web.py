import requests
from flask import Flask, redirect, render_template_string, request

app = Flask(__name__)


@app.route("/hello")
def hello():
    name = request.args.get("name", "")
    return render_template_string("<h1>Hello " + name + "</h1>")


@app.route("/fetch")
def fetch():
    return requests.get(request.args["url"], timeout=5).text


@app.route("/go")
def go():
    return redirect(request.args.get("next", "/"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)
