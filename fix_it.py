import glob, re
for f in glob.glob('AI_EXE/*.py'):
    with open(f, 'r', encoding='utf-8') as file:
        content = file.read()
    new_content = re.sub(r'^from utils import', 'from AI_EXE.utils import', content, flags=re.MULTILINE)
    if new_content != content:
        with open(f, 'w', encoding='utf-8') as file:
            file.write(new_content)
print('Done')
