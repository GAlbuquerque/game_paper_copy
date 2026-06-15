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
- `MAX_WORKERS`: how many browser players run at the same time. Start small, such as `3` or `5`, because each worker opens a browser.
- `HEADLESS_BROWSER`: keep `True` for load testing. Set to `False` if you want to watch the browsers.
- `RATE_NOISE`: how much randomness is added to the current interest rate each turn.

## Running from a terminal

You can also run it from the repository root:

```bash
python scripts/performance_test.py --players 10 --turns 16
```

or:

```bash
python scripts/performance_test.py --players 25 --turns 16 --max-workers 5
```

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
