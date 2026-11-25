import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import FinanceReport, { financePrompts, formatINR } from '../src/FinanceReport.js'

const report = {
  title: 'Financial activity',
  timezone: 'Asia/Kolkata',
  currency: 'INR',
  start_date: '2026-10-01',
  end_date: '2026-11-25',
  notes: ['Uses completed payments and recorded expenses.'],
  metrics: [
    { label: 'Recorded financial movement', value: '-40.25', unit: 'INR' },
    { label: 'Collections change (%)', value: null, unit: 'percent' },
  ],
  charts: [
    {
      title: 'Completed collection trend', kind: 'line', labels: ['Oct 2026', 'Nov 2026'],
      has_activity: true, series: [{ label: 'Collections', values: ['100000.25', '0.00'] }],
    },
    {
      title: 'Collections versus recorded expenses', kind: 'bar', labels: ['Nov 2026'],
      has_activity: true, series: [{ label: 'Collections', values: ['0.00'] }, { label: 'Expenses', values: ['40.25'] }],
    },
  ],
}

test('finance reports render INR axes, keyboard-focusable data, dates and accessible tables', () => {
  const html = renderToStaticMarkup(createElement(FinanceReport, { report }))
  assert.equal(formatINR('100000.25'), '₹1,00,000.25')
  assert.match(html, /2026-10-01 to 2026-11-25 · Asia\/Kolkata · INR/)
  assert.match(html, /<polyline/)
  assert.match(html, /<rect/)
  assert.match(html, /tabindex="0"/)
  assert.match(html, /Oct 2026, Collections: ₹1,00,000\.25/)
  assert.match(html, /<caption>Completed collection trend<\/caption>/)
  assert.match(html, /<td>₹0\.00<\/td>/)
  assert.match(html, /-₹40\.25/)
  assert.match(html, /Unavailable/)
})

test('no recorded activity is shown separately from zero-valued buckets and an unavailable forecast', () => {
  const empty = {
    ...report, charts: [{ ...report.charts[0], has_activity: false }],
    notes: ['Forecast unavailable without sufficient data.'],
  }
  const html = renderToStaticMarkup(createElement(FinanceReport, { report: empty }))
  assert.match(html, /No records in this range\./)
  assert.match(html, /Forecast unavailable/)
  assert.doesNotMatch(html, /<svg/)
  assert.ok(financePrompts.includes('Show monthly collections for the last 12 months'))
})
