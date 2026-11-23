"""The monitor's design tokens: one place for what each state is called, numbered and coloured, and the thresholds that
turn a reading into a colour. The exporter writes the numbers, the dashboard maps them back; nothing else names a state."""

# state, code, colour, what it tells the operator
STATES = (
    ("waiting", 0, "#8b949e", "not started: it waits for a step of another lane, or for a free slot"),
    ("progressing", 1, "#2da44e", "running, and the evidence shows work: rows written, CPU, or a log that moved"),
    ("unclear", 2, "#d4a72c", "running, but only a step sharing its store shows writes; read its log"),
    ("stalled", 3, "#e16f24", "running with no CPU, no rows written and a silent log"),
    ("locked", 4, "#cf222e", "running, but three or more sessions wait on database locks"),
    ("done", 5, "#4493f8", "finished"),
    ("failed", 6, "#8b1a1a", "the scheduler gave up: the same failure came back"),
)
CODE = {name: code for name, code, _, _ in STATES}

# A reading turns a colour at these values (the verdict's own limits, so the dashboard and `--status` agree).
LOG_AGE_MINUTES = (10, 20)      # a log older than ten minutes is the first sign of a stall
LOCK_WAITERS = (1, 3)           # one waiting session is normal; three is the scheduler's own limit
MEMORY_FREE = (0.10, 0.25)      # the machine's pressure limits: under a tenth is high, under a quarter is short
LOAD_PER_CORE = (0.75, 1.5)     # below three quarters of the cores is roomy, above one and a half is pressed

GREEN, AMBER, ORANGE, RED = "#2da44e", "#d4a72c", "#e16f24", "#cf222e"
NEUTRAL, BLUE = "#8b949e", "#4493f8"
