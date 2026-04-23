import os
import sys
import time
from datetime import datetime, timezone

import requests
from google.cloud import bigquery


CITIES = [
    "Riyadh",
    "Jeddah",
    "Mecca",
    "Medina",
    "Dammam",
    "Abha",
    "Tabuk",
    "Buraidah",
    "Khobar",
    "Taif",
]

OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"


def get_env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None or value == "":
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def fetch_weather(city: str, api_key: str, country_code: str = "SA") -> dict:
    params = {
        "q": f"{city},{country_code}",
        "appid": api_key,
        "units": "metric",
    }

    response = requests.get(OPENWEATHER_URL, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()

    if "main" not in data or "weather" not in data or not data["weather"]:
        raise ValueError(f"Unexpected API response for {city}: {data}")

    return {
        "city": city,
        "country_code": country_code,
        "temperature_c": float(data["main"]["temp"]),
        "humidity": int(data["main"]["humidity"]),
        "weather_description": str(data["weather"][0]["description"]),
        "weather_main": str(data["weather"][0]["main"]),
        "pressure": int(data["main"].get("pressure")) if data["main"].get("pressure") is not None else None,
        "wind_speed": float(data["wind"]["speed"]) if data.get("wind", {}).get("speed") is not None else None,
        "cloudiness": int(data["clouds"]["all"]) if data.get("clouds", {}).get("all") is not None else None,
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "openweathermap",
    }


def insert_rows(rows: list[dict], table_id: str) -> None:
    client = bigquery.Client()
    errors = client.insert_rows_json(table_id, rows)

    if errors:
        raise RuntimeError(f"BigQuery insert errors: {errors}")


def main() -> None:
    api_key = get_env("OPENWEATHER_API_KEY")
    project_id = get_env("GCP_PROJECT_ID")
    dataset_id = get_env("BQ_DATASET")
    table_name = get_env("BQ_TABLE")

    table_id = f"{project_id}.{dataset_id}.{table_name}"

    print(f"Starting weather pipeline for {len(CITIES)} cities")
    print(f"Target BigQuery table: {table_id}")

    rows = []
    failures = []

    for city in CITIES:
        try:
            row = fetch_weather(city, api_key)
            rows.append(row)
            print(f"Fetched weather for {city}")
            time.sleep(1)  # gentle pacing for API calls
        except Exception as exc:
            failures.append({"city": city, "error": str(exc)})
            print(f"Failed for {city}: {exc}", file=sys.stderr)

    if rows:
        insert_rows(rows, table_id)
        print(f"Inserted {len(rows)} rows into {table_id}")
    else:
        raise RuntimeError("No rows were fetched successfully; nothing inserted.")

    if failures:
        print("Some cities failed:")
        for f in failures:
            print(f" - {f['city']}: {f['error']}", file=sys.stderr)

    print("Pipeline completed successfully.")


if __name__ == "__main__":
    main()