// "1 showtime" / "2 showtimes": the count decides the form, never a trailing "(s)" (S7.21).
export function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}
