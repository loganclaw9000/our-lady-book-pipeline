"""Enable `python -m book_pipeline` invocation."""
from book_pipeline.cli.main import main

if __name__ == "__main__":
    raise SystemExit(main())
