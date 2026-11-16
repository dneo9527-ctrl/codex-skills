#!/usr/bin/env python3
"""Install only this complete Skill into an explicit Codex home; never overwrite."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys

SOURCE = Path(__file__).resolve().parent
FILES = ('SKILL.md', 'LICENSE', 'install.py', 'scripts/project_memory.py',
         'references/profile-format.md', 'agents/openai.yaml')


def install(codex_home, source=SOURCE):
    source = Path(source).resolve()
    home = Path(codex_home).expanduser().absolute()
    skills = home / 'skills'
    target = skills / 'codex-project-memory'
    for name in FILES:
        path = source / name
        if (not path.is_file() or path.is_symlink()
                or any(parent.is_symlink() for parent in path.parents if parent != source.parent)):
            raise ValueError('Incomplete or linked Skill source: ' + name)
    if home.is_symlink() or skills.is_symlink():
        raise ValueError('Choose a Codex home and skills directory without symbolic links.')
    # mkdir exclusively claims this destination, including against concurrent installs.
    skills.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        target.mkdir(mode=0o700)
    except FileExistsError:
        raise ValueError('The codex-project-memory destination already exists; nothing was overwritten.') from None
    identity = target.stat().st_dev, target.stat().st_ino
    try:
        for name in FILES:
            destination = target / name
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copyfile(source / name, destination)
            destination.chmod(0o600)
    except BaseException:
        if target.is_dir() and not target.is_symlink() and (target.stat().st_dev, target.stat().st_ino) == identity:
            shutil.rmtree(target)
        raise
    return {'installed': str(target), 'files': len(FILES), 'existing_configuration_modified': False,
            'model_or_network_call': False, 'next': 'Reopen or start a Codex chat and use $codex-project-memory.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--codex-home', type=Path,
                        default=Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex'))
    args = parser.parse_args()
    try:
        print(json.dumps(install(args.codex_home)))
        return 0
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
