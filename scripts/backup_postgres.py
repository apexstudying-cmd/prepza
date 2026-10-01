"""Create and verify a portable PostgreSQL backup using pg_dump.
DATABASE_URL must be supplied through the environment/.env.
"""
from __future__ import annotations
import argparse, os, subprocess
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parents[1]
def main():
    load_dotenv(ROOT / ".env"); database_url=os.environ.get("DATABASE_URL")
    if not database_url: raise SystemExit("DATABASE_URL is required")
    parser=argparse.ArgumentParser(); parser.add_argument("--output-dir",default=str(ROOT/"backups")); args=parser.parse_args()
    out_dir=Path(args.output_dir); out_dir.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"); output=out_dir/f"prepza-postgres-{stamp}.dump"
    subprocess.run(["pg_dump","--format=custom","--no-owner","--no-acl","--file",str(output),database_url],check=True)
    subprocess.run(["pg_restore","--list",str(output)],check=True,stdout=subprocess.DEVNULL)
    print(f"Backup created and verified: {output}")
if __name__=="__main__": main()
