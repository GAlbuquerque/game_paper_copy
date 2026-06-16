#!/usr/bin/env python3
"""Browser-load-test the hosted Streamlit game with many simulated players.

Spyder users: edit the constants in the "EDIT THESE VALUES" section below and
press Run. Each simulated player opens the hosted game, clicks Start Game,
chooses an interest rate, and clicks Next for the configured number of turns.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import math
import random
import statistics
import sys
import time
import traceback
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Iterable

SCRIPT_DIR = Path(__file__).resolve().parent

# =============================================================================
# TESTING PARAMETERS -- EDIT THESE VALUES WHEN RUNNING FROM SPYDER
# =============================================================================
# TARGET_URL: the hosted Streamlit game website that the browser bots will open.
TARGET_URL = "https://pirsgame.streamlit.app/"

# NUMBER_OF_PLAYERS: total fake players for the whole test.
# Start with 1 so you can verify the bot reaches the game screen before scaling up.
NUMBER_OF_PLAYERS = 1

# TURNS_PER_PLAYER: how many game turns each fake player should play.
# One turn means: read current rate, choose a new interest rate, type it, click Next.
TURNS_PER_PLAYER = 16

# HEADLESS_BROWSER: whether Chrome is visible.
# False = open a normal visible Chrome window so you can watch/debug.
# True = run Chrome invisibly in the background, which is better for larger load tests.
HEADLESS_BROWSER = False

# GAME_*_LABEL: menu choices the bot clicks before pressing Start Game.
# These strings must exactly match the labels you see in the Streamlit start menu.
GAME_DIFFICULTY_LABEL = "Central Bank Governor"
GAME_SCENARIO_LABEL = "Random"
GAME_MANDATE_LABEL = "Inflation Target"

# PAGE_LOAD_TIMEOUT_SECONDS: maximum seconds Selenium waits for the website to load.
# If the Streamlit app is asleep/cold-starting, increasing this can help.
PAGE_LOAD_TIMEOUT_SECONDS = 60.0

# ACTION_TIMEOUT_SECONDS: maximum seconds Selenium waits for a UI element to appear/click.
# This applies to menu options, Start Game, the interest-rate input, and Next.
# If you see TimeoutException, increase this or run with HEADLESS_BROWSER=False to watch.
ACTION_TIMEOUT_SECONDS = 120.0

# STALE_ELEMENT_RETRIES: how many times the bot re-finds an input/button if
# Streamlit redraws the page between finding the element and clicking it.
# StaleElementReferenceException means Selenium had an old copy of a widget that
# Streamlit replaced with a new, visually identical widget.
STALE_ELEMENT_RETRIES = 3

# RATE_MOVE_LIMIT: maximum absolute move when the bot changes the current interest rate.
# Example: 1.0 means a changed rate is old rate plus/minus up to 1 point.
RATE_MOVE_LIMIT = 1.0

# USE_RANDOM_THINK_TIME: whether bots pause like humans before clicks/typing.
# True is more realistic; False makes the test click as fast as Selenium can.
USE_RANDOM_THINK_TIME = True

# START_CLICK_DELAY_*: delay before clicking Start Game after the menu is ready.
# This models a quick human start click: normal(mean=2, stdev=0.5), floored at 0.5.
START_CLICK_DELAY_MEAN_SECONDS = 2.0
START_CLICK_DELAY_STDEV_SECONDS = 0.5
START_CLICK_DELAY_MIN_SECONDS = 0.5

# TURN_THINK_TIME_*: delay before making each turn after the turn screen is ready.
# This is a shifted log-normal distribution: min + lognormal(mu, sigma).
# The shift keeps the lower bound exact, and mu is chosen so the median is exact.
# Sigma is an honest least-squares fit to the requested p90 ~= 60s and p99 ~= 240s.
TURN_THINK_TIME_MIN_SECONDS = 0.5
TURN_THINK_TIME_MEDIAN_SECONDS = 2.0
TURN_THINK_TIME_TARGET_P90_SECONDS = 60.0
TURN_THINK_TIME_TARGET_P99_SECONDS = 240.0
TURN_THINK_TIME_LOGNORMAL_SIGMA = 2.342

# ARTIFACTS_DIR: folder where screenshots and HTML are saved when a bot fails.
# Check this folder when Selenium cannot find a button or input.
ARTIFACTS_DIR = "performance_test_artifacts"

# ALLOW_FAILURES: whether failures still count as a successful script run.
# False = return a failure exit code if any bot fails. True = always finish successfully.
ALLOW_FAILURES = False
# =============================================================================


@dataclass
class TurnSample:
    player_id: int
    turn_number: int
    interest_rate: float
    elapsed_seconds: float


@dataclass
class Failure:
    player_id: int
    turn_number: int | str
    error: str
    traceback: str
    screenshot_path: str | None = None
    html_path: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Browser-load-test the hosted Streamlit game with simulated players.",
        epilog=(
            "Spyder: edit NUMBER_OF_PLAYERS near the top of this file and press Run.\n"
            "Terminal examples:\n"
            "  python scripts/performance_test.py --players 10\n"
            "  python scripts/performance_test.py --players 25 --turns 16\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--url", default=TARGET_URL, help="Streamlit app URL to test")
    parser.add_argument(
        "-p",
        "--players",
        type=int,
        default=NUMBER_OF_PLAYERS,
        help=f"number of simulated browser players (default from code: {NUMBER_OF_PLAYERS})",
    )
    parser.add_argument(
        "-t",
        "--turns",
        type=int,
        default=TURNS_PER_PLAYER,
        help=f"turns each player takes after starting the game (default from code: {TURNS_PER_PLAYER})",
    )
    parser.add_argument(
        "--difficulty",
        default=GAME_DIFFICULTY_LABEL,
        help=f"menu difficulty label to select (default from code: {GAME_DIFFICULTY_LABEL})",
    )
    parser.add_argument(
        "--scenario",
        default=GAME_SCENARIO_LABEL,
        help=f"menu scenario label to select (default from code: {GAME_SCENARIO_LABEL})",
    )
    parser.add_argument(
        "--mandate",
        default=GAME_MANDATE_LABEL,
        help=f"menu mandate label to select (default from code: {GAME_MANDATE_LABEL})",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="show browser windows instead of running headless",
    )
    parser.add_argument(
        "--page-load-timeout",
        type=float,
        default=PAGE_LOAD_TIMEOUT_SECONDS,
        help=f"page load timeout in seconds (default from code: {PAGE_LOAD_TIMEOUT_SECONDS})",
    )
    parser.add_argument(
        "--action-timeout",
        type=float,
        default=ACTION_TIMEOUT_SECONDS,
        help=f"button/input wait timeout in seconds (default from code: {ACTION_TIMEOUT_SECONDS})",
    )
    parser.add_argument(
        "--stale-element-retries",
        type=int,
        default=STALE_ELEMENT_RETRIES,
        help=(
            "times to re-find Streamlit inputs/buttons after a stale element "
            f"(default from code: {STALE_ELEMENT_RETRIES})"
        ),
    )
    parser.add_argument(
        "--rate-move-limit",
        type=float,
        default=RATE_MOVE_LIMIT,
        help=f"maximum absolute policy-rate move when changing rates (default from code: {RATE_MOVE_LIMIT})",
    )
    parser.add_argument(
        "--no-think-time",
        action="store_true",
        help="disable random human-like pauses between actions",
    )
    parser.add_argument(
        "--allow-failures",
        action="store_true",
        default=ALLOW_FAILURES,
        help="return exit code 0 even if browser players fail",
    )
    return parser.parse_args()


def require_selenium() -> tuple[Any, Any, Any, Any, Any, Any, Any, Any]:
    if importlib.util.find_spec("selenium") is None:
        raise SystemExit(
            "This browser test needs Selenium. Install it locally with:\n"
            "  pip install selenium\n\n"
            "You also need Chrome or Chromium installed on the machine running the test."
        )

    webdriver = importlib.import_module("selenium.webdriver")
    by = importlib.import_module("selenium.webdriver.common.by").By
    keys = importlib.import_module("selenium.webdriver.common.keys").Keys
    options = importlib.import_module("selenium.webdriver.chrome.options").Options
    service = importlib.import_module("selenium.webdriver.chrome.service").Service
    expected_conditions = importlib.import_module("selenium.webdriver.support.expected_conditions")
    wait = importlib.import_module("selenium.webdriver.support.ui").WebDriverWait
    action_chains = importlib.import_module("selenium.webdriver.common.action_chains").ActionChains
    return webdriver, by, keys, options, service, expected_conditions, wait, action_chains


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return float("nan")
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    rank = (len(ordered) - 1) * (pct / 100.0)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    fraction = rank - low
    return ordered[low] + (ordered[high] - ordered[low]) * fraction


def summarize_response_times(samples: list[TurnSample]) -> dict[str, float]:
    elapsed_values = [sample.elapsed_seconds for sample in samples]
    if not elapsed_values:
        return {}
    return {
        "count": float(len(elapsed_values)),
        "mean_s": statistics.fmean(elapsed_values),
        "median_s": percentile(elapsed_values, 50),
        "p95_s": percentile(elapsed_values, 95),
        "p99_s": percentile(elapsed_values, 99),
        "min_s": min(elapsed_values),
        "max_s": max(elapsed_values),
        "stdev_s": statistics.stdev(elapsed_values) if len(elapsed_values) > 1 else 0.0,
    }


def sample_start_click_delay(args: argparse.Namespace) -> float:
    if args.no_think_time or not USE_RANDOM_THINK_TIME:
        return 0.0
    sampled = random.normalvariate(START_CLICK_DELAY_MEAN_SECONDS, START_CLICK_DELAY_STDEV_SECONDS)
    return max(START_CLICK_DELAY_MIN_SECONDS, sampled)


def sample_turn_think_time(args: argparse.Namespace) -> float:
    if args.no_think_time or not USE_RANDOM_THINK_TIME:
        return 0.0

    shifted_median = TURN_THINK_TIME_MEDIAN_SECONDS - TURN_THINK_TIME_MIN_SECONDS
    sampled = random.lognormvariate(math.log(shifted_median), TURN_THINK_TIME_LOGNORMAL_SIGMA)
    return TURN_THINK_TIME_MIN_SECONDS + sampled


def pause(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)


def start_click_pause(args: argparse.Namespace) -> None:
    pause(sample_start_click_delay(args))


def turn_think_pause(args: argparse.Namespace) -> None:
    pause(sample_turn_think_time(args))


def make_driver(args: argparse.Namespace, selenium_api: tuple[Any, Any, Any, Any, Any, Any, Any, Any]) -> Any:
    webdriver, _, _, Options, Service, _, _, _ = selenium_api
    chrome_options = Options()
    if HEADLESS_BROWSER and not args.headed:
        chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1440,1100")
    chrome_options.add_argument(f"--user-agent=PIRSGameBrowserLoadTest/1.0 player")
    driver = webdriver.Chrome(service=Service(), options=chrome_options)
    driver.set_page_load_timeout(args.page_load_timeout)
    return driver


def button_xpath(label: str) -> str:
    label_literal = xpath_literal(label)
    return (
        f"//*[self::button or @role='button' or contains(@class, 'stButton')]"
        f"[normalize-space()={label_literal} or .//*[normalize-space()={label_literal}]]"
    )


def text_xpath(label: str) -> str:
    label_literal = xpath_literal(label)
    return f"//*[normalize-space()={label_literal}]"


def interest_rate_input_xpath() -> str:
    return "//input[@aria-label='New Interest Rate_invisible' or @type='text']"


def visible_elements(driver: Any, By: Any, xpath: str) -> list[Any]:
    return [element for element in driver.find_elements(By.XPATH, xpath) if element.is_displayed()]


def nearest_click_target(driver: Any, element: Any) -> Any:
    return driver.execute_script(
        "return arguments[0].closest('button, label, [role=\"radio\"], [role=\"button\"]') || arguments[0];",
        element,
    )


def robust_click(driver: Any, element: Any, ActionChains: Any) -> None:
    click_target = nearest_click_target(driver, element)
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", click_target)
    time.sleep(0.2)
    try:
        click_target.click()
        return
    except Exception:
        pass
    try:
        ActionChains(driver).move_to_element(click_target).pause(0.2).click().perform()
        return
    except Exception:
        pass
    driver.execute_script("arguments[0].click();", click_target)


def xpath_literal(value: str) -> str:
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    return "concat(" + ", \"'\", ".join(f"'{part}'" for part in value.split("'")) + ")"


def click_visible_text(driver: Any, wait: Any, By: Any, ActionChains: Any, label: str) -> None:
    label_literal = xpath_literal(label)
    xpath = f"//*[normalize-space()={label_literal}]"
    elements = wait.until(lambda d: visible_elements(d, By, xpath))
    robust_click(driver, elements[0], ActionChains)


def select_radio_option(driver: Any, wait: Any, By: Any, ActionChains: Any, group_label: str, option_label: str) -> None:
    group_literal = xpath_literal(group_label)
    option_literal = xpath_literal(option_label)
    radio_xpath = (
        f"//*[@role='radiogroup' and (@aria-label={group_literal} or .//*[normalize-space()={group_literal}])]"
        f"//*[(@role='radio' or self::label) and (normalize-space()={option_literal} or .//*[normalize-space()={option_literal}])]"
    )
    label_fallback_xpath = f"//label[normalize-space()={option_literal} or .//*[normalize-space()={option_literal}]]"
    generic_fallback_xpath = f"//*[normalize-space()={option_literal}]"

    def _find_option(d: Any) -> list[Any]:
        for xpath in (radio_xpath, label_fallback_xpath, generic_fallback_xpath):
            elements = visible_elements(d, By, xpath)
            if elements:
                return elements
        return []

    elements = wait.until(_find_option)
    robust_click(driver, elements[0], ActionChains)


def select_game_setup(driver: Any, wait: Any, By: Any, ActionChains: Any, args: argparse.Namespace) -> None:
    for group_label, option_label in (
        ("Difficulty", args.difficulty),
        ("Scenario", args.scenario),
        ("Mandate", args.mandate),
    ):
        select_radio_option(driver, wait, By, ActionChains, group_label, option_label)


def find_clickable_text(driver: Any, By: Any, label: str) -> list[Any]:
    for xpath in (button_xpath(label), text_xpath(label)):
        elements = visible_elements(driver, By, xpath)
        if elements:
            return elements
    return []


def wait_for_document_ready(driver: Any, wait: Any) -> None:
    wait.until(lambda d: d.execute_script("return document.readyState") == "complete")


def switch_to_streamlit_iframe(driver: Any, wait: Any, By: Any) -> None:
    iframe_xpath = "//iframe[@title='streamlitApp']"
    iframes = wait.until(lambda d: visible_elements(d, By, iframe_xpath))
    driver.switch_to.frame(iframes[0])
    wait_for_document_ready(driver, wait)


def wait_for_start_menu_ready(driver: Any, wait: Any, By: Any, args: argparse.Namespace) -> None:
    wait.until(lambda d: find_clickable_text(d, By, args.difficulty))
    wait.until(lambda d: find_clickable_text(d, By, args.scenario))
    wait.until(lambda d: find_clickable_text(d, By, args.mandate))
    wait.until(lambda d: find_clickable_text(d, By, "Start Game"))


def wait_for_game_turn_ready(driver: Any, wait: Any, By: Any) -> None:
    wait.until(lambda d: visible_elements(d, By, interest_rate_input_xpath()))
    wait.until(lambda d: find_clickable_text(d, By, "Next"))


def click_start_game(driver: Any, wait: Any, By: Any, ActionChains: Any, args: argparse.Namespace) -> None:
    start_buttons = wait.until(lambda d: find_clickable_text(d, By, "Start Game"))
    start_click_pause(args)
    robust_click(driver, start_buttons[0], ActionChains)
    wait_for_game_turn_ready(driver, wait, By)


def read_current_interest_rate(driver: Any, wait: Any, By: Any, EC: Any) -> float:
    input_el = wait.until(EC.presence_of_element_located((By.XPATH, interest_rate_input_xpath())))
    raw_value = input_el.get_attribute("value") or "0"
    try:
        return max(0.0, float(raw_value))
    except ValueError:
        return 0.0


def choose_interest_rate(current_rate: float, rate_move_limit: float) -> float:
    if random.random() < 0.5:
        return current_rate
    move = random.uniform(-abs(rate_move_limit), abs(rate_move_limit))
    return max(0.0, current_rate + move)


def is_stale_element_error(exc: Exception) -> bool:
    return exc.__class__.__name__ == "StaleElementReferenceException"


def replace_input_value(driver: Any, input_el: Any, value: float) -> None:
    input_el.click()
    driver.execute_script(
        "const input = arguments[0];"
        "const value = Math.round(Number(arguments[1]) * 100) / 100;"
        "const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;"
        "setter.call(input, value);"
        "input.dispatchEvent(new Event('input', {bubbles: true}));"
        "input.dispatchEvent(new Event('change', {bubbles: true}));",
        input_el,
        value,
    )


def verified_input_value(input_el: Any) -> float:
    actual_value = input_el.get_attribute("value") or ""
    try:
        return float(actual_value)
    except ValueError:
        return float("nan")


def set_interest_rate_with_retries(driver: Any, wait: Any, By: Any, EC: Any, rate: float, args: argparse.Namespace) -> None:
    rounded_rate = round(rate, 2)
    last_exc: Exception | None = None

    for attempt in range(1, args.stale_element_retries + 1):
        try:
            input_el = wait.until(EC.element_to_be_clickable((By.XPATH, interest_rate_input_xpath())))
            replace_input_value(driver, input_el, rounded_rate)
            actual_rate = verified_input_value(input_el)
            if abs(actual_rate - rounded_rate) <= 0.001:
                return

            # Streamlit may have rerendered or rejected the first update. Find
            # the field fresh and try one more replacement inside this attempt.
            input_el = wait.until(EC.element_to_be_clickable((By.XPATH, interest_rate_input_xpath())))
            replace_input_value(driver, input_el, rounded_rate)
            actual_rate = verified_input_value(input_el)
            if abs(actual_rate - rounded_rate) <= 0.001:
                return
        except Exception as exc:
            if not is_stale_element_error(exc) or attempt == args.stale_element_retries:
                raise
            last_exc = exc
            wait_for_game_turn_ready(driver, wait, By)
            time.sleep(0.2 * attempt)

    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"Could not set interest-rate input to {rounded_rate:.2f}")


def submit_turn(driver: Any, wait: Any, By: Any, EC: Any, Keys: Any, ActionChains: Any, rate: float, args: argparse.Namespace) -> float:
    turn_think_pause(args)
    set_interest_rate_with_retries(driver, wait, By, EC, rate, args)

    for attempt in range(1, args.stale_element_retries + 1):
        try:
            next_buttons = wait.until(lambda d: find_clickable_text(d, By, "Next"))
            started = time.perf_counter()
            robust_click(driver, next_buttons[0], ActionChains)
            wait_for_game_turn_ready(driver, wait, By)
            return time.perf_counter() - started
        except Exception as exc:
            if not is_stale_element_error(exc) or attempt == args.stale_element_retries:
                raise
            wait_for_game_turn_ready(driver, wait, By)
            time.sleep(0.2 * attempt)

    raise RuntimeError("Could not click Next")


def run_player(
    player_id: int,
    args: argparse.Namespace,
    selenium_api: tuple[Any, Any, Any, Any, Any, Any, Any, Any],
) -> tuple[list[TurnSample], list[Failure]]:
    _, By, Keys, _, _, EC, WebDriverWait, ActionChains = selenium_api
    samples: list[TurnSample] = []
    failures: list[Failure] = []
    driver = None

    try:
        driver = make_driver(args, selenium_api)
        wait = WebDriverWait(driver, args.action_timeout)
        driver.get(args.url)
        wait_for_document_ready(driver, wait)
        switch_to_streamlit_iframe(driver, wait, By)
        wait_for_start_menu_ready(driver, wait, By, args)
        select_game_setup(driver, wait, By, ActionChains, args)
        click_start_game(driver, wait, By, ActionChains, args)
    except Exception as exc:  # noqa: BLE001 - this is a failure-reporting harness
        screenshot_path, html_path = save_failure_artifacts(driver, player_id, "startup")
        failures.append(Failure(player_id, "startup", repr(exc), traceback.format_exc(), screenshot_path, html_path))
        if driver is not None:
            driver.quit()
        return samples, failures

    for turn_number in range(1, args.turns + 1):
        try:
            current_rate = read_current_interest_rate(driver, wait, By, EC)
            rate = choose_interest_rate(current_rate, args.rate_move_limit)
            elapsed_seconds = submit_turn(driver, wait, By, EC, Keys, ActionChains, rate, args)
            samples.append(TurnSample(player_id, turn_number, rate, elapsed_seconds))
        except Exception as exc:  # noqa: BLE001 - keep other players running after a failure
            screenshot_path, html_path = save_failure_artifacts(driver, player_id, turn_number)
            failures.append(Failure(player_id, turn_number, repr(exc), traceback.format_exc(), screenshot_path, html_path))
            break

    driver.quit()
    return samples, failures


def save_failure_artifacts(driver: Any, player_id: int, turn_number: int | str) -> tuple[str | None, str | None]:
    if driver is None:
        return None, None
    artifacts_dir = Path(ARTIFACTS_DIR)
    if not artifacts_dir.is_absolute():
        artifacts_dir = SCRIPT_DIR / artifacts_dir
    artifacts_dir.mkdir(exist_ok=True)
    safe_turn = str(turn_number).replace("/", "_").replace("\\", "_")
    screenshot_path = artifacts_dir / f"player_{player_id}_turn_{safe_turn}.png"
    html_path = artifacts_dir / f"player_{player_id}_turn_{safe_turn}.html"
    saved_screenshot: str | None = None
    saved_html: str | None = None
    try:
        driver.save_screenshot(str(screenshot_path))
        saved_screenshot = str(screenshot_path)
    except Exception:
        saved_screenshot = None
    try:
        html_path.write_text(driver.page_source, encoding="utf-8")
        saved_html = str(html_path)
    except Exception:
        saved_html = None
    return saved_screenshot, saved_html


def print_failures(failures: Iterable[Failure]) -> None:
    failures = list(failures)
    if not failures:
        print("Failures/crashes: 0")
        return

    print(f"Failures/crashes: {len(failures)}")
    for failure in failures:
        print(
            f"\n--- Failure: player={failure.player_id} "
            f"turn={failure.turn_number} error={failure.error} ---"
        )
        if failure.screenshot_path:
            print(f"Screenshot: {failure.screenshot_path}")
        if failure.html_path:
            print(f"HTML: {failure.html_path}")
        print(failure.traceback.rstrip())


def main() -> int:
    args = parse_args()
    if args.players < 1:
        raise SystemExit("--players must be at least 1")
    if args.turns < 1:
        raise SystemExit("--turns must be at least 1")
    if args.stale_element_retries < 1:
        raise SystemExit("--stale-element-retries must be at least 1")
    if TURN_THINK_TIME_MEDIAN_SECONDS <= TURN_THINK_TIME_MIN_SECONDS:
        raise SystemExit("TURN_THINK_TIME_MEDIAN_SECONDS must be greater than TURN_THINK_TIME_MIN_SECONDS")
    selenium_api = require_selenium()
    all_samples: list[TurnSample] = []
    all_failures: list[Failure] = []
    suite_started = time.perf_counter()

    workers = args.players
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(run_player, player_id, args, selenium_api)
            for player_id in range(1, args.players + 1)
        ]
        for future in as_completed(futures):
            samples, failures = future.result()
            all_samples.extend(samples)
            all_failures.extend(failures)

    elapsed = time.perf_counter() - suite_started
    expected_turns = args.players * args.turns
    completed_turns = len(all_samples)

    print("Streamlit browser load test complete")
    print(f"URL: {args.url}")
    print(f"Players: {args.players}")
    print(f"Turns per player: {args.turns}")
    print(f"Menu difficulty: {args.difficulty}")
    print(f"Menu scenario: {args.scenario}")
    print(f"Menu mandate: {args.mandate}")
    print(f"Concurrent browser players: {workers}")
    print(f"Random think time: {not args.no_think_time and USE_RANDOM_THINK_TIME}")
    print(f"Stale element retries: {args.stale_element_retries}")
    print(f"Completed turns: {completed_turns}/{expected_turns}")
    print(f"Total wall time: {elapsed:.3f}s")
    if elapsed > 0:
        print(f"Throughput: {completed_turns / elapsed:.2f} turns/sec")

    stats = summarize_response_times(all_samples)
    if stats:
        print("\nTurn response time statistics (seconds from Next click to ready):")
        for key, value in stats.items():
            if key == "count":
                print(f"  {key}: {int(value)}")
            else:
                print(f"  {key}: {value:.3f}")
    else:
        print("\nTurn response time statistics: no successful turns")

    print()
    print_failures(all_failures)
    return 0 if args.allow_failures or not all_failures else 1


if __name__ == "__main__":
    exit_code = main()
    if "spyder_kernels" in sys.modules:
        print(f"Spyder run finished with exit code {exit_code}.")
    else:
        raise SystemExit(exit_code)
