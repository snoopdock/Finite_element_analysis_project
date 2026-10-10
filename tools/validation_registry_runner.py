import argparse
import json
from pathlib import Path
import yaml


def load_schema(repository):
    schema = Path(repository) / "validation" / "schema.json"
    if not schema.exists():
        raise FileNotFoundError(f"Validation schema missing: {schema}")
    return json.loads(schema.read_text())


def discover_profile(repository, requested):
    folder = Path(repository) / "validation" / "profiles"
    profiles = sorted(folder.glob("*.yaml"))

    if requested == "latest":
        if not profiles:
            raise FileNotFoundError("No validation profiles found")
        return profiles[-1]

    profile = folder / f"{requested}.yaml"
    if not profile.exists():
        raise FileNotFoundError(f"Profile not found: {profile}")

    return profile


def validate_profile(data, schema):
    missing = [
        key for key in schema.get("required", [])
        if key not in data
    ]

    if missing:
        raise ValueError(
            "Profile schema validation failed. Missing: "
            + ", ".join(missing)
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--profile", default="latest")
    args = parser.parse_args()

    schema = load_schema(args.repository)
    profile_file = discover_profile(args.repository, args.profile)

    profile = yaml.safe_load(profile_file.read_text())
    validate_profile(profile, schema)

    print(f"Validated profile: {profile['id']}")

    for test in profile.get("target_tests", []):
        print(f"Target test: {test}")


if __name__ == "__main__":
    main()
