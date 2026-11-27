def parse(text):
    """Reads `key=value` lines, skipping blank lines and # comments."""
    properties = {}

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'): continue
        key, _, value = line.partition('=')
        properties[key.strip()] = value.strip()

    return properties


def load(path):
    # utf-8-sig also accepts the byte order mark some Windows editors add.
    with open(path, encoding='utf-8-sig', errors='replace') as file:
        return parse(file.read())
