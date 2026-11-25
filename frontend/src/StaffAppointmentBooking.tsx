import { useEffect, useRef, useState, type FormEvent } from 'react'
import {
  createAppointment, getAvailableSlots, getDoctors, getPatients,
  type AppointmentRecord, type AppointmentSlot, type DoctorRecord, type PatientRecord,
} from './api'
import { asDateKey } from './chatBookingAvailability.js'
import DirectoryAutocomplete, { type DirectoryLookup } from './DirectoryAutocomplete'

const emptyLookup = <T,>(): DirectoryLookup<T> => ({ records: [], loading: true, error: '' })
const errorText = (error: unknown, fallback: string) => error instanceof Error ? error.message : fallback
const doctorLabel = (doctor: DoctorRecord) => [doctor.name, doctor.specialization, doctor.department].filter(Boolean).join(' · ')
const doctorSuggestion = (doctor: DoctorRecord) => [doctorLabel(doctor), doctor.experience_years == null ? '' : `${doctor.experience_years} years of experience`].filter(Boolean).join(' · ')
const patientLabel = (patient: PatientRecord) => `${patient.name} · Patient #${patient.id}`
const slotLabel = (slot: string) => new Date(slot).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })

export default function StaffAppointmentBooking({ token, onClose, onBooked }: {
  token: string
  onClose: () => void
  onBooked: (appointment: AppointmentRecord, patient: PatientRecord, doctor: DoctorRecord) => void
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const [today] = useState(() => asDateKey(new Date()))
  const [patientQuery, setPatientQuery] = useState('')
  const [doctorQuery, setDoctorQuery] = useState('')
  const [specialization, setSpecialization] = useState('')
  const [patients, setPatients] = useState(emptyLookup<PatientRecord>)
  const [doctors, setDoctors] = useState(emptyLookup<DoctorRecord>)
  const [patient, setPatient] = useState<PatientRecord>()
  const [doctor, setDoctor] = useState<DoctorRecord>()
  const [date, setDate] = useState('')
  const [slot, setSlot] = useState('')
  const [slots, setSlots] = useState<AppointmentSlot[]>([])
  const [alternatives, setAlternatives] = useState<string[]>([])
  const [slotsLoading, setSlotsLoading] = useState(false)
  const [slotNotice, setSlotNotice] = useState('')
  const [refresh, setRefresh] = useState(0)
  const [reason, setReason] = useState('')
  const [review, setReview] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [created, setCreated] = useState<AppointmentRecord>()
  const doctorId = doctor?.id

  useEffect(() => {
    const element = dialog.current
    element?.showModal()
    return () => element?.close()
  }, [])

  useEffect(() => {
    let active = true
    const timer = window.setTimeout(() => {
      getPatients(token, patientQuery.trim()).then((records) => {
        if (active) setPatients({ records, loading: false, error: '' })
      }).catch((failure) => {
        if (active) setPatients({ records: [], loading: false, error: errorText(failure, 'Patients could not be loaded.') })
      })
    }, 180)
    return () => { active = false; window.clearTimeout(timer) }
  }, [patientQuery, token])

  useEffect(() => {
    let active = true
    const timer = window.setTimeout(async () => {
      const search = doctorQuery.trim()
      const specialty = specialization.trim()
      const limit = specialty ? 200 : 50
      try {
        const records = await getDoctors(token, { search, specialization: specialty, limit })
        let pageSize = records.length
        while (active && specialty && pageSize === limit) {
          const page = await getDoctors(token, { search, specialization: specialty, limit, offset: records.length })
          records.push(...page)
          pageSize = page.length
        }
        if (active) setDoctors({ records, loading: false, error: '' })
      } catch (failure) {
        if (active) setDoctors({ records: [], loading: false, error: errorText(failure, 'Doctors could not be loaded.') })
      }
    }, 180)
    return () => { active = false; window.clearTimeout(timer) }
  }, [doctorQuery, specialization, token])

  useEffect(() => {
    if (!doctorId || !date) return
    let active = true
    getAvailableSlots(token, doctorId, date).then((result) => {
      if (!active) return
      const open = result.blocked ? [] : result.slots.filter((item) =>
        item.status === 'available' && new Date(item.start).getTime() > Date.now(),
      )
      setSlots(open)
      setAlternatives(result.alternatives)
      setSlotNotice(result.blocked ? 'The doctor has blocked this date.' : open.length ? '' : 'No available times on this date.')
    }).catch((failure) => {
      if (active) setSlotNotice(errorText(failure, 'Appointment times could not be loaded.'))
    }).finally(() => {
      if (active) setSlotsLoading(false)
    })
    return () => { active = false }
  }, [date, doctorId, refresh, token])

  function clearSlots() {
    setSlot('')
    setSlots([])
    setAlternatives([])
    setSlotNotice('')
  }

  function selectDate(value: string) {
    if (value === date) return
    clearSlots()
    setDate(value)
    setSlotsLoading(Boolean(value))
  }

  function selectDoctor(value?: DoctorRecord) {
    setDoctor(value)
    if (value?.id === doctorId) return
    setDate('')
    clearSlots()
    setSlotsLoading(false)
  }

  function changePatientQuery(value: string) {
    setPatient(undefined)
    if (value !== patientQuery) setPatients(emptyLookup())
    setPatientQuery(value)
  }

  function changeDoctorQuery(value: string, field: 'name' | 'specialization') {
    selectDoctor()
    const name = field === 'name' ? value : ''
    const specialty = field === 'specialization' ? value : ''
    if (name !== doctorQuery || specialty !== specialization) setDoctors(emptyLookup())
    setDoctorQuery(name)
    setSpecialization(specialty)
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (saving || !patient || !doctor || !slot || !reason.trim()) return
    setError('')
    if (!review) {
      setReview(true)
      return
    }
    setSaving(true)
    try {
      // Use the schedule timestamp verbatim so browser timezone conversion cannot shift the slot.
      const appointment = await createAppointment(token, {
        patient_id: patient.id, doctor_id: doctor.id, appointment_date: slot, reason: reason.trim(),
      })
      setCreated(appointment)
      onBooked(appointment, patient, doctor)
    } catch (failure) {
      setError(errorText(failure, 'The appointment could not be booked.'))
      setReview(false)
      clearSlots()
      setSlotsLoading(true)
      setRefresh((value) => value + 1)
    } finally {
      setSaving(false)
    }
  }

  return <dialog ref={dialog} className="triage-modal resource-modal staff-booking" aria-labelledby="staff-booking-title" onCancel={(event) => {
    event.preventDefault()
    if (!saving) onClose()
  }}>
    <button className="modal-close" type="button" onClick={onClose} disabled={saving} aria-label="Close appointment form">×</button>
    <p className="eyebrow">Appointments</p>
    <h2 id="staff-booking-title">{created ? 'Booking saved' : review ? 'Review appointment' : 'Add appointment'}</h2>
    {created ? <>
      <p role="status">{patient?.name} · {doctor?.name} · {asDateKey(slot)} at {slotLabel(slot)} · {created.status}</p>
      <button className="dark-button" type="button" onClick={onClose}>Done</button>
    </> : <form className="resource-form" onSubmit={(event) => void submit(event)}>
      {review ? <dl className="booking-review">
        <div><dt>Patient</dt><dd>{patient?.name} · Patient #{patient?.id}</dd></div>
        <div><dt>Doctor</dt><dd>{doctor && doctorLabel(doctor)}</dd></div>
        <div><dt>Date and time</dt><dd>{date} at {slotLabel(slot)}</dd></div>
        <div><dt>Consultation reason</dt><dd>{reason.trim()}</dd></div>
      </dl> : <>
        <div className="booking-directories">
          <fieldset>
            <legend>Patient</legend>
            <DirectoryAutocomplete label="Search by patient name" value={patient?.name ?? patientQuery}
              lookup={patients} selectedId={patient?.id} describe={patientLabel}
              noResults="No registered patients match this search." onChange={changePatientQuery} onSelect={setPatient} />
            <label>Registered patient<select required disabled={patients.loading || !!patients.error} value={patient?.id ?? ''} onChange={(event) => setPatient(patients.records.find((item) => item.id === Number(event.target.value)))}>
              <option value="">Select patient</option>{patients.records.map((item) => <option key={item.id} value={item.id}>{patientLabel(item)}</option>)}
            </select></label>
            {patients.error ? <p className="form-error" role="alert">{patients.error}</p> : <p role="status">{patients.loading ? 'Loading patients…' : patients.records.length ? '' : 'No registered patients match this search.'}</p>}
          </fieldset>
          <fieldset>
            <legend>Doctor</legend>
            <DirectoryAutocomplete label="Search by doctor name" value={doctor?.name ?? doctorQuery}
              lookup={doctors} selectedId={doctorId} describe={doctorSuggestion}
              noResults="No registered doctors match this search." onChange={(value) => changeDoctorQuery(value, 'name')} onSelect={selectDoctor} />
            <DirectoryAutocomplete label="Filter by specialization" value={doctor?.specialization ?? specialization}
              lookup={doctors} selectedId={doctorId} describe={doctorSuggestion}
              noResults="No registered doctors match this specialization." onChange={(value) => changeDoctorQuery(value, 'specialization')} onSelect={selectDoctor} />
            <label>Registered doctor<select required disabled={doctors.loading || !!doctors.error} value={doctorId ?? ''} onChange={(event) => selectDoctor(doctors.records.find((item) => item.id === Number(event.target.value)))}>
              <option value="">Select doctor</option>{doctors.records.map((item) => <option key={item.id} value={item.id}>{doctorLabel(item)}</option>)}
            </select></label>
            {doctors.error ? <p className="form-error" role="alert">{doctors.error}</p> : <p role="status">{doctors.loading ? 'Loading doctors…' : doctors.records.length ? '' : 'No registered doctors match these filters.'}</p>}
          </fieldset>
        </div>
        <label>Appointment date<input required type="date" min={today} disabled={!doctor} value={date} onChange={(event) => selectDate(event.target.value)} /></label>
        {date && <label>Available time<select required disabled={slotsLoading || !slots.length} value={slot} onChange={(event) => setSlot(event.target.value)}>
          <option value="">Select time</option>{slots.map((item) => <option key={item.start} value={item.start}>{slotLabel(item.start)}</option>)}
        </select></label>}
        {(slotsLoading || slotNotice) && <p role="status">{slotsLoading ? 'Checking appointment times…' : slotNotice}</p>}
        {!!alternatives.length && <div className="role-actions" aria-label="Other dates">{alternatives.map((day) => <button className="outline-button" type="button" key={day} onClick={() => selectDate(day)}>{day}</button>)}</div>}
        <label>Consultation reason<input required maxLength={500} value={reason} onChange={(event) => setReason(event.target.value)} /></label>
      </>}
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="role-actions">
        {review && <button type="button" className="outline-button" disabled={saving} onClick={() => setReview(false)}>Edit details</button>}
        <button type="submit" className="dark-button" disabled={saving || slotsLoading || !patient || !doctor || !slot || !reason.trim()}>{saving ? 'Booking…' : review ? 'Confirm booking' : 'Review appointment'}</button>
      </div>
    </form>}
  </dialog>
}
