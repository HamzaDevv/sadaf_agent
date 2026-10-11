import os

base_dir = os.path.abspath(os.path.dirname(__file__))
output_file = os.path.join(base_dir, 'code_context.txt')

exclude_dirs = {
    '.git', '__pycache__', '.pytest_cache', '.gemini', '.agents',
    'venv', 'lib', 'memories', 'reports', 'temp_data'
}
exclude_files = {'code_context.txt'}
binary_exts = {'.sqlite3', '.pyc', '.png', '.jpg', '.jpeg', '.gif', '.wav', '.mp3', '.zip', '.tar', '.gz', '.db', '.DS_Store'}

def should_include_dir(dir_name, rel_path):
    if dir_name in exclude_dirs or dir_name.startswith('.'):
        return False
    if 'tests/reports' in rel_path or 'tests/temp_data' in rel_path:
        return False
    return True

def should_include_file(file_name, rel_path):
    if file_name in exclude_files or file_name.startswith('.DS_Store'):
        return False
    ext = os.path.splitext(file_name)[1].lower()
    if ext in binary_exts:
        return False
    if 'tests/reports' in rel_path or 'tests/temp_data' in rel_path:
        return False
    return True

def build_tree(dir_path, prefix=''):
    entries = sorted(os.listdir(dir_path))
    filtered = []
    for entry in entries:
        full_path = os.path.join(dir_path, entry)
        rel_path = os.path.relpath(full_path, base_dir)
        if os.path.isdir(full_path):
            if should_include_dir(entry, rel_path):
                filtered.append((entry, True, full_path, rel_path))
        else:
            if should_include_file(entry, rel_path):
                filtered.append((entry, False, full_path, rel_path))

    lines = []
    count = len(filtered)
    for i, (name, is_dir, full_path, rel_path) in enumerate(filtered):
        is_last = (i == count - 1)
        connector = '└── ' if is_last else '├── '
        lines.append(prefix + connector + name)
        if is_dir:
            extension = '    ' if is_last else '│   '
            lines.extend(build_tree(full_path, prefix + extension))
    return lines

def get_all_files(dir_path):
    file_list = []
    for root, dirs, files in os.walk(dir_path):
        rel_root = os.path.relpath(root, base_dir)
        dirs[:] = [d for d in dirs if should_include_dir(d, os.path.join(rel_root, d))]
        for f in files:
            rel_path = os.path.relpath(os.path.join(root, f), base_dir)
            if should_include_file(f, rel_path):
                file_list.append((rel_path, os.path.join(root, f)))
    file_list.sort(key=lambda x: x[0])
    return file_list

def main():
    tree_lines = ['Sadaf_2/'] + build_tree(base_dir)
    files_to_write = get_all_files(base_dir)

    with open(output_file, 'w', encoding='utf-8') as out:
        # 1. Write Directory Structure Header
        out.write("================================================================\n")
        out.write("--- Directory Structure ---\n")
        out.write("================================================================\n\n")

        out.write('\n'.join(tree_lines))
        out.write("\n\n\n")

        # 2. Write File Contents
        for rel_path, full_path in files_to_write:
            out.write("================================================================\n")
            out.write(f"--- File: {rel_path} ---\n")
            out.write("================================================================\n\n")

            try:
                with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                out.write(content)
                if not content.endswith('\n'):
                    out.write('\n')
                out.write('\n\n')
            except Exception as e:
                out.write(f"Error reading file: {e}\n\n")

    print(f"Successfully generated {output_file} with {len(files_to_write)} files.")

if __name__ == '__main__':
    main()
