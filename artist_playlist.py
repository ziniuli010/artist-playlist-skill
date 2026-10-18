# -*- coding: utf-8 -*-
"""命令行入口包装，使 `pip install .` 后可直接使用 `artist-playlist` 命令。"""

import sys

from scripts.build_discography import main

if __name__ == "__main__":
    sys.exit(main())
