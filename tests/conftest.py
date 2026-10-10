import os

os.environ["MERIDIAN_EMBEDDING"] = "tfidf"
os.environ.pop("OPENAI_API_KEY", None)
