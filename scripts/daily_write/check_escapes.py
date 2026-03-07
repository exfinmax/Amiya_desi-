import subprocess, re
out = subprocess.check_output(['python','scripts/daily_write/select_resources.py','scripts/daily_write/resources.json','scripts/daily_write/posted_urls.txt']).decode('utf-8').strip().splitlines()
for line in out:
    if '\\n' in line or '\n' in line:
        print('LINE with backslash-n:',repr(line))
    else:
        print('good',line)
