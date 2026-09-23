"""One-command local launch after dependency installation."""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("backend.platform.app:app", host="127.0.0.1", port=8000)
