from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import requests
from matplotlib.widgets import Button, TextBox


BAKU_LATITUDE = 40.4093
BAKU_LONGITUDE = 49.8671
START_DATE = "2015-01-01"
END_DATE = "2025-12-31"

OUTPUT_CSV_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "baku_weather_hourly_data.csv"
)

OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
HOURLY_FIELDS = ["temperature_2m", "weather_code", "wind_speed_10m"]

CATEGORY_COLORS = {
    "Clear": "#f9d71c",
    "Cloudy": "#9e9e9e",
    "Light Rain": "#7fb3d5",
    "Rainy": "#2980b9",
    "Snowy": "#d6eaf8",
    "Foggy": "#bdc3c7",
    "Stormy": "#5b2c6f",
    "Other": "#aaaaaa",
    "Unknown": "#cccccc",
}

LEGEND_ORDER = [
    "Clear",
    "Cloudy",
    "Light Rain",
    "Rainy",
    "Snowy",
    "Foggy",
    "Stormy",
    "Other",
    "Unknown",
]


def weather_code_to_category(code):
    """Open-Meteo WMO weather code -> short category."""
    if pd.isna(code):
        return "Unknown"

    code = int(code)
    if code == 0:
        return "Clear"
    if code in (1, 2, 3):
        return "Cloudy"
    if code in (45, 48):
        return "Foggy"
    if code in (51, 53, 55, 56, 57):
        return "Light Rain"
    if code in (61, 63, 65, 66, 67, 80, 81, 82):
        return "Rainy"
    if code in (71, 73, 75, 77, 85, 86):
        return "Snowy"
    if code in (95, 96, 99):
        return "Stormy"
    return "Other"


def fetch_hourly_weather(start_date: str = START_DATE, end_date: str = END_DATE) -> pd.DataFrame:
    params = {
        "latitude": BAKU_LATITUDE,
        "longitude": BAKU_LONGITUDE,
        "start_date": start_date,
        "end_date": end_date,
        "hourly": ",".join(HOURLY_FIELDS),
        "timezone": "Asia/Baku",
    }
    response = requests.get(OPEN_METEO_ARCHIVE_URL, params=params, timeout=60)
    response.raise_for_status()
    payload = response.json()

    if "hourly" not in payload:
        reason = payload.get("reason", "Open-Meteo response did not include hourly data.")
        raise RuntimeError(reason)

    hourly = payload["hourly"]
    df = pd.DataFrame(
        {
            "time_bin": hourly["time"],
            "temperature": hourly["temperature_2m"],
            "weather_code": hourly["weather_code"],
            "wind_speed": hourly["wind_speed_10m"],
        }
    )
    df["time_bin"] = pd.to_datetime(df["time_bin"])
    return df


def generate_weather_csv(
    output_csv_path: str | Path = OUTPUT_CSV_PATH,
    start_date: str = START_DATE,
    end_date: str = END_DATE,
) -> Path:
    output_csv_path = Path(output_csv_path)
    output_csv_path.parent.mkdir(parents=True, exist_ok=True)

    df = fetch_hourly_weather(start_date=start_date, end_date=end_date)
    df = df.sort_values("time_bin").reset_index(drop=True)
    df["time_bin"] = df["time_bin"].dt.strftime("%Y-%m-%d %H:%M:%S")
    df.to_csv(output_csv_path, index=False)

    print(f"Saved {len(df)} hourly rows to {output_csv_path}")
    print(f"Range: {df['time_bin'].iloc[0]} -> {df['time_bin'].iloc[-1]}")
    return output_csv_path


def visualize_daily_weather(
    csv_path: str | Path = OUTPUT_CSV_PATH,
    target_date: str | None = None,
):
    csv_path = Path(csv_path)
    if not csv_path.exists():
        print(f"Error: File was not found -> {csv_path}")
        return

    df = pd.read_csv(csv_path)
    required_columns = {"time_bin", "temperature", "weather_code", "wind_speed"}
    missing_columns = required_columns.difference(df.columns)
    if missing_columns:
        print(f"Error: Missing required columns: {sorted(missing_columns)}")
        return

    df["time_bin"] = pd.to_datetime(df["time_bin"], errors="coerce")
    df = df.dropna(subset=["time_bin"]).copy()
    df["date"] = df["time_bin"].dt.normalize()

    available_dates = sorted(pd.Timestamp(d) for d in df["date"].dropna().unique())
    if not available_dates:
        print("Error: No valid date was found in the weather data.")
        return

    rain_like_codes = [51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82]
    rainy_days = (
        df[df["weather_code"].isin(rain_like_codes)]["date"]
        .dt.strftime("%Y-%m-%d")
        .unique()
    )

    parsed_target = pd.to_datetime(target_date, errors="coerce") if target_date else pd.NaT
    if pd.isna(parsed_target) or parsed_target.normalize() not in available_dates:
        parsed_target = (
            pd.to_datetime(rainy_days[0]) if len(rainy_days) > 0 else available_dates[0]
        )
    else:
        parsed_target = parsed_target.normalize()

    current_index = available_dates.index(parsed_target)
    output_dir = Path(__file__).resolve().parents[1] / "reports" / "figures"
    output_dir.mkdir(parents=True, exist_ok=True)

    all_category_counts = df["weather_code"].apply(weather_code_to_category).value_counts()

    fig, (ax_temp, ax_wind, ax_cat) = plt.subplots(
        3,
        1,
        figsize=(16, 8.5),
        sharex=True,
        gridspec_kw={"height_ratios": [5, 2, 0.6], "hspace": 0.08},
    )
    plt.subplots_adjust(left=0.07, right=0.80, bottom=0.18, top=0.92)

    def render_plot(selected_date):
        for axis in (ax_temp, ax_wind, ax_cat):
            axis.clear()

        filtered = df[df["date"] == selected_date].copy()
        if filtered.empty:
            ax_temp.set_title("No weather data is available for this date")
            fig.canvas.draw_idle()
            return

        grouped = filtered.sort_values("time_bin").copy()
        grouped["Time"] = grouped["time_bin"].dt.strftime("%H:%M")
        grouped["weather_category"] = grouped["weather_code"].apply(weather_code_to_category)

        n = len(grouped)
        x = list(range(n))
        bar_colors = [CATEGORY_COLORS.get(cat, "#999999") for cat in grouped["weather_category"]]

        ax_temp.bar(
            x,
            grouped["temperature"],
            color=bar_colors,
            edgecolor="#555555",
            linewidth=0.4,
            width=0.9,
        )
        ax_temp.set_ylabel("Temp (C)", fontsize=10)
        ax_temp.grid(alpha=0.25, axis="y")

        date_str = pd.Timestamp(selected_date).strftime("%Y-%m-%d")
        weekday_num = pd.Timestamp(selected_date).isoweekday()
        ax_temp.set_title(
            f"Baku - Daily Weather Chart ({date_str}) | Weekday: {weekday_num}",
            fontsize=15,
            fontweight="bold",
            pad=10,
        )

        wind_vals = grouped["wind_speed"].astype(float).fillna(0.0)
        ax_wind.bar(
            x,
            wind_vals,
            color="#e67e22",
            edgecolor="#555555",
            linewidth=0.3,
            width=0.9,
        )
        ax_wind.set_ylabel("Wind (m/s)", fontsize=10)
        ax_wind.grid(alpha=0.25, axis="y")

        for xi, color in zip(x, bar_colors):
            ax_cat.bar(xi, 1, color=color, edgecolor="none", width=1.0)
        ax_cat.set_ylim(0, 1)
        ax_cat.set_yticks([])
        ax_cat.set_xlim(-0.5, n - 0.5)

        if n <= 24:
            step = 2
        elif n <= 48:
            step = 4
        else:
            step = max(1, n // 24)

        tick_idx = list(range(0, n, step))
        if tick_idx[-1] != n - 1:
            tick_idx.append(n - 1)

        for axis in (ax_temp, ax_wind, ax_cat):
            axis.set_xlim(-0.5, n - 0.5)

        ax_cat.set_xticks(tick_idx)
        ax_cat.set_xticklabels(
            grouped["Time"].iloc[tick_idx], rotation=45, ha="right", fontsize=9
        )
        ax_cat.set_xlabel("Time", fontsize=10)

        from matplotlib.patches import Patch

        legend_handles = [
            Patch(facecolor=CATEGORY_COLORS[name], label=name)
            for name in LEGEND_ORDER
            if name in CATEGORY_COLORS
        ]
        ax_temp.legend(
            handles=legend_handles,
            loc="upper left",
            bbox_to_anchor=(1.01, 1.0),
            fontsize=8,
            title="Weather",
            frameon=True,
        )

        cat_counts = grouped["weather_category"].value_counts()
        summary_lines = [f"{name}: {int(cat_counts.get(name, 0))}" for name in LEGEND_ORDER]
        summary_text = "Daily Category Counts\n\n" + "\n".join(summary_lines)
        ax_temp.text(
            1.01,
            0.55,
            summary_text,
            transform=ax_temp.transAxes,
            va="top",
            ha="left",
            fontsize=9,
            bbox={"boxstyle": "round", "facecolor": "#f7f7f7", "edgecolor": "#cccccc"},
        )

        all_lines = [f"{name}: {int(all_category_counts.get(name, 0))}" for name in LEGEND_ORDER]
        all_text = "All Data Counts\n\n" + "\n".join(all_lines)
        ax_wind.text(
            1.01,
            1.05,
            all_text,
            transform=ax_wind.transAxes,
            va="top",
            ha="left",
            fontsize=9,
            bbox={"boxstyle": "round", "facecolor": "#eef6ff", "edgecolor": "#bcd7f0"},
        )

        fig.canvas.draw_idle()

    def go_previous(_event):
        nonlocal current_index
        current_index = (current_index - 1) % len(available_dates)
        date_input.set_val(pd.Timestamp(available_dates[current_index]).strftime("%Y-%m-%d"))
        render_plot(available_dates[current_index])

    def go_next(_event):
        nonlocal current_index
        current_index = (current_index + 1) % len(available_dates)
        date_input.set_val(pd.Timestamp(available_dates[current_index]).strftime("%Y-%m-%d"))
        render_plot(available_dates[current_index])

    def submit_date(text):
        nonlocal current_index
        selected = pd.to_datetime(text, errors="coerce")
        if pd.isna(selected):
            print("Error: Invalid date format. Example: YYYY-MM-DD")
            return

        selected = selected.normalize()
        if selected not in available_dates:
            print(f"Error: No data is available for {selected.strftime('%Y-%m-%d')}.")
            return

        current_index = available_dates.index(selected)
        render_plot(available_dates[current_index])

    def save_current(_event):
        selected_date = available_dates[current_index]
        date_str = pd.Timestamp(selected_date).strftime("%Y-%m-%d")
        output_image = output_dir / f"baku_weather_{date_str}.png"
        fig.savefig(output_image, dpi=300)
        print(f"Saved: {output_image}")

    input_ax = plt.axes([0.10, 0.03, 0.20, 0.04])
    prev_ax = plt.axes([0.32, 0.03, 0.05, 0.04])
    next_ax = plt.axes([0.38, 0.03, 0.05, 0.04])
    save_ax = plt.axes([0.45, 0.03, 0.08, 0.04])

    date_input = TextBox(
        input_ax,
        "Date: ",
        initial=pd.Timestamp(available_dates[current_index]).strftime("%Y-%m-%d"),
    )
    prev_btn = Button(prev_ax, "<-")
    next_btn = Button(next_ax, "->")
    save_btn = Button(save_ax, "Save")

    date_input.on_submit(submit_date)
    prev_btn.on_clicked(go_previous)
    next_btn.on_clicked(go_next)
    save_btn.on_clicked(save_current)

    render_plot(available_dates[current_index])
    plt.show()


if __name__ == "__main__":
    generate_weather_csv()
