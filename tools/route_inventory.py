"""Runtime inventory of every Flask URL rule registered by Prepza.

This is audit instrumentation only: it does not mutate application routing.
Run with the same environment used by the local QA container.
"""

from collections import defaultdict

from app import app


def main() -> None:
    rows = []
    for rule in app.url_map.iter_rules():
        methods = sorted(m for m in rule.methods if m not in {"HEAD", "OPTIONS"})
        rows.append(
            {
                "path": rule.rule,
                "methods": methods,
                "endpoint": rule.endpoint,
            }
        )

    rows.sort(key=lambda row: (row["path"], tuple(row["methods"]), row["endpoint"]))

    application = [row for row in rows if row["endpoint"] != "static"]
    duplicates = defaultdict(list)
    for row in application:
        key = (row["path"], tuple(row["methods"]))
        duplicates[key].append(row["endpoint"])
    duplicates = {
        key: endpoints
        for key, endpoints in duplicates.items()
        if len(endpoints) > 1
    }

    print(f"TOTAL_FLASK_RULES={len(rows)}")
    print(f"TOTAL_APPLICATION_RULES={len(application)}")
    print(f"DUPLICATE_PATH_METHOD_REGISTRATIONS={len(duplicates)}")
    print()
    print("PATH | METHODS | ENDPOINT")
    for row in application:
        print(
            f"{row['path']} | "
            f"{','.join(row['methods']) or '(no HTTP method after HEAD/OPTIONS removal)'} | "
            f"{row['endpoint']}"
        )

    if duplicates:
        print()
        print("DUPLICATES")
        for (path, methods), endpoints in sorted(duplicates.items()):
            print(f"{path} | {','.join(methods)} | {', '.join(endpoints)}")


if __name__ == "__main__":
    main()
