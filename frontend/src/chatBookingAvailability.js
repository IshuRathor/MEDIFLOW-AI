import React from 'react'

const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
const WEEKDAY_LABELS = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa']
const CALENDAR_DAYS = 90

function asDateKey(value) {
  if (typeof value === 'string') return value.slice(0, 10)
  const date = value instanceof Date ? value : new Date(value)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function utcDate(dateKey) {
  return new Date(`${dateKey}T12:00:00Z`)
}

export function candidateAppointmentDates(rules, startDate = new Date(), dayCount = CALENDAR_DAYS) {
  const startKey = asDateKey(startDate)
  const rulesBySpecificDate = new Map()
  const recurringRules = new Set()

  for (const rule of rules ?? []) {
    if (rule.specific_date) {
      const records = rulesBySpecificDate.get(rule.specific_date) ?? []
      records.push(rule)
      rulesBySpecificDate.set(rule.specific_date, records)
    } else if (rule.is_available) {
      recurringRules.add(rule.day_of_week)
    }
  }

  const candidates = []
  for (let offset = 0; offset < dayCount; offset += 1) {
    const date = utcDate(startKey)
    date.setUTCDate(date.getUTCDate() + offset)
    const dateKey = date.toISOString().slice(0, 10)
    const specificRules = rulesBySpecificDate.get(dateKey)
    const hasAvailableSchedule = specificRules
      ? !specificRules.some((rule) => !rule.is_available) && specificRules.some((rule) => rule.is_available)
      : recurringRules.has(WEEKDAYS[date.getUTCDay()])
    if (hasAvailableSchedule) candidates.push(dateKey)
  }
  return candidates
}

export async function loadDoctorAppointmentDates({ doctorId, startDate, getAvailability, getSlots, dayCount = CALENDAR_DAYS }) {
  const rules = await getAvailability(doctorId)
  const candidates = candidateAppointmentDates(rules, startDate, dayCount)
  const results = new Array(candidates.length)
  let nextIndex = 0
  let firstError = null

  async function checkCandidateDates() {
    while (nextIndex < candidates.length) {
      const index = nextIndex
      nextIndex += 1
      const date = candidates[index]
      try {
        const result = await getSlots(doctorId, date)
        results[index] = !result.blocked && result.slots?.some((slot) => slot.status === 'available') ? date : null
      } catch (error) {
        firstError ??= error
      }
    }
  }

  const workers = Array.from({ length: Math.min(8, candidates.length) }, () => checkCandidateDates())
  await Promise.all(workers)
  if (firstError) throw firstError
  return results.filter(Boolean)
}

export function loadAppointmentDateSlots({ doctorId, date, getSlots }) {
  return getSlots(doctorId, date)
}

export function calendarMonthCells(year, month) {
  const firstWeekday = new Date(year, month, 1).getDay()
  const dayCount = new Date(year, month + 1, 0).getDate()
  return [
    ...Array.from({ length: firstWeekday }, () => null),
    ...Array.from({ length: dayCount }, (_, index) => {
      const day = String(index + 1).padStart(2, '0')
      return `${year}-${String(month + 1).padStart(2, '0')}-${day}`
    }),
  ]
}

function monthStart(dateKey) {
  const date = utcDate(dateKey)
  return new Date(date.getUTCFullYear(), date.getUTCMonth(), 1)
}

function monthLabel(date) {
  return new Intl.DateTimeFormat(undefined, { month: 'long', year: 'numeric' }).format(date)
}

function timeLabel(value) {
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? value.slice(11, 16)
    : date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
}

export function ChatAppointmentPicker({
  availabilityDates = [],
  availabilityLoading = false,
  availabilityError = '',
  selectedDate = '',
  slots = [],
  slotsLoading = false,
  slotsError = '',
  selectedTime = '',
  disabled = false,
  viewMonth: requestedMonth,
  onChangeMonth,
  onSelectDate,
  onSelectSlot,
  startDate = asDateKey(new Date()),
  dayCount = CALENDAR_DAYS,
}) {
  const firstMonth = monthStart(startDate)
  const lastDate = utcDate(startDate)
  lastDate.setUTCDate(lastDate.getUTCDate() + dayCount - 1)
  const lastMonth = new Date(lastDate.getUTCFullYear(), lastDate.getUTCMonth(), 1)
  const viewMonth = requestedMonth ?? (selectedDate ? monthStart(selectedDate) : firstMonth)

  const currentMonthKey = `${viewMonth.getFullYear()}-${String(viewMonth.getMonth() + 1).padStart(2, '0')}`
  const firstMonthKey = `${firstMonth.getFullYear()}-${String(firstMonth.getMonth() + 1).padStart(2, '0')}`
  const lastMonthKey = `${lastMonth.getFullYear()}-${String(lastMonth.getMonth() + 1).padStart(2, '0')}`
  const available = new Set(availabilityDates)
  const slotsAvailable = slots.filter((slot) => slot.status === 'available')

  function changeMonth(amount) {
    onChangeMonth?.(new Date(viewMonth.getFullYear(), viewMonth.getMonth() + amount, 1))
  }

  return React.createElement('section', { className: 'chat-booking-picker', 'aria-label': 'Choose an appointment date and time' },
    React.createElement('div', { className: 'booking-picker-heading' },
      React.createElement('strong', null, 'Choose an available date'),
      availabilityLoading && React.createElement('span', { role: 'status' }, 'Checking schedule…'),
    ),
    availabilityError && React.createElement('p', { className: 'form-error', role: 'alert' }, availabilityError),
    !availabilityLoading && !availabilityError && availabilityDates.length === 0
      ? React.createElement('p', { className: 'dashboard-state' }, 'No appointment dates with open times were found in the next three months. You can still enter another date in your message and MediFlow will check it.')
      : React.createElement(React.Fragment, null,
        React.createElement('div', { className: 'booking-calendar' },
          React.createElement('div', { className: 'calendar-toolbar' },
            React.createElement('button', { type: 'button', className: 'calendar-nav', 'aria-label': 'Previous month', disabled: currentMonthKey <= firstMonthKey, onClick: () => changeMonth(-1) }, '‹'),
            React.createElement('strong', null, monthLabel(viewMonth)),
            React.createElement('button', { type: 'button', className: 'calendar-nav', 'aria-label': 'Next month', disabled: currentMonthKey >= lastMonthKey, onClick: () => changeMonth(1) }, '›'),
          ),
          React.createElement('div', { className: 'calendar-grid calendar-weekdays', 'aria-hidden': true }, WEEKDAY_LABELS.map((day) => React.createElement('span', { key: day }, day))),
          React.createElement('div', { className: 'calendar-grid calendar-days' }, calendarMonthCells(viewMonth.getFullYear(), viewMonth.getMonth()).map((date, index) => {
            if (!date) return React.createElement('span', { className: 'calendar-day-spacer', key: `blank-${currentMonthKey}-${index}` })
            const isInRange = date >= startDate && date <= lastDate.toISOString().slice(0, 10)
            const isAvailable = isInRange && available.has(date)
            const dayNumber = Number(date.slice(-2))
            return React.createElement('button', {
              type: 'button',
              className: `calendar-day${date === selectedDate ? ' selected' : ''}${isAvailable ? ' available' : ''}`,
              key: date,
              disabled: disabled || availabilityLoading || !isAvailable,
              'aria-label': new Intl.DateTimeFormat(undefined, { dateStyle: 'full' }).format(new Date(`${date}T12:00:00`)),
              'aria-pressed': date === selectedDate,
              onClick: () => onSelectDate?.(date),
            }, String(dayNumber))
          })),
        ),
        !availabilityLoading && availabilityDates.length > 0 && React.createElement('p', { className: 'calendar-hint' }, 'Only dates with at least one open appointment time can be selected.'),
        selectedDate && React.createElement('div', { className: 'booking-time-picker' },
          React.createElement('strong', null, `Available times for ${new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date(`${selectedDate}T12:00:00`))}`),
          slotsLoading && React.createElement('p', { role: 'status', className: 'dashboard-state' }, 'Loading open times…'),
          slotsError && React.createElement('p', { className: 'form-error', role: 'alert' }, slotsError),
          !slotsLoading && !slotsError && slotsAvailable.length === 0 && React.createElement('p', { className: 'dashboard-state' }, 'No times are currently available for this date. Choose another date or enter a different date in your message.'),
          !slotsLoading && !slotsError && slotsAvailable.length > 0 && React.createElement('div', { className: 'booking-time-options', 'aria-label': 'Available appointment times' }, slotsAvailable.map((slot) => {
            const time = slot.start.slice(11, 16)
            return React.createElement('button', {
              type: 'button',
              className: `booking-time-option${time === selectedTime ? ' selected' : ''}`,
              key: slot.start,
              disabled,
              onClick: () => onSelectSlot?.(slot),
            }, timeLabel(slot.start))
          })),
        ),
      ),
  )
}

export { asDateKey, CALENDAR_DAYS }
