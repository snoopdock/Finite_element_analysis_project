class Adapter:
    def __init__(self):
        self.calls = 0

    def record(self):
        self.calls += 1
