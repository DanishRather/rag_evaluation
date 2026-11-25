"""Worker process. Claims jobs and runs them. Does not construct infrastructure."""

import logging

from app.main import create_container, process_jobs


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    process_jobs(create_container())


if __name__ == "__main__":
    main()
