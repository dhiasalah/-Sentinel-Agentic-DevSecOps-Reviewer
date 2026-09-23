from fastapi import FastAPI

# TODO(student): create the FastAPI application object and store it in a variable called `app`.
#   Give it a title "Sentinel API" (look for the `title` parameter in the First Steps docs).
app = ...


@app.get("/")
def root():
    # TODO(student): return a dict with one key "message" and a welcome text as the value.
    ...
