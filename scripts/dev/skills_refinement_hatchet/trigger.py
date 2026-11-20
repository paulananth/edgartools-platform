from __future__ import annotations

import argparse
from pathlib import Path

from workflows import TicketInput, workflow


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one skill-refinement ticket through Hatchet")
    parser.add_argument("ticket_path")
    parser.add_argument("--repo", default=None)
    parser.add_argument("--review-feedback-file", default=None)
    args = parser.parse_args()
    feedback = Path(args.review_feedback_file).read_text() if args.review_feedback_file else None

    run = workflow.run(TicketInput(
        ticket_path=args.ticket_path,
        repo=args.repo,
        review_feedback=feedback,
    ))
    print(run)


if __name__ == "__main__":
    main()
