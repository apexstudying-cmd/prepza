from pathlib import Path
import os
import runpy

ROOT = Path(__file__).resolve().parents[1]


def main():
    os.chdir(ROOT)
    runpy.run_path(str(ROOT / 'scripts' / 'apply_document_study_progress.py'), run_name='__main__')


if __name__ == '__main__':
    main()
