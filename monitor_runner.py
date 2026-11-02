from app import run_monitor_cycle


if __name__ == "__main__":
    raise SystemExit(0 if run_monitor_cycle(trigger="scheduled") else 1)
