"""Applique les migrations SQL de migrations/ sur la base du .env (idempotent).

Usage : python migrate.py
"""
from pathlib import Path

from src.data import Database


def statements(sql):
    lines = [line for line in sql.splitlines() if not line.strip().startswith('--')]
    return [s.strip() for s in '\n'.join(lines).split(';') if s.strip()]


def main():
    for path in sorted(Path(__file__).parent.joinpath('migrations').glob('*.sql')):
        with Database() as cursor:
            for statement in statements(path.read_text(encoding='utf-8')):
                cursor.execute(statement)
        print(f'✅ {path.name}')


if __name__ == '__main__':
    main()
