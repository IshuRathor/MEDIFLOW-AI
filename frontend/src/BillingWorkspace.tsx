import { useEffect, useState, type FormEvent } from 'react'
import MediflowLogo from './MediflowLogo'
import {
  getBillDetail, getBillPage, searchBillingPatients, reviewBill, reviewPayment, decideAIApproval,
  type BillDetail, type BillLine, type BillRecord, type BillingOverview,
  type FinanceReview, type PatientRecord,
} from './api'
import { formatINR } from './FinanceReport.js'

const PAGE_SIZE = 15
const methods = ['Cash', 'Card', 'Bank Transfer', 'Insurance', 'Other']
const emptyLine = (): BillLine => ({ description: '', quantity: 1, unit_price: '' })
const money = (amount: string | number) => formatINR(Number(amount))
const dateLabel = (value: string) => new Date(value).toLocaleDateString()
const statusLabel = (status: string) => status === 'Pending' ? 'Unpaid' : status
const errorMessage = (error: unknown) => error instanceof Error ? error.message : 'Billing data is unavailable.'

export function BillingOverviewCards({ overview, patient = false }: { overview?: BillingOverview; patient?: boolean }) {
  if (!overview) return null
  const metrics = patient
    ? [['Outstanding balance', money(overview.outstanding)], ['Total paid', money(overview.collected)]]
    : [['Bills generated', overview.generated], ['Total billed', money(overview.billed)], ['Total collected', money(overview.collected)], ['Outstanding balance', money(overview.outstanding)], ['Paid', overview.paid], ['Partially paid', overview.partial], ['Unpaid', overview.unpaid]]
  return <dl className="billing-metrics">{metrics.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
}

function BillingDetails({ detail }: { detail: BillDetail }) {
  return <>
    <MediflowLogo />
    <p>{detail.patient_name} · Issued {dateLabel(detail.created_at)}</p>
    <p><strong>{statusLabel(detail.status)}</strong> · Total {money(detail.total_amount)} · Received {money(detail.amount_paid)} · Remaining {money(detail.outstanding)}</p>
    <h3>Itemized charges</h3>
    {detail.items.length ? <ul className="billing-records">{detail.items.map((line, index) => <li key={index}><strong>{line.description}</strong><span>{line.quantity} × {money(line.unit_price)}</span><span>{money(line.amount)}</span></li>)}</ul> : <p>No itemized charges were stored for this bill.</p>}
    <h3>Payment history</h3>
    {detail.payments.length ? <ul className="billing-records">{detail.payments.map((payment, index) => <li key={index}><strong>{money(payment.amount)}</strong><span>{payment.payment_method}</span><span>{dateLabel(payment.paid_at)} · {payment.payment_status}</span></li>)}</ul> : <p>No payments recorded.</p>}
  </>
}

function BillingMutation({ token, bill, onClose, onComplete }: {
  token: string; bill?: BillDetail; onClose: () => void; onComplete: () => void
}) {
  const [reference] = useState(() => crypto.randomUUID())
  const [paymentRef, setPaymentRef] = useState('')
  const [patient, setPatient] = useState<PatientRecord>()
  const [patients, setPatients] = useState<PatientRecord[]>([])
  const [query, setQuery] = useState('')
  const [lines, setLines] = useState([emptyLine()])
  const [amount, setAmount] = useState('')
  const [method, setMethod] = useState(methods[0])
  const [review, setReview] = useState<FinanceReview>()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [lookupError, setLookupError] = useState('')
  useEffect(() => {
    if (bill || review) return
    let active = true
    const timer = window.setTimeout(() => {
      searchBillingPatients(token, query.trim()).then((records) => {
        if (active) { setPatients(records); setLookupError('') }
      }).catch((failure) => { if (active) setLookupError(errorMessage(failure)) })
    }, 200)
    return () => { active = false; window.clearTimeout(timer) }
  }, [bill, query, review, token])

  const editLine = (index: number, update: Partial<BillLine>) => setLines((current) =>
    current.map((line, key) => key === index ? { ...line, ...update } : line),
  )
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy || (!bill && !patient)) return
    setBusy(true)
    setError('')
    try {
      if (review) {
        const result = await decideAIApproval(review.approval_id, 'approve', token)
        if (result.status !== 'executed') throw new Error('The approval was not executed. Review the details again.')
        onComplete()
      } else if (bill) {
        setReview(await reviewPayment(token, {
          bill_id: bill.id, amount, payment_method: method, transaction_reference: paymentRef.trim() || reference,
        }))
      } else if (patient) {
        setReview(await reviewBill(token, { patient_id: patient.id, bill_number: 'MF-' + reference, items: lines }))
      }
    } catch (failure) {
      setError(errorMessage(failure))
    } finally {
      setBusy(false)
    }
  }

  async function exit(close: boolean) {
    if (busy) return
    setBusy(true)
    setError('')
    try {
      if (review) await decideAIApproval(review.approval_id, 'reject', token)
      setReview(undefined)
      if (close) onClose()
    } catch (failure) {
      setError(errorMessage(failure))
      setReview(undefined)
      if (close) onClose()
    } finally {
      setBusy(false)
    }
  }

  return <form className="resource-form billing-form" onSubmit={(event) => void submit(event)}>
    <fieldset className="billing-fields" disabled={busy}>
    {review ? <>
      <h3>Review {bill ? 'payment' : 'bill'}</h3>
      <p>{bill ? bill.bill_number + ' · ' + method : patient?.name + ' · MF-' + reference}</p>
      {!bill && <ul className="billing-records">{lines.map((line, index) => <li key={index}><strong>{line.description}</strong><span>{line.quantity} × {money(line.unit_price)}</span><span>{money(line.quantity * Number(line.unit_price))}</span></li>)}</ul>}
      <p><strong>{bill ? 'Payment amount' : 'Server-calculated total'} {money(review.total_amount)}</strong></p>
      <p>{bill ? 'Confirm to record a payment already received.' : 'Confirm to issue this bill today. It will appear in the patient’s My Bills.'}</p>
    </> : bill ? <>
      <p><strong>{bill.bill_number}</strong> · Outstanding {money(bill.outstanding)}</p>
      <label>Amount received<input required type="number" min="0.01" max={bill.outstanding} step="0.01" value={amount} onChange={(event) => setAmount(event.target.value)} /></label>
      <label>Payment method<select value={method} onChange={(event) => setMethod(event.target.value)}>{methods.map((item) => <option key={item}>{item}</option>)}</select></label>
      <label>Receipt or transaction reference (optional)<input maxLength={120} value={paymentRef} onChange={(event) => setPaymentRef(event.target.value)} /></label>
    </> : <>
      <label>Find a registered patient<input maxLength={120} value={query} placeholder="Search by name or email" onChange={(event) => { setQuery(event.target.value); setPatient(undefined) }} /></label>
      {lookupError && <p role="alert" className="form-error">{lookupError}</p>}
      <label>Patient<select required value={patient?.id ?? ''} onChange={(event) => setPatient(patients.find((item) => item.id === Number(event.target.value)))}><option value="">Select patient</option>{patients.map((item) => <option key={item.id} value={item.id}>{item.name}{item.email ? ' · ' + item.email : ' · Patient ' + item.id}</option>)}</select></label>
      <p>The bill date is recorded when you issue the bill.</p>
      {lines.map((line, index) => <fieldset className="billing-line" key={index}>
        <legend>Service {index + 1}</legend>
        <label>Description<input required maxLength={250} value={line.description} onChange={(event) => editLine(index, { description: event.target.value })} /></label>
        <label>Quantity<input required type="number" min="1" max="100000" step="1" value={line.quantity || ''} onChange={(event) => editLine(index, { quantity: Number(event.target.value) })} /></label>
        <label>Unit price<input required type="number" min="0" max="9999999999.99" step="0.01" value={line.unit_price} onChange={(event) => editLine(index, { unit_price: event.target.value })} /></label>
        <output>{money(line.quantity * Number(line.unit_price))}</output>
        <button type="button" className="outline-button" disabled={lines.length === 1 || busy} onClick={() => setLines(lines.filter((_, key) => key !== index))}>Remove</button>
      </fieldset>)}
      <button type="button" className="outline-button" disabled={lines.length >= 50 || busy} onClick={() => setLines([...lines, emptyLine()])}>Add line item</button>
      <p>Estimated total <strong>{money(lines.reduce((total, line) => total + line.quantity * Number(line.unit_price), 0))}</strong></p>
    </>}
    </fieldset>
    {error && <p className="form-error" role="alert">{error}</p>}
    <div className="role-actions">
      <button className="dark-button" type="submit" disabled={busy}>{busy ? 'Working…' : review ? bill ? 'Confirm payment' : 'Generate bill' : 'Review'}</button>
      {review && <button className="outline-button" type="button" disabled={busy} onClick={() => void exit(false)}>Edit details</button>}
      <button className="outline-button" type="button" disabled={busy} onClick={() => void exit(true)}>Cancel</button>
    </div>
  </form>
}

export default function BillingWorkspace({ token, role, overview, recentOnly = false, onRefresh }: {
  token: string; role: 'staff' | 'admin' | 'patient'; overview?: BillingOverview; recentOnly?: boolean; onRefresh: () => void
}) {
  const patient = role === 'patient'
  const [rows, setRows] = useState<BillRecord[]>([])
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('')
  const [offset, setOffset] = useState(0)
  const [next, setNext] = useState(false)
  const [revision, setRevision] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<number>()
  const [detail, setDetail] = useState<BillDetail>()
  const [detailError, setDetailError] = useState('')
  const [mode, setMode] = useState<'bill' | 'payment'>()
  const [notice, setNotice] = useState('')

  useEffect(() => {
    let active = true
    const limit = recentOnly ? 5 : PAGE_SIZE
    const timer = window.setTimeout(() => {
      getBillPage(token, query.trim(), status, offset, limit + 1).then((data) => {
        if (!active) return
        setRows(data.slice(0, limit)); setNext(data.length > limit); setError('')
      }).catch((failure) => { if (active) setError(errorMessage(failure)) })
        .finally(() => { if (active) setLoading(false) })
    }, 150)
    return () => { active = false; window.clearTimeout(timer) }
  }, [token, query, status, offset, revision, recentOnly])

  useEffect(() => {
    if (selected == null) return
    let active = true
    getBillDetail(token, selected).then((data) => { if (active) { setDetail(data); setDetailError('') } })
      .catch((failure) => { if (active) setDetailError(errorMessage(failure)) })
    return () => { active = false }
  }, [token, selected, revision])

  function showDetails(id: number) {
    setDetail(undefined)
    setDetailError('')
    setSelected(id)
  }

  function complete() {
    setNotice(mode === 'bill' ? 'Bill generated and visible in My Bills.' : 'Payment recorded.')
    if (mode === 'bill') { setOffset(0); setQuery(''); setStatus('') }
    if (mode === 'payment') setDetail(undefined)
    setMode(undefined)
    setLoading(true)
    setRevision((current) => current + 1)
    onRefresh()
  }

  return <section className="panel capacity-panel billing-workspace">
    <div className="panel-heading"><div><p className="eyebrow">Billing</p><h2>{patient ? recentOnly ? 'Recent bills' : 'My Bills' : 'Billing Management'}</h2></div>
      {!patient && <button type="button" className="dark-button" onClick={() => setMode('bill')}>Generate New Bill</button>}
    </div>
    <BillingOverviewCards overview={overview} patient={patient} />
    {notice && <p role="status">{notice}</p>}
    {!recentOnly && <div className="resource-form billing-filters">
      <label>Search bills<input maxLength={120} value={query} onChange={(event) => { setLoading(true); setQuery(event.target.value); setOffset(0) }} placeholder={patient ? 'Bill reference' : 'Bill reference or patient name'} /></label>
      <label>Status<select value={status} onChange={(event) => { setLoading(true); setStatus(event.target.value); setOffset(0) }}><option value="">All statuses</option>{['Pending', 'Partially Paid', 'Paid', 'Cancelled'].map((item) => <option key={item} value={item}>{statusLabel(item)}</option>)}</select></label>
    </div>}
    {loading ? <p role="status">Loading bills…</p> : error ? <p role="alert" className="form-error">{error}</p> : rows.length ? <>
      <div className="billing-table"><table>
        <caption>Issued bills</caption>
        <thead><tr><th scope="col">Bill reference</th>{!patient && <th scope="col">Patient</th>}<th scope="col">Issued</th><th scope="col">Total</th><th scope="col">Paid</th><th scope="col">Outstanding</th><th scope="col">Status</th></tr></thead>
        <tbody>{rows.map((bill) => <tr key={bill.id}><th scope="row"><button className="row-action" type="button" onClick={() => showDetails(bill.id)}>{bill.bill_number}</button></th>{!patient && <td>{bill.patient_name}</td>}<td>{dateLabel(bill.created_at)}</td><td>{money(bill.total_amount)}</td><td>{money(bill.amount_paid)}</td><td>{money(bill.outstanding)}</td><td>{statusLabel(bill.status)}</td></tr>)}</tbody>
      </table></div>
      {!recentOnly && <div className="role-actions"><button className="outline-button" type="button" disabled={!offset} onClick={() => { setLoading(true); setOffset(offset - PAGE_SIZE) }}>Previous</button><button className="outline-button" type="button" disabled={!next} onClick={() => { setLoading(true); setOffset(offset + PAGE_SIZE) }}>Next</button></div>}
    </> : <p className="dashboard-state">{query || status || offset ? 'No bills match these filters.' : patient ? "You don't have any bills yet. Bills will appear here when the hospital's Finance team generates a bill for your services." : 'No bills have been generated yet.'}</p>}
    {(selected != null || mode) && <div className="modal-backdrop">
      <div className="triage-modal patient-triage-modal billing-dialog" role="dialog" aria-modal="true" aria-labelledby="billing-dialog-title">
        <h2 id="billing-dialog-title">{mode === 'bill' ? 'Generate New Bill' : mode === 'payment' ? 'Record Payment' : detail?.bill_number ?? 'Bill details'}</h2>
        {mode ? <BillingMutation token={token} bill={mode === 'payment' ? detail : undefined} onComplete={complete} onClose={() => setMode(undefined)} /> : <>
          {detailError ? <p role="alert">{detailError}</p> : detail ? <BillingDetails detail={detail} /> : <p role="status">Loading bill details…</p>}
          <div className="role-actions">
            {!patient && detail && Number(detail.outstanding) > 0 && <button type="button" className="dark-button" onClick={() => setMode('payment')}>Record Payment</button>}
            <button type="button" className="outline-button" onClick={() => setSelected(undefined)}>Close</button>
          </div>
        </>}
      </div>
    </div>}
  </section>
}
