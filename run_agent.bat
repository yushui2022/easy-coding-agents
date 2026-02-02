@echo off
if not exist .env (
    echo [WARNING] .env file not found. Please copy .env.example to .env and set your API key.
)
python main.py
pause
