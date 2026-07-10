import logging
import os
from pathlib import Path


SHOW_NB_LOG_LOGO = False
SHOW_IMPORT_NB_LOG_CONFIG_PATH = False
SHOW_PYCHARM_COLOR_SETINGS = False
DISPLAY_BACKGROUD_COLOR_IN_CONSOLE = False
DEFAULUT_USE_COLOR_HANDLER = True
AUTO_PATCH_PRINT = False

LOG_PATH = os.getenv("LOG_PATH") or Path(__file__).resolve().parent / "runtime" / "logs"
LOG_LEVEL_FILTER = logging.INFO
ROOT_LOGGER_LEVEL = logging.INFO
ROOT_LOGGER_FILENAME = "root.log"
ROOT_LOGGER_FILENAME_ERROR = "root.error.log"
FORMATTER_KIND = 5
