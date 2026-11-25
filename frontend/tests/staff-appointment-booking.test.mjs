import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const read = (name) => readFileSync(new URL(`../src/${name}`, import.meta.url), 'utf8')
const app = read('App.tsx')
const form = read('StaffAppointmentBooking.tsx')
const autocomplete = read('DirectoryAutocomplete.tsx')

test('staff and admin booking loads authenticated directory options independently', () => {
  assert.match(app, /staffBookingOpen && \(currentUser\?\.role === 'staff' \|\| currentUser\?\.role === 'admin'\)/)
  assert.match(form, /getPatients\(token, patientQuery\.trim\(\)\)/)
  assert.match(form, /getDoctors\(token, \{ search, specialization: specialty, limit \}\)/)
  assert.match(form, /doctors\.records\.find/)
  assert.match(form, /patients\.records\.find/)
})

test('booking uses verified slot timestamps and requires review before creation', () => {
  assert.match(form, /getAvailableSlots\(token, doctorId, date\)/)
  assert.match(form, /item\.status === 'available'/)
  assert.match(form, /if \(!review\) \{\s+setReview\(true\)\s+return/)
  assert.match(form, /appointment_date: slot/)
  assert.match(form, /created\.status/)
})

test('all three directory fields open searchable options with loading, empty and error states', () => {
  for (const label of ['Search by patient name', 'Search by doctor name', 'Filter by specialization']) {
    assert.ok(form.includes(`<DirectoryAutocomplete label="${label}"`))
  }
  assert.match(autocomplete, /onChange=\{\(event\) => \{ onChange\(event\.target\.value\); setOpen\(true\)/)
  assert.match(autocomplete, /records\.map\(\(record, position\)/)
  assert.match(autocomplete, /Loading matches/)
  assert.match(autocomplete, /role="alert"/)
  assert.match(autocomplete, /records\.length && <p role="status">\{noResults\}/)
  assert.match(form, /while \(active && specialty && pageSize === limit\)/)
})

test('autocomplete and native selects share the selected records and synchronize their labels', () => {
  assert.match(autocomplete, /onClick=\{\(\) => choose\(record\)\}/)
  assert.match(autocomplete, /onSelect\(record\)/)
  assert.match(form, /value=\{patient\?\.name \?\? patientQuery\}/)
  assert.match(form, /value=\{doctor\?\.name \?\? doctorQuery\}/)
  assert.match(form, /value=\{doctor\?\.specialization \?\? specialization\}/)
  assert.match(form, /onChange=\{changePatientQuery\} onSelect=\{setPatient\}/)
  assert.equal((form.match(/onSelect=\{selectDoctor\}/g) ?? []).length, 2)
  assert.match(form, /value=\{patient\?\.id \?\? ''\} onChange=\{\(event\) => setPatient\(patients\.records\.find/)
  assert.match(form, /value=\{doctorId \?\? ''\} onChange=\{\(event\) => selectDoctor\(doctors\.records\.find/)
  assert.match(form, /function changePatientQuery[^\n]*\n\s*setPatient\(undefined\)/)
  assert.match(form, /function changeDoctorQuery[^\n]*\n\s*selectDoctor\(\)/)
  assert.match(form, /if \(saving \|\| !patient \|\| !doctor \|\| !slot/)
})

test('suggestions use keyboard navigation and selected and active states', () => {
  assert.match(autocomplete, /case 'ArrowDown':[\s\S]*case 'ArrowUp':/)
  assert.match(autocomplete, /case 'Enter':[\s\S]*choose\(records\[activeIndex\]\)/)
  assert.match(autocomplete, /case 'Escape':[\s\S]*event\.preventDefault\(\)/)
  assert.match(autocomplete, /addEventListener\('pointerdown', closeOutside\)/)
  assert.match(autocomplete, /aria-selected=\{record\.id === selectedId\}/)
})
