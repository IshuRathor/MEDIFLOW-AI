import { useEffect, useState, type FormEvent } from 'react'
import './App.css'
import {
  getAppointments,
  getBills,
  getRoleDashboard,
  createDoctor,
  createPatient,
  cancelAppointment,
  createAppointment,
  createBill,
  createPayment,
  chatWithMediflow,
  decideAIApproval,
  deleteDoctor,
  deletePatient,
  getCurrentUser,
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
  login,
  register,
  runTriage,
  type DoctorRecord,
  type BillRecord,
  type AppointmentRecord,
  type PaymentUpdate,
  type ChatResponse,
  type RoleDashboardData,
  type AvailabilityRecord,
  type AppointmentSlot,
  type PatientRecord,
  type TriageResponse,
  type UserRecord,
} from './api'

type Appointment = { id: number; time: string; patient: string; detail: string; doctor: string; status: string; accent: string }

const roleOptions: Array<{ value: UserRecord['role']; label: string; description: string }> = [
  { value: 'admin', label: 'Administrator', description: 'Full hospital workspace access' },
  { value: 'patient', label: 'Patient', description: 'Appointments, care and bills' },
  { value: 'clinician', label: 'Doctor', description: 'Care team and patient workflow' },
  { value: 'staff', label: 'Finance staff', description: 'Billing and hospital operations' },
]

function navItemsForRole(role: UserRecord['role']) {
  if (role === 'patient') return ['Overview']
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
  const [registrationRole, setRegistrationRole] = useState<'patient' | 'clinician' | 'staff' | 'admin'>('patient')
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
        <div className="brand-lockup auth-brand"><div className="brand-mark">M</div><div><strong>MediFlow</strong><span>Care operations</span></div></div>
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
                  ['admin', 'Administrator', 'Full hospital workspace access'],
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

function ResourcePage({
  activeNav,
  role,
  patients,
  doctors,
  bills,
  appointments,
  users,
  pendingUsers,
  loading,
  error,
  onAdd,
  onDeletePatient,
  onDeleteDoctor,
  onCancelAppointment,
  onAddBill,
  onAddAppointment,
  onPayBill,
  onAddAccount,
  onApproveUser,
  onRejectUser,
}: {
  activeNav: string
  role: UserRecord['role']
  patients: PatientRecord[]
  doctors: DoctorRecord[]
  bills: BillRecord[]
  appointments: Appointment[]
  users: UserRecord[]
  pendingUsers: UserRecord[]
  loading: boolean
  error: string
  onAdd: () => void
  onDeletePatient: (id: number) => void
  onDeleteDoctor: (id: number) => void
  onCancelAppointment: (id: number) => void
  onAddBill: () => void
  onAddAppointment: () => void
  onPayBill: (id: number) => void
  onAddAccount: () => void
  onApproveUser: (id: number) => void
  onRejectUser: (id: number) => void
}) {
  const patientById = new Map(patients.map((patient) => [patient.id, patient.name]))

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

  if (activeNav === 'Billing') {
    return <section className="panel resource-panel">
      <div className="panel-heading"><div><p className="eyebrow">Financial operations</p><h2>Billing</h2></div>{(role === 'admin' || role === 'staff') && <button className="outline-button" type="button" onClick={onAddBill}>+ Add bill</button>}</div>
      {bills.length === 0 ? <p className="dashboard-state">No bills have been created yet.</p> : <div className="resource-list">{bills.map((bill) => <div className="resource-row" key={bill.id}><div className="queue-icon lime-icon">$</div><div><strong>{bill.bill_number}</strong><span>{patientById.get(bill.patient_id) ?? `Patient #${bill.patient_id}`}</span></div><strong>${bill.total_amount.toFixed(2)}</strong><span className={`status-pill ${bill.status.toLowerCase().replaceAll(' ', '-')}`}>{bill.status}</span>{(role === 'admin' || role === 'staff') && bill.status !== 'Paid' && bill.status !== 'Cancelled' && <button className="row-action" type="button" onClick={() => onPayBill(bill.id)}>Record payment</button>}</div>)}</div>}
    </section>
  }

  if (activeNav === 'Appointments') {
    return <section className="panel resource-panel">
      <div className="panel-heading"><div><p className="eyebrow">Live schedule</p><h2>Appointments</h2></div><button className="outline-button" type="button" onClick={onAddAppointment}>+ Add appointment</button></div>
      {appointments.length === 0 ? <p className="dashboard-state">No appointments have been scheduled yet.</p> : <div className="resource-list">{appointments.map((appointment) => <div className="resource-row appointment-resource-row" key={appointment.id}><time>{appointment.time}</time><div><strong>{appointment.patient}</strong><span>{appointment.detail}</span></div><span>{appointment.doctor}</span><span className={`status-pill ${appointment.status.toLowerCase().replaceAll(' ', '-')}`}>{appointment.status}</span>{appointment.status !== 'Cancelled' && <button className="row-action" type="button" onClick={() => onCancelAppointment(appointment.id)}>Cancel</button>}</div>)}</div>}
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
  patients,
  doctors,
  bills,
  onClose,
  onCreated,
}: {
  resource: 'Patients' | 'Doctors' | 'Billing' | 'Appointments' | 'Payment'
  token: string
  onClose: () => void
  patients: PatientRecord[]
  doctors: DoctorRecord[]
  bills: BillRecord[]
  onCreated: (record: PatientRecord | DoctorRecord | BillRecord | AppointmentRecord | PaymentUpdate | undefined) => void
}) {
  const [values, setValues] = useState({ name: '', email: '', age: '', gender: '', phone: '', specialization: '', department: '', experience_years: '0', patient_id: '', doctor_id: '', bill_id: '', bill_number: '', total_amount: '', appointment_date: '', reason: '', payment_method: 'Card' })
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSaving(true)
    setError('')
    try {
      const record = resource === 'Patients'
        ? await createPatient(token, { name: values.name.trim(), email: values.email.trim(), age: Number(values.age), gender: values.gender || undefined, phone: values.phone || undefined })
        : resource === 'Doctors'
          ? await createDoctor(token, { name: values.name.trim(), email: values.email.trim(), specialization: values.specialization.trim(), department: values.department || undefined, phone: values.phone || undefined, experience_years: Number(values.experience_years) })
          : resource === 'Billing'
            ? await createBill(token, Number(values.patient_id), values.bill_number.trim(), Number(values.total_amount))
            : resource === 'Appointments'
              ? await createAppointment(token, { patient_id: Number(values.patient_id), doctor_id: Number(values.doctor_id), appointment_date: new Date(values.appointment_date).toISOString(), reason: values.reason || undefined })
              : await createPayment(token, Number(values.bill_id), Number(values.total_amount), values.payment_method)
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
    <p className="eyebrow">Care operations</p><h2 id="create-resource-title">{resource === 'Payment' ? 'Record payment' : `Add ${resource === 'Patients' ? 'patient' : resource === 'Doctors' ? 'doctor' : resource === 'Billing' ? 'bill' : 'appointment'}`}</h2>
    <form className="resource-form" onSubmit={submit}>
      {resource === 'Billing' ? <><label>Patient<select required value={values.patient_id} onChange={(event) => setValues({ ...values, patient_id: event.target.value })}><option value="">Select patient</option>{patients.map((patient) => <option value={patient.id} key={patient.id}>{patient.name}</option>)}</select></label><label>Bill number<input required value={values.bill_number} onChange={(event) => setValues({ ...values, bill_number: event.target.value })} /></label><label>Total amount<input required type="number" min="0.01" step="0.01" value={values.total_amount} onChange={(event) => setValues({ ...values, total_amount: event.target.value })} /></label></> : resource === 'Payment' ? <><label>Bill<select required value={values.bill_id} onChange={(event) => setValues({ ...values, bill_id: event.target.value })}><option value="">Select bill</option>{bills.filter((bill) => bill.status !== 'Paid' && bill.status !== 'Cancelled').map((bill) => <option value={bill.id} key={bill.id}>{bill.bill_number} — ${bill.total_amount.toFixed(2)}</option>)}</select></label><label>Amount<input required type="number" min="0.01" step="0.01" value={values.total_amount} onChange={(event) => setValues({ ...values, total_amount: event.target.value })} /></label><label>Payment method<select value={values.payment_method} onChange={(event) => setValues({ ...values, payment_method: event.target.value })}><option>Card</option><option>Cash</option><option>Bank Transfer</option><option>Insurance</option><option>Other</option></select></label></> : resource === 'Appointments' ? <><label>Patient<select required value={values.patient_id} onChange={(event) => setValues({ ...values, patient_id: event.target.value })}><option value="">Select patient</option>{patients.map((patient) => <option value={patient.id} key={patient.id}>{patient.name}</option>)}</select></label><label>Doctor<select required value={values.doctor_id} onChange={(event) => setValues({ ...values, doctor_id: event.target.value })}><option value="">Select doctor</option>{doctors.map((doctor) => <option value={doctor.id} key={doctor.id}>Dr. {doctor.name}</option>)}</select></label><label>Date and time<input required type="datetime-local" value={values.appointment_date} onChange={(event) => setValues({ ...values, appointment_date: event.target.value })} /></label><label>Reason<input value={values.reason} onChange={(event) => setValues({ ...values, reason: event.target.value })} /></label></> : <><label>Name<input required minLength={2} value={values.name} onChange={(event) => setValues({ ...values, name: event.target.value })} /></label><label>Email<input required type="email" value={values.email} onChange={(event) => setValues({ ...values, email: event.target.value })} /></label>{resource === 'Patients' ? <><label>Age<input required type="number" min="0" max="130" value={values.age} onChange={(event) => setValues({ ...values, age: event.target.value })} /></label><label>Gender<input value={values.gender} onChange={(event) => setValues({ ...values, gender: event.target.value })} /></label></> : <><label>Specialization<input required value={values.specialization} onChange={(event) => setValues({ ...values, specialization: event.target.value })} /></label><label>Department<input value={values.department} onChange={(event) => setValues({ ...values, department: event.target.value })} /></label><label>Experience years<input required type="number" min="0" value={values.experience_years} onChange={(event) => setValues({ ...values, experience_years: event.target.value })} /></label></>}<label>Phone<input value={values.phone} onChange={(event) => setValues({ ...values, phone: event.target.value })} /></label></>}
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
}: {
  token: string
  doctors: DoctorRecord[]
  onBooked: () => void
}) {
  const [doctorId, setDoctorId] = useState('')
  const [targetDate, setTargetDate] = useState('')
  const [slots, setSlots] = useState<AppointmentSlot[]>([])
  const [selectedSlot, setSelectedSlot] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [booking, setBooking] = useState(false)

  async function loadSlots() {
    if (!doctorId || !targetDate) return
    setError('')
    setMessage('')
    setSelectedSlot('')
    try {
      const result = await getAvailableSlots(token, Number(doctorId), targetDate)
      setSlots(result.slots)
      if (result.blocked) setError('The doctor has blocked this date.')
      if (result.slots.length === 0 && result.alternatives.length > 0) setError(`No slots today. Next available dates: ${result.alternatives.join(', ')}`)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Slots could not be loaded')
    }
  }

  async function book() {
    if (!selectedSlot) return
    setBooking(true)
    setError('')
    setMessage('')
    try {
      const appointment = await createAppointment(token, { patient_id: 0, doctor_id: Number(doctorId), appointment_date: selectedSlot })
      const doctor = doctors.find((item) => item.id === Number(doctorId))
      const date = new Date(appointment.appointment_date)
      setMessage(`Your appointment has been booked successfully! Dr. ${doctor?.name ?? 'your doctor'} — ${date.toLocaleDateString()} at ${date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`)
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
      <label>Doctor<select required value={doctorId} onChange={(event) => setDoctorId(event.target.value)}><option value="">Select doctor</option>{doctors.map((doctor) => <option value={doctor.id} key={doctor.id}>Dr. {doctor.name} — {doctor.specialization}</option>)}</select></label>
      <label>Date<input required type="date" value={targetDate} onChange={(event) => setTargetDate(event.target.value)} /></label>
      <button className="outline-button" type="button" disabled={!doctorId || !targetDate} onClick={() => void loadSlots()}>View slots</button>
      {slots.length > 0 && <div className="slot-grid">{slots.map((slot) => <button type="button" key={slot.start} disabled={slot.status !== 'available'} className={selectedSlot === slot.start ? 'slot-option selected' : 'slot-option'} onClick={() => setSelectedSlot(slot.start)}><strong>{new Date(slot.start).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</strong><span>{slot.status}</span></button>)}</div>}
      {error && <p className="form-error" role="alert">{error}</p>}
      {message && <p className="auth-message" role="status">{message}</p>}
      <button className="dark-button" type="button" disabled={!selectedSlot || booking} onClick={() => void book()}>{booking ? 'Booking…' : 'Confirm booking'} <span>→</span></button>
    </div>
  </article>
}

function MetricCard({ label, value, tone = 'metric-light' }: { label: string; value: string | number; tone?: string }) {
  return <article className={`metric-card ${tone}`}><div className="metric-label">{label}</div><strong>{value}</strong></article>
}

function RoleDashboard({
  data,
  loading,
  error,
  onNavigate,
  token,
  doctors,
  onDashboardRefresh,
}: {
  data: RoleDashboardData | null
  loading: boolean
  error: string
  onNavigate: (nav: string) => void
  token: string
  doctors: DoctorRecord[]
  onDashboardRefresh: () => void
}) {
  if (loading) return <p className="dashboard-state">Loading role dashboard…</p>
  if (error) return <p className="form-error" role="alert">{error}</p>
  if (!data) return <p className="dashboard-state">Dashboard data is unavailable.</p>

  if (data.role === 'clinician') {
    const stats = data.stats as Record<string, number>
    const schedule = (data.today_schedule ?? []) as Array<Record<string, unknown>>
    const patients = (data.assigned_patients ?? []) as Array<Record<string, unknown>>
    return <>
      <section className="metrics-grid" aria-label="Doctor metrics">
        <MetricCard label="Today's appointments" value={stats.todays_appointments ?? 0} tone="metric-dark" />
        <MetricCard label="Upcoming appointments" value={stats.upcoming_appointments ?? 0} tone="metric-coral" />
        <MetricCard label="Assigned patients" value={stats.assigned_patients ?? 0} tone="metric-lime" />
        <MetricCard label="Completed consultations" value={stats.completed_consultations ?? 0} />
      </section>
      <section className="metrics-grid role-secondary-metrics" aria-label="Doctor status metrics">
        <MetricCard label="Pending consultations" value={stats.pending_consultations ?? 0} tone="metric-coral" />
        <MetricCard label="Cancelled appointments" value={stats.cancelled_appointments ?? 0} tone="metric-light" />
      </section>
      <section className="dashboard-grid">
        <article className="panel appointments-panel"><div className="panel-heading"><div><p className="eyebrow">My schedule</p><h2>Today's appointments</h2></div></div>{schedule.length === 0 ? <p className="dashboard-state">No appointments scheduled for today.</p> : <div className="appointment-list">{schedule.map((item) => <div className="appointment-row" key={String(item.id)}><time>{new Date(String(item.appointment_date)).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</time><div className="appointment-marker lime" /><div className="patient-info"><strong>{String(item.patient_name)}</strong><span>{String(item.reason ?? 'General consultation')}</span></div><span className="status-pill confirmed">{String(item.status)}</span></div>)}</div>}</article>
        <article className="panel capacity-panel"><div className="panel-heading"><div><p className="eyebrow">Quick actions</p><h2>Clinical tools</h2></div></div><div className="role-actions"><button className="outline-button" type="button" onClick={() => onNavigate('Patients')}>View patients</button><button className="outline-button" type="button" onClick={() => onNavigate('Appointments')}>View appointments</button></div></article>
      </section>
      <section className="bottom-grid"><article className="panel queue-panel"><div className="panel-heading"><div><p className="eyebrow">Assigned care</p><h2>My patients</h2></div></div>{patients.length === 0 ? <p className="dashboard-state">No assigned patients yet.</p> : <div className="resource-list">{patients.map((patient) => <div className="resource-row" key={String(patient.id)}><div className="avatar avatar-light">{String(patient.name).slice(0, 2).toUpperCase()}</div><div><strong>{String(patient.name)}</strong><span>{String(patient.email ?? 'Email unavailable')}</span></div></div>)}</div>}</article><DoctorAvailabilityManager token={token} /></section>
    </>
  }

  if (data.role === 'patient') {
    const stats = data.stats as Record<string, number>
    const upcoming = (data.upcoming ?? []) as Array<Record<string, unknown>>
    const previous = (data.previous ?? []) as Array<Record<string, unknown>>
    const bills = (data.bills ?? []) as Array<Record<string, unknown>>
    const payments = (data.payments ?? []) as Array<Record<string, unknown>>
    const doctor = data.assigned_doctor as Record<string, unknown> | null
    return <>
      <section className="metrics-grid" aria-label="Patient metrics"><MetricCard label="My upcoming appointments" value={stats.upcoming_appointments ?? 0} tone="metric-dark" /><MetricCard label="My previous appointments" value={stats.previous_appointments ?? 0} tone="metric-coral" /><MetricCard label="My bills" value={stats.bills ?? 0} tone="metric-lime" /><MetricCard label="Pending payments" value={stats.pending_payments ?? 0} /></section>
      <section className="bottom-grid"><PatientBooking token={token} doctors={doctors} onBooked={onDashboardRefresh} /></section>
      <section className="dashboard-grid"><article className="panel appointments-panel"><div className="panel-heading"><div><p className="eyebrow">Care journey</p><h2>Upcoming appointments</h2></div></div>{upcoming.length === 0 ? <p className="dashboard-state">No upcoming appointments.</p> : <div className="appointment-list">{upcoming.map((item) => <div className="appointment-row" key={String(item.id)}><time>{new Date(String(item.appointment_date)).toLocaleString()}</time><div className="patient-info"><strong>Dr. {String(item.doctor_name)}</strong><span>{String(item.reason ?? 'General consultation')}</span></div><span className="status-pill confirmed">{String(item.status)}</span></div>)}</div>}</article><article className="panel capacity-panel"><div className="panel-heading"><div><p className="eyebrow">My care</p><h2>Assigned doctor</h2></div></div>{doctor ? <div className="capacity-copy"><strong>Dr. {String(doctor.name)}</strong><span>{String(doctor.specialization)}</span></div> : <p className="dashboard-state">No assigned doctor yet.</p>}<div className="role-actions"><button className="outline-button" type="button" onClick={() => onNavigate('Appointments')}>Book appointment</button><button className="outline-button" type="button" onClick={() => onNavigate('Billing')}>View bills</button></div></article></section>
      <section className="bottom-grid"><article className="panel queue-panel"><div className="panel-heading"><div><p className="eyebrow">Personal history</p><h2>Previous appointments</h2></div></div>{previous.length === 0 ? <p className="dashboard-state">No previous appointments.</p> : <div className="resource-list">{previous.map((item) => <div className="resource-row" key={String(item.id)}><strong>{new Date(String(item.appointment_date)).toLocaleDateString()}</strong><span>{String(item.reason ?? 'General consultation')}</span><span>{String(item.status)}</span></div>)}</div>}</article><article className="panel capacity-panel"><div className="panel-heading"><div><p className="eyebrow">Personal finance</p><h2>Recent bills</h2></div></div>{bills.length === 0 ? <p className="dashboard-state">No bills found.</p> : <div className="resource-list">{bills.slice(0, 6).map((bill) => <div className="resource-row" key={String(bill.id)}><strong>{String(bill.bill_number)}</strong><span>${Number(bill.total_amount).toFixed(2)}</span><span>{String(bill.status)}</span></div>)}</div>}<small>Payment history: {payments.length === 0 ? 'No payments recorded.' : `${payments.length} record(s)`}</small></article></section>
    </>
  }

  if (data.role === 'staff') {
    const stats = data.stats as Record<string, number>
    const transactions = (data.recent_transactions ?? []) as Array<Record<string, unknown>>
    return <>
      <section className="metrics-grid" aria-label="Finance metrics"><MetricCard label="Total revenue" value={`$${Number(stats.total_revenue ?? 0).toFixed(2)}`} tone="metric-dark" /><MetricCard label="Today's collections" value={`$${Number(stats.todays_collections ?? 0).toFixed(2)}`} tone="metric-lime" /><MetricCard label="Monthly revenue" value={`$${Number(stats.monthly_revenue ?? 0).toFixed(2)}`} tone="metric-coral" /><MetricCard label="Outstanding bills" value={`$${Number(stats.outstanding_bills ?? 0).toFixed(2)}`} /></section>
      <section className="metrics-grid role-secondary-metrics"><MetricCard label="Pending payments" value={stats.pending_payments ?? 0} tone="metric-coral" /><MetricCard label="Bills generated" value={stats.total_bills_generated ?? 0} /><MetricCard label="Completed payments" value={stats.completed_payments ?? 0} tone="metric-lime" /></section>
      <section className="dashboard-grid"><article className="panel appointments-panel"><div className="panel-heading"><div><p className="eyebrow">Recent activity</p><h2>Transactions</h2></div></div>{transactions.length === 0 ? <p className="dashboard-state">No completed transactions.</p> : <div className="resource-list">{transactions.map((item) => <div className="resource-row" key={String(item.id)}><strong>${Number(item.amount).toFixed(2)}</strong><span>{String(item.payment_method)}</span><span>{String(item.payment_status)}</span></div>)}</div>}</article><article className="panel capacity-panel"><div className="panel-heading"><div><p className="eyebrow">Quick actions</p><h2>Financial tools</h2></div></div><div className="role-actions"><button className="outline-button" type="button" onClick={() => onNavigate('Billing')}>Create bill</button><button className="outline-button" type="button" onClick={() => onNavigate('Billing')}>Record payment</button></div></article></section>
    </>
  }

  const stats = data.stats as Record<string, number | null>
  const departments = (data.department_statistics ?? []) as Array<Record<string, unknown>>
  const recentAppointments = (data.recent_appointments ?? []) as Array<Record<string, unknown>>
  const activity = (data.recent_activity ?? []) as Array<Record<string, unknown>>
  return <>
    <section className="metrics-grid" aria-label="Administrator metrics"><MetricCard label="Total patients" value={stats.total_patients ?? 0} tone="metric-dark" /><MetricCard label="Total doctors" value={stats.total_doctors ?? 0} tone="metric-coral" /><MetricCard label="Total appointments" value={stats.total_appointments ?? 0} tone="metric-lime" /><MetricCard label="Today's appointments" value={stats.todays_appointments ?? 0} /></section>
    <section className="metrics-grid role-secondary-metrics"><MetricCard label="Revenue" value={`$${Number(stats.revenue ?? 0).toFixed(2)}`} tone="metric-lime" /><MetricCard label="Pending bills" value={stats.pending_bills ?? 0} tone="metric-coral" /><MetricCard label="Pending approvals" value={stats.pending_staff_approvals ?? 0} tone="metric-dark" /><MetricCard label="Hospital occupancy" value={stats.hospital_occupancy === null ? 'Unavailable' : String(stats.hospital_occupancy)} /></section>
    <section className="dashboard-grid"><article className="panel appointments-panel"><div className="panel-heading"><div><p className="eyebrow">Hospital operations</p><h2>Recent appointments</h2></div></div>{recentAppointments.length === 0 ? <p className="dashboard-state">No appointments recorded.</p> : <div className="resource-list">{recentAppointments.map((item) => <div className="resource-row" key={String(item.id)}><strong>{String(item.patient_name)}</strong><span>{String(item.doctor_name)}</span><span>{String(item.status)}</span></div>)}</div>}</article><article className="panel capacity-panel"><div className="panel-heading"><div><p className="eyebrow">Quick actions</p><h2>Administration</h2></div></div><div className="role-actions"><button className="outline-button" type="button" onClick={() => onNavigate('Accounts')}>Manage staff</button><button className="outline-button" type="button" onClick={() => onNavigate('Patients')}>Manage patients</button><button className="outline-button" type="button" onClick={() => onNavigate('Doctors')}>Manage doctors</button></div></article></section>
    <section className="bottom-grid"><article className="panel queue-panel"><div className="panel-heading"><div><p className="eyebrow">Departments</p><h2>Doctor statistics</h2></div></div>{departments.length === 0 ? <p className="dashboard-state">No department data available.</p> : <div className="resource-list">{departments.map((item) => <div className="resource-row" key={String(item.department)}><strong>{String(item.department)}</strong><span>{String(item.doctor_count)} doctors</span></div>)}</div>}</article><article className="panel capacity-panel"><div className="panel-heading"><div><p className="eyebrow">Audit trail</p><h2>Recent activity</h2></div></div>{activity.length === 0 ? <p className="dashboard-state">No recent activity.</p> : <div className="resource-list">{activity.map((item) => <div className="resource-row" key={String(item.id)}><strong>{String(item.action)}</strong><span>{String(item.resource)}</span></div>)}</div>}</article></section>
  </>
}

function App() {
  const [activeNav, setActiveNav] = useState('Overview')
  const [triageOpen, setTriageOpen] = useState(false)
  const [symptoms, setSymptoms] = useState('')
  const [triageResult, setTriageResult] = useState<TriageResponse | null>(null)
  const [triageError, setTriageError] = useState('')
  const [triageLoading, setTriageLoading] = useState(false)
  const [chatOpen, setChatOpen] = useState(false)
  const [chatQuery, setChatQuery] = useState('')
  const [chatResponse, setChatResponse] = useState<ChatResponse | null>(null)
  const [chatError, setChatError] = useState('')
  const [chatLoading, setChatLoading] = useState(false)
  const [conversationId, setConversationId] = useState<string>()
  const [approvalLoading, setApprovalLoading] = useState(false)
  const [token, setToken] = useState(() => localStorage.getItem('mediflow_access_token') ?? '')
  const [currentUser, setCurrentUser] = useState<UserRecord | null>(null)
  const [appointments, setAppointments] = useState<Appointment[]>([])
  const [patients, setPatients] = useState<PatientRecord[]>([])
  const [doctors, setDoctors] = useState<DoctorRecord[]>([])
  const [bills, setBills] = useState<BillRecord[]>([])
  const [dataLoading, setDataLoading] = useState(Boolean(token))
  const [dataError, setDataError] = useState('')
  const [createResource, setCreateResource] = useState<'Patients' | 'Doctors' | 'Billing' | 'Appointments' | 'Payment' | null>(null)
  const [currentTime] = useState(() => new Date())
  const [roleDashboard, setRoleDashboard] = useState<RoleDashboardData | null>(null)
  const [users, setUsers] = useState<UserRecord[]>([])
  const [pendingUsers, setPendingUsers] = useState<UserRecord[]>([])
  const [accountModalOpen, setAccountModalOpen] = useState(false)

  useEffect(() => {
    if (!token) return

    async function loadDashboard(role: UserRecord['role']) {
      try {
        const roleData = await getRoleDashboard(token, role)
        setRoleDashboard(roleData)

        const appointmentRecords = await getAppointments(token)
        let patientRecords: PatientRecord[] = []
        let doctorRecords: DoctorRecord[] = []
        let billRecords: BillRecord[] = []

        if (role === 'admin') {
          ;[patientRecords, doctorRecords, billRecords] = await Promise.all([
            getPatients(token),
            getDoctors(token),
            getBills(token),
          ])
          setUsers(await getUsers(token))
          setPendingUsers(await getPendingUsers(token))
        } else if (role === 'clinician') {
          ;[patientRecords, doctorRecords] = await Promise.all([
            getPatients(token),
            getDoctors(token),
          ])
        } else if (role === 'patient') {
          ;[billRecords, doctorRecords] = await Promise.all([
            getBills(token),
            getDoctors(token),
          ])
        } else {
          billRecords = await getBills(token)
        }

        setPatients(patientRecords)
        setDoctors(doctorRecords)
        setBills(billRecords)

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
    })
  }, [token])

  if (!token) {
    return <AuthScreen onAuthenticated={(accessToken, user) => {
      localStorage.setItem('mediflow_access_token', accessToken)
      setToken(accessToken)
      setCurrentUser(user)
    }} />
  }

  async function submitTriage() {
    if (symptoms.trim().length < 3) {
      setTriageError('Describe at least three characters of symptoms.')
      return
    }

    if (!token) {
      setTriageError('Sign in to the backend before running an assessment.')
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

  async function submitChat(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (chatQuery.trim().length < 3) {
      setChatError('Ask a question with at least three characters.')
      return
    }
    setChatLoading(true)
    setChatError('')
    try {
      const response = await chatWithMediflow(chatQuery.trim(), token, conversationId)
      setChatResponse(response)
      setConversationId(response.conversation_id)
    } catch (error) {
      setChatError(error instanceof Error ? error.message : 'The AI assistant is unavailable.')
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
      setChatResponse({
        ...chatResponse,
        status: 'completed',
        message: String(response.result?.message ?? (decision === 'approve' ? 'Operation completed.' : 'Operation rejected.')),
        approval_id: null,
        data: response.result ?? {},
      })
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
        <div className="brand-lockup"><div className="brand-mark">M</div><div><strong>MediFlow</strong><span>Care operations</span></div></div>
        <div className="sidebar-section-label">Workspace</div>
        <nav className="main-nav" aria-label="Main navigation">
          {navItems.map((item, index) => <button className={activeNav === item ? 'nav-item active' : 'nav-item'} key={item} onClick={() => setActiveNav(item)} type="button"><span className="nav-number">0{index + 1}</span>{item}</button>)}
        </nav>
        <div className="sidebar-spacer" />
        <div className="system-status"><span className="status-dot" /><div><strong>Workspace connected</strong><span>API session active</span></div></div>
        <div className="user-chip"><div className="avatar avatar-dark">{(currentUser?.full_name ?? 'AR').slice(0, 2).toUpperCase()}</div><div><strong>{currentUser?.full_name ?? 'Hospital user'}</strong><span>{currentUser?.role ?? 'Administrator'}</span></div><button type="button" className="more-button" aria-label="Sign out" onClick={() => { localStorage.removeItem('mediflow_access_token'); setToken(''); setCurrentUser(null); setConversationId(undefined); setChatResponse(null) }}>↗</button></div>
      </aside>

      <main className="main-content">
        <header className="topbar"><div className="breadcrumb"><span>Workspace</span><b>/</b>{activeNav}</div><div className="topbar-actions"><button className="icon-button" type="button" aria-label="Search">⌕</button><button className="icon-button notification" type="button" aria-label="Notifications">◌<span /></button>{currentUser?.role === 'admin' && <button className="outline-button" type="button" onClick={() => setAccountModalOpen(true)}>+ Create account</button>}<button className="outline-button" type="button" onClick={() => setChatOpen(true)}>Ask MediFlow</button><button className="outline-button" type="button" onClick={() => setTriageOpen(true)}>+ New triage</button></div></header>
        <div className="content-wrap">
          {activeNav !== 'Overview' ? <ResourcePage activeNav={activeNav} role={currentUser?.role ?? 'clinician'} patients={patients} doctors={doctors} bills={bills} appointments={appointments} users={users} pendingUsers={pendingUsers} loading={dataLoading} error={dataError} onAdd={() => { if (activeNav === 'Patients' || activeNav === 'Doctors') setCreateResource(activeNav) }} onAddBill={() => setCreateResource('Billing')} onAddAppointment={() => setCreateResource('Appointments')} onAddAccount={() => setAccountModalOpen(true)} onApproveUser={(id) => { void runMutation(async () => { await approveUser(token, id); setPendingUsers((current) => current.filter((user) => user.id !== id)); setUsers(await getUsers(token)) }) }} onRejectUser={(id) => { void runMutation(async () => { await rejectUser(token, id); setPendingUsers((current) => current.filter((user) => user.id !== id)); setUsers(await getUsers(token)) }) }} onPayBill={(_id) => setCreateResource('Payment')} onDeletePatient={(id) => { if (!window.confirm('Delete this patient?')) return; void runMutation(async () => { await deletePatient(token, id); setPatients((current) => current.filter((patient) => patient.id !== id)) }) }} onDeleteDoctor={(id) => { if (!window.confirm('Delete this doctor?')) return; void runMutation(async () => { await deleteDoctor(token, id); setDoctors((current) => current.filter((doctor) => doctor.id !== id)) }) }} onCancelAppointment={(id) => { if (!window.confirm('Cancel this appointment?')) return; void runMutation(async () => { await cancelAppointment(token, id); setAppointments((current) => current.map((appointment) => appointment.id === id ? { ...appointment, status: 'Cancelled' } : appointment)) }) }} /> : <>
          <section className="welcome-row"><div><p className="eyebrow">{dashboardCopy.label} <span>·</span> {todayLabel} <span>·</span> {timeLabel}</p><h1>{dashboardCopy.title}<span>.</span></h1><p className="subhead">{dashboardCopy.text}</p></div></section>
          <RoleDashboard
            data={roleDashboard}
            loading={dataLoading}
            error={dataError}
            onNavigate={setActiveNav}
            token={token}
            doctors={doctors}
            onDashboardRefresh={() => {
              void getRoleDashboard(token, 'patient').then(setRoleDashboard).catch((requestError) => setDataError(requestError instanceof Error ? requestError.message : 'Dashboard could not be refreshed'))
            }}
          />
          </>}
        </div>
      </main>
      </>})()}

      {triageOpen && <div className="modal-backdrop" role="presentation" onClick={() => setTriageOpen(false)}><div className="triage-modal" role="dialog" aria-modal="true" aria-labelledby="triage-title" onClick={(event) => event.stopPropagation()}><button className="modal-close" type="button" onClick={() => setTriageOpen(false)} aria-label="Close triage">×</button><p className="eyebrow">AI assisted triage</p><h2 id="triage-title">What is the patient feeling?</h2>{triageResult ? <div className="triage-result"><strong>{triageResult.urgency} urgency</strong><span>{triageResult.recommended_department}</span><p>{triageResult.recommended_action}</p><small>{triageResult.safety_notice}</small><small>{triageResult.disclaimer}</small><button className="dark-button" type="button" onClick={() => setTriageResult(null)}>Run another <span>→</span></button></div> : <><textarea value={symptoms} maxLength={500} onChange={(event) => setSymptoms(event.target.value)} placeholder="Describe symptoms in plain language..." />{triageError && <p className="form-error" role="alert">{triageError}</p>}<div className="modal-footer"><span>{symptoms.length}/500</span><button className="dark-button" type="button" onClick={submitTriage} disabled={triageLoading}>{triageLoading ? 'Assessing…' : 'Run assessment'} <span>→</span></button></div></>}</div></div>}
      {chatOpen && <div className="modal-backdrop" role="presentation" onClick={() => setChatOpen(false)}>
        <div className="triage-modal chat-modal" role="dialog" aria-modal="true" aria-labelledby="chat-title" onClick={(event) => event.stopPropagation()}>
          <button className="modal-close" type="button" onClick={() => setChatOpen(false)} aria-label="Close AI assistant">×</button>
          <p className="eyebrow">Operational assistant</p><h2 id="chat-title">Ask MyDFlow AI.</h2>
          <p className="auth-copy">Ask in natural language to complete authorized hospital operations.</p>
          <div className="ai-prompts">
            {(dashboardRole === 'patient'
              ? ['Find a cardiologist', 'Show my upcoming appointments', 'Show my pending bills', 'Book an appointment']
              : dashboardRole === 'clinician'
                ? ['Show my appointments today', 'Show my upcoming patients', 'Show my availability']
                : dashboardRole === 'staff'
                  ? ["Show today's collections", 'Find pending payments', "Generate this month's financial summary"]
                  : ['Show hospital overview', 'How many appointments are scheduled today?', 'Show pending staff approvals']
            ).map((prompt) => <button type="button" key={prompt} onClick={() => setChatQuery(prompt)}>{prompt}</button>)}
          </div>
          {chatResponse && <div className="chat-response">
            <strong>{chatResponse.agent ?? 'MyDFlow AI'}</strong>
            <p>{chatResponse.message ?? 'The assistant returned a structured operational result.'}</p>
            {chatResponse.status === 'approval_required' && chatResponse.approval_id && <div className="approval-actions"><button className="dark-button" type="button" disabled={approvalLoading} onClick={() => void decideApproval('approve')}>{approvalLoading ? 'Processing…' : 'Approve'} <span>→</span></button><button className="outline-button" type="button" disabled={approvalLoading} onClick={() => void decideApproval('reject')}>Cancel</button></div>}
            <small>{chatResponse.status === 'completed' ? 'Completed' : chatResponse.status === 'clarification_required' ? 'Clarification needed' : chatResponse.status === 'approval_required' ? 'Waiting for approval' : 'Request error'}</small>
            {chatResponse.trace.length > 0 && <small>{chatResponse.trace.map((item) => `${item.tool}: ${item.status}`).join(' · ')}</small>}
          </div>}
          <form className="resource-form" onSubmit={submitChat}><label>Question<textarea required minLength={3} maxLength={2000} value={chatQuery} onChange={(event) => setChatQuery(event.target.value)} placeholder="Ask about operations, billing, scheduling, or support..." /></label>{chatError && <p className="form-error" role="alert">{chatError}</p>}<button className="dark-button" type="submit" disabled={chatLoading}>{chatLoading ? 'Thinking…' : 'Ask assistant'} <span>→</span></button></form>
        </div>
      </div>}
      {accountModalOpen && <CreateAccountModal token={token} patients={patients} onClose={() => setAccountModalOpen(false)} onCreated={(user) => setUsers((current) => [...current, user])} />}
      {createResource && <CreateResourceModal resource={createResource} token={token} patients={patients} doctors={doctors} bills={bills} onClose={() => setCreateResource(null)} onCreated={(record) => { if (!record) return; if (createResource === 'Patients') setPatients((current) => [...current, record as PatientRecord]); else if (createResource === 'Doctors') setDoctors((current) => [...current, record as DoctorRecord]); else if (createResource === 'Billing') setBills((current) => [...current, record as BillRecord]); else if (createResource === 'Payment') { const update = record as PaymentUpdate; setBills((current) => current.map((bill) => bill.id === update.billId ? { ...bill, status: update.status } : bill)) } else if (createResource === 'Appointments') setAppointments((current) => [...current, { id: (record as AppointmentRecord).id, time: new Date((record as AppointmentRecord).appointment_date).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }), patient: patients.find((patient) => patient.id === (record as AppointmentRecord).patient_id)?.name ?? `Patient #${(record as AppointmentRecord).patient_id}`, detail: (record as AppointmentRecord).reason ?? 'General consultation', doctor: `Doctor #${(record as AppointmentRecord).doctor_id}`, status: 'Confirmed', accent: 'blue' }]) }} />}
    </div>
  )
}

export default App
