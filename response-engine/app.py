from fastapi import FastAPI
import subprocess

app = FastAPI()

@app.get("/")
def home():
    return {"status": "Response Engine Running"}

@app.post("/block_ip")
def block_ip(ip: str):
    try:
        subprocess.run(["echo", f"Blocking IP: {ip}"])
        return {"message": f"{ip} blocked (simulated)"}
    except Exception as e:
        return {"error": str(e)}
