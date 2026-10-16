"""Score recorded pre-match 1X2 forecasts against independently supplied results."""
import argparse
import json
from ops.offline_1x2_ledger_settlement import settle_ledger

def main(argv=None):
    parser=argparse.ArgumentParser(description="Offline football 1X2 forecast settlement")
    parser.add_argument("--ledger",required=True)
    parser.add_argument("--results",required=True)
    args=parser.parse_args(argv)
    report=settle_ledger(args.ledger,args.results)
    print(json.dumps(report,indent=2,allow_nan=False))
    return report

if __name__=="__main__":
    main()
