import type { FinanceReportData } from './FinanceReport.js'
import type { AdminReportData } from './AdminReport.js'

const API_BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api'

export type UserRecord = {
  id: number
  full_name: string
  email: string
  role: 'admin' | 'staff' | 'clinician' | 'patient'
  is_active: boolean
  approval_status: 'approved' | 'pending' | 'rejected'
  created_at: string
}

export type PatientInput = {
  name: string
  age: number
  gender?: string
  phone?: string
  email: string
}

export type DoctorInput = {
  name: string
  specialization: string
  phone?: string
  email: string
  department?: string
  experience_years: number
}

export type TokenResponse = {
  access_token: string
  token_type: string
  user: UserRecord
}

async function post<T>(path: string, body: unknown, token?: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  })

  if (!response.ok) {
    const result = await response.json().catch(() => null) as { detail?: string | { message?: string } } | null
    const detail = result?.detail
    throw new Error(typeof detail === 'string' ? detail : detail?.message ?? 'The request could not be completed.')
  }

  return response.json() as Promise<T>
}

export function login(email: string, password: string, role: UserRecord['role']): Promise<TokenResponse> {
  return post<TokenResponse>('/auth/login', { email, password, role })
}

export type PublicRegistrationInput = {
  full_name: string
  email: string
  phone: string
  password: string
  confirm_password: string
  role: 'patient' | 'clinician' | 'staff'
  specialization?: string
  department?: string
  experience_years?: number
}

export function register(
  input: PublicRegistrationInput,
): Promise<UserRecord> {
  return post<UserRecord>('/auth/register', input)
}

export function registerPatient(
  fullName: string,
  email: string,
  phone: string,
  password: string,
  confirmPassword: string,
): Promise<UserRecord> {
  return post<UserRecord>('/auth/register-patient', {
    full_name: fullName,
    email,
    phone,
    password,
    confirm_password: confirmPassword,
  })
}

export async function getRegistrationStatus(): Promise<boolean> {
  const response = await fetch(`${API_BASE_URL}/auth/registration-status`)
  if (!response.ok) {
    return false
  }
  const result = await response.json() as { registration_allowed: boolean }
  return result.registration_allowed
}

export function getCurrentUser(token: string): Promise<UserRecord> {
  return get<UserRecord>('/auth/me', token)
}

export function getUsers(token: string): Promise<UserRecord[]> {
  return get<UserRecord[]>('/auth/users', token)
}

export function getPendingUsers(token: string): Promise<UserRecord[]> {
  return get<UserRecord[]>('/auth/pending-users', token)
}

export function approveUser(token: string, userId: number): Promise<UserRecord> {
  return post<UserRecord>(`/auth/users/${userId}/approve`, {}, token)
}

export function rejectUser(token: string, userId: number): Promise<UserRecord> {
  return post<UserRecord>(`/auth/users/${userId}/reject`, {}, token)
}

export type CreateUserInput = {
  full_name: string
  email: string
  password: string
  role: 'staff' | 'clinician' | 'patient'
  patient_id?: number
}

export function createUser(token: string, input: CreateUserInput): Promise<UserRecord> {
  return post<UserRecord>('/auth/users', input, token)
}

export type AppointmentRecord = {
  id: number
  patient_id: number
  doctor_id: number
  appointment_date: string
  reason: string | null
  status: 'Pending Doctor Approval' | 'Scheduled' | 'Declined' | 'Completed' | 'Cancelled' | 'No-show'
  notes: string | null
  decline_reason?: string | null
  created_at: string
}

export type PatientRecord = {
  id: number
  name: string
  age: number | null
  gender: string | null
  phone: string | null
  email: string | null
  created_at: string
}

export type DoctorRecord = {
  id: number
  name: string
  specialization: string
  phone: string | null
  email: string | null
  department: string | null
  experience_years: number | null
  created_at: string
}

export type BillRecord = {
  id: number
  patient_id: number
  bill_number: string
  total_amount: string
  patient_name: string | null
  amount_paid: string
  outstanding: string
  status: 'Pending' | 'Partially Paid' | 'Paid' | 'Cancelled'
  created_at: string
}

export type BillLine = { description: string; quantity: number; unit_price: string }
export type BillDetail = BillRecord & {
  items: (BillLine & { amount: string })[]
  payments: { amount: string; payment_method: string; payment_status: string; paid_at: string }[]
}
export type BillingOverview = {
  generated: number; billed: number; collected: number; outstanding: number
  unpaid: number; partial: number; paid: number
  recent: { reference: string; date: string; amount: number }[]
}
export type FinanceReview = { approval_id: string; total_amount: string }

export function getBillPage(token: string, search: string, status: string, offset: number, limit: number) {
  const query = new URLSearchParams({ search, status, offset: String(offset), limit: String(limit) })
  return get<BillRecord[]>(`/bills/?${query}`, token)
}

export function getBillDetail(token: string, billId: number) {
  return get<BillDetail>(`/bills/${billId}`, token)
}

export function searchBillingPatients(token: string, search: string) {
  const query = new URLSearchParams({ search, sort: 'name', order: 'asc' })
  return get<PatientRecord[]>(`/patients/?${query}`, token)
}

export function reviewBill(token: string, draft: { patient_id: number; bill_number: string; items: BillLine[] }) {
  return post<FinanceReview>('/bills/', draft, token)
}

export function reviewPayment(token: string, draft: { bill_id: number; amount: string; payment_method: string; transaction_reference: string }) {
  return post<FinanceReview>('/payments/', draft, token)
}

export type PaymentUpdate = {
  billId: number
  status: BillRecord['status']
}

export type AppointmentInput = {
  patient_id: number
  doctor_id: number
  appointment_date: string
  reason?: string
  notes?: string
}

export type DashboardMetrics = {
  appointments_today: number
  patients_registered: number
  doctors_registered: number
  recorded_billing: number
  outstanding_bills: number
}

async function get<T>(path: string, token: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  })

  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null
    throw new Error(body?.detail ?? 'The hospital data could not be loaded.')
  }

  return response.json() as Promise<T>
}

export function getAppointments(token: string): Promise<AppointmentRecord[]> {
  return get<AppointmentRecord[]>('/appointments/', token)
}

export function getDashboardMetrics(token: string): Promise<DashboardMetrics> {
  return get<DashboardMetrics>('/dashboard/metrics', token)
}

export type RoleDashboardData = {
  role: 'clinician' | 'patient' | 'staff' | 'admin'
  billing_overview?: BillingOverview
  [key: string]: unknown
}

export function getRoleDashboard(token: string, role: UserRecord['role']): Promise<RoleDashboardData> {
  const route = role === 'clinician' ? 'doctor' : role === 'patient' ? 'patient' : role === 'staff' ? 'finance' : 'admin'
  return get<RoleDashboardData>(`/dashboard/${route}`, token)
}

async function processAppointmentRequest(appointmentId: number, action: 'accept' | 'decline', token: string, reason?: string): Promise<AppointmentRecord> {
  const response = await fetch(`${API_BASE_URL}/appointments/${appointmentId}/${action}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: action === 'decline' ? JSON.stringify({ reason: reason ?? null }) : undefined,
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null
    throw new Error(body?.detail ?? 'The appointment request could not be processed.')
  }
  const result = await response.json() as { appointment: AppointmentRecord }
  return result.appointment
}

export function acceptAppointmentRequest(appointmentId: number, token: string): Promise<AppointmentRecord> {
  return processAppointmentRequest(appointmentId, 'accept', token)
}

export function declineAppointmentRequest(appointmentId: number, token: string, reason?: string): Promise<AppointmentRecord> {
  return processAppointmentRequest(appointmentId, 'decline', token, reason)
}
export async function createAppointment(token: string, input: AppointmentInput): Promise<AppointmentRecord> {
  const query = new URLSearchParams({
    patient_id: String(input.patient_id),
    doctor_id: String(input.doctor_id),
    appointment_date: input.appointment_date,
  })
  if (input.reason) query.set('reason', input.reason)
  if (input.notes) query.set('notes', input.notes)
  const response = await fetch(`${API_BASE_URL}/appointments/?${query.toString()}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string | { message?: string } } | null
    const detail = body?.detail
    throw new Error(typeof detail === 'string' ? detail : detail?.message ?? 'The appointment could not be created.')
  }
  const result = await response.json() as { appointment: AppointmentRecord }
  return result.appointment
}

export function getPatients(token: string, search?: string): Promise<PatientRecord[]> {
  const query = search === undefined ? '' : '?' + new URLSearchParams({ search, sort: 'name', order: 'asc' })
  return get<PatientRecord[]>(`/patients/${query}`, token)
}

export function createPatient(token: string, input: PatientInput): Promise<PatientRecord> {
  return post<PatientRecord>('/patients/', input, token)
}

export function deletePatient(token: string, patientId: number): Promise<void> {
  return remove(`/patients/${patientId}`, token)
}

export function getDoctors(token: string, filters?: { search: string; specialization: string; offset?: number; limit?: number }): Promise<DoctorRecord[]> {
  const query = filters ? '?' + new URLSearchParams({
    search: filters.search, specialization: filters.specialization, sort: 'name', order: 'asc',
    offset: String(filters.offset ?? 0), limit: String(filters.limit ?? 50),
  }) : ''
  return get<DoctorRecord[]>(`/doctors/${query}`, token)
}

export type AvailabilityRecord = {
  id: number
  doctor_id: number
  day_of_week: string
  specific_date: string | null
  start_time: string
  end_time: string
  is_available: boolean
}

export type AppointmentSlot = {
  start: string
  end: string
  status: 'available' | 'booked'
}

export function getMyAvailability(token: string): Promise<AvailabilityRecord[]> {
  return get<AvailabilityRecord[]>('/availability/me', token)
}

export function getDoctorAvailability(token: string, doctorId: number): Promise<AvailabilityRecord[]> {
  return get<AvailabilityRecord[]>(`/availability/doctor/${doctorId}`, token)
}

export function createAvailability(
  token: string,
  input: { day_of_week: string; start_time: string; end_time: string; specific_date?: string; is_available: boolean },
): Promise<{ availability: AvailabilityRecord }> {
  const query = new URLSearchParams({
    day_of_week: input.day_of_week,
    start_time: input.start_time,
    end_time: input.end_time,
    is_available: String(input.is_available),
  })
  if (input.specific_date) query.set('specific_date', input.specific_date)
  return post<{ availability: AvailabilityRecord }>(`/availability/?${query.toString()}`, {}, token)
}

export function deleteAvailability(token: string, availabilityId: number): Promise<void> {
  return remove(`/availability/${availabilityId}`, token)
}

export async function updateAvailability(
  token: string,
  availabilityId: number,
  input: { day_of_week: string; start_time: string; end_time: string; specific_date?: string; is_available: boolean },
): Promise<{ availability: AvailabilityRecord }> {
  const query = new URLSearchParams({
    day_of_week: input.day_of_week,
    start_time: input.start_time,
    end_time: input.end_time,
    is_available: String(input.is_available),
  })
  if (input.specific_date) query.set('specific_date', input.specific_date)
  const response = await fetch(`${API_BASE_URL}/availability/${availabilityId}?${query.toString()}`, {
    method: 'PUT',
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null
    throw new Error(body?.detail ?? 'Availability could not be updated')
  }
  return response.json() as Promise<{ availability: AvailabilityRecord }>
}

export async function getAvailableSlots(token: string, doctorId: number, date: string): Promise<{ blocked: boolean; slots: AppointmentSlot[]; alternatives: string[] }> {
  return get<{ blocked: boolean; slots: AppointmentSlot[]; alternatives: string[] }>(`/availability/slots/${doctorId}?date=${encodeURIComponent(date)}`, token)
}

export function createDoctor(token: string, input: DoctorInput): Promise<DoctorRecord> {
  return post<DoctorRecord>('/doctors/', input, token)
}

export function deleteDoctor(token: string, doctorId: number): Promise<void> {
  return remove(`/doctors/${doctorId}`, token)
}

export function cancelAppointment(token: string, appointmentId: number): Promise<void> {
  return remove(`/appointments/${appointmentId}`, token)
}

export type DoctorCancellationRequest = {
  id: number
  request_id: string
  patient_name: string
  appointment_date: string
  requested_at: string
  status: 'Pending Doctor Approval'
  can_approve: boolean
}

export type PatientCancellationUpdate = {
  doctor_name: string
  appointment_date: string
  status: string
  cancellation_status: 'Pending Doctor Approval' | 'Approved' | 'Rejected'
  cancellation_reason: string | null
}

export function decideCancellation(token: string, request: DoctorCancellationRequest, decision: 'approve' | 'reject', reason?: string) {
  return post<{ status: 'Approved' | 'Rejected' }>(
    `/appointments/${request.id}/cancellation/${decision}`,
    { request_id: request.request_id, reason },
    token,
  )
}

export function getBills(token: string): Promise<BillRecord[]> {
  return get<BillRecord[]>('/bills/', token)
}

export async function createBill(token: string, patientId: number, billNumber: string, totalAmount: number): Promise<BillRecord> {
  const query = new URLSearchParams({
    patient_id: String(patientId),
    bill_number: billNumber,
    total_amount: String(totalAmount),
  })
  const response = await fetch(`${API_BASE_URL}/bills/?${query.toString()}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null
    throw new Error(body?.detail ?? 'The bill could not be created.')
  }
  const result = await response.json() as { bill: BillRecord }
  return result.bill
}

export async function createPayment(token: string, billId: number, amount: number, paymentMethod: string): Promise<{ billId: number; status: BillRecord['status'] }> {
  const query = new URLSearchParams({
    bill_id: String(billId),
    amount: String(amount),
    payment_method: paymentMethod,
  })
  const response = await fetch(`${API_BASE_URL}/payments/?${query.toString()}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null
    throw new Error(body?.detail ?? 'The payment could not be recorded.')
  }
  const result = await response.json() as { bill_status: BillRecord['status'] }
  return { billId, status: result.bill_status }
}

async function remove(path: string, token: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null
    throw new Error(body?.detail ?? 'The record could not be deleted.')
  }
}

export type TriageDoctor = {
  id: number
  name: string
  specialization: string
  department: string | null
  experience_years: number | null
  availability: 'available' | 'no_slots' | 'unverified'
  upcoming_slots: string[]
  matching_explanation: string
}

export type TriageResponse = {
  urgency: 'Low' | 'Medium' | 'High' | 'Emergency'
  recommended_department: string
  symptoms_summary: string
  recommended_action: string
  disclaimer: string
  safety_notice: string
  recommended_doctors: TriageDoctor[]
  availability_window_days: number | null
}

export type ChatResponse = {
  conversation_id: string
  agent: string
  status: 'completed' | 'clarification_required' | 'approval_required' | 'error'
  message: string
  data: Record<string, unknown> & { finance_report?: FinanceReportData; admin_report?: AdminReportData }
  trace: Array<{ tool: string; status: 'success' | 'error' | 'skipped' | 'approval_required'; duration_ms: number }>
  approval_id: string | null
  [key: string]: unknown
}

export type ConversationMessage = {
  role: 'user' | 'assistant'
  content: string
}

export type LatestConversation = {
  conversation_id: string | null
  messages: ConversationMessage[]
  last_response: {
    status: ChatResponse['status']
    agent: string
    data: ChatResponse['data']
    trace?: ChatResponse['trace']
  } | null
  pending_approval: { id: string; action: string; expires_at: string } | null
  expired_approval: boolean
}

export async function getLatestAIConversation(token: string): Promise<LatestConversation> {
  const response = await fetch(`${API_BASE_URL}/ai/conversations/latest`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null
    throw new Error(body?.detail ?? 'The saved conversation could not be restored.')
  }
  return response.json() as Promise<LatestConversation>
}

export async function deleteAIConversation(token: string, conversationId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/ai/conversations/${encodeURIComponent(conversationId)}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null
    throw new Error(body?.detail ?? 'The conversation could not be deleted.')
  }
}

export async function chatWithMediflow(query: string, token: string, conversationId?: string, doctorPatientId?: number): Promise<ChatResponse> {
  const response = await fetch(`${API_BASE_URL}/ai/chat`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ query, conversation_id: conversationId ?? null, doctor_patient_id: doctorPatientId }),
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null
    throw new Error(body?.detail ?? 'The AI assistant could not process this request.')
  }
  return response.json() as Promise<ChatResponse>
}

export type ApprovalResponse = {
  approval_id: string
  status: 'pending' | 'approved' | 'rejected' | 'expired' | 'executed'
  action: string
  parameters: Record<string, unknown>
  result: Record<string, unknown> | null
}

export function selectCancellationAppointment(token: string, conversationId: string, appointmentId: number) {
  return post<ChatResponse>(
    `/ai/conversations/${encodeURIComponent(conversationId)}/cancellation-selection`,
    { appointment_id: appointmentId },
    token,
  )
}

export async function decideAIApproval(
  approvalId: string,
  decision: 'approve' | 'reject',
  token: string,
): Promise<ApprovalResponse> {
  const response = await fetch(`${API_BASE_URL}/ai/approvals/${approvalId}/${decision}`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null
    throw new Error(body?.detail ?? 'The approval could not be processed.')
  }
  return response.json() as Promise<ApprovalResponse>
}

export async function runTriage(symptoms: string, token: string): Promise<TriageResponse> {
  const response = await fetch(`${API_BASE_URL}/triage/`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ symptoms }),
  })

  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null
    throw new Error(body?.detail ?? 'The triage service could not process this request.')
  }

  return response.json() as Promise<TriageResponse>
}
