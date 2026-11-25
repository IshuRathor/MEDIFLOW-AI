import { createElement as h } from 'react'

function DoctorRecommendation({ doctor, windowDays, onBook }) {
  const nextSlot = doctor.availability === 'available' && doctor.upcoming_slots[0]
  const availability = nextSlot
    ? h('time', { dateTime: nextSlot }, new Date(nextSlot).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }))
    : doctor.availability === 'no_slots'
      ? `No verified open slots in the next ${windowDays} days.`
      : 'Availability could not be verified from the recorded schedule.'

  return h('li', { className: 'triage-doctor' },
    h('div', null,
      h('h4', null, doctor.name),
      h('p', null, [doctor.specialization, doctor.department !== doctor.specialization && doctor.department].filter(Boolean).join(' · ')),
      doctor.experience_years != null && h('p', null, `${doctor.experience_years} years of experience`),
      h('p', null, doctor.matching_explanation),
      h('p', null, nextSlot && h('strong', null, 'Next verified slot · '), availability),
    ),
    h('button', { className: 'outline-button', type: 'button', onClick: () => onBook(doctor), 'aria-label': `View booking options for ${doctor.name}` }, 'View booking options'),
  )
}

function EmergencyDirectory({ doctors, directoryChecked }) {
  return h('section', { className: 'triage-recommendations', 'aria-labelledby': 'triage-cardiology-title' },
    h('h3', { id: 'triage-cardiology-title' }, 'Cardiology directory'),
    h('p', null, 'Cardiology may be relevant after emergency evaluation. This specialty suggestion does not establish a diagnosis.'),
    doctors.length > 0
      ? h('ul', null, doctors.map((doctor) => h('li', { key: doctor.id, className: 'triage-doctor' },
        h('div', null, h('h4', null, doctor.name), h('p', null, doctor.specialization),
          doctor.experience_years != null && h('p', null, `${doctor.experience_years} years of experience`)),
      )))
      : h('p', null, directoryChecked
        ? 'No matching cardiologist is currently registered in the hospital directory.'
        : 'Cardiology directory information could not be verified.'),
  )
}

export default function TriageResults({ result, onBook, onReset }) {
  const emergency = result.urgency === 'Emergency'
  const [first, ...alternatives] = result.recommended_doctors ?? []
  const renderDoctor = (doctor) => h(DoctorRecommendation, {
    key: doctor.id, doctor, windowDays: result.availability_window_days, onBook,
  })

  return h('div', { className: 'triage-result' },
    h('strong', null, `${result.urgency} urgency`),
    h('span', null, result.recommended_department),
    h('p', { role: emergency ? 'alert' : undefined, className: emergency ? 'triage-emergency-guidance' : undefined }, result.recommended_action),
    h('small', null, result.safety_notice),
    h('small', null, result.disclaimer),
    emergency && result.recommended_department === 'Emergency / Cardiology' && h(EmergencyDirectory, {
      doctors: result.recommended_doctors ?? [],
      directoryChecked: result.availability_window_days != null,
    }),
    !emergency && h('section', { className: 'triage-recommendations', 'aria-labelledby': 'triage-doctors-title' },
      h('h3', { id: 'triage-doctors-title' }, 'Recommended doctors'),
      first ? h('ul', null, renderDoctor(first)) : h('p', null, `No doctor matching ${result.recommended_department} is currently registered in the hospital directory.`),
      alternatives.length > 0 && h('h3', null, 'Other matching doctors'),
      alternatives.length > 0 && h('ul', null, alternatives.map(renderDoctor)),
    ),
    h('button', { className: 'dark-button', type: 'button', onClick: onReset }, 'Run another'),
  )
}
