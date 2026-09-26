from fastapi import FastAPI

app = FastAPI(title="Sentinel API")


@app.get("/")
def root():
    return {"message": "Sentinel API is running"}