import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    ZHIPU_API_KEY = os.getenv("ZHIPU_API_KEY")
    MODEL_NAME = os.getenv("MODEL_NAME", "glm-4")
    MAX_HISTORY_TOKENS = int(os.getenv("MAX_HISTORY_TOKENS", "8000"))
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"

    @classmethod
    def validate(cls):
        if not cls.ZHIPU_API_KEY:
            # For demo purposes, we might warn but not crash immediately until runtime
            pass
