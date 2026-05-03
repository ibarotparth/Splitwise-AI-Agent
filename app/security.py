import os
from dataclasses import dataclass
from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    splitwise_consumer_key: str
    splitwise_consumer_secret: str
    splitwise_access_token: str
    splitwise_access_token_secret: str
    openai_api_key: str
    # Model strategy: cheap model for reads/classification, smarter for writes/extraction
    classifier_model: str           # e.g. "gpt-4o-mini"
    extractor_model: str            # e.g. "gpt-4o"

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        required = [
            "SPLITWISE_CONSUMER_KEY",
            "SPLITWISE_CONSUMER_SECRET",
            "SPLITWISE_ACCESS_TOKEN",
            "SPLITWISE_ACCESS_TOKEN_SECRET",
            "OPENAI_API_KEY",
        ]
        missing = [k for k in required if not os.getenv(k)]
        if missing:
            raise EnvironmentError(f"Missing required environment variables: {missing}")

        return cls(
            splitwise_consumer_key=os.environ["SPLITWISE_CONSUMER_KEY"],
            splitwise_consumer_secret=os.environ["SPLITWISE_CONSUMER_SECRET"],
            splitwise_access_token=os.environ["SPLITWISE_ACCESS_TOKEN"],
            splitwise_access_token_secret=os.environ["SPLITWISE_ACCESS_TOKEN_SECRET"],
            openai_api_key=os.environ["OPENAI_API_KEY"],
            classifier_model=os.getenv("OPENAI_CLASSIFIER_MODEL", "gpt-4o-mini"),
            extractor_model=os.getenv("OPENAI_EXTRACTOR_MODEL", "gpt-4o"),
        )
