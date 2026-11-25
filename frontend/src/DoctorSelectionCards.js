import React from 'react'

export function patientDoctorOptions(data) {
  if (Array.isArray(data?.doctors)) return data.doctors

  const doctorToolResult = Array.isArray(data?.tool_results)
    ? data.tool_results.find((item) => item?.tool === 'search_doctors')?.result
    : null
  return Array.isArray(doctorToolResult?.doctors) ? doctorToolResult.doctors : []
}

export function visibleChatTrace(role, trace) {
  if (role === 'patient' || !trace?.length) return null
  return trace.map((item) => `${item.tool}: ${item.status}`).join(' · ')
}

export default function DoctorSelectionCards({ doctors, onSelect, disabled }) {
  if (!doctors.length) return null

  return React.createElement(
    'div',
    { className: 'doctor-choice-list', 'aria-label': 'Available doctors' },
    doctors.map((doctor) => React.createElement(
      'article',
      { className: 'doctor-choice-card', key: String(doctor.id) },
      React.createElement('div', null,
        React.createElement('strong', null, `Dr. ${doctor.name}`),
        React.createElement('span', null, doctor.specialization || 'Specialization not listed'),
        React.createElement('span', null, doctor.department || 'Department not listed'),
      ),
      React.createElement('button', {
        className: 'outline-button',
        type: 'button',
        disabled,
        onClick: () => onSelect(doctor),
      }, 'Select Doctor'),
    )),
  )
}
