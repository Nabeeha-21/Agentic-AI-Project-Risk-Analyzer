"""Central settings for PROJEX. Tweak thresholds here instead of hunting through the code."""
import os

# ---- Detection thresholds -------------------------------------------------
OWNER_CAPACITY = 3            # concurrent active tasks one person can handle comfortably
BEHIND_PACE_POINTS = 20.0     # progress gap (percentage points) that counts as "behind pace"
STALL_DAYS = 10               # in-progress task with no commits for this many days = stalled
ISSUE_HIGH_THRESHOLD = 2      # open critical/high issues on a task before we raise a risk
ISSUE_TOTAL_THRESHOLD = 4     # total open issues on a task before we raise a risk
BOTTLENECK_DOWNSTREAM = 4     # tasks that block >= this many others are bottlenecks if late

# ---- Scoring ---------------------------------------------------------------
LEVEL_THRESHOLDS = [("Critical", 55.0), ("High", 35.0), ("Medium", 18.0), ("Low", 0.0)]
PRIORITY_WEIGHT = {"low": 0.5, "medium": 1.0, "high": 1.5, "critical": 2.0}

# ---- What-if / Monte Carlo ------------------------------------------------
RESOURCE_GAIN = 0.6           # each extra person adds 60% productivity (Brooks's-law style discount)
OVERLOAD_PENALTY = 0.25       # +25% duration per task above OWNER_CAPACITY
MC_RUNS = 2000

# ---- LLM -------------------------------------------------------------------
LLM_PROVIDER = os.getenv("PROJEX_LLM_PROVIDER", "anthropic")   # anthropic | gemini | none
ANTHROPIC_MODEL = os.getenv("PROJEX_ANTHROPIC_MODEL", "claude-sonnet-5-5")
GEMINI_MODEL = os.getenv("PROJEX_GEMINI_MODEL", "gemini-2.0-flash")
LLM_MAX_RISKS = 5             # how many top risks get LLM-written explanations (keeps cost low)

# ---- Storage ---------------------------------------------------------------
DB_PATH = os.getenv("PROJEX_DB", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "projex.db"))
