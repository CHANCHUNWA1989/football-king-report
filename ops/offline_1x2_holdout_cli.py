"""Offline chronological football forecast audit from user-supplied CSV."""
import argparse
import csv
import json
from ops.offline_1x2_holdout import holdout_1x2

COLUMNS=["event_id","forecast_at","kickoff_at","settled_at",
         "home_prob","draw_prob","away_prob","outcome"]

def holdout_csv(path, *, train_fraction=.7, min_test=2):
    rows=[]
    with open(path,encoding="utf-8-sig",newline="") as handle:
        reader=csv.DictReader(handle)
        if reader.fieldnames!=COLUMNS:
            raise ValueError("Unexpected CSV schema")
        for row in reader:
            if len(rows)>=100000 or None in row or any(v is None or not v.strip() for v in row.values()):
                raise ValueError("Invalid or oversized CSV")
            rows.append({"event_id":row["event_id"],
                         "forecast_at":row["forecast_at"],
                         "kickoff_at":row["kickoff_at"],
                         "settled_at":row["settled_at"],
                         "probabilities":{"H":float(row["home_prob"]),
                                          "D":float(row["draw_prob"]),
                                          "A":float(row["away_prob"])},
                         "outcome":row["outcome"]})
    return holdout_1x2(rows,train_fraction=train_fraction,min_test=min_test)

def main(argv=None):
    parser=argparse.ArgumentParser(description="Offline football 1X2 chronological holdout")
    parser.add_argument("--csv",required=True)
    parser.add_argument("--train-fraction",type=float,default=.7)
    parser.add_argument("--min-test",type=int,default=2)
    args=parser.parse_args(argv)
    print(json.dumps(holdout_csv(args.csv,train_fraction=args.train_fraction,
                                 min_test=args.min_test),indent=2,allow_nan=False))

if __name__=="__main__":
    main()
