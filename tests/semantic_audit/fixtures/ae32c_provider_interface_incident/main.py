"""Entry point used to establish workflow-to-consumer relationships."""
from pipeline.extractor import extract
from providers.factory import build_provider


def main() -> int:
    return extract(build_provider())


if __name__ == "__main__":
    main()
