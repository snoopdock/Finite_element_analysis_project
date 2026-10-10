import argparse
from pathlib import Path
import yaml

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--profile",default="latest")
    a=p.parse_args()
    folder=Path("validation/profiles")
    f=sorted(folder.glob("*.yaml"))[-1] if a.profile=="latest" else folder/(a.profile+".yaml")
    data=yaml.safe_load(f.read_text())
    print("Validation profile:", data["id"])
    for t in data.get("target_tests", []):
        print("Target:", t)

if __name__=="__main__":
    main()
