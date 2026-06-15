# Hosted Streamlit browser load testing

This script tests the hosted game at:

```text
https://pirsgame.streamlit.app/
```

It opens real browser sessions, clicks **Start Game**, chooses an interest rate,
and clicks **Next** for each simulated turn.

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
values in the `EDIT THESE VALUES WHEN RUNNING FROM SPYDER` section:

```python
TARGET_URL = "https://pirsgame.streamlit.app/"
NUMBER_OF_PLAYERS = 10
TURNS_PER_PLAYER = 16
MAX_WORKERS = 3
HEADLESS_BROWSER = True
PAGE_LOAD_TIMEOUT_SECONDS = 60.0
ACTION_TIMEOUT_SECONDS = 30.0
SECONDS_BETWEEN_TURNS = 0.25
RATE_NOISE = 0.25
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

## Important settings

- `NUMBER_OF_PLAYERS`: total simulated players to run.
- `TURNS_PER_PLAYER`: how many times each player chooses an interest rate and clicks **Next**.
- `MAX_WORKERS`: how many browser players run at the same time. Start small, such as `1`, `3`, or `5`, because each worker opens a browser.
- `HEADLESS_BROWSER`: keep `True` for load testing. Set to `False` if you want to watch the browsers and debug why a click fails.
- `RATE_NOISE`: how much randomness is added to the current interest rate each turn.
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
2. Set `HEADLESS_BROWSER = False` so you can watch the browser.
3. Increase `ACTION_TIMEOUT_SECONDS` to `90.0` or `120.0` if the app is waking up slowly.
4. Look in `performance_test_artifacts` for the saved screenshot and HTML from the failed browser.

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
- failures/crashes with full tracebacks

## Notes

This is heavier than the earlier HTTP-only test because it opens real browser
sessions and interacts with the UI. For large tests, raise `NUMBER_OF_PLAYERS`
gradually and keep `MAX_WORKERS` modest so your own computer does not run out of
CPU or memory before the Streamlit server is actually stressed.
