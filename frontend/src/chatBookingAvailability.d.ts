import type { ReactElement } from 'react'
import type { AppointmentSlot } from './api'

export const CALENDAR_DAYS: number
export function asDateKey(value: string | Date): string
export function candidateAppointmentDates(
  rules: Array<{ specific_date: string | null; day_of_week: string; is_available: boolean }>,
  startDate?: string | Date,
  dayCount?: number,
): string[]
export function loadDoctorAppointmentDates(options: {
  doctorId: number
  startDate: string | Date
  dayCount?: number
  getAvailability: (doctorId: number) => Promise<Array<{ specific_date: string | null; day_of_week: string; is_available: boolean }>>
  getSlots: (doctorId: number, date: string) => Promise<{ blocked: boolean; slots: AppointmentSlot[]; alternatives: string[] }>
}): Promise<string[]>
export function loadAppointmentDateSlots(options: {
  doctorId: number
  date: string
  getSlots: (doctorId: number, date: string) => Promise<{ blocked: boolean; slots: AppointmentSlot[]; alternatives: string[] }>
}): Promise<{ blocked: boolean; slots: AppointmentSlot[]; alternatives: string[] }>
export function calendarMonthCells(year: number, month: number): Array<string | null>
export function ChatAppointmentPicker(props: {
  availabilityDates: string[]
  availabilityLoading?: boolean
  availabilityError?: string
  selectedDate?: string
  slots?: AppointmentSlot[]
  slotsLoading?: boolean
  slotsError?: string
  selectedTime?: string
  disabled?: boolean
  viewMonth?: Date
  onChangeMonth?: (month: Date) => void
  onSelectDate?: (date: string) => void
  onSelectSlot?: (slot: AppointmentSlot) => void
  startDate?: string
  dayCount?: number
}): ReactElement
