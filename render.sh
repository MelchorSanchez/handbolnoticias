#!/bin/bash
set -e
cd "$(dirname "$0")"
git pull
python3 -c "
import sys, sqlite3
sys.path.insert(0, 'scripts')
from renderer import render_all
conn = sqlite3.connect('data/articles.db')
conn.row_factory = sqlite3.Row
render_all(conn)
conn.close()
"
git add templates/ docs/
git commit -m "chore: regenerate docs"
git push
echo "Done."
