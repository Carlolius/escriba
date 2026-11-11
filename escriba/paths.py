"""How paths are shown to the user."""
import os
from pathlib import Path


def shown_path(path):
    """~/... under the home folder (not on Windows, where ~ isn't usual)."""
    path = Path(path)
    if os.name != "nt":
        try:
            return "~/" + str(path.relative_to(Path.home()))
        except ValueError:
            pass
    return str(path)
