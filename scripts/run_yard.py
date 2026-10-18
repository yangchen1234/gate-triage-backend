"""Start the local yard API with the repository's private .env file."""
import argparse
import os
from pathlib import Path
import re
import sys

from dotenv import load_dotenv
import uvicorn

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8010)
    parser.add_argument('--check-env', action='store_true', help='Check presence and format only; never call Claude or print credentials.')
    args = parser.parse_args()
    load_dotenv(ROOT / '.env', override=False)
    if args.check_env:
        key, model, code = (os.getenv(name, '') for name in ('ANTHROPIC_API_KEY','ANTHROPIC_MODEL','CONSOLE_TEAM_ACCESS_CODE'))
        valid = dict(api_key=16 <= len(key) <= 2048 and not any(c.isspace() for c in key),
                     model=bool(re.fullmatch(r'claude-[A-Za-z0-9._-]{1,80}', model)),
                     access_code=16 <= len(code) <= 256 and not any(c.isspace() for c in code))
        for name, ok in valid.items(): print(f'{name}: {"configured" if ok else "missing or invalid"}')
        print('No provider request was made. Credentials were not printed.')
        return
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    uvicorn.run('main:app', host='127.0.0.1', port=args.port, workers=1, access_log=False)


if __name__ == '__main__': main()
