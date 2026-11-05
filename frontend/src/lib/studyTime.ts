export function formatStudyTime(totalSeconds: number): string {
  const hours = totalSeconds / 3600
  if (hours >= 1) return `${hours.toFixed(1)}h`
  return `${Math.round(totalSeconds / 60)}m`
}
