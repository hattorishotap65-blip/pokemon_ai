"""Launch the PTCG battle sandbox web server.

Usage (from WSL):
    python3 experiments/web/launch.py [--port PORT]

Requirements (WSL):
    pip install pymupdf pillow numpy

The server runs at http://localhost:8000 by default.
Open in Windows browser to play interactively against AI agents.

Card images:
    - Cards in card_images.json → loaded from pokemontcg.io CDN
    - Cards in card_imgs/ → served as local fallback
    - For missing cards, run extract_card_images.py beforehand:
        kaggle competitions download -f "Card_ID List_EN.pdf" pokemon-tcg-ai-battle -p reference/
        python3 experiments/web/extract_card_images.py
"""
import sys, os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
CG_PATH = os.path.join(PROJECT_ROOT, "reference", "extracted")

agents_dir = os.path.join(SCRIPT_DIR, "agents")
if not os.path.isdir(agents_dir):
    print("[launch] agents/ not found, running setup_agents.py...")
    import subprocess as _sp
    _r = _sp.run([sys.executable, os.path.join(SCRIPT_DIR, "setup_agents.py")])
    if _r.returncode != 0 or not os.path.isdir(agents_dir):
        print("Setup failed. Run manually:")
        print("  python3 experiments/web/setup_agents.py")
        sys.exit(1)

sys.path.insert(0, CG_PATH)

server_path = os.path.join(SCRIPT_DIR, "server.py")
code = open(server_path, encoding="utf-8").read()

code = code.replace(
    "ROOT + '/docs/official/models/cg-lib'",
    "'%s'" % CG_PATH,
)

code = code.replace(
    "ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))",
    "ROOT = '%s'" % SCRIPT_DIR.replace("\\", "/"),
)

# server.py expects ROOT/web/ for static files, but ROOT is already experiments/web/
code = code.replace("ROOT + '/web/", "ROOT + '/")

port = 8000
if "--port" in sys.argv:
    idx = sys.argv.index("--port")
    if idx + 1 < len(sys.argv):
        port = int(sys.argv[idx + 1])
code = code.replace(
    "int(sys.argv[1]) if len(sys.argv) > 1 else 8000",
    str(port),
)

exec(compile(code, server_path, "exec"))
