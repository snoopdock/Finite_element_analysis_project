import argparse
from pathlib import Path
import yaml

def resolve_profile(repository, requested):
    profiles = Path(repository) / "validation" / "profiles"
    if requested == "latest":
        candidates = sorted(profiles.glob("*.yaml"))
        if not candidates:
            raise FileNotFoundError("No validation profiles found")
        return candidates[-1]
    return profiles / f"{requested}.yaml"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--profile", default="latest")
    args = parser.parse_args()

    profile = resolve_profile(args.repository, args.profile)
    data = yaml.safe_load(profile.read_text())

    print(f"Validation profile: {data['id']}")
    for test in data.get("target_tests", []):
        print(f"Target test: {test}")

if __name__ == "__main__":
    main()
