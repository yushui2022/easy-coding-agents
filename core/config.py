import os
from dotenv import load_dotenv

load_dotenv(encoding="utf-8-sig")

class Config:
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "modelscope").lower()
    MODELSCOPE_API_KEY = os.getenv("MODELSCOPE_API_KEY")
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
    OPENAI_COMPATIBLE_API_KEY = os.getenv("OPENAI_COMPATIBLE_API_KEY")
    OPENAI_COMPATIBLE_BASE_URL = os.getenv("OPENAI_COMPATIBLE_BASE_URL")
    MODEL_NAME = os.getenv("MODEL_NAME")
    # Increased default token limit to 32k to avoid frequent compression
    MAX_HISTORY_TOKENS = int(os.getenv("MAX_HISTORY_TOKENS", "32000"))
    MAX_AUTONOMOUS_TURNS = int(os.getenv("MAX_AUTONOMOUS_TURNS", "30"))
    SIMPLE_TASK_TOOL_BUDGET = int(os.getenv("SIMPLE_TASK_TOOL_BUDGET", "2"))
    DEFAULT_TASK_TOOL_BUDGET = int(os.getenv("DEFAULT_TASK_TOOL_BUDGET", "12"))
    LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.1"))
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"

    @classmethod
    def validate(cls):
        if not cls.api_key():
            raise ValueError(
                f"Missing Configuration: API key is not set for provider '{cls.LLM_PROVIDER}'.\n"
                "Please create a .env file and set the provider API key.\n"
                "Refer to .env.example for details."
            )

    @classmethod
    def provider_label(cls) -> str:
        labels = {
            "modelscope": "ModelScope",
            "deepseek": "DeepSeek",
            "openai-compatible": "OpenAI-Compatible",
        }
        return labels.get(cls.LLM_PROVIDER, cls.LLM_PROVIDER)

    @classmethod
    def get_default_model(cls) -> str:
        if cls.LLM_PROVIDER == "deepseek":
            return "deepseek-v4-flash"
        return "Qwen/Qwen2.5-Coder-32B-Instruct"

    @classmethod
    def api_key(cls) -> str:
        if cls.LLM_PROVIDER == "deepseek":
            return cls.DEEPSEEK_API_KEY or ""
        if cls.LLM_PROVIDER == "openai-compatible":
            return cls.OPENAI_COMPATIBLE_API_KEY or ""
        return cls.MODELSCOPE_API_KEY or ""

    @classmethod
    def base_url(cls) -> str:
        if cls.OPENAI_COMPATIBLE_BASE_URL:
            return cls.OPENAI_COMPATIBLE_BASE_URL
        if cls.LLM_PROVIDER == "deepseek":
            return "https://api.deepseek.com"
        return "https://api-inference.modelscope.cn/v1"


Config.MODEL_NAME = Config.MODEL_NAME or Config.get_default_model()
