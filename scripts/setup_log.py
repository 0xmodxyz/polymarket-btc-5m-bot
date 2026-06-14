import logging
import sys
from pathlib import Path

# Log to both console and file
log_file = Path("bot_output.log")
log_file.write_text("")  # clear

handler = logging.FileHandler("bot_output.log", encoding="utf-8")
handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))

root = logging.getLogger()
root.addHandler(handler)
