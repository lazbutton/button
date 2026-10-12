export type DaypartRange<T extends { day_of_week: number; minute: number }> = {
  slot: T;
  day: number;
  start: number;
  end: number;
};

export function daypartRanges<T extends { day_of_week: number; minute: number }>(slots: T[]): DaypartRange<T>[] {
  const ranges: DaypartRange<T>[] = [];
  for (let day = 0; day < 7; day++) {
    const daySlots = slots
      .filter((slot) => slot.day_of_week === day)
      .slice()
      .sort((a, b) => a.minute - b.minute);
    for (let i = 0; i < daySlots.length; i++) {
      const slot = daySlots[i];
      const next = daySlots[i + 1];
      ranges.push({
        slot,
        day,
        start: slot.minute,
        end: next ? next.minute : 1440,
      });
    }
  }
  return ranges;
}

export function rangeAtMinute<T extends { day_of_week: number; minute: number }>(
  ranges: DaypartRange<T>[],
  day: number,
  minute: number,
): DaypartRange<T> | null {
  return ranges.find((range) => range.day === day && range.start <= minute && minute < range.end) ?? null;
}

export function formatDayMinute(minute: number): string {
  if (minute >= 1440) return "24:00";
  const hour = Math.floor(Math.max(0, minute) / 60);
  const min = Math.max(0, minute) % 60;
  return `${String(hour).padStart(2, "0")}:${String(min).padStart(2, "0")}`;
}
