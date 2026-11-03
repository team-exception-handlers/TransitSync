// AI contribution: Below 50% AI-generated

export function formatTime(
    time_s: number,
    start_clock_s: number,
): string {
    const secondsPerDay = 24 * 60 * 60;

    const total = Math.floor(start_clock_s + time_s);

    const clock = ((total % secondsPerDay) + secondsPerDay) % secondsPerDay;

    const hours = Math.floor(clock / 3600);

    const minutes = Math.floor(
        (clock % 3600) / 60,
    );

    const seconds = clock % 60;

    return [hours, minutes, seconds]
        .map((value) =>
            String(value).padStart(2, "0"),
        )
        .join(":");
}