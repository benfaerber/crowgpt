"""python -m analyzer.photo crow.jpg [--lat 40.76 --lon -111.89] [--json]"""

import argparse
import json
import sys
from pathlib import Path

from .identify import ModelMissing, PhotoIdentifier


def main():
    parser = argparse.ArgumentParser(description="Name the corvid in a photo.")
    parser.add_argument("photos", nargs="+", type=Path)
    parser.add_argument("--lat", type=float, help="where it was taken; read from EXIF when omitted")
    parser.add_argument("--lon", type=float)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--top", type=int, default=3)
    args = parser.parse_args()
    try:
        identifier = PhotoIdentifier.load()
    except ModelMissing as error:
        sys.exit(str(error))
    for path in args.photos:
        result = identifier.identify(path, args.lat, args.lon)
        if args.json:
            print(json.dumps({"photo": str(path), **result.to_dict()}))
            continue
        print(path)
        for score in result.ranking[:args.top]:
            print(f"  {score.probability:6.1%}  {score.common_name} ({score.scientific_name})")
        notes = ["location used" if result.used_location else "pixels only, no usable location"]
        if result.bird_box is None:
            notes.append("no bird found, judged on the whole frame")
        print("  " + "; ".join(notes))


if __name__ == "__main__":
    main()
