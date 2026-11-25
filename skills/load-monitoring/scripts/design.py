"""The monitor's design tokens: one place for what each state is called, numbered and coloured, and the thresholds that
turn a reading into a colour. The exporter writes the numbers, the dashboard maps them back; nothing else names a state."""

# state, code, colour, what it tells the operator. A code is never reused or renumbered: Prometheus keeps the codes it stored, and
# a changed number would repaint the history (code 2 was `unclear`, removed; it stays unused).
STATES = (
    ("waiting", 0, "#8b949e", "not started: it waits for a step of another lane, or for a free slot"),
    ("progressing", 1, "#2da44e", "running, and its own evidence shows work: a database session of its own, CPU, or a log that moved"),
    ("stalled", 3, "#cf222e", "running with no CPU, no session of its own working and a silent log: the Why column says why"),
    ("locked", 4, "#cf222e", "running, its own sessions wait on database locks and three or more sessions wait on the store"),
    ("done", 5, "#2da44e", "finished"),
    ("failed", 6, "#cf222e", "the scheduler gave up: the same failure came back"),
)
CODE = {name: code for name, code, _, _ in STATES}

# A reading turns a colour at these values (the verdict's own limits, so the dashboard and `--status` agree).
LOG_AGE_MINUTES = (10, 20)      # a log older than ten minutes is the first sign of a stall
LOCK_WAITERS = (1, 3)           # one waiting session is normal; three is the scheduler's own limit
MEMORY_FREE = (0.10, 0.25)      # the machine's pressure limits: under a tenth is high, under a quarter is short
LOAD_PER_CORE = (0.75, 1.5)     # below three quarters of the cores is roomy, above one and a half is pressed

GREEN, AMBER, ORANGE, RED = "#2da44e", "#d4a72c", "#e16f24", "#cf222e"
NEUTRAL = "#8b949e"
