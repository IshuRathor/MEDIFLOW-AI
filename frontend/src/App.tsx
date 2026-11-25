import { useCallback, useEffect, useState, type CSSProperties, type FormEvent, type ReactNode } from 'react'
import './App.css'
import MediflowLogo from './MediflowLogo'
import {
  getAppointments,
  getRoleDashboard,
  createDoctor,
  createPatient,
  cancelAppointment,
  acceptAppointmentRequest,
  declineAppointmentRequest,
  createAppointment,
  chatWithMediflow,
  selectCancellationAppointment,
  decideCancellation,
  decideAIApproval,
  deleteAIConversation,
  deleteDoctor,
  deletePatient,
  getCurrentUser,
  getLatestAIConversation,
  getDoctors,
  getPatients,
  getUsers,
  createUser,
  getPendingUsers,
  approveUser,
  rejectUser,
  getMyAvailability,
  createAvailability,
  deleteAvailability,
  updateAvailability,
  getAvailableSlots,
  getDoctorAvailability,
  login,
  register,
  runTriage,
  type DoctorRecord,
  type ChatResponse,
  type DoctorCancellationRequest,
  type PatientCancellationUpdate,
  type ConversationMessage,
  type RoleDashboardData,
  type AvailabilityRecord,
  type AppointmentSlot,
  type PatientRecord,
  type PublicRegistrationInput,
  type TriageResponse,
  type TriageDoctor,
  type UserRecord,
} from './api'
import DoctorSelectionCards, { patientDoctorOptions, visibleChatTrace, type PatientDoctorOption } from './DoctorSelectionCards.js'
import TriageResults from './TriageResults.js'
import BillingWorkspace, { BillingOverviewCards } from './BillingWorkspace'
import StaffAppointmentBooking from './StaffAppointmentBooking'
import { restoreConversationState, startNewConversationState } from './aiConversationState.js'
import ChatCancellation from './ChatCancellation.js'
import DoctorIntelligence, { doctorPrompts, type DoctorIntelligenceResult } from './DoctorIntelligence.js'
import FinanceReport, { financePrompts, formatINR } from './FinanceReport.js'
import AdminReport, { adminPrompts } from './AdminReport.js'
import { asDateKey, CALENDAR_DAYS, ChatAppointmentPicker, loadAppointmentDateSlots, loadDoctorAppointmentDates } from './chatBookingAvailability.js'

type Appointment = { id: number; time: string; patient: string; detail: string; doctor: string; status: string; accent: string }

const roleOptions: Array<{ value: UserRecord['role']; label: string; description: string }> = [
  { value: 'admin', label: 'Administrator', description: 'Full hospital workspace access' },
  { value: 'patient', label: 'Patient', description: 'Appointments, care and bills' },
  { value: 'clinician', label: 'Doctor', description: 'Care team and patient workflow' },
  { value: 'staff', label: 'Finance staff', description: 'Billing and hospital operations' },
]

function navItemsForRole(role: UserRecord['role']) {
  if (role === 'patient') return ['Overview', 'Billing']
  if (role === 'clinician') return ['Overview', 'Appointments', 'Patients', 'Doctors']
  if (role === 'staff') return ['Overview', 'Appointments', 'Patients', 'Doctors', 'Billing']
  return ['Overview', 'Appointments', 'Patients', 'Doctors', 'Billing', 'Accounts']
}

function AuthScreen({ onAuthenticated }: { onAuthenticated: (token: string, user: UserRecord) => void }) {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [registrationRole, setRegistrationRole] = useState<PublicRegistrationInput['role']>('patient')
  const [specialization, setSpecialization] = useState('')
  const [department, setDepartment] = useState('')
  const [experienceYears, setExperienceYears] = useState('0')
  const [showPassword, setShowPassword] = useState(false)
  const [role, setRole] = useState<UserRecord['role']>('admin')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setMessage('')
    setLoading(true)
    try {
      if (mode === 'register') {
        if (password !== confirmPassword) {
          setError('Passwords do not match.')
          return
        }
        await register({
          full_name: fullName.trim(),
          email: email.trim(),
          phone: phone.trim(),
          password,
          confirm_password: confirmPassword,
          role: registrationRole,
          ...(registrationRole === 'clinician' ? {
            specialization: specialization.trim(),
            department: department.trim() || undefined,
            experience_years: Number(experienceYears),
          } : {}),
        })
        setMode('login')
        setMessage(registrationRole === 'patient'
          ? 'Account created. Sign in to open your patient workspace.'
          : 'Registration submitted. An administrator must approve it before sign-in.')
      } else {
        const response = await login(email.trim(), password, role)
        onAuthenticated(response.access_token, response.user)
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Authentication failed.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-card">
        <div className="brand-lockup auth-brand"><MediflowLogo /></div>
        <p className="eyebrow">{mode === 'login' ? 'Secure workspace' : 'Patient account'}</p>
        <h1>{mode === 'login' ? 'Welcome back.' : 'Create your account.'}</h1>
        <p className="auth-copy">{mode === 'login' ? 'Choose your workspace, then sign in with your account.' : 'Create an account and submit it for the appropriate approval.'}</p>
        <form className="auth-form" onSubmit={submit}>
          {mode === 'register' && <>
            <fieldset className="role-picker registration-role-picker">
              <legend>Create account as</legend>
              <div className="role-options">
                {([
                  ['patient', 'Patient', 'Appointments, care and bills'],
                  ['clinician', 'Doctor', 'Care team and patient workflow'],
                  ['staff', 'Finance staff', 'Billing and hospital operations'],
                ] as const).map(([value, label, description]) => (
                  <button type="button" className={registrationRole === value ? 'role-option selected' : 'role-option'} key={value} onClick={() => setRegistrationRole(value)}>
                    <strong>{label}</strong><span>{description}</span>
                  </button>
                ))}
              </div>
            </fieldset>
            <label>Full name<input required minLength={2} maxLength={120} value={fullName} onChange={(event) => setFullName(event.target.value)} autoComplete="name" /></label>
            <label>Phone number<input required type="tel" minLength={7} maxLength={30} value={phone} onChange={(event) => setPhone(event.target.value)} autoComplete="tel" /></label>
            {registrationRole === 'clinician' && <>
              <label>Specialization<input required minLength={2} maxLength={120} value={specialization} onChange={(event) => setSpecialization(event.target.value)} /></label>
              <label>Department<input maxLength={120} value={department} onChange={(event) => setDepartment(event.target.value)} /></label>
              <label>Experience years<input required type="number" min="0" max="80" value={experienceYears} onChange={(event) => setExperienceYears(event.target.value)} /></label>
            </>}
          </>}
          {mode === 'login' && <fieldset className="role-picker"><legend>Who are you?</legend><div className="role-options">{roleOptions.map((option) => <button className={role === option.value ? 'role-option selected' : 'role-option'} key={option.value} type="button" onClick={() => setRole(option.value)}><strong>{option.label}</strong><span>{option.description}</span></button>)}</div></fieldset>}
          <label>Email<input required type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" /></label>
          <label>Password<div className="password-field"><input required minLength={8} maxLength={128} type={showPassword ? 'text' : 'password'} value={password} onChange={(event) => setPassword(event.target.value)} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} /><button type="button" onClick={() => setShowPassword((current) => !current)} aria-label={showPassword ? 'Hide password' : 'Show password'}>{showPassword ? 'Hide' : 'Show'}</button></div></label>
          {mode === 'register' && <label>Confirm password<div className="password-field"><input required minLength={8} maxLength={128} type={showPassword ? 'text' : 'password'} value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} autoComplete="new-password" /><button type="button" onClick={() => setShowPassword((current) => !current)} aria-label={showPassword ? 'Hide passwords' : 'Show passwords'}>{showPassword ? 'Hide' : 'Show'}</button></div></label>}
          {error && <p className="form-error" role="alert">{error}</p>}
          {message && <p className="auth-message" role="status">{message}</p>}
          <button className="dark-button auth-submit" type="submit" disabled={loading}>{loading ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'} <span>→</span></button>
        </form>
        <button className="auth-switch" type="button" onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError(''); setMessage(''); setConfirmPassword(''); setShowPassword(false) }}>
          {mode === 'login' ? 'New here? Create account.' : 'Already have an account? Sign in.'}
        </button>
      </section>
    </main>
  )
}

type ScheduleEntry = {
  id: string | number
  name: string
  detail?: string
  time?: string
  dateTime?: string
  doctor?: string
  status: string
  action?: ReactNode
}

function StatusBadge({ status }: { status: string }) {
  return <span className="status-pill dashboard-status" data-status={status.toLowerCase()}>{status}</span>
}

function scheduleTiming(value: unknown, mode: 'time' | 'date' | 'both' = 'both') {
  if (typeof value !== 'string') return {}
  const date = new Date(value)
  return {
    dateTime: value,
    time: mode === 'time'
      ? date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      : mode === 'date' ? date.toLocaleDateString() : date.toLocaleString(),
  }
}

function ScheduleList({ entries, title, nameLabel, empty }: {
  entries: ScheduleEntry[]
  title: string
  nameLabel: string
  empty: string
}) {
  if (!entries.length) return <p className="dashboard-state">{empty}</p>
  const hasTime = entries.some((entry) => entry.time)
  const hasDoctor = entries.some((entry) => entry.doctor)
  const hasActions = entries.some((entry) => entry.action)
  const columns = ['schedule-list', hasTime && 'schedule-with-time', hasDoctor && 'schedule-with-doctor', hasActions && 'schedule-with-actions'].filter(Boolean).join(' ')

  return <div className={columns}>
    <div className="schedule-columns schedule-labels" aria-hidden="true">
      {hasTime && <span>When</span>}
      <span>{nameLabel}</span>
      {hasDoctor && <span>Doctor</span>}
      <span>Status</span>
      {hasActions && <span>Action</span>}
    </div>
    <ul role="list" aria-label={title}>
      {entries.map((entry) => <li className="schedule-columns schedule-entry" key={entry.id}>
        {hasTime && <time className="schedule-time" dateTime={entry.dateTime}>{entry.time}</time>}
        <div className="schedule-person"><strong>{entry.name}</strong>{entry.detail && <span>{entry.detail}</span>}</div>
        {hasDoctor && <span className="schedule-doctor">{entry.doctor}</span>}
        <div className="schedule-status"><StatusBadge status={entry.status} /></div>
        {hasActions && <div className="schedule-action">{entry.action}</div>}
      </li>)}
    </ul>
  </div>
}

function ResourcePage({
  activeNav,
  role,
  patients,
  doctors,
  appointments,
  users,
  pendingUsers,
  loading,
  error,
  onAdd,
  onDeletePatient,
  onDeleteDoctor,
  onCancelAppointment,
  onAddAppointment,
  onAddAccount,
  onApproveUser,
  onRejectUser,
}: {
  activeNav: string
  role: UserRecord['role']
  patients: PatientRecord[]
  doctors: DoctorRecord[]
  appointments: Appointment[]
  users: UserRecord[]
  pendingUsers: UserRecord[]
  loading: boolean
  error: string
  onAdd: () => void
  onDeletePatient: (id: number) => void
  onDeleteDoctor: (id: number) => void
  onCancelAppointment: (id: number) => void
  onAddAppointment: () => void
  onAddAccount: () => void
  onApproveUser: (id: number) => void
  onRejectUser: (id: number) => void
}) {
  if (loading) return <p className="dashboard-state">Loading {activeNav.toLowerCase()}…</p>
  if (error) return <p className="form-error" role="alert">{error}</p>

  if (activeNav === 'Patients') {
    return <section className="panel resource-panel">
      <div className="panel-heading"><div><p className="eyebrow">Care records</p><h2>Patients</h2></div><button className="outline-button" type="button" onClick={onAdd}>+ Add patient</button></div>
      {patients.length === 0 ? <p className="dashboard-state">No patients have been added yet.</p> : <div className="resource-list">{patients.map((patient) => <div className="resource-row" key={patient.id}><div className="avatar avatar-light">{patient.name.slice(0, 2).toUpperCase()}</div><div><strong>{patient.name}</strong><span>{patient.email} · {patient.phone ?? 'No phone number'}</span></div><span>{patient.age ? `${patient.age} years` : 'Age unavailable'}</span><span>{patient.gender ?? 'Gender unavailable'}</span>{(role === 'admin' || role === 'staff') && <button className="row-action" type="button" onClick={() => onDeletePatient(patient.id)}>Delete</button>}</div>)}</div>}
    </section>
  }

  if (activeNav === 'Doctors') {
    return <section className="panel resource-panel">
      <div className="panel-heading"><div><p className="eyebrow">Care team</p><h2>Doctors</h2></div>{(role === 'admin' || role === 'staff') && <button className="outline-button" type="button" onClick={onAdd}>+ Add doctor</button>}</div>
      {doctors.length === 0 ? <p className="dashboard-state">No doctors have been added yet.</p> : <div className="resource-list">{doctors.map((doctor) => <div className="resource-row" key={doctor.id}><div className="avatar avatar-light">{doctor.name.slice(0, 2).toUpperCase()}</div><div><strong>Dr. {doctor.name.replace(/^Dr\.\s*/i, '')}</strong><span>{doctor.specialization} · {doctor.department ?? 'Department unavailable'}</span></div><span>{doctor.experience_years} years experience</span><span>{doctor.email}</span>{role === 'admin' && <button className="row-action" type="button" onClick={() => onDeleteDoctor(doctor.id)}>Delete</button>}</div>)}</div>}
    </section>
  }

  if (activeNav === 'Appointments') {
    return <section className="schedule-page">
      <div className="panel-heading schedule-page-heading"><div><p className="eyebrow">Live schedule</p><h2>Appointments</h2></div>{(role === 'admin' || role === 'staff') && <button className="outline-button" type="button" onClick={onAddAppointment}>+ Add appointment</button>}</div>
      <ScheduleList title="Appointments" nameLabel="Patient and appointment" empty="No appointments have been scheduled yet."
        entries={appointments.map((appointment) => ({
          id: appointment.id,
          time: appointment.time,
          name: appointment.patient,
          detail: appointment.detail,
          doctor: appointment.doctor,
          status: appointment.status,
          action: appointment.status !== 'Cancelled' && <button className="row-action" type="button" onClick={() => onCancelAppointment(appointment.id)}>Cancel</button>,
        }))} />
    </section>
  }

  if (activeNav === 'Accounts') {
    return <section className="panel resource-panel">
      <div className="panel-heading"><div><p className="eyebrow">Workspace access</p><h2>Accounts</h2></div><button className="outline-button" type="button" onClick={onAddAccount}>+ Create account</button></div>
      {pendingUsers.length > 0 && <div><p className="eyebrow">Pending approval</p><div className="resource-list">{pendingUsers.map((user) => <div className="resource-row" key={user.id}><div className="avatar avatar-light">{user.full_name.slice(0, 2).toUpperCase()}</div><div><strong>{user.full_name}</strong><span>{user.email}</span></div><span>{user.role}</span><div className="approval-actions"><button className="dark-button" type="button" onClick={() => onApproveUser(user.id)}>Approve</button><button className="outline-button" type="button" onClick={() => onRejectUser(user.id)}>Reject</button></div></div>)}</div></div>}
      {users.length === 0 ? <p className="dashboard-state">No accounts have been added yet.</p> : <div className="resource-list">{users.map((user) => <div className="resource-row" key={user.id}><div className="avatar avatar-light">{user.full_name.slice(0, 2).toUpperCase()}</div><div><strong>{user.full_name}</strong><span>{user.email}</span></div><span>{user.role}</span><span>{user.is_active ? 'Active' : 'Inactive'}</span></div>)}</div>}
    </section>
  }

  return null
}

function CreateResourceModal({
  resource,
  token,
  onClose,
  onCreated,
}: {
  resource: 'Patients' | 'Doctors'
  token: string
  onClose: () => void
  onCreated: (record: PatientRecord | DoctorRecord) => void
}) {
  const [values, setValues] = useState({ name: '', email: '', age: '', gender: '', phone: '', specialization: '', department: '', experience_years: '0' })
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSaving(true)
    setError('')
    try {
      const record = resource === 'Patients'
        ? await createPatient(token, { name: values.name.trim(), email: values.email.trim(), age: Number(values.age), gender: values.gender || undefined, phone: values.phone || undefined })
        : await createDoctor(token, { name: values.name.trim(), email: values.email.trim(), specialization: values.specialization.trim(), department: values.department || undefined, phone: values.phone || undefined, experience_years: Number(values.experience_years) })
      onCreated(record)
      onClose()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'The record could not be created.')
    } finally {
      setSaving(false)
    }
  }

  return <div className="modal-backdrop" role="presentation" onClick={onClose}><div className="triage-modal resource-modal" role="dialog" aria-modal="true" aria-labelledby="create-resource-title" onClick={(event) => event.stopPropagation()}>
    <button className="modal-close" type="button" onClick={onClose} aria-label="Close form">×</button>
    <p className="eyebrow">Care operations</p><h2 id="create-resource-title">{`Add ${resource === 'Patients' ? 'patient' : 'doctor'}`}</h2>
    <form className="resource-form" onSubmit={submit}>
      <label>Name<input required minLength={2} value={values.name} onChange={(event) => setValues({ ...values, name: event.target.value })} /></label><label>Email<input required type="email" value={values.email} onChange={(event) => setValues({ ...values, email: event.target.value })} /></label>{resource === 'Patients' ? <><label>Age<input required type="number" min="0" max="130" value={values.age} onChange={(event) => setValues({ ...values, age: event.target.value })} /></label><label>Gender<input value={values.gender} onChange={(event) => setValues({ ...values, gender: event.target.value })} /></label></> : <><label>Specialization<input required value={values.specialization} onChange={(event) => setValues({ ...values, specialization: event.target.value })} /></label><label>Department<input value={values.department} onChange={(event) => setValues({ ...values, department: event.target.value })} /></label><label>Experience years<input required type="number" min="0" value={values.experience_years} onChange={(event) => setValues({ ...values, experience_years: event.target.value })} /></label></>}<label>Phone<input value={values.phone} onChange={(event) => setValues({ ...values, phone: event.target.value })} /></label>
      {error && <p className="form-error" role="alert">{error}</p>}
      <button className="dark-button" type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save record'} <span>→</span></button>
    </form>
  </div></div>
}

function CreateAccountModal({
  token,
  patients,
  onClose,
  onCreated,
}: {
  token: string
  patients: PatientRecord[]
  onClose: () => void
  onCreated: (user: UserRecord) => void
}) {
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<'staff' | 'clinician' | 'patient'>('staff')
  const [patientId, setPatientId] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSaving(true)
    setError('')
    try {
      const user = await createUser(token, {
        full_name: fullName.trim(),
        email: email.trim(),
        password,
        role,
        ...(role === 'patient' ? { patient_id: Number(patientId) } : {}),
      })
      onCreated(user)
      onClose()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'The account could not be created.')
    } finally {
      setSaving(false)
    }
  }

  return <div className="modal-backdrop" role="presentation" onClick={onClose}><div className="triage-modal resource-modal" role="dialog" aria-modal="true" aria-labelledby="create-account-title" onClick={(event) => event.stopPropagation()}>
    <button className="modal-close" type="button" onClick={onClose} aria-label="Close account form">×</button>
    <p className="eyebrow">Workspace access</p><h2 id="create-account-title">Create account</h2>
    <form className="resource-form" onSubmit={submit}>
      <label>Full name<input required minLength={2} maxLength={120} value={fullName} onChange={(event) => setFullName(event.target.value)} /></label>
      <label>Email<input required type="email" value={email} onChange={(event) => setEmail(event.target.value)} /></label>
      <label>Password<input required type="password" minLength={8} maxLength={128} value={password} onChange={(event) => setPassword(event.target.value)} /></label>
      <label>Role<select value={role} onChange={(event) => setRole(event.target.value as 'staff' | 'clinician' | 'patient')}><option value="staff">Finance staff</option><option value="clinician">Doctor</option><option value="patient">Patient</option></select></label>
      {role === 'patient' && <label>Patient record<select required value={patientId} onChange={(event) => setPatientId(event.target.value)}><option value="">Select patient</option>{patients.map((patient) => <option value={patient.id} key={patient.id}>{patient.name}</option>)}</select></label>}
      {error && <p className="form-error" role="alert">{error}</p>}
      <button className="dark-button" type="submit" disabled={saving}>{saving ? 'Creating…' : 'Create account'} <span>→</span></button>
    </form>
  </div></div>
}

function DoctorAvailabilityManager({ token }: { token: string }) {
  const [items, setItems] = useState<AvailabilityRecord[]>([])
  const [day, setDay] = useState('Monday')
  const [specificDate, setSpecificDate] = useState('')
  const [startTime, setStartTime] = useState('09:00')
  const [endTime, setEndTime] = useState('17:00')
  const [isAvailable, setIsAvailable] = useState(true)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getMyAvailability(token).then(setItems).catch((requestError) => setError(requestError instanceof Error ? requestError.message : 'Availability could not be loaded'))
  }, [token])

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    try {
      const input = {
        day_of_week: day,
        start_time: startTime,
        end_time: endTime,
        specific_date: specificDate || undefined,
        is_available: isAvailable,
      }
      if (editingId) await updateAvailability(token, editingId, input)
      else await createAvailability(token, input)
      setItems(await getMyAvailability(token))
      setEditingId(null)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Availability could not be saved')
    }
  }

  async function removeItem(id: number) {
    setError('')
    try {
      await deleteAvailability(token, id)
      setItems((current) => current.filter((item) => item.id !== id))
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Availability could not be deleted')
    }
  }

  return <article className="panel capacity-panel"><div className="panel-heading"><div><p className="eyebrow">My schedule</p><h2>Manage availability</h2></div></div>
    <form className="resource-form" onSubmit={save}>
      <label>Day<select value={day} onChange={(event) => setDay(event.target.value)}>{['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'].map((value) => <option key={value}>{value}</option>)}</select></label>
      <label>Specific date (optional)<input type="date" value={specificDate} onChange={(event) => setSpecificDate(event.target.value)} /></label>
      <label>Start<input type="time" required value={startTime} onChange={(event) => setStartTime(event.target.value)} /></label>
      <label>End<input type="time" required value={endTime} onChange={(event) => setEndTime(event.target.value)} /></label>
      <label>Status<select value={isAvailable ? 'available' : 'blocked'} onChange={(event) => setIsAvailable(event.target.value === 'available')}><option value="available">Available</option><option value="blocked">Unavailable / blocked</option></select></label>
      {error && <p className="form-error" role="alert">{error}</p>}
      <button className="dark-button" type="submit">Save schedule <span>→</span></button>
    </form>
    <div className="resource-list">{items.map((item) => <div className="resource-row" key={item.id}><strong>{item.specific_date ?? item.day_of_week}</strong><span>{item.start_time}–{item.end_time}</span><span>{item.is_available ? 'Available' : 'Blocked'}</span><button className="row-action" type="button" onClick={() => { setEditingId(item.id); setDay(item.day_of_week); setSpecificDate(item.specific_date ?? ''); setStartTime(item.start_time.slice(0, 5)); setEndTime(item.end_time.slice(0, 5)); setIsAvailable(item.is_available) }}>Edit</button><button className="row-action" type="button" onClick={() => void removeItem(item.id)}>Delete</button></div>)}</div>
  </article>
}

function PatientBooking({
  token,
  doctors,
  onBooked,
  initialDoctorId,
}: {
  token: string
  doctors: Pick<DoctorRecord, 'id' | 'name' | 'specialization'>[]
  onBooked: () => void
  initialDoctorId?: number
}) {
  const [doctorId, setDoctorId] = useState(initialDoctorId?.toString() ?? '')
  const [targetDate, setTargetDate] = useState('')
  const [slots, setSlots] = useState<AppointmentSlot[]>([])
  const [selectedSlot, setSelectedSlot] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [booking, setBooking] = useState(false)
  const [loadingSlots, setLoadingSlots] = useState(false)
  const [reason, setReason] = useState('')

  async function loadSlots() {
    if (!doctorId || !targetDate || loadingSlots) return
    setLoadingSlots(true)
    setError('')
    setSelectedSlot('')
    setSlots([])
    try {
      const result = await getAvailableSlots(token, Number(doctorId), targetDate)
      setSlots(result.slots)
      if (result.blocked) setError('The doctor has blocked this date.')
      if (result.slots.length === 0 && result.alternatives.length > 0) setError(`No slots today. Next available dates: ${result.alternatives.join(', ')}`)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Slots could not be loaded')
    } finally {
      setLoadingSlots(false)
    }
  }

  async function book() {
    if (!selectedSlot) return
    setBooking(true)
    setError('')
    setMessage('')
    try {
      const appointment = await createAppointment(token, { patient_id: 0, doctor_id: Number(doctorId), appointment_date: selectedSlot, reason: reason.trim() || undefined })
      const doctor = doctors.find((item) => item.id === Number(doctorId))
      const date = new Date(appointment.appointment_date)
      setMessage(`Request #${appointment.id} is awaiting doctor approval. Dr. ${doctor?.name ?? 'your doctor'} — ${date.toLocaleDateString()} at ${date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`)
      await loadSlots()
      setSelectedSlot('')
      onBooked()
    } catch (requestError) {
      const raw = requestError instanceof Error ? requestError.message : 'Appointment could not be booked'
      if (raw === 'Doctor is not available at this time.') setError(raw)
      else if (raw === 'This appointment slot is already booked.' || raw.toLowerCase().includes('no longer available')) setError('This appointment slot is already booked.')
      else setError(raw)
      await loadSlots()
    } finally {
      setBooking(false)
    }
  }

  return <article className="panel capacity-panel"><div className="panel-heading"><div><p className="eyebrow">Appointments</p><h2>Book appointment</h2></div></div>
    <div className="resource-form">
      <label>Doctor<select required disabled={loadingSlots || booking} value={doctorId} onChange={(event) => { setDoctorId(event.target.value); setSlots([]); setSelectedSlot('') }}><option value="">Select doctor</option>{doctors.map((doctor) => <option value={doctor.id} key={doctor.id}>Dr. {doctor.name} — {doctor.specialization}</option>)}</select></label>
      <label>Date<input required type="date" disabled={loadingSlots || booking} value={targetDate} onChange={(event) => { setTargetDate(event.target.value); setSlots([]); setSelectedSlot('') }} /></label>
      <label>Reason for appointment<input value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Optional" /></label>
      <button className="outline-button" type="button" disabled={!doctorId || !targetDate || loadingSlots || booking} onClick={() => { setMessage(''); void loadSlots() }}>{loadingSlots ? 'Checking slots…' : 'View slots'}</button>
      {slots.length > 0 && <div className="slot-grid">{slots.map((slot) => <button type="button" key={slot.start} disabled={slot.status !== 'available'} className={selectedSlot === slot.start ? 'slot-option selected' : 'slot-option'} onClick={() => setSelectedSlot(slot.start)}><strong>{new Date(slot.start).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</strong><span>{slot.status}</span></button>)}</div>}
      {error && <p className="form-error" role="alert">{error}</p>}
      {message && <p className="auth-message" role="status">{message}</p>}
      <button className="dark-button" type="button" disabled={!selectedSlot || booking} onClick={() => void book()}>{booking ? 'Sending request…' : 'Request appointment'} <span>→</span></button>
    </div>
  </article>
}

function PatientTriageModal({ token, onClose, onBooked }: { token: string; onClose: () => void; onBooked: () => void }) {
  const [symptoms, setSymptoms] = useState('')
  const [triageResult, setTriageResult] = useState<TriageResponse | null>(null)
  const [triageBookingDoctor, setTriageBookingDoctor] = useState<TriageDoctor | null>(null)
  const [triageError, setTriageError] = useState('')
  const [triageLoading, setTriageLoading] = useState(false)

  async function submitTriage() {
    if (symptoms.trim().length < 3) {
      setTriageError('Describe at least three characters of symptoms.')
      return
    }

    setTriageLoading(true)
    setTriageError('')
    try {
      setTriageResult(await runTriage(symptoms.trim(), token))
    } catch (error) {
      setTriageError(error instanceof Error ? error.message : 'The triage request failed.')
    } finally {
      setTriageLoading(false)
    }
  }

  return <div className="modal-backdrop" role="presentation" onClick={onClose}>
    <div className="triage-modal patient-triage-modal" role="dialog" aria-modal="true" aria-labelledby="triage-title" onClick={(event) => event.stopPropagation()}>
      <button className="modal-close" type="button" onClick={onClose} aria-label="Close triage">×</button>
      <p className="eyebrow">AI assisted triage</p>
      <h2 id="triage-title">{triageBookingDoctor ? 'Request an appointment' : triageResult ? 'Triage assessment' : 'What symptoms are you experiencing?'}</h2>
      {triageBookingDoctor ? <>
        <button className="outline-button" type="button" onClick={() => setTriageBookingDoctor(null)}>Back to assessment</button>
        <PatientBooking token={token} doctors={[triageBookingDoctor]} initialDoctorId={triageBookingDoctor.id} onBooked={onBooked} />
      </> : triageResult ? <TriageResults result={triageResult} onBook={setTriageBookingDoctor} onReset={() => setTriageResult(null)} /> : <>
        <textarea aria-label="Symptoms" value={symptoms} maxLength={500} onChange={(event) => setSymptoms(event.target.value)} placeholder="Describe symptoms in plain language..." />
        {triageError && <p className="form-error" role="alert">{triageError}</p>}
        <div className="modal-footer"><span>{symptoms.length}/500</span><button className="dark-button" type="button" onClick={submitTriage} disabled={triageLoading}>{triageLoading ? 'Assessing…' : 'Run assessment'} <span>→</span></button></div>
      </>}
    </div>
  </div>
}

function MetricCard({ label, value, tone = 'metric-light' }: { label: string; value: string | number; tone?: string }) {
  const money = typeof value === 'string' && value.includes('₹')
  return <article className={`metric-card ${tone}`}>
    <div className="metric-label">{label}</div>
    <strong className={money ? 'metric-money' : undefined} style={money ? { '--metric-length': String(value).length } as CSSProperties : undefined}>
      {value}
    </strong>
  </article>
}

function AppointmentRequestsPanel({ requests, token, onUpdated }: { requests: Array<Record<string, unknown>>; token: string; onUpdated: () => void }) {
  const [busyId, setBusyId] = useState<number | null>(null)
  const [error, setError] = useState('')
  async function decide(id: number, action: 'accept' | 'decline') {
    const reason = action === 'decline' ? window.prompt('Optional reason for declining this request:') : undefined
    if (action === 'decline' && reason === null) return
    setBusyId(id)
    setError('')
    try {
      if (action === 'accept') await acceptAppointmentRequest(id, token)
      else await declineAppointmentRequest(id, token, reason?.trim() || undefined)
      onUpdated()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'The request could not be processed.')
    } finally {
      setBusyId(null)
    }
  }
  return <article className="panel queue-panel"><div className="panel-heading"><div><p className="eyebrow">Doctor review</p><h2>Appointment Requests</h2></div></div>{requests.length === 0 ? <p className="dashboard-state">No appointment requests are waiting for review.</p> : <div className="resource-list review-list">{requests.map((item) => <div className="resource-row" key={String(item.id)}><strong>Request #{String(item.id)} · {String(item.patient_name)}</strong><span>{new Date(String(item.appointment_date)).toLocaleString()} · {String(item.department ?? 'Department not assigned')}</span><span>{String(item.reason ?? 'General consultation')}</span><span>Requested {item.created_at ? new Date(String(item.created_at)).toLocaleString() : 'time unavailable'} · {String(item.status)}</span><div className="approval-actions"><button className="dark-button" type="button" disabled={busyId !== null} onClick={() => void decide(Number(item.id), 'accept')}>{busyId === Number(item.id) ? 'Saving…' : 'Accept'}</button><button className="outline-button" type="button" disabled={busyId !== null} onClick={() => void decide(Number(item.id), 'decline')}>Decline</button></div></div>)}</div>}{error && <p className="form-error" role="alert">{error}</p>}</article>
}

function CancellationRequestsPanel({ requests, token, onUpdated }: {
  requests: DoctorCancellationRequest[]
  token: string
  onUpdated: () => void
}) {
  const [rejecting, setRejecting] = useState<string | null>(null)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function decide(request: DoctorCancellationRequest, decision: 'approve' | 'reject') {
    setBusy(true)
    setError('')
    try {
      await decideCancellation(token, request, decision, decision === 'reject' ? reason : undefined)
      setRejecting(null)
      setReason('')
      onUpdated()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'The cancellation request could not be processed.')
    } finally {
      setBusy(false)
    }
  }

  return <article className="panel queue-panel">
    <div className="panel-heading"><h2>Cancellation requests</h2></div>
    {requests.length === 0 ? <p className="dashboard-state">No cancellation requests are waiting for review.</p> :
      <div className="resource-list review-list">{requests.map((request) => <div className="resource-row" key={request.request_id}>
        <strong>{request.patient_name}</strong>
        <span>{new Date(request.appointment_date).toLocaleString()}</span>
        <span>Requested {new Date(request.requested_at).toLocaleString()}</span>
        <span>{request.status}</span>
        {rejecting === request.request_id ?
          <form className="resource-form" onSubmit={(event) => { event.preventDefault(); void decide(request, 'reject') }}>
            <label>Reason (optional)<input value={reason} onChange={(event) => setReason(event.target.value)} maxLength={500} disabled={busy} /></label>
            <div className="approval-actions">
              <button className="dark-button" type="submit" disabled={busy}>Confirm rejection</button>
              <button className="outline-button" type="button" disabled={busy} onClick={() => setRejecting(null)}>Back</button>
            </div>
          </form> :
          <div className="approval-actions">
            <button className="dark-button" type="button" disabled={busy || !request.can_approve} onClick={() => void decide(request, 'approve')}>Approve cancellation</button>
            <button className="outline-button" type="button" disabled={busy} onClick={() => { setReason(''); setRejecting(request.request_id) }}>Reject cancellation</button>
          </div>}
      </div>)}</div>}
    {error && <p className="form-error" role="alert">{error}</p>}
  </article>
}

function PatientCancellationHistory({ updates }: { updates: PatientCancellationUpdate[] }) {
  return <article className={updates.length ? 'panel queue-panel' : undefined} aria-live="polite">
    {updates.length > 0 && <>
      <div className="panel-heading"><h2>Appointment cancellation updates</h2></div>
      <div className="resource-list">{updates.map((item, index) => <div className="resource-row" key={`${item.appointment_date}-${item.doctor_name}-${index}`}>
        <strong>Dr. {item.doctor_name.replace(/^Dr\.\s*/i, '')}</strong>
        <span>{new Date(item.appointment_date).toLocaleString()}</span>
        <span>{item.cancellation_status === 'Pending Doctor Approval'
          ? 'Cancellation Requested · Pending Doctor Approval'
          : `Cancellation ${item.cancellation_status.toLowerCase()} · ${item.status}`}</span>
        {item.cancellation_reason && <span>{item.cancellation_reason}</span>}
      </div>)}</div>
    </>}
  </article>
}

function RoleDashboard({
  data,
  loading,
  error,
  onNavigate,
  token,
  doctors,
  onDashboardRefresh,
  onAskAI,
  onInsightPrompt,
}: {
  data: RoleDashboardData | null
  loading: boolean
  error: string
  onNavigate: (nav: string) => void
  token: string
  doctors: DoctorRecord[]
  onDashboardRefresh: () => void
  onAskAI: () => void
  onInsightPrompt: (prompt: string) => void
}) {
  if (loading) return <p className="dashboard-state">Loading role dashboard…</p>
  if (error) return <p className="form-error" role="alert">{error}</p>
  if (!data) return <p className="dashboard-state">Dashboard data is unavailable.</p>

  if (data.role === 'clinician') {
    const stats = data.stats as Record<string, number>
    const schedule = (data.today_schedule ?? []) as Array<Record<string, unknown>>
    const patients = (data.assigned_patients ?? []) as Array<Record<string, unknown>>
    const pendingRequests = (data.pending_requests ?? []) as Array<Record<string, unknown>>
    const pastAppointments = (data.past_appointments ?? []) as Array<Record<string, unknown>>
    return <>
      <article className="panel capacity-panel">
        <div className="panel-heading"><h2>Doctor AI</h2></div>
        <div className="ai-prompts" aria-label="Doctor AI suggestions">
          {doctorPrompts.map((prompt) => <button key={prompt} type="button" onClick={() => onInsightPrompt(prompt)}>{prompt}</button>)}
        </div>
      </article>
      <section className="metrics-grid" aria-label="Doctor metrics">
        <MetricCard label="Today's appointments" value={stats.todays_appointments ?? 0} tone="metric-dark" />
        <MetricCard label="Upcoming appointments" value={stats.upcoming_appointments ?? 0} tone="metric-coral" />
        <MetricCard label="Assigned patients" value={stats.assigned_patients ?? 0} tone="metric-lime" />
        <MetricCard label="Completed consultations" value={stats.completed_consultations ?? 0} />
      </section>
      <section className="metrics-grid role-secondary-metrics" aria-label="Doctor status metrics">
        <MetricCard label="Appointment requests" value={stats.pending_requests ?? 0} tone="metric-coral" />
        <MetricCard label="Pending consultations" value={stats.pending_consultations ?? 0} tone="metric-coral" />
        <MetricCard label="Cancelled appointments" value={stats.cancelled_appointments ?? 0} tone="metric-light" />
      </section>
      <section className="dashboard-grid">
        <article className="schedule-section">
          <div className="panel-heading"><div><p className="eyebrow">My schedule</p><h2>Today's appointments</h2></div></div>
          <ScheduleList title="Today's appointments" nameLabel="Patient and appointment" empty="No appointments scheduled for today."
            entries={schedule.map((item) => ({
              id: String(item.id), ...scheduleTiming(item.appointment_date, 'time'), name: String(item.patient_name),
              detail: String(item.reason ?? 'General consultation'), status: String(item.status),
            }))} />
        </article>
        <article className="panel capacity-panel"><div className="panel-heading"><div><p className="eyebrow">Quick actions</p><h2>Clinical tools</h2></div></div><div className="role-actions"><button className="outline-button" type="button" onClick={() => onNavigate('Patients')}>View patients</button><button className="outline-button" type="button" onClick={() => onNavigate('Appointments')}>View appointments</button></div></article>
      </section>
      <section className="bottom-grid" aria-label="Appointment review">
        <AppointmentRequestsPanel requests={pendingRequests} token={token} onUpdated={onDashboardRefresh} />
        <CancellationRequestsPanel requests={(data.cancellation_requests ?? []) as DoctorCancellationRequest[]} token={token} onUpdated={onDashboardRefresh} />
      </section>
      <article className="schedule-section">
        <div className="panel-heading"><div><p className="eyebrow">Past appointments</p><h2>Recent patient visits</h2></div></div>
        <ScheduleList title="Recent patient visits" nameLabel="Patient and appointment" empty="No past appointments yet."
          entries={pastAppointments.map((item) => ({
            id: String(item.id), ...scheduleTiming(item.appointment_date),
            name: `#${String(item.id)} · ${String(item.patient_name)}`,
            detail: String(item.reason ?? 'General consultation'), status: String(item.status),
          }))} />
      </article>
      <section className="bottom-grid"><article className="panel capacity-panel"><div className="panel-heading"><div><p className="eyebrow">Assigned care</p><h2>My patients</h2></div></div>{patients.length === 0 ? <p className="dashboard-state">No assigned patients yet.</p> : <div className="resource-list">{patients.map((patient) => <div className="resource-row" key={String(patient.id)}><div className="avatar avatar-light">{String(patient.name).slice(0, 2).toUpperCase()}</div><div><strong>{String(patient.name)}</strong><span>{String(patient.email ?? 'Email unavailable')}</span></div></div>)}</div>}</article><DoctorAvailabilityManager token={token} /></section>
    </>
  }

  if (data.role === 'patient') {
    const stats = data.stats as Record<string, number>
    const upcoming = (data.upcoming ?? []) as Array<Record<string, unknown>>
    const pendingRequests = (data.pending_requests ?? []) as Array<Record<string, unknown>>
    const declined = (data.declined ?? []) as Array<Record<string, unknown>>
    const cancelled = (data.cancelled ?? []) as Array<Record<string, unknown>>
    const previous = (data.previous ?? []) as Array<Record<string, unknown>>
    const cancellationUpdates = (data.cancellation_history ?? []) as PatientCancellationUpdate[]
    const doctor = data.assigned_doctor as Record<string, unknown> | null
    return <>
      <section className="metrics-grid" aria-label="Patient metrics"><MetricCard label="My upcoming appointments" value={stats.upcoming_appointments ?? 0} tone="metric-dark" /><MetricCard label="Pending requests" value={stats.pending_requests ?? 0} tone="metric-coral" /><MetricCard label="My bills" value={stats.bills ?? 0} tone="metric-lime" /><MetricCard label="Pending payments" value={stats.pending_payments ?? 0} /></section>
      <PatientCancellationHistory updates={cancellationUpdates} />
      <section className="bottom-grid"><article className="panel capacity-panel"><div className="panel-heading"><div><p className="eyebrow">AI appointment agent</p><h2>Find a doctor and request a time</h2></div></div><p className="capacity-copy">Ask in your own words. MediFlow checks the doctor directory and recorded availability, then asks you to review and confirm the request.</p><button className="dark-button" type="button" onClick={onAskAI}>Ask MediFlow AI <span>→</span></button></article><PatientBooking token={token} doctors={doctors} onBooked={onDashboardRefresh} /></section>
      <section className="dashboard-grid"><article className="schedule-section">
        <div className="panel-heading"><div><p className="eyebrow">Care journey</p><h2>Upcoming appointments</h2></div></div>
        <ScheduleList title="Upcoming appointments" nameLabel="Doctor and appointment" empty="No upcoming appointments."
          entries={upcoming.map((item) => ({
            id: String(item.id), ...scheduleTiming(item.appointment_date), name: `Dr. ${String(item.doctor_name)}`,
            detail: String(item.reason ?? 'General consultation'), status: String(item.status),
          }))} />
      </article><article className="panel capacity-panel"><div className="panel-heading"><div><p className="eyebrow">My care</p><h2>Assigned doctor</h2></div></div>{doctor ? <div className="capacity-copy"><strong>Dr. {String(doctor.name)}</strong><span>{String(doctor.specialization)}</span></div> : <p className="dashboard-state">No assigned doctor yet.</p>}<div className="role-actions"><button className="outline-button" type="button" onClick={() => onNavigate('Appointments')}>Book appointment</button><button className="outline-button" type="button" onClick={() => onNavigate('Billing')}>View bills</button></div></article></section>
      <section className="schedule-section">
        <div className="panel-heading"><div><p className="eyebrow">Request tracking</p><h2>Pending doctor approval</h2></div><button className="outline-button" type="button" onClick={onDashboardRefresh}>Refresh status</button></div>
        <ScheduleList title="Pending doctor approval" nameLabel="Request and doctor" empty="No pending requests."
          entries={pendingRequests.map((item) => ({
            id: String(item.id), ...scheduleTiming(item.appointment_date),
            name: `Request #${String(item.id)} · Dr. ${String(item.doctor_name)}`,
            detail: String(item.reason ?? 'General consultation'), status: 'Pending Doctor Approval',
          }))} />
      </section>
      {(declined.length > 0 || cancelled.length > 0) && <section className="bottom-grid"><article className="panel queue-panel"><div className="panel-heading"><div><p className="eyebrow">Request updates</p><h2>Declined and cancelled</h2></div></div><div className="resource-list">{[...declined, ...cancelled].map((item) => <div className="resource-row" key={String(item.id)}><strong>Request #{String(item.id)} · {String(item.status)}</strong><span>Dr. {String(item.doctor_name)} · {new Date(String(item.appointment_date)).toLocaleString()}</span><span>{String(item.reason ?? 'General consultation')}</span>{Boolean(item.decline_reason) && <span>Reason: {String(item.decline_reason)}</span>}</div>)}</div></article></section>}
      <section className="bottom-grid"><article className="schedule-section">
        <div className="panel-heading"><div><p className="eyebrow">Personal history</p><h2>Previous appointments</h2></div></div>
        <ScheduleList title="Previous appointments" nameLabel="Appointment" empty="No previous appointments."
          entries={previous.map((item) => ({
            id: String(item.id), ...scheduleTiming(item.appointment_date, 'date'),
            name: String(item.reason ?? 'General consultation'), status: String(item.status),
          }))} />
      </article><BillingWorkspace token={token} role="patient" overview={data.billing_overview} recentOnly onRefresh={onDashboardRefresh} /></section>
    </>
  }

  if (data.role === 'staff') {
    const stats = data.stats as Record<string, number>
    const transactions = (data.recent_transactions ?? []) as Array<Record<string, unknown>>
    return <>
      <section className="metrics-grid" aria-label="Finance metrics"><MetricCard label="Total collections" value={formatINR(Number(stats.total_revenue ?? 0))} tone="metric-dark" /><MetricCard label="Today's collections" value={formatINR(Number(stats.todays_collections ?? 0))} tone="metric-lime" /><MetricCard label="Monthly collections" value={formatINR(Number(stats.monthly_revenue ?? 0))} tone="metric-coral" /><MetricCard label="Outstanding bills" value={formatINR(Number(stats.outstanding_bills ?? 0))} /></section>
      <section className="metrics-grid role-secondary-metrics"><MetricCard label="Pending payments" value={stats.pending_payments ?? 0} tone="metric-coral" /><MetricCard label="Bills generated" value={stats.total_bills_generated ?? 0} /><MetricCard label="Completed payments" value={stats.completed_payments ?? 0} tone="metric-lime" /></section>
      <section className="dashboard-grid"><article className="panel appointments-panel"><div className="panel-heading"><div><p className="eyebrow">Recent activity</p><h2>Transactions</h2></div></div>{transactions.length === 0 ? <p className="dashboard-state">No completed transactions.</p> : <div className="resource-list transaction-list">{transactions.map((item) => <div className="resource-row" key={String(item.id)}><strong>{formatINR(Number(item.amount))}</strong><span>{String(item.payment_method)}</span><StatusBadge status={String(item.payment_status)} /></div>)}</div>}</article><article className="panel capacity-panel"><div className="panel-heading"><div><p className="eyebrow">Quick actions</p><h2>Financial tools</h2></div></div><div className="role-actions"><button className="outline-button" type="button" onClick={() => onNavigate('Billing')}>Create bill</button><button className="outline-button" type="button" onClick={() => onNavigate('Billing')}>Record payment</button></div></article></section>
      <BillingWorkspace token={token} role="staff" overview={data.billing_overview} onRefresh={onDashboardRefresh} />
    </>
  }

  const stats = data.stats as Record<string, number | null>
  const departments = (data.department_statistics ?? []) as Array<Record<string, unknown>>
  const recentAppointments = (data.recent_appointments ?? []) as Array<Record<string, unknown>>
  const activity = (data.recent_activity ?? []) as Array<Record<string, unknown>>
  return <>
    <article className="panel capacity-panel">
      <div className="panel-heading"><h2>Admin AI</h2></div>
      <div className="ai-prompts" aria-label="Admin AI suggestions">
        {adminPrompts.map((prompt) => <button key={prompt} type="button" onClick={() => onInsightPrompt(prompt)}>{prompt}</button>)}
      </div>
    </article>
    <section className="metrics-grid" aria-label="Administrator metrics"><MetricCard label="Total patients" value={stats.total_patients ?? 0} tone="metric-dark" /><MetricCard label="Total doctors" value={stats.total_doctors ?? 0} tone="metric-coral" /><MetricCard label="Total appointments" value={stats.total_appointments ?? 0} tone="metric-lime" /><MetricCard label="Today's appointments" value={stats.todays_appointments ?? 0} /></section>
    <section className="metrics-grid role-secondary-metrics"><MetricCard label="Collections" value={formatINR(Number(stats.revenue ?? 0))} tone="metric-lime" /><MetricCard label="Pending bills" value={stats.pending_bills ?? 0} tone="metric-coral" /><MetricCard label="Pending approvals" value={stats.pending_staff_approvals ?? 0} tone="metric-dark" /><MetricCard label="Hospital occupancy" value={stats.hospital_occupancy === null ? 'Unavailable' : String(stats.hospital_occupancy)} /></section>
    {data.billing_overview && <section className="panel capacity-panel billing-workspace">
      <div className="panel-heading"><h2>Billing overview</h2><button className="outline-button" type="button" onClick={() => onNavigate('Billing')}>View bills</button></div>
      <BillingOverviewCards overview={data.billing_overview} />
      <h3>Recently issued bills</h3>
      {data.billing_overview.recent.length ? <ul className="billing-records">{data.billing_overview.recent.map((bill) => <li key={bill.reference}><strong>{bill.reference}</strong><span>{new Date(bill.date).toLocaleDateString()}</span><span>{formatINR(bill.amount)}</span></li>)}</ul> : <p>No bills have been generated yet.</p>}
    </section>}
    <section className="dashboard-grid"><article className="schedule-section">
        <div className="panel-heading"><div><p className="eyebrow">Hospital operations</p><h2>Recent appointments</h2></div></div>
        <ScheduleList title="Recent appointments" nameLabel="Patient and appointment" empty="No appointments recorded."
          entries={recentAppointments.map((item) => ({
            id: String(item.id), ...scheduleTiming(item.appointment_date), name: String(item.patient_name),
            detail: typeof item.reason === 'string' ? item.reason : undefined,
            doctor: String(item.doctor_name), status: String(item.status),
          }))} />
      </article><article className="panel capacity-panel"><div className="panel-heading"><div><p className="eyebrow">Quick actions</p><h2>Administration</h2></div></div><div className="role-actions"><button className="outline-button" type="button" onClick={() => onNavigate('Accounts')}>Manage staff</button><button className="outline-button" type="button" onClick={() => onNavigate('Patients')}>Manage patients</button><button className="outline-button" type="button" onClick={() => onNavigate('Doctors')}>Manage doctors</button></div></article></section>
    <section className="bottom-grid"><article className="panel queue-panel"><div className="panel-heading"><div><p className="eyebrow">Departments</p><h2>Doctor statistics</h2></div></div>{departments.length === 0 ? <p className="dashboard-state">No department data available.</p> : <div className="resource-list">{departments.map((item) => <div className="resource-row" key={String(item.department)}><strong>{String(item.department)}</strong><span>{String(item.doctor_count)} doctors</span></div>)}</div>}</article><article className="panel capacity-panel"><div className="panel-heading"><div><p className="eyebrow">Audit trail</p><h2>Recent activity</h2></div></div>{activity.length === 0 ? <p className="dashboard-state">No recent activity.</p> : <div className="resource-list">{activity.map((item) => <div className="resource-row" key={String(item.id)}><strong>{String(item.action)}</strong><span>{String(item.resource)}</span></div>)}</div>}</article></section>
  </>
}

function App() {
  const [activeNav, setActiveNav] = useState('Overview')
  const [triageOpen, setTriageOpen] = useState(false)
  const [chatOpen, setChatOpen] = useState(false)
  const [chatQuery, setChatQuery] = useState('')
  const [chatResponse, setChatResponse] = useState<ChatResponse | null>(null)
  const [chatMessages, setChatMessages] = useState<ConversationMessage[]>([])
  const [selectedChatDoctor, setSelectedChatDoctor] = useState<PatientDoctorOption | null>(null)
  const [selectedChatDate, setSelectedChatDate] = useState('')
  const [selectedChatTime, setSelectedChatTime] = useState('')
  const [chatCalendarMonth, setChatCalendarMonth] = useState(() => {
    const now = new Date()
    return new Date(now.getFullYear(), now.getMonth(), 1)
  })
  const [chatAvailabilityDates, setChatAvailabilityDates] = useState<string[]>([])
  const [chatAvailabilityLoading, setChatAvailabilityLoading] = useState(false)
  const [chatAvailabilityError, setChatAvailabilityError] = useState('')
  const [chatDateSlots, setChatDateSlots] = useState<AppointmentSlot[]>([])
  const [chatDateSlotsLoading, setChatDateSlotsLoading] = useState(false)
  const [chatDateSlotsError, setChatDateSlotsError] = useState('')
  const [chatError, setChatError] = useState('')
  const [chatLoading, setChatLoading] = useState(false)
  const [chatRestoreLoading, setChatRestoreLoading] = useState(false)
  const [freshConversation, setFreshConversation] = useState(false)
  const [conversationId, setConversationId] = useState<string>()
  const [approvalLoading, setApprovalLoading] = useState(false)
  const [token, setToken] = useState(() => localStorage.getItem('mediflow_access_token') ?? '')
  const [currentUser, setCurrentUser] = useState<UserRecord | null>(null)
  const [appointments, setAppointments] = useState<Appointment[]>([])
  const [patients, setPatients] = useState<PatientRecord[]>([])
  const [doctors, setDoctors] = useState<DoctorRecord[]>([])
  const [dataLoading, setDataLoading] = useState(Boolean(token))
  const [dataError, setDataError] = useState('')
  const [createResource, setCreateResource] = useState<'Patients' | 'Doctors' | null>(null)
  const [staffBookingOpen, setStaffBookingOpen] = useState(false)
  const [currentTime] = useState(() => new Date())
  const [roleDashboard, setRoleDashboard] = useState<RoleDashboardData | null>(null)
  const [users, setUsers] = useState<UserRecord[]>([])
  const [pendingUsers, setPendingUsers] = useState<UserRecord[]>([])
  const [accountModalOpen, setAccountModalOpen] = useState(false)

  const loadChatDoctorAvailability = useCallback(async (doctor: PatientDoctorOption, restoredDate = '') => {
    const doctorId = Number(doctor.id)
    if (!Number.isInteger(doctorId) || doctorId < 1) {
      setChatAvailabilityError('The selected doctor schedule could not be loaded.')
      return
    }
    setChatAvailabilityLoading(true)
    setChatAvailabilityError('')
    try {
      const availableDates = await loadDoctorAppointmentDates({
        doctorId,
        startDate: asDateKey(currentTime),
        getAvailability: (id) => getDoctorAvailability(token, id),
        getSlots: (id, date) => getAvailableSlots(token, id, date),
        dayCount: CALENDAR_DAYS,
      })
      setChatAvailabilityDates(availableDates)
    } catch (error) {
      setChatAvailabilityDates([])
      setChatAvailabilityError(error instanceof Error ? error.message : 'The doctor schedule could not be loaded.')
    } finally {
      setChatAvailabilityLoading(false)
    }

    if (restoredDate) {
      setChatDateSlotsLoading(true)
      setChatDateSlotsError('')
      try {
        const result = await loadAppointmentDateSlots({ doctorId, date: restoredDate, getSlots: (id, date) => getAvailableSlots(token, id, date) })
        setChatDateSlots(result.slots)
      } catch (error) {
        setChatDateSlots([])
        setChatDateSlotsError(error instanceof Error ? error.message : 'Appointment times could not be loaded.')
      } finally {
        setChatDateSlotsLoading(false)
      }
    }
  }, [currentTime, token])

  function selectChatDoctor(doctor: PatientDoctorOption) {
    setSelectedChatDoctor(doctor)
    setSelectedChatDate('')
    setSelectedChatTime('')
    setChatAvailabilityDates([])
    const now = currentTime
    setChatCalendarMonth(new Date(now.getFullYear(), now.getMonth(), 1))
    setChatDateSlots([])
    setChatDateSlotsError('')
    void loadChatDoctorAvailability(doctor)
    void askChat(`I want to book an appointment with Dr. ${doctor.name}`)
  }

  async function selectChatAppointmentDate(date: string) {
    if (!selectedChatDoctor) return
    setSelectedChatDate(date)
    setSelectedChatTime('')
    setChatDateSlots([])
    setChatDateSlotsError('')
    setChatDateSlotsLoading(true)
    void askChat(date)
    try {
      const result = await loadAppointmentDateSlots({
        doctorId: Number(selectedChatDoctor.id),
        date,
        getSlots: (id, targetDate) => getAvailableSlots(token, id, targetDate),
      })
      setChatDateSlots(result.slots)
      if (result.blocked || !result.slots.some((slot) => slot.status === 'available')) {
        setChatAvailabilityDates((dates) => dates.filter((item) => item !== date))
      }
    } catch (error) {
      setChatDateSlotsError(error instanceof Error ? error.message : 'Appointment times could not be loaded.')
    } finally {
      setChatDateSlotsLoading(false)
    }
  }

  function selectChatAppointmentTime(slot: AppointmentSlot) {
    if (!selectedChatDate) return
    const time = slot.start.slice(11, 16)
    setSelectedChatTime(time)
    void askChat(`${selectedChatDate} at ${time}`)
  }

  useEffect(() => {
    if (!token) return

    async function loadDashboard(role: UserRecord['role']) {
      try {
        const roleData = await getRoleDashboard(token, role)
        setRoleDashboard(roleData)

        const appointmentRecords = await getAppointments(token)
        let patientRecords: PatientRecord[] = []
        let doctorRecords: DoctorRecord[] = []

        if (role === 'admin') {
          ;[patientRecords, doctorRecords] = await Promise.all([
            getPatients(token),
            getDoctors(token),
          ])
          setUsers(await getUsers(token))
          setPendingUsers(await getPendingUsers(token))
        } else if (role === 'clinician' || role === 'staff') {
          ;[patientRecords, doctorRecords] = await Promise.all([
            getPatients(token),
            getDoctors(token),
          ])
        } else if (role === 'patient') {
          doctorRecords = await getDoctors(token)
        }

        setPatients(patientRecords)
        setDoctors(doctorRecords)

        const patientById = new Map<number, PatientRecord>(patientRecords.map((patient) => [patient.id, patient]))
        const doctorById = new Map<number, DoctorRecord>(doctorRecords.map((doctor) => [doctor.id, doctor]))
        const colors = ['coral', 'lime', 'blue', 'yellow']
        setAppointments(appointmentRecords
          .sort((left, right) => left.appointment_date.localeCompare(right.appointment_date))
          .slice(0, 8)
          .map((appointment, index) => {
            const patient = patientById.get(appointment.patient_id)
            const doctor = doctorById.get(appointment.doctor_id)
            return {
              id: appointment.id,
              time: new Date(appointment.appointment_date).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
              patient: patient?.name ?? `Patient #${appointment.patient_id}`,
              detail: `${appointment.reason ?? 'General consultation'} · ${doctor?.specialization ?? 'Care team'}`,
              doctor: doctor ? `Dr. ${doctor.name.replace(/^Dr\.\s*/i, '')}` : `Doctor #${appointment.doctor_id}`,
              status: appointment.status === 'Scheduled' ? 'Confirmed' : appointment.status,
              accent: colors[index % colors.length],
            }
          }))
      } catch (error) {
        setDataError(error instanceof Error ? error.message : 'The hospital data could not be loaded.')
      } finally {
        setDataLoading(false)
      }
    }

    void getCurrentUser(token).then((user) => {
      setCurrentUser(user)
      void loadDashboard(user.role)
    }).catch(() => {
      localStorage.removeItem('mediflow_access_token')
      setToken('')
      setConversationId(undefined)
      setChatResponse(null)
      setChatMessages([])
      setSelectedChatDoctor(null)
      setSelectedChatDate('')
      setSelectedChatTime('')
      setChatAvailabilityDates([])
      setChatDateSlots([])
      setChatAvailabilityError('')
      setChatDateSlotsError('')
      setFreshConversation(false)
    })
  }, [token])

  useEffect(() => {
    const role = currentUser?.role
    if (!token || (role !== 'patient' && role !== 'clinician')) return
    let active = true
    const interval = window.setInterval(() => {
      if (document.hidden) return
      void getRoleDashboard(token, role).then((dashboard) => {
        if (active) setRoleDashboard(dashboard)
      }).catch(() => {})
    }, 30_000)
    return () => {
      active = false
      window.clearInterval(interval)
    }
  }, [token, currentUser?.role])

  useEffect(() => {
    if (!chatOpen || !token || freshConversation) return
    let active = true
    void getLatestAIConversation(token).then((snapshot) => {
      if (!active) return
      const restored = restoreConversationState(snapshot)
      setConversationId(restored.conversationId)
      setChatMessages(restored.messages)
      setChatResponse(restored.response)
      setSelectedChatDoctor(restored.selectedDoctor as PatientDoctorOption | null)
      setSelectedChatDate(restored.selectedDate)
      setSelectedChatTime(restored.selectedTime)
      if (restored.selectedDate) {
        const restoredDate = new Date(`${restored.selectedDate}T12:00:00`)
        setChatCalendarMonth(new Date(restoredDate.getFullYear(), restoredDate.getMonth(), 1))
      }
      if (restored.selectedDoctor && currentUser?.role === 'patient') {
        void loadChatDoctorAvailability(restored.selectedDoctor as PatientDoctorOption, restored.selectedDate)
      }
      setChatError('')
    }).catch((error) => {
      if (!active) return
      const empty = startNewConversationState()
      setConversationId(empty.conversationId)
      setChatMessages(empty.messages)
      setChatResponse(empty.response)
      setSelectedChatDoctor(empty.selectedDoctor)
      setSelectedChatDate(empty.selectedDate)
      setSelectedChatTime(empty.selectedTime)
      setChatAvailabilityDates([])
      setChatDateSlots([])
      setChatAvailabilityError('')
      setChatDateSlotsError('')
      setChatError(error instanceof Error ? `Saved conversation unavailable: ${error.message}` : 'Saved conversation unavailable. Start a new conversation.')
    }).finally(() => {
      if (active) setChatRestoreLoading(false)
    })
    return () => { active = false }
  }, [chatOpen, token, freshConversation, currentUser?.role, loadChatDoctorAvailability])

  if (!token) {
    return <AuthScreen onAuthenticated={(accessToken, user) => {
      localStorage.setItem('mediflow_access_token', accessToken)
      setToken(accessToken)
      setCurrentUser(user)
    }} />
  }

  function refreshRoleDashboard() {
    if (!currentUser) return
    void getRoleDashboard(token, currentUser.role).then(setRoleDashboard).catch((error) => setDataError(error instanceof Error ? error.message : 'Dashboard could not be refreshed'))
  }

  async function askChat(text: string, doctorPatientId?: number) {
    if (text.trim().length < 3) return
    setChatLoading(true)
    setChatError('')
    try {
      setChatQuery(text)
      const response = await chatWithMediflow(text.trim(), token, conversationId, doctorPatientId)
      setChatResponse(response)
      setConversationId(response.conversation_id)
      setChatMessages((messages) => [
        ...messages,
        { role: 'user', content: text.trim() },
        { role: 'assistant', content: response.message },
      ])
      setFreshConversation(false)
      if ('cancellation_options' in response.data || 'cancellation_selection' in response.data) {
        setSelectedChatDoctor(null)
        setSelectedChatDate('')
        setSelectedChatTime('')
      }
      const doctor = response.data.doctor
      if (doctor && typeof doctor === 'object' && 'id' in doctor && 'name' in doctor) {
        setSelectedChatDoctor(doctor as PatientDoctorOption)
      }
      const responseDate = response.data.date ?? response.data.appointment_date
      if (typeof responseDate === 'string') setSelectedChatDate(responseDate.slice(0, 10))
      const responseTime = response.data.time ?? response.data.appointment_time
      if (typeof responseTime === 'string') setSelectedChatTime(responseTime.slice(0, 5))
    } catch (error) {
      const message = error instanceof Error ? error.message : 'The AI assistant is unavailable.'
      if (message.toLowerCase().includes('no longer available')) {
        const empty = startNewConversationState()
        setConversationId(empty.conversationId)
        setChatMessages(empty.messages)
        setChatResponse(empty.response)
        setSelectedChatDoctor(empty.selectedDoctor)
        setFreshConversation(true)
        setChatError('This conversation was deleted or is unavailable. Start a new conversation to continue.')
      } else {
        setChatError(message)
      }
    } finally {
      setChatLoading(false)
    }
  }

  async function submitChat(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (chatQuery.trim().length < 3) {
      setChatError('Ask a question with at least three characters.')
      return
    }
    await askChat(chatQuery)
  }

  async function selectChatCancellation(appointmentId: number) {
    if (!conversationId || chatLoading) return
    setChatLoading(true)
    setChatError('')
    try {
      const response = await selectCancellationAppointment(token, conversationId, appointmentId)
      setChatResponse(response)
      setChatMessages((messages) => [...messages, { role: 'assistant', content: response.message }])
    } catch (error) {
      setChatError(error instanceof Error ? error.message : 'The appointment could not be selected.')
    } finally {
      setChatLoading(false)
    }
  }

  function openAIChat() {
    if (!freshConversation) setChatRestoreLoading(true)
    setChatOpen(true)
  }

  function startNewConversation() {
    if (chatResponse?.status === 'approval_required') {
      setChatError('Resolve the pending confirmation before starting a new conversation.')
      return
    }
    const empty = startNewConversationState()
    setConversationId(empty.conversationId)
    setChatMessages(empty.messages)
    setChatResponse(empty.response)
    setSelectedChatDoctor(empty.selectedDoctor)
    setSelectedChatDate(empty.selectedDate)
    setSelectedChatTime(empty.selectedTime)
    setChatAvailabilityDates([])
    setChatDateSlots([])
    setChatAvailabilityError('')
    setChatDateSlotsError('')
    setChatQuery('')
    setChatError('')
    setFreshConversation(true)
  }

  async function removeCurrentConversation() {
    if (!conversationId) return
    if (!window.confirm('Delete this conversation and its associated AI approvals?')) return
    setChatLoading(true)
    try {
      await deleteAIConversation(token, conversationId)
      const empty = startNewConversationState()
      setConversationId(empty.conversationId)
      setChatMessages(empty.messages)
      setChatResponse(empty.response)
      setSelectedChatDoctor(empty.selectedDoctor)
      setSelectedChatDate(empty.selectedDate)
      setSelectedChatTime(empty.selectedTime)
      setChatAvailabilityDates([])
      setChatDateSlots([])
      setChatAvailabilityError('')
      setChatDateSlotsError('')
      setChatQuery('')
      setChatError('Conversation deleted.')
      setFreshConversation(true)
    } catch (error) {
      setChatError(error instanceof Error ? error.message : 'The conversation could not be deleted.')
    } finally {
      setChatLoading(false)
    }
  }

  async function decideApproval(decision: 'approve' | 'reject') {
    if (!chatResponse?.approval_id) return
    setApprovalLoading(true)
    setChatError('')
    try {
      const response = await decideAIApproval(chatResponse.approval_id, decision, token)
      const resultMessage = response.result?.status === 'Pending Doctor Approval' && response.result?.appointment_id
        ? `Appointment request #${String(response.result.appointment_id)} submitted. Status: Pending Doctor Approval. Waiting for doctor approval.`
        : String(response.result?.message ?? (decision === 'approve' ? 'Operation completed.' : 'Operation rejected.'))
      setChatResponse({
        ...chatResponse,
        status: 'completed',
        message: resultMessage,
        approval_id: null,
        data: response.result ?? {},
      })
      setChatMessages((messages) => [...messages, { role: 'assistant', content: resultMessage }])
      if (currentUser) void getRoleDashboard(token, currentUser.role).then(setRoleDashboard)
    } catch (error) {
      setChatError(error instanceof Error ? error.message : 'The approval could not be processed.')
    } finally {
      setApprovalLoading(false)
    }
  }

  async function runMutation(action: () => Promise<void>) {
    try {
      setDataError('')
      await action()
    } catch (error) {
      setDataError(error instanceof Error ? error.message : 'The requested action could not be completed.')
    }
  }

  const dashboardRole = currentUser?.role ?? 'admin'
  const chatDoctors = chatResponse ? patientDoctorOptions(chatResponse.data) : []
  const chatEmergency = chatResponse?.data.urgency === 'Emergency'
  const chatTraceLabel = chatResponse ? visibleChatTrace(currentUser?.role, chatResponse.trace) : null
  const latestAssistantMessageIndex = chatMessages.reduce((latest, message, index) => message.role === 'assistant' ? index : latest, -1)
  const dashboardCopy = {
    admin: { label: 'Administrator dashboard', title: 'Hospital command center', text: 'Monitor every department, team, and operational decision from one workspace.' },
    staff: { label: 'Finance staff dashboard', title: 'Financial operations center', text: 'Keep billing, collections, and hospital operations moving smoothly.' },
    clinician: { label: 'Doctor dashboard', title: 'Care team workspace', text: 'Focus on today’s schedule, patient records, and the next clinical decision.' },
    patient: { label: 'Patient dashboard', title: 'Your care journey', text: 'Keep track of your care, appointments, and conversations with the hospital.' },
  }[dashboardRole]
  const todayLabel = new Intl.DateTimeFormat(undefined, { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' }).format(currentTime)
  const timeLabel = new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit' }).format(currentTime)

  return (
    <div className="app-shell">
      {(() => {
        const role = currentUser?.role ?? 'admin'
        const navItems = navItemsForRole(role)
        return <>
      <aside className="sidebar">
        <div className="brand-lockup"><MediflowLogo /></div>
        <div className="sidebar-section-label">Workspace</div>
        <nav className="main-nav" aria-label="Main navigation">
          {navItems.map((item, index) => <button className={activeNav === item ? 'nav-item active' : 'nav-item'} key={item} onClick={() => setActiveNav(item)} type="button"><span className="nav-number">0{index + 1}</span>{item}</button>)}
        </nav>
        <div className="sidebar-spacer" />
        <div className="system-status"><span className="status-dot" /><div><strong>Workspace connected</strong><span>API session active</span></div></div>
      <div className="user-chip"><div className="avatar avatar-dark">{(currentUser?.full_name ?? 'AR').slice(0, 2).toUpperCase()}</div><div><strong>{currentUser?.full_name ?? 'Hospital user'}</strong><span>{currentUser?.role ?? 'Administrator'}</span></div><button type="button" className="more-button" aria-label="Sign out" onClick={() => { localStorage.removeItem('mediflow_access_token'); setToken(''); setCurrentUser(null); setRoleDashboard(null); setActiveNav('Overview'); setStaffBookingOpen(false); setTriageOpen(false); setConversationId(undefined); setChatResponse(null); setChatMessages([]); setSelectedChatDoctor(null); setSelectedChatDate(''); setSelectedChatTime(''); setChatAvailabilityDates([]); setChatDateSlots([]); setFreshConversation(false) }}>↗</button></div>
      </aside>

      <main className="main-content">
        <header className="topbar"><div className="breadcrumb"><span>Workspace</span><b>/</b>{activeNav}</div><div className="topbar-actions"><button className="icon-button" type="button" aria-label="Search">⌕</button><button className="icon-button notification" type="button" aria-label="Notifications">◌<span /></button>{currentUser?.role === 'admin' && <button className="outline-button" type="button" onClick={() => setAccountModalOpen(true)}>+ Create account</button>}<button className="outline-button" type="button" onClick={openAIChat}>Ask MediFlow</button>{currentUser?.role === 'patient' && <button className="outline-button" type="button" onClick={() => setTriageOpen(true)}>+ New triage</button>}</div></header>
        <div className="content-wrap">
          {activeNav === 'Billing' && currentUser && currentUser.role !== 'clinician' ? <BillingWorkspace token={token} role={currentUser.role} overview={roleDashboard?.billing_overview} onRefresh={refreshRoleDashboard} /> : activeNav !== 'Overview' ? <ResourcePage activeNav={activeNav} role={currentUser?.role ?? 'clinician'} patients={patients} doctors={doctors} appointments={appointments} users={users} pendingUsers={pendingUsers} loading={dataLoading} error={dataError} onAdd={() => { if (activeNav === 'Patients' || activeNav === 'Doctors') setCreateResource(activeNav) }} onAddAppointment={() => setStaffBookingOpen(true)} onAddAccount={() => setAccountModalOpen(true)} onApproveUser={(id) => { void runMutation(async () => { await approveUser(token, id); setPendingUsers((current) => current.filter((user) => user.id !== id)); setUsers(await getUsers(token)) }) }} onRejectUser={(id) => { void runMutation(async () => { await rejectUser(token, id); setPendingUsers((current) => current.filter((user) => user.id !== id)); setUsers(await getUsers(token)) }) }} onDeletePatient={(id) => { if (!window.confirm('Delete this patient?')) return; void runMutation(async () => { await deletePatient(token, id); setPatients((current) => current.filter((patient) => patient.id !== id)) }) }} onDeleteDoctor={(id) => { if (!window.confirm('Delete this doctor?')) return; void runMutation(async () => { await deleteDoctor(token, id); setDoctors((current) => current.filter((doctor) => doctor.id !== id)) }) }} onCancelAppointment={(id) => { if (!window.confirm('Cancel this appointment?')) return; void runMutation(async () => { await cancelAppointment(token, id); setAppointments((current) => current.map((appointment) => appointment.id === id ? { ...appointment, status: 'Cancelled' } : appointment)) }) }} /> : <>
          <section className="welcome-row"><div><p className="eyebrow">{dashboardCopy.label} <span>·</span> {todayLabel} <span>·</span> {timeLabel}</p><h1>{dashboardCopy.title}<span>.</span></h1><p className="subhead">{dashboardCopy.text}</p></div></section>
          <div className="dashboard-stack"><RoleDashboard
            data={roleDashboard}
            loading={dataLoading}
            error={dataError}
            onNavigate={setActiveNav}
            token={token}
            doctors={doctors}
            onAskAI={openAIChat}
            onInsightPrompt={(prompt) => { setChatQuery(prompt); openAIChat() }}
            onDashboardRefresh={refreshRoleDashboard}
          /></div>
          </>}
        </div>
      </main>
      </>})()}

      {currentUser?.role === 'patient' && triageOpen && <PatientTriageModal token={token} onClose={() => setTriageOpen(false)} onBooked={refreshRoleDashboard} />}
      {chatOpen && <div className="modal-backdrop chat-modal-backdrop" role="presentation" onClick={() => setChatOpen(false)}>
        <div className="triage-modal chat-modal" role="dialog" aria-modal="true" aria-labelledby="chat-title" onClick={(event) => event.stopPropagation()}>
          <button className="modal-close" type="button" onClick={() => setChatOpen(false)} aria-label="Close AI assistant">×</button>
          <header className="chat-modal-header">
            <p className="eyebrow">Operational assistant</p><h2 id="chat-title">{dashboardRole === 'clinician' ? 'Doctor AI' : dashboardRole === 'staff' ? 'Finance AI' : dashboardRole === 'admin' ? 'Admin AI' : 'Ask MyDFlow AI.'}</h2>
            <p className="auth-copy">Ask in natural language to complete authorized hospital operations.</p>
          </header>
          <div className="chat-modal-tools">
            <div className="conversation-actions">
              <button className="outline-button" type="button" onClick={startNewConversation} disabled={chatLoading || chatRestoreLoading}>New conversation</button>
              {conversationId && <button className="outline-button" type="button" onClick={() => void removeCurrentConversation()} disabled={chatLoading || chatRestoreLoading}>Delete conversation</button>}
            </div>
            <div className="ai-prompts">
              {(dashboardRole === 'patient'
                ? ['Find a cardiologist', 'Show my upcoming appointments', 'Show my pending bills', 'Book an appointment', 'Cancel my appointment']
                : dashboardRole === 'clinician'
                  ? doctorPrompts
                  : dashboardRole === 'staff'
                    ? financePrompts
                    : adminPrompts
              ).map((prompt) => <button type="button" key={prompt} onClick={() => setChatQuery(prompt)}>{prompt}</button>)}
            </div>
          </div>
          {chatRestoreLoading && <p className="dashboard-state">Restoring your latest conversation…</p>}
          <div className="conversation-transcript" aria-live="polite">
            {currentUser?.role === 'admin' && chatLoading && <AdminReport loading />}
            {chatMessages.map((message, index) => <div className={`conversation-message ${message.role}`} key={`${conversationId ?? 'new'}-${index}`}>
              {message.role === 'assistant' && index === latestAssistantMessageIndex && <strong>{chatResponse?.agent ?? 'MediFlow AI'}</strong>}
              {currentUser?.role === 'admin' && message.role === 'assistant' && index === latestAssistantMessageIndex &&
                chatResponse?.agent === 'Admin AI Agent' && chatResponse.status === 'error'
                ? <AdminReport error={message.content} /> : <p>{message.content}</p>}
              {message.role === 'assistant' && index === latestAssistantMessageIndex && chatResponse && <>
                {(currentUser?.role === 'staff' || currentUser?.role === 'admin') && <FinanceReport report={chatResponse.data.finance_report} />}
                {currentUser?.role === 'admin' && <AdminReport report={chatResponse.data.admin_report} />}
                {currentUser?.role === 'clinician' && <DoctorIntelligence
                  result={chatResponse.data.doctor_intelligence as DoctorIntelligenceResult | undefined}
                  disabled={chatLoading || chatRestoreLoading || approvalLoading}
                  onSelect={(id) => void askChat("Show this patient's appointment history", id)}
                />}
                {!chatEmergency && <DoctorSelectionCards doctors={chatDoctors} disabled={chatLoading || chatAvailabilityLoading} onSelect={selectChatDoctor} />}
                {!chatEmergency && selectedChatDoctor && <p className="chat-selection-note">Selected doctor: Dr. {selectedChatDoctor.name}</p>}
                {!chatEmergency && currentUser?.role === 'patient' && selectedChatDoctor && <ChatAppointmentPicker
                  availabilityDates={chatAvailabilityDates}
                  availabilityLoading={chatAvailabilityLoading}
                  availabilityError={chatAvailabilityError}
                  selectedDate={selectedChatDate}
                  slots={chatDateSlots}
                  slotsLoading={chatDateSlotsLoading}
                  slotsError={chatDateSlotsError}
                  selectedTime={selectedChatTime}
                  viewMonth={chatCalendarMonth}
                  onChangeMonth={setChatCalendarMonth}
                  startDate={asDateKey(currentTime)}
                  disabled={chatLoading || chatResponse.status === 'approval_required'}
                  onSelectDate={(date) => void selectChatAppointmentDate(date)}
                  onSelectSlot={selectChatAppointmentTime}
                />}
                {(!selectedChatDoctor || currentUser?.role !== 'patient') && Array.isArray(chatResponse.data.available_slots) && <div className="ai-prompts" aria-label="Available appointment times">{(chatResponse.data.available_slots as string[]).map((slot) => { const time = new Date(slot); const label = Number.isNaN(time.getTime()) ? slot : time.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }); return <button type="button" key={slot} disabled={chatLoading} onClick={() => void askChat(label)}>{label}</button> })}</div>}
                {currentUser?.role === 'patient' && <ChatCancellation
                  data={chatResponse.data}
                  disabled={chatLoading || chatRestoreLoading || approvalLoading}
                  canConfirm={chatResponse.status === 'approval_required' && Boolean(chatResponse.approval_id)}
                  onSelect={(id) => void selectChatCancellation(id)}
                  onDecision={(decision) => void decideApproval(decision)}
                />}
                {chatResponse.status === 'approval_required' && chatResponse.approval_id && !chatResponse.data.cancellation_selection && <div className="approval-actions"><button className="dark-button" type="button" disabled={approvalLoading} onClick={() => void decideApproval('approve')}>{approvalLoading ? 'Processing…' : chatResponse.trace.some((item) => item.tool === 'create_appointment') ? 'Confirm and send request' : 'Approve'} <span>→</span></button><button className="outline-button" type="button" disabled={approvalLoading} onClick={() => void decideApproval('reject')}>Cancel</button></div>}
                <small>{chatResponse.status === 'completed' ? 'Completed' : chatResponse.status === 'clarification_required' ? 'Clarification needed' : chatResponse.status === 'approval_required' ? 'Waiting for approval' : 'Request error'}</small>
                {chatTraceLabel && <small>{chatTraceLabel}</small>}
              </>}
            </div>)}
          </div>
          <form className="resource-form chat-composer" onSubmit={submitChat}><label>Question<textarea required minLength={3} maxLength={2000} disabled={chatLoading || chatRestoreLoading || chatResponse?.status === 'approval_required'} value={chatQuery} onChange={(event) => setChatQuery(event.target.value)} placeholder="Ask about operations, billing, scheduling, or support..." /></label>{chatError && <p className="form-error" role="alert">{chatError}</p>}<button className="dark-button" type="submit" disabled={chatLoading || chatRestoreLoading || chatResponse?.status === 'approval_required'}>{chatLoading ? 'Thinking…' : 'Ask assistant'} <span>→</span></button></form>
        </div>
      </div>}
      {accountModalOpen && <CreateAccountModal token={token} patients={patients} onClose={() => setAccountModalOpen(false)} onCreated={(user) => setUsers((current) => [...current, user])} />}
      {staffBookingOpen && (currentUser?.role === 'staff' || currentUser?.role === 'admin') && <StaffAppointmentBooking
        token={token}
        onClose={() => setStaffBookingOpen(false)}
        onBooked={(appointment, patient, doctor) => {
          setAppointments((current) => [...current, {
            id: appointment.id, time: new Date(appointment.appointment_date).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }),
            patient: patient.name, detail: appointment.reason ?? doctor.specialization,
            doctor: doctor.name, status: appointment.status, accent: 'blue',
          }])
          refreshRoleDashboard()
        }}
      />}
      {createResource && <CreateResourceModal resource={createResource} token={token} onClose={() => setCreateResource(null)} onCreated={(record) => {
        if (createResource === 'Patients') setPatients((current) => [...current, record as PatientRecord])
        else setDoctors((current) => [...current, record as DoctorRecord])
      }} />}
    </div>
  )
}

export default App
