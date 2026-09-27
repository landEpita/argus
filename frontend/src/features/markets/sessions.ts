/**
 * Whether the main cash sessions are open, from the exchange's own clock.
 * Regular hours only: holidays, lunch breaks and half days are not modelled,
 * and the interface says so.
 */
export interface Exchange {
  name: string;
  timeZone: string;
  /** Minutes after local midnight. */
  open: number;
  close: number;
}

export const EXCHANGES: readonly Exchange[] = [
  { name: "Asia", timeZone: "Asia/Tokyo", open: 9 * 60, close: 15 * 60 + 30 },
  { name: "Europe", timeZone: "Europe/Berlin", open: 9 * 60, close: 17 * 60 + 30 },
  { name: "US", timeZone: "America/New_York", open: 9 * 60 + 30, close: 16 * 60 },
];

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function localClock(at: Date, timeZone: string): { day: number; minute: number } {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(at);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return {
    day: WEEKDAYS.indexOf(get("weekday")),
    minute: Number(get("hour")) * 60 + Number(get("minute")),
  };
}

export interface SessionState {
  name: string;
  open: boolean;
  /** Until it closes (open) or opens (closed). */
  minutesUntilChange: number;
}

export function sessionState(exchange: Exchange, at: Date): SessionState {
  const { day, minute } = localClock(at, exchange.timeZone);
  const weekday = day >= 1 && day <= 5;
  if (weekday && minute >= exchange.open && minute < exchange.close) {
    return { name: exchange.name, open: true, minutesUntilChange: exchange.close - minute };
  }
  // Next opening: later today, or the next weekday.
  let days = 0;
  if (!(weekday && minute < exchange.open)) {
    days = 1;
    while (![1, 2, 3, 4, 5].includes((day + days) % 7)) days += 1;
  }
  return {
    name: exchange.name,
    open: false,
    minutesUntilChange: days * 1440 + exchange.open - minute,
  };
}

export function formatDuration(minutes: number): string {
  const d = Math.floor(minutes / 1440);
  const h = Math.floor((minutes % 1440) / 60);
  const m = minutes % 60;
  if (d) return `${d} d ${h} h`;
  return h ? `${h} h ${m} min` : `${m} min`;
}
