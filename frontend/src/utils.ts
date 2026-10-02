export const money = new Intl.NumberFormat('en-IN', {
  style: 'currency', currency: 'INR', maximumFractionDigits: 2,
})

export const istTime = new Intl.DateTimeFormat('en-IN', {
  timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', second: '2-digit',
})

export const istDateTime = new Intl.DateTimeFormat('en-IN', {
  timeZone: 'Asia/Kolkata', day: '2-digit', month: 'short', year: 'numeric',
  hour: '2-digit', minute: '2-digit', second: '2-digit',
})

export function apiDate(value: string) {
  return new Date(/[zZ]|[+-]\d{2}:\d{2}$/.test(value) ? value : `${value}Z`)
}

export function formatIstTime(value: Date) { return `${istTime.format(value)} IST` }
export function formatIstDateTime(value: string) { return `${istDateTime.format(apiDate(value))} IST` }

export function environmentLabel(broker: string) {
  if (broker === 'UPSTOX_SANDBOX') return 'UPSTOX SANDBOX'
  if (broker === 'UPSTOX' || broker === 'UPSTOX_LIVE') return 'UPSTOX LIVE'
  return 'PAPER'
}
