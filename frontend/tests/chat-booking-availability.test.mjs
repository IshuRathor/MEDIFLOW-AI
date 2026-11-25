import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import { renderToStaticMarkup } from 'react-dom/server'
import {
  candidateAppointmentDates,
  ChatAppointmentPicker,
  loadAppointmentDateSlots,
  loadDoctorAppointmentDates,
} from '../src/chatBookingAvailability.js'

function findElements(element, predicate, found = []) {
  if (Array.isArray(element)) {
    for (const child of element) findElements(child, predicate, found)
  } else if (element && typeof element === 'object' && element.props) {
    if (predicate(element)) found.push(element)
    findElements(element.props.children, predicate, found)
  }
  return found
}

const weekdayRule = (day, isAvailable = true, specificDate = null) => ({
  day_of_week: day,
  specific_date: specificDate,
  is_available: isAvailable,
})

test('candidate dates use real weekly schedules and specific-date blocks', () => {
  const dates = candidateAppointmentDates([
    weekdayRule('Monday'),
    weekdayRule('Friday'),
    weekdayRule('Friday', false, '2026-01-02'),
    weekdayRule('Saturday', true, '2026-01-03'),
  ], '2026-01-01', 10)

  assert.deepEqual(dates, ['2026-01-03', '2026-01-05', '2026-01-09'])
  assert.equal(candidateAppointmentDates([weekdayRule('Thursday')], '2026-01-01', 3).includes('2026-01-01'), true)
  assert.deepEqual(candidateAppointmentDates([weekdayRule('Sunday')], '2026-01-05', 3), [])
})

test('selecting a doctor loads its schedule and only enables dates with open slots', async () => {
  const scheduleCalls = []
  const slotCalls = []
  const dates = await loadDoctorAppointmentDates({
    doctorId: 42,
    startDate: '2026-01-05',
    dayCount: 4,
    getAvailability: async (doctorId) => {
      scheduleCalls.push(doctorId)
      return [weekdayRule('Monday'), weekdayRule('Tuesday'), weekdayRule('Wednesday')]
    },
    getSlots: async (doctorId, date) => {
      slotCalls.push([doctorId, date])
      return {
        blocked: date === '2026-01-07',
        slots: [{ start: `${date}T09:00:00`, end: `${date}T09:30:00`, status: date === '2026-01-06' ? 'booked' : 'available' }],
        alternatives: [],
      }
    },
  })

  assert.deepEqual(scheduleCalls, [42])
  assert.deepEqual(slotCalls, [[42, '2026-01-05'], [42, '2026-01-06'], [42, '2026-01-07']])
  assert.deepEqual(dates, ['2026-01-05'])
})

test('empty schedule returns no dates and makes no invented slot requests', async () => {
  let slotCalls = 0
  const dates = await loadDoctorAppointmentDates({
    doctorId: 8,
    startDate: '2026-01-05',
    getAvailability: async () => [],
    getSlots: async () => { slotCalls += 1; return { blocked: false, slots: [], alternatives: [] } },
  })
  assert.deepEqual(dates, [])
  assert.equal(slotCalls, 0)
  assert.match(renderToStaticMarkup(ChatAppointmentPicker({ availabilityDates: [] })), /No appointment dates with open times/)
})

test('available dates can be selected while past and unavailable dates are disabled', () => {
  let selectedDate = ''
  const tree = ChatAppointmentPicker({
    availabilityDates: ['2026-01-05', '2026-01-08'],
    startDate: '2026-01-05',
    dayCount: 20,
    onSelectDate: (date) => { selectedDate = date },
  })
  const buttons = findElements(tree, (element) => element.type === 'button' && element.props.className?.includes('calendar-day'))
  const past = buttons.find((element) => element.key === '2026-01-04')
  const available = buttons.find((element) => element.key === '2026-01-05')
  const unavailable = buttons.find((element) => element.key === '2026-01-06')

  assert.equal(past.props.disabled, true)
  assert.equal(unavailable.props.disabled, true)
  assert.equal(available.props.disabled, false)
  available.props.onClick()
  assert.equal(selectedDate, '2026-01-05')
})

test('choosing a date fetches that date slots and selecting a time continues the booking prompt', async () => {
  let requested = null
  const result = await loadAppointmentDateSlots({
    doctorId: 11,
    date: '2026-01-08',
    getSlots: async (doctorId, date) => {
      requested = { doctorId, date }
      return { blocked: false, slots: [{ start: `${date}T10:30:00`, end: `${date}T11:00:00`, status: 'available' }], alternatives: [] }
    },
  })
  assert.deepEqual(requested, { doctorId: 11, date: '2026-01-08' })
  assert.equal(result.slots[0].status, 'available')

  let chosenSlot = null
  const picker = ChatAppointmentPicker({
    availabilityDates: ['2026-01-08'],
    startDate: '2026-01-05',
    dayCount: 10,
    selectedDate: '2026-01-08',
    slots: result.slots,
    onSelectSlot: (slot) => { chosenSlot = slot },
  })
  const timeButton = findElements(picker, (element) => element.type === 'button' && element.props.className?.includes('booking-time-option'))[0]
  timeButton.props.onClick()
  assert.equal(chosenSlot, result.slots[0])
})

test('chat modal stays viewport-bound with a scrollable transcript and fixed composer', async () => {
  const css = await readFile(new URL('../src/App.css', import.meta.url), 'utf8')
  const app = await readFile(new URL('../src/App.tsx', import.meta.url), 'utf8')
  assert.match(css, /\.chat-modal\s*\{[^}]*max-height:\s*90vh;[^}]*max-height:\s*90dvh;/s)
  assert.match(css, /\.chat-modal \.conversation-transcript\s*\{[^}]*flex:\s*1 1 auto;[^}]*min-height:\s*0;[^}]*max-height:\s*none;/s)
  assert.match(css, /\.chat-modal \.chat-composer\s*\{[^}]*flex:\s*0 0 auto;/s)
  assert.match(css, /safe-area-inset-bottom/)
  assert.match(app, /className="resource-form chat-composer"[\s\S]*Ask assistant/)
})
