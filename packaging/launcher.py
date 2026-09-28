"""Entry point for the bundled app (PyInstaller).

Same as `python -m mathassistant`; in a bundled build it shows the small
control window, never loads `.env`, and never tries to build the web app.
"""

from mathassistant.__main__ import main

if __name__ == "__main__":
    main()
