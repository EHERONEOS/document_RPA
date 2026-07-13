import logging
from pathlib import Path


SHOW_IMPORT_NB_LOG_CONFIG_PATH = False
SHOW_NB_LOG_LOGO = False
SHOW_PYCHARM_COLOR_SETINGS = False
AUTO_PATCH_PRINT = False
DEFAULUT_USE_COLOR_HANDLER = True
DISPLAY_BACKGROUD_COLOR_IN_CONSOLE = False

LOG_LEVEL_FILTER = logging.INFO
ROOT_LOGGER_LEVEL = logging.INFO
ROOT_LOGGER_FILENAME = "root.log"
ROOT_LOGGER_FILENAME_ERROR = "root.error.log"
LOG_PATH = Path(__file__).resolve().parent / "runtime" / "logs"
FORMATTER_DICT = {
    5: logging.Formatter(
        "%(asctime)s - %(name)s - \"%(pathname)s:%(lineno)d\" - %(funcName)s - %(levelname)s - %(message)s",
        "%Y-%m-%d %H:%M:%S",
    ),
    12: logging.Formatter(
        "%(asctime)s|%(threadName)s|%(filename)s|%(funcName)s|%(lineno)d|%(levelname)s|%(message)s"
    ),
}
FORMATTER_KIND = 12

PRINT_WRTIE_FILE_NAME = None
SYS_STD_FILE_NAME = None
