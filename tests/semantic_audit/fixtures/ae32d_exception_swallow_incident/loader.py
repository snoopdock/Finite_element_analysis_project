def load_config(reader):
    try:
        return reader()
    except OSError:
        return {}


def failing_reader():
    raise OSError("disk unavailable")
