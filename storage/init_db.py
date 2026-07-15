from __future__ import annotations

try:
    from .schema import init_schema
    from .db import unavailable_reason
except ImportError:
    from schema import init_schema
    from db import unavailable_reason


def main() -> None:
    try:
        initialized = init_schema()
    except Exception as exc:
        print(f"storage PostgreSQL schema was not initialized: {exc}")
        return

    if initialized:
        print("storage PostgreSQL schema initialized")
        return
    reason = unavailable_reason()
    if reason:
        print(f"storage PostgreSQL schema was not initialized: {reason}")
        return
    print("storage PostgreSQL schema was not initialized")


if __name__ == "__main__":
    main()
