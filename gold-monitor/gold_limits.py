"""Owner-editable gold alert thresholds, serialized with the hourly monitor."""
import argparse
import fcntl
import json
import os
from decimal import Decimal
from pathlib import Path
import re
import tempfile


def limits(private, lower=None, upper=None):
    path = private / 'config.json'
    with (private / 'run.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        config = json.loads(path.read_text())
        pair = {k: str(config[k]) for k in ('lower', 'upper')}
        for key, value in (('lower', lower), ('upper', upper)):
            if value is not None:
                if not re.fullmatch(r'[0-9]{1,6}(?:\.[0-9]{1,2})?', value):
                    raise ValueError('invalid_price')
                pair[key] = value
        if not 0 < Decimal(pair['lower']) < Decimal(pair['upper']):
            raise ValueError('invalid_range')
        if lower is not None or upper is not None:
            config.update(pair)
            with tempfile.NamedTemporaryFile('w', dir=private, delete=False, encoding='utf-8') as out:
                temp = Path(out.name)
                try:
                    json.dump(config, out, ensure_ascii=False, indent=2)
                    out.flush()
                    os.fsync(out.fileno())
                except BaseException:
                    temp.unlink(missing_ok=True)
                    raise
            try:
                os.replace(temp, path)
            finally:
                temp.unlink(missing_ok=True)
        return pair


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--lower')
    parser.add_argument('--upper')
    args = parser.parse_args()
    try:
        result = limits(Path(__file__).resolve().parent / '.private', args.lower, args.upper)
    except ValueError:
        result = {'error': 'invalid_limits'}
    print(json.dumps(result))
