"""Controlled source-oracle fixture; intentionally risky Python patterns."""
import subprocess


def shared(items=[]):
    items.append('again')
    return items


def swallowed():
    try:
        raise RuntimeError('control')
    except Exception:
        pass


def suppresses_exception():
    try:
        raise RuntimeError('control')
    finally:
        return 1


def overwrites_key():
    return {1: 'first', True: 'second'}


def optimized_away_check():
    assert side_effect()


def risky_subprocess():
    return subprocess.run('echo benign', shell=True)


def bare_handler():
    try:
        return 1
    except:
        pass
