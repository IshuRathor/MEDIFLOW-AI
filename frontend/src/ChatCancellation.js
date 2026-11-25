import React from 'react'

function appointmentDetails(appointment) {
  const date = new Date(appointment.appointment_date)
  const doctor = appointment.doctor_name.replace(/^Dr\.\s*/i, '')
  return React.createElement('div', null,
    React.createElement('strong', null, `Dr. ${doctor}`),
    React.createElement('span', null, appointment.specialization),
    React.createElement('span', null, date.toLocaleDateString()),
    React.createElement('span', null, date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })),
    React.createElement('span', null, appointment.status),
  )
}

export default function ChatCancellation({ data, disabled, canConfirm, onSelect, onDecision }) {
  if (data.cancellation_selection && canConfirm) {
    return React.createElement('div', { className: 'doctor-choice-card' },
      appointmentDetails(data.cancellation_selection),
      React.createElement('div', { className: 'approval-actions' },
        React.createElement('button', {
          className: 'dark-button', type: 'button', disabled, onClick: () => onDecision('approve'),
        }, 'Confirm cancellation request'),
        React.createElement('button', {
          className: 'outline-button', type: 'button', disabled, onClick: () => onDecision('reject'),
        }, 'Keep appointment'),
      ),
    )
  }
  if (!Array.isArray(data.cancellation_options) || !data.cancellation_options.length) return null

  return React.createElement('div', { className: 'doctor-choice-list', 'aria-label': 'Appointments eligible for cancellation' },
    data.cancellation_options.map((appointment) => React.createElement('article', {
      className: 'doctor-choice-card', key: appointment.id,
    },
    appointmentDetails(appointment),
    React.createElement('button', {
      className: 'outline-button', type: 'button', disabled, onClick: () => onSelect(appointment.id),
    }, 'Select appointment'),
    )),
  )
}
