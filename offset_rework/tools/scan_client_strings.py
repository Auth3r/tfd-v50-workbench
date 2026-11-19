import re, sys, os

def scan(path, keys, out_path, minlen=6):
    data = open(path, 'rb').read()
    pat = re.compile(rb'[ -~]{%d,}' % minlen)
    n = 0
    with open(out_path, 'w', encoding='utf-8', errors='replace') as out:
        for m in pat.finditer(data):
            s = m.group().decode('ascii', errors='replace')
            low = s.lower()
            if any(k in low for k in keys):
                out.write('%d\t%s\n' % (m.start(), s))
                n += 1
    print(path, 'size', len(data), 'hits', n)

scan(r"E:\第二后裔\TFD发布端V50\TFD发布端V50\unpacked\client.dll",
     ['characters', 'account_', 'account_mastery', 'selection', 'sqlite', 'character_count'],
     os.path.join(os.environ['TEMP'], 'tfd_client_strings.txt'))
