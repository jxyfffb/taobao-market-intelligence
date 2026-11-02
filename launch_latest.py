import os
from pathlib import Path


APPLICATION_DATA_DIRECTORY_ENV = "TAOBAO_MARKET_DATA_DIRECTORY"
PACKAGED_DIRECTORY_NAME = "LaobingMarketIntelligence"


def configure_shared_application_data(environment=None):
    environment = os.environ if environment is None else environment
    local_app_data = str(environment.get("LOCALAPPDATA") or "").strip()
    if not local_app_data:
        raise ValueError("LOCALAPPDATA is required to reuse the installed application data")

    application_data_directory = (
        Path(local_app_data) / PACKAGED_DIRECTORY_NAME / "data"
    )
    environment[APPLICATION_DATA_DIRECTORY_ENV] = str(application_data_directory)
    return application_data_directory


def main():
    configure_shared_application_data()
    from app import main as application_main

    return application_main(["--open-browser"])


if __name__ == "__main__":
    raise SystemExit(main())
