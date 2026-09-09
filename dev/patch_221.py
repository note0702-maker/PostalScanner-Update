from pathlib import Path
import ast
import re

p = Path('src/PostalScanner.py')
s = p.read_text(encoding='utf-8')

# Production patch: version bump.
s, n = re.subn(r'APP_VERSION\s*=\s*"2\.2\.0"', 'APP_VERSION = "2.2.1"', s, count=1)
if n != 1:
    raise SystemExit('APP_VERSION 2.2.0 anchor not found')


def replace_top_assignment(source: str, name: str, expression: str, required: bool = True) -> str:
    tree = ast.parse(source)
    target = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
                target = node
                break
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            target = node
            break
    if target is None:
        if required:
            raise SystemExit(f'assignment not found: {name}')
        return source
    lines = source.splitlines()
    lines[target.lineno - 1:target.end_lineno] = [f'{name} = {expression}']
    return '\n'.join(lines) + '\n'


# Keep replaceable program files and persistent work data physically separate.
# On Windows this resolves to %LOCALAPPDATA%\PostalScanner\data.
s = replace_top_assignment(
    s,
    'PERSISTENT_ROOT',
    'Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")) / "PostalScanner"',
)
s = replace_top_assignment(s, 'DATA_DIR', 'PERSISTENT_ROOT / "data"')

# Force every user/work-data path under DATA_DIR when those names exist.
for name, expr in (
    ('ORIGINAL_DIR', 'DATA_DIR / "original"'),
    ('OUTPUT_DIR', 'DATA_DIR / "output"'),
    ('AUDIT_DIR', 'DATA_DIR / "audit"'),
    ('ADDRESS_ALIAS_FILE', 'DATA_DIR / "address_aliases.json"'),
    ('OPENAI_CONFIG_FILE', 'DATA_DIR / "openai_config.json"'),
    ('SESSION_LOCK_FILE', 'DATA_DIR / "session.lock"'),
    ('OPENAI_SECURE_KEY_FILE', 'DATA_DIR / "openai_key.dat"'),
):
    s = replace_top_assignment(s, name, expr, required=False)

# Replace legacy migration with COPY-ONLY migration. Existing 2.1/2.2 files are
# never deleted or moved during first production launch.
tree = ast.parse(s)
fn = next((node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'migrate_legacy_data_layout'), None)
if fn is None:
    raise SystemExit('migrate_legacy_data_layout not found')

new_fn = '''def migrate_legacy_data_layout():
    """Copy legacy user/work data into 2.2.1 persistent storage without deleting source data."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Sources supported:
    # - 2.1.x install-root data
    # - early 2.2 preview install-root/data
    # - early 2.2 LocalAppData root before the explicit /data split
    legacy_roots = [
        BASE_DIR,
        BASE_DIR / "data",
        PERSISTENT_ROOT,
    ]

    seen = set()
    for root in legacy_roots:
        try:
            root = Path(root)
            key = str(root.resolve()).lower()
        except Exception:
            root = Path(root)
            key = str(root).lower()
        if key in seen:
            continue
        seen.add(key)

        for name in ("original", "output", "audit", "metrics"):
            src = root / name
            dst = DATA_DIR / name
            try:
                if not src.exists() or src.resolve() == dst.resolve():
                    continue
                if src.is_dir():
                    shutil.copytree(src, dst, dirs_exist_ok=True)
            except Exception:
                # Migration failure must never remove or damage the source.
                pass

        for name in ("openai_key.dat", "openai_config.json", "address_aliases.json"):
            src = root / name
            dst = DATA_DIR / name
            try:
                if not src.is_file() or src.resolve() == dst.resolve() or dst.exists():
                    continue
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            except Exception:
                # Keep the legacy copy untouched and allow manual import later.
                pass
'''
lines = s.splitlines()
lines[fn.lineno - 1:fn.end_lineno] = new_fn.rstrip('\n').splitlines()
s = '\n'.join(lines) + '\n'

# Make the management/system-health text explicit so operators can verify that
# work data is outside the replaceable install directory.
if '실업무 안정판' not in s:
    s = s.replace(
        'f"{APP_VERSION}',
        'f"{APP_VERSION} · 실업무 안정판',
        1,
    )

p.write_text(s, encoding='utf-8')
print('2.2.1 production data-safety patch applied')
