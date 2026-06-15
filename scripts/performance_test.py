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
import random
import statistics
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Iterable

# =============================================================================
# EDIT THESE VALUES WHEN RUNNING FROM SPYDER
# =============================================================================
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
# =============================================================================


@dataclass
class TurnSample:
    player_id: int
    turn_number: int
    interest_rate: float
    elapsed_ms: float


@dataclass
class Failure:
    player_id: int
    turn_number: int | str
    error: str
    traceback: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Browser-load-test the hosted Streamlit game with simulated players.",
        epilog=(
            "Spyder: edit NUMBER_OF_PLAYERS near the top of this file and press Run.\n"
            "Terminal examples:\n"
            "  python scripts/performance_test.py --players 10\n"
            "  python scripts/performance_test.py --players 25 --turns 16 --max-workers 5\n"
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
        "--max-workers",
        type=int,
        default=MAX_WORKERS,
        help=f"maximum concurrent browser players (default from code: {MAX_WORKERS})",
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
        "--delay",
        type=float,
        default=SECONDS_BETWEEN_TURNS,
        help=f"seconds to wait between turns for each player (default from code: {SECONDS_BETWEEN_TURNS})",
    )
    parser.add_argument(
        "--rate-noise",
        type=float,
        default=RATE_NOISE,
        help=f"random policy-rate noise added each turn (default from code: {RATE_NOISE})",
    )
    parser.add_argument(
        "--allow-failures",
        action="store_true",
        default=ALLOW_FAILURES,
        help="return exit code 0 even if browser players fail",
    )
    return parser.parse_args()


def require_selenium() -> tuple[Any, Any, Any, Any, Any, Any, Any]:
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
    return webdriver, by, keys, options, service, expected_conditions, wait


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
    elapsed_values = [sample.elapsed_ms for sample in samples]
    if not elapsed_values:
        return {}
    return {
        "count": float(len(elapsed_values)),
        "mean_ms": statistics.fmean(elapsed_values),
        "median_ms": percentile(elapsed_values, 50),
        "p95_ms": percentile(elapsed_values, 95),
        "p99_ms": percentile(elapsed_values, 99),
        "min_ms": min(elapsed_values),
        "max_ms": max(elapsed_values),
        "stdev_ms": statistics.stdev(elapsed_values) if len(elapsed_values) > 1 else 0.0,
    }


def make_driver(args: argparse.Namespace, selenium_api: tuple[Any, Any, Any, Any, Any, Any, Any]) -> Any:
    webdriver, _, _, Options, Service, _, _ = selenium_api
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


def click_start_game(driver: Any, wait: Any, By: Any, EC: Any) -> None:
    start_button_xpath = "//button[.//*[normalize-space()='Start Game'] or normalize-space()='Start Game']"
    start_button = wait.until(EC.element_to_be_clickable((By.XPATH, start_button_xpath)))
    start_button.click()
    next_button_xpath = "//button[.//*[normalize-space()='Next'] or normalize-space()='Next']"
    wait.until(EC.element_to_be_clickable((By.XPATH, next_button_xpath)))


def read_current_interest_rate(driver: Any, wait: Any, By: Any, EC: Any) -> float:
    input_el = wait.until(EC.presence_of_element_located((By.XPATH, "//input")))
    raw_value = input_el.get_attribute("value") or "0"
    try:
        return max(0.0, float(raw_value))
    except ValueError:
        return 0.0


def choose_interest_rate(current_rate: float, rate_noise: float) -> float:
    return max(0.0, current_rate + random.gauss(0.0, rate_noise))


def submit_turn(driver: Any, wait: Any, By: Any, EC: Any, Keys: Any, rate: float) -> None:
    input_el = wait.until(EC.element_to_be_clickable((By.XPATH, "//input")))
    input_el.send_keys(Keys.CONTROL, "a")
    input_el.send_keys(f"{rate:.2f}")

    next_button_xpath = "//button[.//*[normalize-space()='Next'] or normalize-space()='Next']"
    next_button = wait.until(EC.element_to_be_clickable((By.XPATH, next_button_xpath)))
    next_button.click()
    wait.until(EC.element_to_be_clickable((By.XPATH, next_button_xpath)))


def run_player(
    player_id: int,
    args: argparse.Namespace,
    selenium_api: tuple[Any, Any, Any, Any, Any, Any, Any],
) -> tuple[list[TurnSample], list[Failure]]:
    _, By, Keys, _, _, EC, WebDriverWait = selenium_api
    samples: list[TurnSample] = []
    failures: list[Failure] = []
    driver = None

    try:
        driver = make_driver(args, selenium_api)
        wait = WebDriverWait(driver, args.action_timeout)
        driver.get(args.url)
        click_start_game(driver, wait, By, EC)
    except Exception as exc:  # noqa: BLE001 - this is a failure-reporting harness
        failures.append(Failure(player_id, "startup", repr(exc), traceback.format_exc()))
        if driver is not None:
            driver.quit()
        return samples, failures

    for turn_number in range(1, args.turns + 1):
        try:
            current_rate = read_current_interest_rate(driver, wait, By, EC)
            rate = choose_interest_rate(current_rate, args.rate_noise)
            started = time.perf_counter()
            submit_turn(driver, wait, By, EC, Keys, rate)
            samples.append(TurnSample(player_id, turn_number, rate, (time.perf_counter() - started) * 1000.0))
        except Exception as exc:  # noqa: BLE001 - keep other players running after a failure
            failures.append(Failure(player_id, turn_number, repr(exc), traceback.format_exc()))
            break
        if args.delay > 0 and turn_number < args.turns:
            time.sleep(args.delay)

    driver.quit()
    return samples, failures


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
        print(failure.traceback.rstrip())


def main() -> int:
    args = parse_args()
    if args.players < 1:
        raise SystemExit("--players must be at least 1")
    if args.turns < 1:
        raise SystemExit("--turns must be at least 1")
    if args.max_workers < 1:
        raise SystemExit("--max-workers must be at least 1")

    selenium_api = require_selenium()
    all_samples: list[TurnSample] = []
    all_failures: list[Failure] = []
    suite_started = time.perf_counter()

    workers = min(args.players, args.max_workers)
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
    print(f"Concurrent browser workers: {workers}")
    print(f"Completed turns: {completed_turns}/{expected_turns}")
    print(f"Total wall time: {elapsed:.3f}s")
    if elapsed > 0:
        print(f"Throughput: {completed_turns / elapsed:.2f} turns/sec")

    stats = summarize_response_times(all_samples)
    if stats:
        print("\nTurn response time statistics (milliseconds from Next click to ready):")
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
    raise SystemExit(main())
