from workflows import hatchet, workflow


def main() -> None:
    worker = hatchet.worker("skills-refinement-worker", workflows=[workflow], slots=1)
    worker.start()


if __name__ == "__main__":
    main()
