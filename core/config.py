import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    MODELSCOPE_API_KEY = os.getenv("MODELSCOPE_API_KEY")
    MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-Coder-32B-Instruct")
    # Increased default token limit to 32k to avoid frequent compression
    MAX_HISTORY_TOKENS = int(os.getenv("MAX_HISTORY_TOKENS", "32000"))
    MAX_AUTONOMOUS_TURNS = int(os.getenv("MAX_AUTONOMOUS_TURNS", "30"))
    LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.1"))
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"

    @classmethod
    def validate(cls):
        if not cls.MODELSCOPE_API_KEY:
            raise ValueError(
                "Missing Configuration: MODELSCOPE_API_KEY is not set.\n"
                "Please create a .env file and set MODELSCOPE_API_KEY.\n"
                "Refer to .env.example for details."
            )

    @classmethod
    def provider_label(cls) -> str:
        return "ModelScope"

    @classmethod
    def get_default_model(cls) -> str:
        return "Qwen/Qwen2.5-Coder-32B-Instruct"

Config.MODEL_NAME = Config.MODEL_NAME or Config.get_default_model()
