# Hosted Streamlit browser load testing

This script tests the hosted game at:

```text
https://pirsgame.streamlit.app/
```

It opens real browser sessions, selects the game setup menu, clicks **Start Game**, finds the interest-rate input by its Streamlit aria label, chooses an interest rate using a 50% keep / 50% old-rate-plus-or-minus rule, and clicks **Next** for each simulated turn.

## Install once before running

The script uses Selenium so it can click the real Streamlit UI. Install Selenium
on the machine where you will run Spyder:

```bash
pip install selenium
```

You also need Chrome or Chromium installed. Selenium Manager will normally find
or download the matching driver automatically.

## Running from Spyder

Open `scripts/performance_test.py` in Spyder. Near the top of the file, edit the
values in the `TESTING PARAMETERS -- EDIT THESE VALUES WHEN RUNNING FROM SPYDER` section. The script comments above each parameter explain what it means:

```python
TARGET_URL = "https://pirsgame.streamlit.app/"
NUMBER_OF_PLAYERS = 1
TURNS_PER_PLAYER = 16
MAX_WORKERS = 1
HEADLESS_BROWSER = False
GAME_DIFFICULTY_LABEL = "Central Bank Governor"
GAME_SCENARIO_LABEL = "Random"
GAME_MANDATE_LABEL = "Inflation Target"
PAGE_LOAD_TIMEOUT_SECONDS = 60.0
ACTION_TIMEOUT_SECONDS = 120.0
SECONDS_BETWEEN_TURNS = 0.25
RATE_MOVE_LIMIT = 1.0
USE_RANDOM_THINK_TIME = True
THINK_TIME_MEDIAN_SECONDS = 5.0
THINK_TIME_SIGMA = 0.55
THINK_TIME_MIN_SECONDS = 2.0
THINK_TIME_MAX_SECONDS = 45.0
ARTIFACTS_DIR = "performance_test_artifacts"
ALLOW_FAILURES = False
```

To test more players, change `NUMBER_OF_PLAYERS`. For example:

```python
NUMBER_OF_PLAYERS = 50
```

Then press Run in Spyder.

## Important testing parameters

- `NUMBER_OF_PLAYERS`: total simulated players to run. It is set to `1` by default so you can confirm the bot passes the menu before scaling up.
- `TURNS_PER_PLAYER`: how many times each player chooses an interest rate using a 50% keep / 50% old-rate-plus-or-minus rule and clicks **Next**.
- `MAX_WORKERS`: how many browser players run at the same time. It is set to `1` by default for debugging; raise it after one player works.
- `HEADLESS_BROWSER`: set to `False` by default so you can watch the browser pass the menu. Set it to `True` for larger load tests.
- `GAME_DIFFICULTY_LABEL`, `GAME_SCENARIO_LABEL`, and `GAME_MANDATE_LABEL`: menu choices the bot selects before clicking **Start Game**. The script targets the Streamlit radio groups named Difficulty, Scenario, and Mandate, so these values should match the visible radio option text.
- `RATE_MOVE_LIMIT`: when the bot changes rates, the largest allowed move up or down from the old rate. The bot has a 50% chance to keep the old rate and a 50% chance to choose old rate plus/minus up to this value, floored at 0.
- `USE_RANDOM_THINK_TIME`: adds human-like pauses before clicks and typing.
- `THINK_TIME_MEDIAN_SECONDS`, `THINK_TIME_SIGMA`, `THINK_TIME_MIN_SECONDS`, and `THINK_TIME_MAX_SECONDS`: control the random wait distribution. The default is concentrated around fast actions of a few seconds with a long right tail.

## Running from a terminal

You can also run it from the repository root:

```bash
python scripts/performance_test.py --players 10 --turns 16
```

or:

```bash
python scripts/performance_test.py --players 25 --turns 16 --max-workers 5
```

## Understanding the report

Example fields:

- `Players`: how many simulated browser players were attempted.
- `Turns per player`: how many turns each player should take.
- `Concurrent browser workers`: how many browser players were running at once.
- `Completed turns`: successful turns divided by expected turns. For example, `0/200` means none of the 200 expected turns completed.
- `Throughput`: successful turns per second. If completed turns is `0`, throughput is also `0`.
- `Turn response time statistics`: only appears when at least one turn succeeds.
- `Failures/crashes`: number of players or turns that failed.

If you see `turn=startup error=TimeoutException()`, Selenium opened the browser but
could not find or click **Start Game** before `ACTION_TIMEOUT_SECONDS` expired. In
that case the test never reached the interest-rate screen, so it is not evidence
that Streamlit failed under turn load. Try these debugging steps:

1. Set `NUMBER_OF_PLAYERS = 1` and `MAX_WORKERS = 1`.
2. Keep `HEADLESS_BROWSER = False` so you can watch the browser.
3. Keep `ACTION_TIMEOUT_SECONDS = 120.0` if the app is waking up slowly.
4. Look in `scripts/performance_test_artifacts` for the saved screenshot and HTML from the failed browser. The folder is created beside `performance_test.py`, even when Spyder runs with a different working directory.

The `autoreload of typing_extensions failed` message shown by Spyder/IPython is
not the load-test result. It is an IPython autoreload warning. You can usually
ignore it, or disable autoreload in Spyder if it is distracting.

## Human-like bot timing

By default, bots do not click instantly. The script samples random think times
from a log-normal distribution:

- most pauses are fast, often in the 2-10 second range
- some pauses are much longer because of the right tail
- pauses are capped by `THINK_TIME_MAX_SECONDS`

This is intended to be more realistic than every bot clicking at exactly the same
interval.

## What it reports

The script reports:

- completed turns and total wall time
- throughput in turns per second
- response-time statistics for a turn: mean, median, p95, p99, min, max, and standard deviation
- failures/crashes with full tracebacks and, when possible, screenshots/HTML saved under `scripts/performance_test_artifacts`

The hosted Streamlit page wraps the actual app inside an iframe named `streamlitApp`; the script switches into that iframe before looking for menu controls. The click helper is also designed for Streamlit markup where the visible text may be inside nested elements such as `<p>Next</p>` rather than directly on a `<button>`.

## Notes

This is heavier than the earlier HTTP-only test because it opens real browser
sessions and interacts with the UI. For large tests, raise `NUMBER_OF_PLAYERS`
gradually and keep `MAX_WORKERS` modest so your own computer does not run out of
CPU or memory before the Streamlit server is actually stressed.
