from pathlib import Path
import re

patch_path = Path('dev/patch_223_ledger_excel.py')
code = patch_path.read_text(encoding='utf-8')

pattern = re.compile(
    r"write_seg = top_function_segment\(s, 'write_excel'\).*?"
    r"s = replace_top_function\(s, 'write_excel', write_seg\)\n",
    re.S,
)

replacement = r'''# Robust Excel display insertion: find the first workbook.Save() inside
# write_excel using AST and insert the display-only formatter immediately before it.
tree_for_write = parse_top(s)
write_fn = next(
    (x for x in tree_for_write.body if isinstance(x, ast.FunctionDef) and x.name == 'write_excel'),
    None,
)
if write_fn is None:
    raise SystemExit('write_excel function not found')

save_nodes = []
for node in ast.walk(write_fn):
    if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
        continue
    call = node.value
    func = call.func
    if (
        isinstance(func, ast.Attribute)
        and func.attr == 'Save'
        and isinstance(func.value, ast.Name)
        and func.value.id == 'workbook'
    ):
        save_nodes.append(node)

if not save_nodes:
    raise SystemExit('workbook.Save() not found inside write_excel')
save_node = min(save_nodes, key=lambda x: x.lineno)
lines_for_write = s.splitlines()
save_line = lines_for_write[save_node.lineno - 1]
indent = save_line[:len(save_line) - len(save_line.lstrip())]
lines_for_write.insert(
    save_node.lineno - 1,
    indent + '_apply_postal_excel_display(sheet, row)',
)
s = '\n'.join(lines_for_write) + '\n'
'''

# Use a callable replacement so re.sub does not reinterpret backslashes in
# the embedded Python source (notably the literal "\\n" joins above).
new_code, count = pattern.subn(lambda _m: replacement, code, count=1)
if count != 1:
    raise SystemExit('could not harden Excel insertion block in 2.2.3 patch')

namespace = {
    '__name__': '__main__',
    '__file__': str(patch_path),
}
exec(compile(new_code, str(patch_path), 'exec'), namespace, namespace)
