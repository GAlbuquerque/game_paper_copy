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
HEADLESS_BROWSER = False
GAME_DIFFICULTY_LABEL = "Central Bank Governor"
GAME_SCENARIO_LABEL = "Random"
GAME_MANDATE_LABEL = "Inflation Target"
PAGE_LOAD_TIMEOUT_SECONDS = 60.0
ACTION_TIMEOUT_SECONDS = 120.0
STALE_ELEMENT_RETRIES = 3
RATE_MOVE_LIMIT = 1.0
USE_RANDOM_THINK_TIME = True
START_CLICK_DELAY_MEAN_SECONDS = 2.0
START_CLICK_DELAY_STDEV_SECONDS = 0.5
START_CLICK_DELAY_MIN_SECONDS = 0.5
TURN_THINK_TIME_MIN_SECONDS = 0.5
TURN_THINK_TIME_MEDIAN_SECONDS = 2.0
TURN_THINK_TIME_P90_SECONDS = 60.0
TURN_THINK_TIME_P99_SECONDS = 240.0
TURN_THINK_TIME_MAX_SECONDS = 300.0
ARTIFACTS_DIR = "performance_test_artifacts"
ALLOW_FAILURES = False
```

To test more players, change `NUMBER_OF_PLAYERS`. For example:

```python
NUMBER_OF_PLAYERS = 50
```

Then press Run in Spyder.

## Important testing parameters

- `NUMBER_OF_PLAYERS`: total simulated players to run. Every player runs concurrently, so this also controls the number of simultaneous browser players. It is set to `1` by default so you can confirm the bot passes the menu before scaling up.
- `TURNS_PER_PLAYER`: how many times each player chooses an interest rate using a 50% keep / 50% old-rate-plus-or-minus rule and clicks **Next**.
- `HEADLESS_BROWSER`: set to `False` by default so you can watch the browser pass the menu. Set it to `True` for larger load tests.
- `GAME_DIFFICULTY_LABEL`, `GAME_SCENARIO_LABEL`, and `GAME_MANDATE_LABEL`: menu choices the bot selects before clicking **Start Game**. The script targets the Streamlit radio groups named Difficulty, Scenario, and Mandate, so these values should match the visible radio option text.
- `STALE_ELEMENT_RETRIES`: how many times Selenium re-finds a widget if Streamlit redraws the page after Selenium first found it. This protects against `StaleElementReferenceException`, where the input or button still appears on screen but Selenium's old reference points to a replaced widget.
- `RATE_MOVE_LIMIT`: when the bot changes rates, the largest allowed move up or down from the old rate. The bot has a 50% chance to keep the old rate and a 50% chance to choose old rate plus/minus up to this value, floored at 0.
- `USE_RANDOM_THINK_TIME`: adds human-like pauses before clicks and typing.
- `START_CLICK_DELAY_MEAN_SECONDS`, `START_CLICK_DELAY_STDEV_SECONDS`, and `START_CLICK_DELAY_MIN_SECONDS`: control the pause before clicking **Start Game** after the menu is ready. The default is approximately normal with mean 2 seconds and standard deviation 0.5 seconds, floored at 0.5 seconds.
- `TURN_THINK_TIME_MIN_SECONDS`, `TURN_THINK_TIME_MEDIAN_SECONDS`, `TURN_THINK_TIME_P90_SECONDS`, `TURN_THINK_TIME_P99_SECONDS`, and `TURN_THINK_TIME_MAX_SECONDS`: control the turn-to-turn human delay. The default has a minimum of 0.5 seconds, median of 2 seconds, 90th percentile near 60 seconds, and 99th percentile near 240 seconds.

## Loading behavior

The script does not rely on a fixed number of seconds before acting. It waits for
the browser document to finish loading, switches into the hosted Streamlit iframe,
waits for the start-menu controls to be present, and after each click waits for
the next game controls to be available. Random think time is only meant to mimic
human hesitation after the page is ready; it is not used as the loading signal.

## Running from a terminal

You can also run it from the repository root:

```bash
python scripts/performance_test.py --players 10 --turns 16
```

or:

```bash
python scripts/performance_test.py --players 25 --turns 16
```

## Understanding the report

Example fields:

- `Players`: how many simulated browser players were attempted.
- `Turns per player`: how many turns each player should take.
- `Concurrent browser players`: how many browser players were running at once.
- `Stale element retries`: how many times Selenium will re-find a Streamlit widget after the page redraws it.
- `Completed turns`: successful turns divided by expected turns. For example, `0/200` means none of the 200 expected turns completed.
- `Throughput`: successful turns per second. If completed turns is `0`, throughput is also `0`.
- `Total wall time`: the real elapsed clock time from the start of the whole test until the script finishes. With multiple players, this is not the sum of each player's time; it is how long you waited in real life.
- `Turn response time statistics`: only appears when at least one turn succeeds. These values are reported in seconds.
- `Failures/crashes`: number of players or turns that failed.

If you see `turn=startup error=TimeoutException()`, Selenium opened the browser but
could not find or click **Start Game** before `ACTION_TIMEOUT_SECONDS` expired. In
that case the test never reached the interest-rate screen, so it is not evidence
that Streamlit failed under turn load. Try these debugging steps:

1. Set `NUMBER_OF_PLAYERS = 1`.
2. Keep `HEADLESS_BROWSER = False` so you can watch the browser.
3. Keep `ACTION_TIMEOUT_SECONDS = 120.0` if the app is waking up slowly.
4. Look in `scripts/performance_test_artifacts` for the saved screenshot and HTML from the failed browser. The folder is created beside `performance_test.py`, even when Spyder runs with a different working directory.

The `autoreload of typing_extensions failed` message shown by Spyder/IPython is
not the load-test result. It is an IPython autoreload warning. You can usually
ignore it, or disable autoreload in Spyder if it is distracting.

## Human-like bot timing

By default, bots do not click instantly:

- Before clicking **Start Game**, the bot uses a quick normal delay with mean 2 seconds and standard deviation 0.5 seconds, bounded below at 0.5 seconds.
- Between turns, the bot uses a custom long-tail delay with minimum 0.5 seconds, median 2 seconds, 90th percentile near 60 seconds, and 99th percentile near 240 seconds.

This is intended to be more realistic than every bot clicking at exactly the same
interval.

## What it reports

The script reports:

- completed turns and total wall time
- throughput in turns per second
- response-time statistics for a turn in seconds: mean, median, p95, p99, min, max, and standard deviation
- failures/crashes with full tracebacks and, when possible, screenshots/HTML saved under `scripts/performance_test_artifacts`

The hosted Streamlit page wraps the actual app inside an iframe named `streamlitApp`; the script switches into that iframe before looking for menu controls. The click helper is also designed for Streamlit markup where the visible text may be inside nested elements such as `<p>Next</p>` rather than directly on a `<button>`.

## Notes

This is heavier than the earlier HTTP-only test because it opens real browser
sessions and interacts with the UI. For large tests, raise `NUMBER_OF_PLAYERS` gradually so your own computer does not run out of CPU or memory before the Streamlit server is actually stressed.
