from pathlib import Path
import ast
import re

p = Path('src/PostalScanner.py')
s = p.read_text(encoding='utf-8')

# 1) Version bump for the work-stable production build.
s, n = re.subn(r'APP_VERSION\s*=\s*"2\.2\.0"', 'APP_VERSION = "2.2.1"', s, count=1)
if n != 1:
    raise SystemExit('APP_VERSION 2.2.0 anchor not found')

# 2) Keep the already-correct LocalAppData architecture and verify it before
# touching the migration helper.
required_layout = [
    'PERSISTENT_ROOT = get_persistent_root()',
    'DATA_DIR = PERSISTENT_ROOT / "data"',
    'ORIGINAL_DIR = DATA_DIR / "original"',
    'OUTPUT_DIR = DATA_DIR / "output"',
    'AUDIT_DIR = DATA_DIR / "audit"',
    'OPENAI_SECURE_KEY_FILE = DATA_DIR / "openai_key.dat"',
]
missing = [x for x in required_layout if x not in s]
if missing:
    raise SystemExit('persistent data layout mismatch: ' + repr(missing))

# 3) Harden the actual 2.2.0 helper. Migration is COPY ONLY and now merges
# legacy directories instead of skipping an entire directory when destination
# already exists. Source files are never moved, deleted or overwritten.
tree = ast.parse(s)
fn = next((node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == '_copy_legacy_data_once'), None)
if fn is None:
    raise SystemExit('_copy_legacy_data_once not found')

new_fn = '''def _copy_legacy_data_once():
    """Copy 2.1.x/early-2.2 data into the persistent store without deleting sources."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Supported legacy locations:
    # - 2.1.x: files/folders beside PostalScanner.exe
    # - early 2.2 preview: install-root/data
    # - early LocalAppData layout: %LOCALAPPDATA%/PostalScanner/<name>
    legacy_roots = [
        BASE_DIR,
        BASE_DIR / "data",
        PERSISTENT_ROOT,
    ]

    seen = set()
    for root in legacy_roots:
        root = Path(root)
        try:
            key = str(root.resolve()).lower()
        except Exception:
            key = str(root).lower()
        if key in seen:
            continue
        seen.add(key)

        for name in ("original", "output", "audit", "metrics"):
            src = root / name
            dst = DATA_DIR / name
            try:
                if not src.is_dir() or src.resolve() == dst.resolve():
                    continue
                dst.mkdir(parents=True, exist_ok=True)
                shutil.copytree(src, dst, dirs_exist_ok=True)
            except Exception:
                # Never damage the source when migration cannot complete.
                pass

        for name in ("openai_key.dat", "openai_config.json", "address_aliases.json", UPDATE_CONFIG_NAME):
            src = root / name
            dst = DATA_DIR / name
            try:
                if not src.is_file() or src.resolve() == dst.resolve() or dst.exists():
                    continue
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            except Exception:
                # Keep the old file untouched and allow manual import later.
                pass
'''
lines = s.splitlines()
lines[fn.lineno - 1:fn.end_lineno] = new_fn.rstrip('\n').splitlines()
s = '\n'.join(lines) + '\n'

# 4) Production contract: no destructive migration calls anywhere in app code.
if 'shutil.move(' in s:
    raise SystemExit('destructive shutil.move remains in PostalScanner.py')

p.write_text(s, encoding='utf-8')
print('2.2.1 production data-safety patch applied')
