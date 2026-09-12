from pathlib import Path
from runpy import run_path

ROOT = Path(__file__).resolve().parent.parent

for name in (
    "apply_public_document_watermark.py",
    "apply_studyhub_library_flow.py",
    "apply_studyhub_existing_save_repair.py",
    "apply_upload_share_choice_ux.py",
    "apply_upload_publish_binding.py",
    "apply_library_publish_ownership_guard.py",
    "cleanup_studyhub_library_flow.py",
):
    print(f"==> applying {name}")
    run_path(str(ROOT / "scripts" / name), run_name="__main__")

print("All StudyHub/Library flow patches applied")