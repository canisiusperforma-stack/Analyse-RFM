import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.config import settings


def configurer_logging() -> None:
    formateur = logging.Formatter(settings.LOG_FORMAT)

    niveau = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    logger_racine = logging.getLogger()
    logger_racine.setLevel(niveau)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(niveau)
    console_handler.setFormatter(formateur)
    logger_racine.addHandler(console_handler)

    chemin_logs = Path(settings.LOG_FILE)
    chemin_logs.parent.mkdir(parents=True, exist_ok=True)

    fichier_handler = RotatingFileHandler(
        chemin_logs,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    fichier_handler.setLevel(niveau)
    fichier_handler.setFormatter(formateur)
    logger_racine.addHandler(fichier_handler)


def get_logger(module: str) -> logging.Logger:
    return logging.getLogger(module)