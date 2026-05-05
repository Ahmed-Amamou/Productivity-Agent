import warnings

# google-api-core spams a FutureWarning about Python 3.10 EOL; silence to keep CLI clean.
warnings.filterwarnings("ignore", category=FutureWarning, module=r"google\.api_core.*")

__version__ = "0.1.0"
