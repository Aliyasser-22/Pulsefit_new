import os, re

for fname in os.listdir('.'):
    if not fname.endswith('.py'):
        continue
    try:
        txt = open(fname, encoding='utf-8', errors='ignore').read()
        new = re.sub(r'from .utils import', 'from .utils import', txt)
        new = re.sub(r'from .ai_coach3 import', 'from .ai_coach3 import', new)
        new = re.sub(r'from .messages import', 'from .messages import', new)
        if new != txt:
            open(fname, 'w', encoding='utf-8').write(new)
            print('Fixed: ' + fname)
    except Exception as e:
        print(f'Skipped {fname}: {e}')

print('Done!')
